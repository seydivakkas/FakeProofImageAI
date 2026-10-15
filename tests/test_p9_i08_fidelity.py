"""P9-I08 source-backed presentation contract and no fabricated confidence tests."""
import json
from pathlib import Path
from types import SimpleNamespace

from aiforensics.ui_polish import MODULE_GROUPS, dashboard_stats, module_cards, latest_e03


def sample(runs=(), images=(), root=None):
    return SimpleNamespace(data={"runs":list(runs),"images":list(images)},
                           root=root or Path("/missing"),name="Controlled")


def test_eight_module_panels_no_default_success():
    cards=module_cards(sample())
    assert len(cards)==8
    assert [x["prefix"] for x in cards]==["P1","P2","P3","P4","P5","P6","P7","P8"]
    assert len({x["entry"] for x in cards})==8
    assert all(x["state"]=="Kayıt yok" and not x["validated"] for x in cards)


def test_module_panels_show_execution_not_physics_confidence():
    cards=module_cards(sample([
       {"module_id":"P1-G01","state":"SUCCEEDED"},
       {"module_id":"P2-S01","state":"FAILED"},
       {"module_id":"P2-S02","state":"TIMEOUT"},
       {"module_id":"P8-E01","state":"SUCCEEDED"}
    ]))
    indexed={x["prefix"]:x for x in cards}
    assert indexed["P1"]["succeeded"]==1
    assert indexed["P2"]["failed"]==2
    assert indexed["P2"]["state"]=="Çalışma hatası"
    assert indexed["P3"]["state"]=="Kayıt yok"
    assert indexed["P8"]["succeeded"]==1
    assert all(x["validated"] is False for x in cards)


def test_metrics_do_not_mix_empty_and_failed():
    obj=sample([
      {"module_id":"P1-G01","state":"SUCCEEDED"},
      {"module_id":"P2-S01","state":"FAILED"},
      {"module_id":"P7-S02","state":"TIMEOUT"},
      {"module_id":"P8-E03","state":"SUCCEEDED"},
    ],images=[{"file":"first.png"}])
    snap=dashboard_stats(obj)
    assert (snap["image_count"],snap["successful_runs"],snap["failed_runs"])==(1,2,2)
    assert snap["origin_decision"]=="NO_AI_ORIGIN_CONCLUSION"
    assert snap["camera_validation"]=="NOT_PERFORMED"


def test_no_unverified_e03_report(tmp_path):
    from aiforensics.desktop_core import Project
    project=Project(tmp_path,"SyntheticUI")
    assert latest_e03(project) is None
    folder=project.root/"runs"/"0001_P8_E03"
    folder.mkdir()
    path=folder/"p8_e03_explainable_report.json"
    path.write_text(json.dumps({"schema_version":"p8.e03.v1",
                               "decision":"AI_GENERATED","findings":[]}),encoding="utf-8")
    project.data["runs"]=[{"run_id":folder.name,"module_id":"P8-E03","state":"SUCCEEDED"}]
    assert latest_e03(project) is None


def test_e03_report_requires_registered_source(tmp_path):
    from aiforensics.desktop_core import Project
    p=Project(tmp_path,"ValidSynthetic")
    folder=p.root/"runs"/"0001_P8_E03"
    folder.mkdir()
    (folder/"p8_e03_explainable_report.json").write_text(
       json.dumps({"schema_version":"p8.e03.v1",
                   "decision":"NO_AI_ORIGIN_CONCLUSION",
                   "findings":[{"record_id":"P1-G01/test"}]}),encoding="utf-8")
    p.data["runs"]=[{"run_id":folder.name,"module_id":"P8-E03","state":"SUCCEEDED"}]
    result=latest_e03(p)
    assert result and len(result["report"]["findings"])==1
    assert len(result["report_sha256"])==64


def test_existing_desktop_actions_connected():
    import inspect
    from aiforensics.desktop_app import DesktopApp
    from aiforensics.integration_ui import render_unified_home
    assert "render_overview" in inspect.getsource(render_unified_home)
    for name,fn in [("screen_3","render_calibration"),
                    ("screen_4","render_measurements"),
                    ("screen_5","render_evidence")]:
        assert fn in inspect.getsource(getattr(DesktopApp,name))


def test_explicitly_preserves_existing_synthetic_demo():
    import inspect
    from aiforensics.ui_polish import render_overview
    assert "run_synthetic_from_ui" in inspect.getsource(render_overview)


def test_catalog_not_redefined_for_fidelity():
    assert len(MODULE_GROUPS)==8
