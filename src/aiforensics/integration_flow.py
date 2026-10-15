"""P9-I06: guarded, source-hashed synthetic E01→E02→E03 workflow.

Only a controlled physical residual manifest is processed; this is not
an image-origin, camera identity, or real-world validation system.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .desktop_core import atomic_json, sha256

STAGES = (
    ("P8-E01", "p8_e01_evidence_report.json", "p8.e01.v1"),
    ("P8-E02", "p8_e02_fusion_report.json", "p8.e02.v1"),
    ("P8-E03", "p8_e03_explainable_report.json", "p8.e03.v1"),
)
MAX_BYTES = 32 * 1024 * 1024


class IntegrationFlowError(ValueError):
    pass


def example_manifest():
    """Toy model residuals, not real image measurements."""
    records = []
    for module, obs, delta, asset in (
        ("P1-G01", "demo_geometry", 4.0, "synthetic-a"),
        ("P3-R01", "demo_reflection", 0.2, "synthetic-a"),
        ("P7-S01", "demo_sensor", 0.1, "synthetic-b"),
    ):
        records.append({
            "module_id": module, "observation_id": obs,
            "measured": 20.0 + delta, "predicted": 20.0, "unit": "px",
            "assumptions": [{
                "name": "controlled synthetic model", "status": "supported",
                "source": "generated sample, NOT a physical measurement"}],
            "provenance": {
                "source_id": asset, "calibration_id": "cal-" + asset,
                "split": "holdout", "independent_of_training": True,
                "external_reference_verified": True},
            "uncertainty": {"measurement_std": 1.0, "prediction_std": 0.0,
                            "error_correlation": 0.0},
            "test": {"null_distribution": "normal_zero_mean_residual",
                     "alpha": 0.01, "pre_registered": True,
                     "distribution_independently_checked": True},
            "lineage": {
                "raw_asset_id": asset, "calibration_asset_id": "cal-" + asset,
                "reference_id": "reference-" + asset,
                "holdout_batch_id": "holdout-" + asset,
                "feature_family_id": "features-" + asset,
                "model_family_id": "model-" + module},
        })
    return {
        "schema_version": "p8.e01.v1", "dataset_scope": "synthetic_controlled",
        "records": records,
        "fusion": {"familywise_alpha": 0.01, "plan_pre_registered": True,
                   "dependency_audit_verified": True,
                   "dependence_unknown": False, "declared_edges": []},
    }


def validate_source(path):
    original = Path(path).expanduser()
    if original.is_symlink():
        raise IntegrationFlowError("Manifest symlink kabul edilmez")
    source = original.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".json":
        raise IntegrationFlowError("E01-E03 JSON ölçüm manifesti gerektirir")
    if not 0 < source.stat().st_size <= MAX_BYTES:
        raise IntegrationFlowError("Manifest boyutu geçersiz")
    payload = source.read_bytes()

    def invalid_constant(value):
        raise IntegrationFlowError("JSON sonlu olmayan sayı: " + value)

    try:
        manifest = json.loads(payload, parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as exc:
        raise IntegrationFlowError("Geçersiz JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "p8.e01.v1":
        raise IntegrationFlowError("E01 şeması geçersiz")
    if manifest.get("dataset_scope") != "synthetic_controlled":
        raise IntegrationFlowError("Gerçek kamera doğrulaması burada yapılmaz")
    if not isinstance(manifest.get("records"), list) or not manifest["records"]:
        raise IntegrationFlowError("Ölçüm kaydı bulunmuyor")
    if not isinstance(manifest.get("fusion"), dict):
        raise IntegrationFlowError("E02 fusion yapılandırması zorunludur")
    return payload, manifest, hashlib.sha256(payload).hexdigest()


def save_example(project):
    destination = project.root / "manifests" / "p9_i06_controlled_synthetic.json"
    atomic_json(destination, example_manifest())
    return destination


def run_evidence_chain(project, manifest_path, *, on_stage=None):
    """Run real existing allowlisted CLI engines, stopping at first failure."""
    payload, _, digest = validate_source(manifest_path)
    manifests = project.root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    snapshot = manifests / ("p9_i06_input_" + digest + ".json")
    if snapshot.exists():
        if snapshot.is_symlink() or sha256(snapshot) != digest:
            raise IntegrationFlowError("Kaydedilmiş manifest SHA-256 uyuşmazlığı")
    else:
        snapshot.write_bytes(payload)
    steps = []
    for module, report_name, schema in STAGES:
        if sha256(snapshot) != digest:
            raise IntegrationFlowError("Analiz sırasında manifest değişti")
        if on_stage:
            on_stage(module, "STARTED")
        execution, folder = project.run(module, snapshot)
        if execution.get("state") != "SUCCEEDED" or execution.get("returncode") != 0:
            if on_stage:
                on_stage(module, "FAILED")
            raise IntegrationFlowError(module + " başarısız: " + str(execution.get("state")))
        runroot = (project.root / "runs").resolve()
        report = (Path(folder) / report_name).resolve()
        if (not report.is_relative_to(runroot) or not report.is_file()
                or report.is_symlink()):
            raise IntegrationFlowError(module + " rapor dosyası bulunmuyor")
        try:
            result = json.loads(report.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise IntegrationFlowError(module + " JSON raporu geçersiz") from exc
        if (result.get("schema_version") != schema or
                result.get("decision") != "NO_AI_ORIGIN_CONCLUSION"):
            raise IntegrationFlowError(module + " bilimsel sınır/şema ihlali")
        steps.append({
            "module_id": module, "run_id": execution["run_id"],
            "source_sha256": digest, "state": "SUCCEEDED",
            "report": report.relative_to(project.root).as_posix(),
            "report_sha256": sha256(report),
        })
        if on_stage:
            on_stage(module, "SUCCEEDED")
    html = (project.root / steps[-1]["report"]).with_suffix(".html")
    if html.name != "p8_e03_explainable_report.html" or not html.is_file():
        raise IntegrationFlowError("E03 HTML raporu eksik")
    audit = {
        "schema_version": "fakeproof.p9.i06.integration.v1",
        "scope": "SYNTHETIC_CONTROLLED_SOFTWARE_ONLY",
        "source_manifest_sha256": digest,
        "steps": steps,
        "final_html": html.relative_to(project.root).as_posix(),
        "final_html_sha256": sha256(html),
        "camera_validation": "NOT_PERFORMED",
        "windows_user_acceptance": "NOT_PERFORMED",
        "decision": "NO_AI_ORIGIN_CONCLUSION",
    }
    target = project.root / "exports" / ("p9_i06_chain_" + digest[:16] + ".json")
    atomic_json(target, audit)
    audit["index_file"] = target.as_posix()
    return audit
