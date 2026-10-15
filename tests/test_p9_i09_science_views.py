"""P9-I09: reports are source-backed; negative provenance controls and UI wiring."""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from aiforensics.desktop_core import Project
from aiforensics.science_panel_data import (
    ScientificViewError,recorded_calibrations,residual_groups,valid_roi)
from aiforensics.focus_region import save_focus,get_focus,list_focus
from aiforensics.review_workspace import bind_finding_to_image


def created(project,mid,rid,filename,body):
    directory=project.root/"runs"/rid
    directory.mkdir()
    (directory/filename).write_text(json.dumps(body),encoding="utf-8")
    project.data["runs"].append({"run_id":rid,"state":"SUCCEEDED","module_id":mid})
    project.save()
    return directory/filename


def g02_body():
    return {"state":"MEASURED","decision":"NO_AI_ORIGIN_CONCLUSION",
            "g01_models":[{"vp_xy_px":[120.,30.],"inlier_count":10},
                          {"vp_xy_px":[230.,100.],"inlier_count":9}],
            "g02_calibration":{"state":"MEASURED",
             "K":[[1200.,0.,640.],[0.,1200.,360.],[0.,0.,1.]],
             "focal_length_px":1200.,"assumptions":["external orthogonality"]}}


def g04_body():
    return {"state":"MEASURED","decision":"NO_AI_ORIGIN_CONCLUSION",
            "train_reprojection_rmse_px":0.31,
            "holdout_reprojection_errors_px":[0.5,1.2,0.8],
            "holdout_reprojection_rmse_px":0.88,"holdout_threshold_px":3.0}


def evidence():
    return {"schema_version":"p8.e03.v1","decision":"NO_AI_ORIGIN_CONCLUSION",
            "findings":[
              {"record_id":"P1-G01/a",
               "measurement":{"signed_residual":2.,"unit":"px",
                 "confidence_interval_95_for_residual":[1.,3.]},
               "uncertainty":{"residual_std":0.5},"single_test":{"state":"INCONSISTENT_UNDER_ASSUMPTIONS"}},
              {"record_id":"P1-G02/b",
               "measurement":{"signed_residual":1.,"unit":"degree",
                 "confidence_interval_95_for_residual":None},
               "uncertainty":{"residual_std":None}},
              {"record_id":"P7-S01/c",
               "measurement":{"signed_residual":-1.,"unit":"px",
                 "confidence_interval_95_for_residual":None},
               "uncertainty":{}}]}


def test_empty_calibration_does_not_invent_vps(tmp_path):
    p=Project(tmp_path,"Empty")
    assert recorded_calibrations(p)=={}


def test_existing_g02_matrix_and_vps(tmp_path):
    p=Project(tmp_path,"Calibration")
    created(p,"P1-G02","0001_P1_G02","g01_g02_report.json",g02_body())
    result=recorded_calibrations(p)["P1-G02"]
    assert result["K"][0][0]==1200.
    assert result["vps"]==[[120.,30.],[230.,100.]]
    assert result["calibration_state"]=="MEASURED"
    assert result["image_sha256"] is None
    assert len(result["sha256"])==64


def test_g04_holdout_not_train_mixed(tmp_path):
    p=Project(tmp_path,"Holdout")
    created(p,"P1-G04","0001_P1_G04","g04_homography_report.json",g04_body())
    out=recorded_calibrations(p)["P1-G04"]
    assert out["train_reprojection_rmse_px"]==0.31
    assert out["errors_px"]==[0.5,1.2,0.8]
    assert out["holdout_threshold_px"]==3.0


def test_failed_run_not_shown(tmp_path):
    p=Project(tmp_path,"NotSuccess")
    created(p,"P1-G02","0001_P1_G02","g01_g02_report.json",g02_body())
    p.data["runs"][0]["state"]="FAILED"
    assert "P1-G02" not in recorded_calibrations(p)


def test_foreign_report_origin_claim_rejected(tmp_path):
    p=Project(tmp_path,"Origin")
    bad=dict(g02_body(),decision="AI_GENERATED")
    created(p,"P1-G02","0001_P1_G02","g01_g02_report.json",bad)
    assert recorded_calibrations(p)=={}


def test_nonfinite_vps_are_ignored(tmp_path):
    p=Project(tmp_path,"NaN")
    body=g02_body()
    body["g01_models"]=[{"vp_xy_px":[float("nan"),2.]}]
    created(p,"P1-G02","0001_P1_G02","g01_g02_report.json",body)
    # Nonfinite raw JSON is rejected altogether, no plausible VP guessed.
    assert recorded_calibrations(p)=={}


def test_invalid_k_is_not_silently_estimated(tmp_path):
    p=Project(tmp_path,"InvalidK")
    body=g02_body()
    body["g02_calibration"]["K"]=[[1,2],[3,4]]
    created(p,"P1-G02","0001_P1_G02","g01_g02_report.json",body)
    assert recorded_calibrations(p)["P1-G02"]["K"] is None


def test_e03_residuals_separate_units():
    groups=residual_groups(evidence())
    assert set(groups)=={"px","degree"}
    assert len(groups["px"])==2
    assert groups["degree"][0]["ci95"] is None
    assert groups["px"][0]["ci95"]==[1.,3.]
    assert groups["px"][1]["ci95"] is None


def test_e03_reject_wrong_origin_decision():
    with pytest.raises(ScientificViewError):
        residual_groups(dict(evidence(),decision="AI_GENERATED"))


def test_e03_reject_missing_schema():
    with pytest.raises(ScientificViewError):
        residual_groups(dict(evidence(),schema_version="old"))


@pytest.mark.parametrize("roi",[
    [0.,0.,0.,20.],[-1.,0.,20.,25.],[0.,0.,401.,15.],
    [1.,1.,float("nan"),30.],[True,1.,25.,30.],[1.,1.,24.]
])
def test_unverified_bad_roi_rejected(roi):
    with pytest.raises(ScientificViewError):
        valid_roi((400,250),roi)


def test_roi_boundary_inclusive():
    assert valid_roi((400,250),[0,0,400,250])==[0.,0.,400.,250.]


@pytest.fixture
def linked_project(tmp_path):
    p=Project(tmp_path,"Linked")
    image=p.root/"images"/"source.png"
    Image.new("RGB",(120,80),(1,2,3)).save(image)
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    p.data["images"].append({"name":"source.png","file":"source.png",
                              "sha256":digest,"camera_origin_verified":False})
    rid="0001_P8_E03"
    report={"schema_version":"p8.e03.v1","decision":"NO_AI_ORIGIN_CONCLUSION",
            "findings":[{"record_id":"P1-G01/test"}],"dependency_groups":[]}
    created(p,"P8-E03",rid,"p8_e03_explainable_report.json",report)
    return p,digest,rid+"/p8_e03_explainable_report.json"


def test_unlinked_finding_cannot_claim_region(linked_project):
    p,digest,rid=linked_project
    with pytest.raises(ScientificViewError,match="Explicit"):
        save_focus(p,rid,"P1-G01/test",digest,[1,1,20,20])


def test_saved_focus_requires_user_link(linked_project):
    p,digest,rid=linked_project
    bind_finding_to_image(p,rid,"P1-G01/test",digest)
    item=save_focus(p,rid,"P1-G01/test",digest,[1,2,100,60])
    assert item["provenance"]=="user_asserted_not_verified"
    assert get_focus(p,rid,"P1-G01/test",digest)["roi_xyxy_px"]==[1.,2.,100.,60.]
    assert len(list_focus(p))==1


def test_focus_update_replaces_not_multiplies(linked_project):
    p,digest,rid=linked_project
    bind_finding_to_image(p,rid,"P1-G01/test",digest)
    save_focus(p,rid,"P1-G01/test",digest,[1,2,100,60])
    save_focus(p,rid,"P1-G01/test",digest,[3,4,50,55])
    assert len(list_focus(p))==1


def test_changed_image_invalidates_focus(linked_project):
    p,digest,rid=linked_project
    bind_finding_to_image(p,rid,"P1-G01/test",digest)
    save_focus(p,rid,"P1-G01/test",digest,[1,1,20,20])
    (p.root/"images"/"source.png").write_bytes(b"altered")
    with pytest.raises(ValueError):
        get_focus(p,rid,"P1-G01/test",digest)


def test_ui_is_connected():
    import inspect
    from aiforensics.ui_polish import render_calibration,render_measurements
    from aiforensics.review_ui import ReviewWindow
    assert "attach_calibration" in inspect.getsource(render_calibration)
    assert "attach_residuals" in inspect.getsource(render_measurements)
    assert "_focus_finding" in inspect.getsource(ReviewWindow._make_finding_tab)


def test_ui_imports_without_display():
    import aiforensics.science_panel_ui as ui
    from aiforensics.focus_view_ui import FindingFocusWindow
    assert hasattr(ui,"show_vps") and hasattr(ui,"show_residuals")
    assert hasattr(FindingFocusWindow,"save")
