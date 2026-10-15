"""P9-I06 dark desktop dashboard and explicit synthetic E01-E03 entrypoint."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from .journey_core import journey_snapshot
from .journey_ui import stage_caption
from .integration_flow import run_evidence_chain, save_example
from .desktop_core import sha256

BG="#0a1420"; PANEL="#142639"; CARD="#20384e"; BLUE="#1976d2"
CYAN="#19c5ff"; INK="#e7f2fa"; MUTED="#abbfd1"


def selected_asset(project, digest):
    if not isinstance(digest, str):
        return None
    for item in project.data.get("images", []):
        if item.get("sha256") != digest:
            continue
        root = (project.root / "images").resolve()
        try:
            path = (root / item["file"]).resolve(strict=True)
            if path.parent != root or not path.is_file() or sha256(path) != digest:
                return None
            return item, path
        except (KeyError, OSError, ValueError):
            return None
    return None


def stage_action(app, key):
    if key == "image":
        app.go("Görüntü Yükleme")
    elif key == "calibration":
        app.go("Kalibrasyon")
    elif key == "analysis":
        app.open_workflow()
    elif key == "evidence":
        app.open_review("Kanıt İnceleme")
    elif key == "export":
        app.open_review("Rapor Gezgini")


def run_synthetic_from_ui(app):
    if app.busy:
        return
    if not messagebox.askyesno(
        "SENTETİK DEMO", "Yalnız sentetik örnekten E01→E02→E03 çalışacak. "
        "Gerçek kamera veya AI köken kararı verilmez. Devam?", parent=app
    ):
        return
    project = app.project
    app.busy = True
    app.status.set("Sentetik E01→E02→E03 çalışıyor")

    def finish(result, error):
        app.busy = False
        if error is not None:
            app.err(error)
            return
        app.run_id = result["steps"][-1]["run_id"]
        app.status.set("Sentetik kanıt zinciri kaydedildi; gerçek doğrulama yapılmadı")
        app.go("Kanıt İnceleme")

    def worker():
        try:
            result = run_evidence_chain(project, save_example(project))
            app.after(0, lambda: finish(result, None))
        except Exception as exc:
            detail = str(exc)
            app.after(0, lambda: finish(None, detail))
    threading.Thread(target=worker, daemon=True).start()


def render_unified_home(app):
    """P9-I08 UI: render only project records; do not infer origin."""
    from .ui_polish import render_overview
    return render_overview(app)
