"""P4-O03 synthetic, negative, train/holdout leakage and CLI regression."""
import copy
import json
import math
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest
from aiforensics.optical_consistency import (OpticalConsistencyError,OpticalConfig,
        focal_to_fov,camera_fovs,native_to_output_K,project_points,analyze_optical_manifest,
        run_optical_manifest)
from aiforensics.optical_synthetic import synthetic_optical_fixture


def fixture(**kw):return synthetic_optical_fixture(**kw)[0]


def test_central_symmetric_fov():
    assert focal_to_fov(1000,640,1280)==pytest.approx(2*math.degrees(math.atan(640/1000)))


def test_off_center_fov_exact():
    assert focal_to_fov(1000,100,1280)==pytest.approx(math.degrees(math.atan(.1)+math.atan(1.18)))
    assert focal_to_fov(1000,100,1280)!=pytest.approx(2*math.degrees(math.atan(.64)))


def test_cropped_and_resized_focal():
    K=[[1200,0,770],[0,1200,450],[0,0,1]]
    dest=native_to_output_K(K,[1600,1000],[140,100,1280,720],[640,360])
    assert np.allclose(dest,[[600,0,315],[0,600,175],[0,0,1]])


def test_project_3d_obeys_inverse_depth():
    K=np.array([[1000,0,500],[0,1000,300],[0,0,1]])
    pts=project_points([[1,0,2],[1,0,4]],K,np.eye(3),np.zeros(3))
    assert pts[:,0].tolist()==pytest.approx([1000,750])
    assert pts[:,1].tolist()==pytest.approx([300,300])


def test_world_pose_projection():
    data=fixture(corrupt=0)
    K=data['K'];p=data['samples'][0]
    x=project_points([p['world_xyz']],K,np.array(data['pose']['R_world_to_camera']),
                np.array(data['pose']['t_world_to_camera']))[0]
    assert np.linalg.norm(x-p['observed_xy_px'])<2.


def test_valid_fixture_no_corruption():
    report=analyze_optical_manifest(fixture(corrupt=0))
    assert report['state']=='CONSISTENT'
    assert report['holdout_count']==32
    assert report['counts']['inconsistent']==0
    assert report['K'][0][0]==1200


def test_negative_control_corruption():
    data,truth=synthetic_optical_fixture(corrupt=3)
    result=analyze_optical_manifest(data)
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    bad={r['id'] for r in result['holdout_results'] if r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'}
    assert set(truth['corrupted_ids'])==bad


def test_focal_fit_clean():
    report=analyze_optical_manifest(fixture(fit_focal=True,corrupt=0))
    assert report['state']=='CONSISTENT'
    assert abs(report['K'][0][0]-1200)<4
    assert abs(report['K'][1][1]-1200)<4
    assert report['train_count']==24


def test_focal_fit_holdout_leakage():
    data=fixture(fit_focal=True,corrupt=0)
    before=analyze_optical_manifest(data)['K']
    for r in data['samples']:
        if r['role']=='holdout':r['observed_xy_px'][0]+=100
    after=analyze_optical_manifest(data)['K']
    assert before==after
    assert analyze_optical_manifest(data)['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_focal_fit_weak_diversity_abstains():
    data=fixture(fit_focal=True,corrupt=0)
    for r in data['samples']:
        if r['role']=='train':r['world_xyz']=[0,0,10]
    assert analyze_optical_manifest(data)['state']=='INDETERMINATE'


def test_focal_fit_refuses_joint_unknown_distortion():
    data=fixture(fit_focal=True,corrupt=0)
    data['brown_conrady_coefficients']=[.1,-.02,.001,.002,0.]
    assert analyze_optical_manifest(data)['state']=='INDETERMINATE'


def test_known_distortion_separate_from_focal_fit():
    data=fixture(corrupt=0,distortion=[.05,-.015,.001,-.001,0])
    report=analyze_optical_manifest(data)
    assert report['state']=='CONSISTENT'
    assert report['counts']['inconsistent']==0


def test_bad_claimed_horizontal_fov():
    data=fixture(corrupt=0)
    data['independent_claims']['horizontal_fov_deg']=20.
    report=analyze_optical_manifest(data)
    assert report['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert any(x['name']=='horizontal_fov_deg' and x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for x in report['sensor_and_claim_checks'])


def test_correct_claim_fov():
    data=fixture(corrupt=0)
    data['independent_claims']['horizontal_fov_deg']=camera_fovs(data['K'],data['image_size_wh'])['horizontal_deg']
    assert analyze_optical_manifest(data)['state']=='CONSISTENT'


def test_wrong_independent_native_focal_metadata():
    data=fixture(corrupt=0)
    data['sensor_metadata']['focal_length_mm']=15
    report=analyze_optical_manifest(data)
    assert report['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_wrong_crop_assumption():
    data=fixture(corrupt=0)
    data['image_transform']['crop_xywh'][0]+=35
    assert analyze_optical_manifest(data)['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_segment_projected_size():
    data=fixture(corrupt=0)
    r=analyze_optical_manifest(data)['segment_holdouts'][0]
    assert r['state']=='CONSISTENT'
    assert r['expected_length_px']==pytest.approx(120.,abs=1.e-8)


def test_segment_invalid_corrupted():
    data=fixture(corrupt=0)
    data['segment_holdouts'][0]['observed_endpoints_xy_px'][1][0]+=30
    assert analyze_optical_manifest(data)['segment_holdouts'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_wrong_vp_direction_or_annotation():
    data=fixture(corrupt=0)
    data['vanishing_point_holdouts'][0]['observed_xy_px'][0]+=60
    assert analyze_optical_manifest(data)['vanishing_point_holdouts'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_vp_at_infinity_abstains():
    data=fixture(corrupt=0)
    R=np.array(data['pose']['R_world_to_camera'])
    data['vanishing_point_holdouts'][0]['direction_world']=(R.T@np.array([1.,0.,0.])).tolist()
    assert analyze_optical_manifest(data)['vanishing_point_holdouts'][0]['state']=='INDETERMINATE'


def test_vp_distorted_abstains():
    data=fixture(corrupt=0,distortion=[.05,-.015,.001,-.001,0])
    data['vanishing_point_holdouts']=[{'id':'vp','direction_world':[0,0,1],
      'observed_xy_px':[0,0],'observed_sigma_px':1}]
    assert analyze_optical_manifest(data)['vanishing_point_holdouts'][0]['state']=='INDETERMINATE'


def test_outside_frame_holdout_abstains():
    data=fixture(corrupt=0)
    r=data['samples'][24]
    R=np.array(data['pose']['R_world_to_camera']);t=np.array(data['pose']['t_world_to_camera'])
    r['world_xyz']=((np.array([5.,0.,6.])-t)@R).tolist()
    report=analyze_optical_manifest(data)
    assert report['holdout_results'][0]['state']=='INDETERMINATE'


def test_unverified_provenance_abstains():
    data=fixture(corrupt=0)
    del data['samples'][24]['measurement_provenance']
    assert analyze_optical_manifest(data)['holdout_results'][0]['state']=='INDETERMINATE'


def test_no_data_provenance_abstains():
    data=fixture();data.pop('data_provenance')
    assert analyze_optical_manifest(data)['state']=='INDETERMINATE'


def test_insufficient_holdouts_abstains():
    data=fixture();data['samples']=[r for r in data['samples'] if r['role']=='train']
    assert analyze_optical_manifest(data)['state']=='INDETERMINATE'


def test_duplicate_point_ids_rejected():
    data=fixture();data['samples'][1]['id']=data['samples'][0]['id']
    with pytest.raises(OpticalConsistencyError):analyze_optical_manifest(data)


@pytest.mark.parametrize('bad',[[[-1,0,0],[0,1,0],[0,0,1]],[[100,3,0],[0,100,0],[0,0,1]],[[1,0,0],[0,1,0],[.1,0,1]]])
def test_invalid_K_rejected(bad):
    data=fixture();data['K']=bad
    with pytest.raises(OpticalConsistencyError):analyze_optical_manifest(data)


def test_reflection_rotation_rejected():
    data=fixture();data['pose']['R_world_to_camera']=[[-1,0,0],[0,1,0],[0,0,1]]
    with pytest.raises(OpticalConsistencyError):analyze_optical_manifest(data)


def test_negative_depth_indeterminate():
    data=fixture(corrupt=0)
    data['samples'][24]['world_xyz']=[0,0,-10]
    assert analyze_optical_manifest(data)['holdout_results'][0]['state']=='INDETERMINATE'


def test_invalid_sensor_pitch_rejected():
    data=fixture();data['sensor_metadata']['pixel_pitch_x_um']=-4
    with pytest.raises(OpticalConsistencyError):analyze_optical_manifest(data)


def test_crop_out_of_bounds_rejected():
    with pytest.raises(OpticalConsistencyError):native_to_output_K(np.eye(3),[100,100],[80,80,50,50],[640,480])


def test_known_truth_fixture_serializes_finite(tmp_path):
    f=tmp_path/'input.json';f.write_text(json.dumps(fixture(),allow_nan=False),encoding='utf-8')
    r=run_optical_manifest(f,tmp_path/'out')
    assert json.loads((tmp_path/'out'/'p4_o03_report.json').read_text())['state']==r['state']


def test_cli_demo_and_analyze(tmp_path):
    a=tmp_path/'demo';b=tmp_path/'check'
    x=subprocess.run([sys.executable,'-m','aiforensics','demo-optics','--out',str(a)],capture_output=True,text=True)
    assert x.returncode==0,x.stderr
    y=subprocess.run([sys.executable,'-m','aiforensics','analyze-optics','--input',str(a/'p4_o03_fixture.json'),'--out',str(b)],capture_output=True,text=True)
    assert y.returncode==0,y.stderr
    assert (b/'p4_o03_report.json').is_file()


def test_fov_error_nonpositive():
    with pytest.raises(OpticalConsistencyError):focal_to_fov(-100,0,100)


def test_crop_verified_without_sensor_metadata():
    data=fixture(corrupt=0)
    data.pop('sensor_metadata')
    data['image_transform']['crop_xywh'][0]+=20
    r=analyze_optical_manifest(data)
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_unverified_focal_train_abstains():
    data=fixture(fit_focal=True,corrupt=0)
    data['samples'][0].pop('measurement_provenance')
    assert analyze_optical_manifest(data)['state']=='INDETERMINATE'


def test_exact_diagonal_fov_offcenter():
    k=[[1000,0,130],[0,1200,200],[0,0,1]]
    v=camera_fovs(k,[1280,720])
    assert len(v['diagonal_spans_deg'])==2
    assert v['diagonal_spans_deg'][0]!=pytest.approx(v['diagonal_spans_deg'][1])
