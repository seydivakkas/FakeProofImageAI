"""Headless integration checks; real camera and user-device acceptance deferred."""
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from aiforensics.desktop_core import COMMANDS, Project, DesktopIntegrationError, module_catalog


def test_all_physics_modules_and_evidence_are_mapped():
    from aiforensics.evidence_contract import MODULES
    assert len(MODULES)==24
    assert set(MODULES)<=set(COMMANDS)
    assert len(module_catalog())==27


@pytest.mark.parametrize("name",["../escape","name with spaces","","/etc","ü"])
def test_project_name_rejected(tmp_path,name):
    with pytest.raises(DesktopIntegrationError):
        Project(tmp_path,name)


def test_local_image_import_hash_and_no_origin_claim(tmp_path):
    p=Project(tmp_path/"w","case")
    path=tmp_path/"a.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+b"fixture")
    item=p.import_image(path)
    assert item["camera_origin_verified"] is False
    assert p.import_image(path)==item
    assert len(p.data["images"])==1
    assert (p.root/"images"/item["file"]).read_bytes()==path.read_bytes()


def test_calibration_saved_without_real_verification(tmp_path):
    p=Project(tmp_path/"w","case")
    path=tmp_path/"c.json";path.write_text('{"camera": "synthetic"}')
    p.set_calibration(path)
    assert (p.root/"manifests"/p.data["calibration"]).exists()
    assert p.data["data_scope"]!="real_verified"


def test_allowlisted_cli_and_export(tmp_path):
    p=Project(tmp_path/"w","case")
    path=tmp_path/"p.json";path.write_text("{}")
    called=[]
    def runner(args,**kwargs):
        called.append(args)
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=0,stdout="{}",stderr="")
    result,folder=p.run("P8-E03",path,runner=runner)
    assert called[0][3]=="explain-evidence"
    assert result["decision"]=="NO_AI_ORIGIN_CONCLUSION"
    assert (folder/"execution.json").is_file()
    bundle=p.export_run(result["run_id"],tmp_path/"export.zip")
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
        assert "EXPORT_MANIFEST.json" in archive.namelist()


def test_invalid_module_and_input_blocked(tmp_path):
    p=Project(tmp_path/"w","case")
    path=tmp_path/"p.json";path.write_text("{}")
    with pytest.raises(DesktopIntegrationError):
        p.run("P8-E99",path)
    with pytest.raises(DesktopIntegrationError):
        p.run("P1-G01",path)
    with pytest.raises(DesktopIntegrationError):
        p.export_run("../../wrong",tmp_path/"wrong.zip")


def test_e01_integration_executes_existing_engine(tmp_path):
    p=Project(tmp_path/"w","case")
    fixture=Path(__file__).resolve().parents[1]/"examples"/"p8_e01_evidence.json"
    result,out=p.run("P8-E01",fixture)
    assert result["returncode"]==0
    data=json.loads((out/"p8_e01_evidence_report.json").read_text(encoding="utf-8"))
    assert data["decision"]=="NO_AI_ORIGIN_CONCLUSION"


def test_desktop_ui_imports_headlessly():
    from aiforensics.desktop_app import DesktopApp, PAGES
    assert DesktopApp.__name__=="DesktopApp"
    assert len(PAGES)==9
