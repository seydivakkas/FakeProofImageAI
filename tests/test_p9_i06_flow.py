"""P9-I06 local safety, UI wiring and real-CLI synthetic integration."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from aiforensics.integration_flow import (
    STAGES, example_manifest, save_example, run_evidence_chain,
    validate_source, IntegrationFlowError,
)
from aiforensics.integration_ui import selected_asset, stage_action
from aiforensics.desktop_core import atomic_json, sha256, Project


class Stub:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.fail = None
        for part in ("manifests", "runs", "exports"):
            (root / part).mkdir(parents=True, exist_ok=True)
        self.data = {"images": []}

    def run(self, module, source):
        self.calls.append((module, Path(source)))
        out = self.root / "runs" / f"{len(self.calls):04d}_{module}"
        out.mkdir()
        if module == self.fail:
            return {"run_id": out.name, "state": "FAILED", "returncode": 1}, out
        _, file, schema = next(s for s in STAGES if s[0] == module)
        (out / file).write_text(json.dumps({
            "schema_version": schema,
            "decision": "NO_AI_ORIGIN_CONCLUSION"
        }), encoding="utf-8")
        if module == "P8-E03":
            (out / "p8_e03_explainable_report.html").write_text("<html>toy</html>")
        return {"run_id": out.name, "state": "SUCCEEDED", "returncode": 0}, out


def sample(tmp_path):
    project = Stub(tmp_path / "Test")
    return project, save_example(project)


def test_example_is_explicit_synthetic():
    x = example_manifest()
    assert x["dataset_scope"] == "synthetic_controlled"
    assert len(x["records"]) == 3


def test_three_stages_and_audit(tmp_path):
    project, path = sample(tmp_path)
    audit = run_evidence_chain(project, path)
    assert [x[0] for x in project.calls] == ["P8-E01", "P8-E02", "P8-E03"]
    assert len({str(x[1]) for x in project.calls}) == 1
    assert audit["decision"] == "NO_AI_ORIGIN_CONCLUSION"
    assert audit["camera_validation"] == "NOT_PERFORMED"
    assert audit["windows_user_acceptance"] == "NOT_PERFORMED"
    assert Path(audit["index_file"]).is_file()
    for item in audit["steps"]:
        assert sha256(project.root / item["report"]) == item["report_sha256"]


def test_failed_engine_halts(tmp_path):
    project, path = sample(tmp_path)
    project.fail = "P8-E02"
    with pytest.raises(IntegrationFlowError, match="P8-E02 başarısız"):
        run_evidence_chain(project, path)
    assert len(project.calls) == 2


def test_real_unverified_is_not_synthetic(tmp_path):
    project, path = sample(tmp_path)
    data = json.loads(path.read_text())
    data["dataset_scope"] = "real_unverified"
    atomic_json(path, data)
    with pytest.raises(IntegrationFlowError):
        run_evidence_chain(project, path)
    assert not project.calls


def test_missing_fusion_rejected(tmp_path):
    project, path = sample(tmp_path)
    data = json.loads(path.read_text())
    del data["fusion"]
    atomic_json(path, data)
    with pytest.raises(IntegrationFlowError, match="fusion"):
        run_evidence_chain(project, path)


def test_nonfinite_json_rejected(tmp_path):
    file = tmp_path / "bad.json"
    file.write_text('{"schema_version":"p8.e01.v1","x":NaN}')
    with pytest.raises(IntegrationFlowError):
        validate_source(file)


def test_snapshot_tamper_prevents_execution(tmp_path):
    project, path = sample(tmp_path)
    bad = project.root / "manifests" / ("p9_i06_input_" + sha256(path) + ".json")
    bad.write_text("changed")
    with pytest.raises(IntegrationFlowError, match="SHA-256"):
        run_evidence_chain(project, path)
    assert not project.calls


def test_preview_hash_and_parent_dir(tmp_path):
    project, path = sample(tmp_path)
    images = project.root / "images"
    images.mkdir()
    file = images / "image.png"
    file.write_bytes(b"simulated-image")
    digest = sha256(file)
    project.data["images"] = [{"name": "image.png", "file": "image.png",
                              "sha256": digest}]
    assert selected_asset(project, digest)[1] == file
    file.write_bytes(b"modified")
    assert selected_asset(project, digest) is None
    project.data["images"][0]["file"] = "../../image.png"
    assert selected_asset(project, digest) is None


def test_workflow_actions_do_real_navigation():
    actions = []
    app = SimpleNamespace(
        go=lambda x: actions.append(("go", x)),
        open_workflow=lambda: actions.append(("workflow", None)),
        open_review=lambda x: actions.append(("review", x)),
    )
    for key in ("image", "calibration", "analysis", "evidence", "export"):
        stage_action(app, key)
    assert actions == [
        ("go", "Görüntü Yükleme"), ("go", "Kalibrasyon"),
        ("workflow", None), ("review", "Kanıt İnceleme"),
        ("review", "Rapor Gezgini"),
    ]


def test_real_cli_full_synthetic_e2e(tmp_path):
    project = Project(tmp_path, "E2ESynthetic")
    audit = run_evidence_chain(project, save_example(project))
    assert len(audit["steps"]) == 3
    report = json.loads((project.root / audit["steps"][-1]["report"]).read_text(
        encoding="utf-8"))
    assert report["summary"]["record_count"] == 3
    assert report["origin_probability"] is None
    assert audit["decision"] == "NO_AI_ORIGIN_CONCLUSION"


def test_main_dashboard_wiring():
    import inspect
    from aiforensics.desktop_app import DesktopApp
    assert "render_unified_home" in inspect.getsource(DesktopApp.screen_0)
