"""Validate real-camera integration contract with a synthetic fixture; no field claims."""
import json
from pathlib import Path
import numpy as np
import cv2
import pytest
from aiforensics.calibration import CalibrationError
from aiforensics.synthetic_camera import camera_ground_truth,labeled_segments_from_vps
from aiforensics.real_validation import evaluate_real_case,RealValidationError,run_real_manifest
from aiforensics.vp import VPConfig

CONFIG=VPConfig(max_trials=600,bootstrap_trials=0)


def fixture(tmp_path):
    im=np.zeros((720,1280,3),dtype=np.uint8)
    cv2.imwrite(str(tmp_path/'fixture.jpg'),im)
    K,_,vps=camera_ground_truth()
    groups=labeled_segments_from_vps(vps, count_per_group=60,endpoint_noise=.12,seed=4)
    return {'image':'fixture.jpg','image_shape_hw':[720,1280],
            'known_intrinsics_K':K.tolist(),
            'train_orthogonal_groups':[g[:42].tolist() for g in groups],
            'holdout_orthogonal_groups':[g[42:].tolist() for g in groups],
            'source':'SYNTHETIC TEST FIXTURE (not real camera)',
            'capture_and_calibration_provenance':'Test-only synthetic known K'}


def test_real_validate_requires_file(tmp_path):
    result=evaluate_real_case({'image':'absent.jpg','image_shape_hw':[720,1280],
            'known_intrinsics_K':np.eye(3).tolist(),'train_orthogonal_groups':[[],[],[]],
            'holdout_orthogonal_groups':[[],[],[]],'source':'test',
            'capture_and_calibration_provenance':'test'},tmp_path)
    assert result['state']=='INDETERMINATE'


def test_real_validate_rejects_missing_ground_truth(tmp_path):
    d=fixture(tmp_path)
    del d['known_intrinsics_K']
    assert evaluate_real_case(d,tmp_path)['state']=='INDETERMINATE'


def test_real_holdout_and_refK_synthetic_contract(tmp_path):
    d=fixture(tmp_path)
    result=evaluate_real_case(d,tmp_path,CONFIG)
    assert result['state']=='MEASURED', result.get('reason')
    assert result['absolute_focal_error_px']<20
    assert result['principal_point_error_px']<20
    assert len(result['independent_holdout_group_metrics'])==3
    assert max(a['holdout_line_to_vp_median_px'] for a in result['independent_holdout_group_metrics'])<4


def test_real_overlap_rejected(tmp_path):
    d=fixture(tmp_path);d['holdout_orthogonal_groups'][0][0]=d['train_orthogonal_groups'][0][0]
    with pytest.raises(RealValidationError,match='overlap'):
        evaluate_real_case(d,tmp_path,CONFIG)


def test_real_manifest_cli_no_data_is_indeterminate(tmp_path):
    p=tmp_path/'case.json'
    p.write_text(json.dumps({'image':'unavailable.jpg'}))
    result=run_real_manifest(p,tmp_path/'out')
    assert result['state']=='INDETERMINATE'
    assert (tmp_path/'out'/'g02_real_independent_validation.json').exists()
