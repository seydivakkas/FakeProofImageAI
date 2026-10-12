"""G02 analytical + G01 integration regression tests; controlled, NOT real-photo tests."""
import json
import numpy as np
import pytest
from aiforensics.calibration import (
    CalibrationConfig, CalibrationError, calibrate_three_orthogonal_vps,
    calibrate_from_g01_groups,
)
from aiforensics.synthetic_camera import camera_ground_truth, labeled_segments_from_vps
from aiforensics.vp import VPConfig
from aiforensics.cli import run_calibration_from_segments, run_calibration_from_points

SHAPE=(720, 1280)
FAST=VPConfig(max_trials=500, bootstrap_trials=0, random_seed=2026)


def test_intrinsics_and_extrinsics_from_exact_vps():
    Ktrue, Rtrue, vps = camera_ground_truth()
    result=calibrate_three_orthogonal_vps(vps, SHAPE)
    assert np.allclose(result.K, Ktrue, rtol=1e-10, atol=1e-7)
    assert np.allclose(result.omega / result.omega[2, 2],
                       (np.linalg.inv(Ktrue).T @ np.linalg.inv(Ktrue)) / (
                           np.linalg.inv(Ktrue).T @ np.linalg.inv(Ktrue))[2,2])
    assert np.allclose(result.R.T @ result.R, np.eye(3), atol=1e-12)
    assert np.linalg.det(result.R) == pytest.approx(1, abs=1e-12)
    # World-direction sign ambiguity: each column can flip without changing its VP.
    assert np.allclose(np.abs(np.sum(result.R * Rtrue, axis=0)), np.ones(3), atol=1e-9)
    assert max(result.orthogonality_residuals) < 1e-11


def test_principal_point_not_forced_to_image_center():
    K, R, vps = camera_ground_truth(focal=720., principal=(592.,388.))
    got=calibrate_three_orthogonal_vps(vps, SHAPE)
    assert np.allclose(got.K, K, atol=1e-7)


def test_exact_solution_under_three_direction_sign_reordering():
    K, R, vps = camera_ground_truth()
    cal=calibrate_three_orthogonal_vps(vps[[2,0,1]], SHAPE)
    assert np.allclose(cal.K, K, atol=1e-7)
    assert np.linalg.det(cal.R) == pytest.approx(1, abs=1e-12)


def test_g01_labeled_families_to_g02_integration():
    K, _, vps = camera_ground_truth()
    groups=labeled_segments_from_vps(vps, count_per_group=60, endpoint_noise=.20, seed=21)
    output=calibrate_from_g01_groups(groups, SHAPE, FAST)
    assert output['state'] == 'MEASURED', output.get('reason')
    assert all(f['inlier_count'] >= 20 for f in output['g01_models'])  # conservative finite-VP RANSAC
    estimated=np.asarray(output['g02_calibration']['K'])
    assert abs(estimated[0,0]-K[0,0]) < 15
    assert np.linalg.norm(estimated[:2,2]-K[:2,2]) < 15
    assert output['decision'] == 'NO_AI_ORIGIN_CONCLUSION'


def test_missing_group_is_indeterminate():
    _,_,vps=camera_ground_truth()
    groups=labeled_segments_from_vps(vps, count_per_group=40)
    groups[2] = np.zeros((0,4))
    result=calibrate_from_g01_groups(groups, SHAPE, FAST)
    assert result['state']=='INDETERMINATE'
    assert 'group 2' in result['reason']


def test_number_of_groups_must_be_three():
    with pytest.raises(CalibrationError, match='Exactly three'):
        calibrate_from_g01_groups([], SHAPE, FAST)


def test_collinear_vps_rejected_as_degenerate():
    with pytest.raises(CalibrationError, match='Degenerate'):
        calibrate_three_orthogonal_vps(np.array([[100., 100.], [200., 200.], [300., 300.]]), SHAPE)


def test_invalid_vps_rejected():
    with pytest.raises(CalibrationError, match='finite'):
        calibrate_three_orthogonal_vps([[0,0],[1,2],[np.nan,2]], SHAPE)
    with pytest.raises(CalibrationError, match='finite'):
        calibrate_three_orthogonal_vps([[1,2],[3,4]], SHAPE)
    with pytest.raises(CalibrationError, match='positive'):
        calibrate_three_orthogonal_vps([[1,2],[3,4],[5,6]], (0, 1280))


def test_negative_f_squared_rejected():
    # Three point configuration with no positive real pinhole focal solution.
    vps=np.array([[0.,0.],[500.,0.],[250.,100.]])
    with pytest.raises(CalibrationError, match='Non-positive squared focal'):
        calibrate_three_orthogonal_vps(vps, SHAPE)


def test_camera_model_range_guard_is_configurable():
    _,_,vps=camera_ground_truth(focal=900.)
    config=CalibrationConfig(max_focal_ratio_to_diagonal=.3)
    with pytest.raises(CalibrationError, match='Focal length outside'):
        calibrate_three_orthogonal_vps(vps, SHAPE,config)


def test_noise_resilience_controlled_monte_carlo():
    rng=np.random.default_rng(9)
    K,_,vps=camera_ground_truth()
    errs=[]
    for _ in range(200):
        noisy=vps+rng.normal(0,.50,size=(3,2))
        try:
            result=calibrate_three_orthogonal_vps(noisy, SHAPE)
        except CalibrationError:
            continue
        errs.append((abs(result.focal_length_px-K[0,0]),
                     np.linalg.norm(np.array(result.principal_point_xy)-K[:2,2])))
    assert len(errs)>=195
    assert np.percentile(errs,90,axis=0)[0] < 15
    assert np.percentile(errs,90,axis=0)[1] < 10


def test_reports_json_valid_and_origin_unknown(tmp_path):
    K,_,vps=camera_ground_truth()
    result=run_calibration_from_points(vps.tolist(),SHAPE,tmp_path/'points')
    assert result['state']=='MEASURED'
    assert json.loads((tmp_path/'points'/'g02_calibration.json').read_text())['decision']=='NO_AI_ORIGIN_CONCLUSION'
    groups=labeled_segments_from_vps(vps, count_per_group=35,endpoint_noise=.15)
    inp=tmp_path/'groups.json'
    inp.write_text(json.dumps({'image_shape_hw':list(SHAPE),
                               'orthogonal_groups':[a.tolist() for a in groups]}))
    result=run_calibration_from_segments(inp,tmp_path/'segments',FAST)
    assert result['state']=='MEASURED'
    assert json.loads((tmp_path/'segments'/'g01_g02_report.json').read_text())['module']=='G01_TO_G02_ORTHOGONAL_CALIBRATION'
