"""P9-I05: source-backed user journey, never an image provenance or physics verdict."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

PROJECT_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
PAGES = ("Görüntü Yükleme", "Kalibrasyon", "Analiz Planı", "Kanıt İnceleme", "Rapor Dışa Aktarma")

@dataclass(frozen=True)
class JourneyStep:
    key: str
    label: str
    page: str
    state: str
    detail: str

def available_projects(workspace: str | Path) -> list[str]:
    """Ignore invalid folder names and symlinks, never traverse external dirs."""
    root = Path(workspace).expanduser()
    if not root.is_dir():
        return []
    items = []
    for entry in root.iterdir():
        if (not PROJECT_RE.fullmatch(entry.name) or entry.is_symlink()
                or not entry.is_dir()):
            continue
        marker = entry / "project.json"
        if marker.is_file() and not marker.is_symlink():
            items.append(entry.name)
    return sorted(items, key=str.casefold)

def _annotation_count(project) -> int:
    seen = set()
    count = 0
    for image in project.data.get("images", []):
        digest = image.get("sha256", "")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            continue
        if digest in seen:
            continue
        seen.add(digest)
        file = project.root / "manifests" / ("annotations_" + digest + ".json")
        if not file.is_file() or file.is_symlink():
            continue
        try:
            from .annotation_model import AnnotationDocument
            doc = AnnotationDocument.load(file, image_sha256=digest)
            if doc.image_sha256 == digest and doc.marks:
                count += 1
        except (ValueError, TypeError, OSError, KeyError, ImportError):
            continue
    return count

def journey_snapshot(project) -> dict:
    """States signify local work recorded, not physical validity or camera truth."""
    images = project.data.get("images", [])
    runs = [r for r in project.data.get("runs", []) if isinstance(r, dict)]
    successful_physics = [r for r in runs if r.get("state") == "SUCCEEDED"
                          and re.match(r"^P[1-7]-", str(r.get("module_id", "")))]
    successful_evidence = [r for r in runs if r.get("state") == "SUCCEEDED"
                           and re.match(r"^P8-E0[1-3]$", str(r.get("module_id", "")))]
    failures = sum(r.get("state") in ("FAILED", "TIMEOUT") for r in runs)
    attempted_physics = any(re.match(r"^P[1-7]-", str(r.get("module_id", ""))) for r in runs)
    drafts = _annotation_count(project)
    calibration = bool(project.data.get("calibration"))
    states = [
        ("image", "Görüntü", PAGES[0], "RECORDED" if images else "ACTION_REQUIRED",
         f"{len(images)} yerel dosya; kaynak doğrulanmadı"),
        ("calibration", "Anotasyon / Kalibrasyon", PAGES[1],
         "DRAFT" if drafts or calibration else "ACTION_REQUIRED",
         f"{drafts} anotasyon taslağı; kalibrasyon {'eklendi' if calibration else 'yok'}; bağımsız doğrulama yok"),
        ("analysis", "Fizik Analizi", PAGES[2],
         "RECORDED" if successful_physics else "ATTEMPTED" if attempted_physics else "ACTION_REQUIRED",
         f"{len(successful_physics)} başarılı fizik koşumu; {failures} başarısız / zaman aşımı"),
        ("evidence", "P8 Kanıt", PAGES[3],
         "RECORDED" if successful_evidence else "ACTION_REQUIRED",
         f"{len(successful_evidence)} başarılı E01/E02/E03 koşumu; AI kararı yok"),
        ("export", "Rapor", PAGES[4],
         "READY_TO_SELECT" if runs else "ACTION_REQUIRED",
         "Dışa aktarım için çalışma seçin; PDF/imza bulunmuyor"),
    ]
    steps = [JourneyStep(*s) for s in states]
    recommended = next((s.key for s in steps if s.state == "ACTION_REQUIRED"), "export")
    return {"project": project.name, "image_count": len(images), "run_count": len(runs),
            "annotation_draft_count": drafts, "physics_success_count": len(successful_physics),
            "evidence_success_count": len(successful_evidence), "failed_run_count": failures,
            "recommended_step": recommended, "steps": steps,
            "scope": "SYNTHETIC_OR_UNVERIFIED_NOT_REAL_ACCEPTANCE",
            "decision": "NO_AI_ORIGIN_CONCLUSION"}
