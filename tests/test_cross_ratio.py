import numpy as np
import pytest
from aiforensics.cross_ratio import analyze_repeated_landmarks, cross_ratio_1d, ProjectiveEvidenceError
from aiforensics.cli import main
import json


def projected_points(indices, noise=0., seed=1):
    ix=np.asarray(indices,dtype=float)
    t=(18.*ix+35.)/(.11*ix+1.)
    unit=np.array([.82,.57236352]); unit/=np.linalg.norm(unit)
    p=np.array([160.,85.])+t[:,None]*unit
    return p+np.random.default_rng(seed).normal(0,noise,size=p.shape)


def test_g03_cross_ratio_exact():
    p=projected_points(range(5))
    result=analyze_repeated_landmarks(p,bootstrap_samples=0,training_indices=[0,1,3])
    assert result['cross_ratio_observed']==pytest.approx(4/3,abs=1e-10)
    assert result['holdout']['reprojection_rmse_px']<1e-8
    assert result['collinearity_rms_px']<1e-10
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_g03_cross_ratio_rotation_translation_scale():
    p=projected_points(range(5))
    rot=np.array([[.4,-.916515139],[.916515139,.4]])
    out=analyze_repeated_landmarks(3*p@rot.T+np.array([345,112]),bootstrap_samples=0)
    assert out['cross_ratio_observed']==pytest.approx(4/3,abs=1e-10)


def test_g03_non_equal_spacing_detected():
    # The physical index labels say equal intervals, but one observed mark is displaced.
    p=projected_points(range(5))
    p[2]+=np.array([5.,3.489])
    result=analyze_repeated_landmarks(p,pixel_sigma=.1,bootstrap_samples=250)
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert result['cross_ratio_abs_error']>.005


def test_g03_noncollinear_is_indeterminate():
    p=projected_points(range(5));p[2]+=np.array([-11,20])
    result=analyze_repeated_landmarks(p,pixel_sigma=.2,bootstrap_samples=60)
    assert result['state']=='INDETERMINATE'


def test_g03_holdout_detects_bad_fifth_point_even_when_first_four_match():
    p=projected_points(range(6))
    p[5]+=np.array([10.,10.])
    result=analyze_repeated_landmarks(p,training_indices=[0,1,2,3],bootstrap_samples=0)
    assert result['holdout']['reprojection_rmse_px']>5
    assert result['cross_ratio_abs_error']<1e-8


def test_g03_custom_lattice_indices():
    idx=np.array([0,2,3,5,8])
    res=analyze_repeated_landmarks(projected_points(idx),idx,bootstrap_samples=0)
    assert res['cross_ratio_observed']==pytest.approx(cross_ratio_1d(idx[:4]),abs=1e-10)


def test_g03_invalid_points_and_indices():
    with pytest.raises(ProjectiveEvidenceError): analyze_repeated_landmarks(np.zeros((3,2)))
    with pytest.raises(ProjectiveEvidenceError): analyze_repeated_landmarks(projected_points(range(4)),[1,1,3,4])
    with pytest.raises(ProjectiveEvidenceError): analyze_repeated_landmarks(projected_points(range(4)),training_indices=[0,1,2,3])


def test_g03_json_cli(tmp_path):
    path=tmp_path/'points.json'
    path.write_text(json.dumps({'points_xy':projected_points(range(6)).tolist(),
                               'training_indices':[0,1,2,3], 'bootstrap_samples':0}))
    main(['analyze-g03','--input',str(path),'--out',str(tmp_path/'out')])
    data=json.loads((tmp_path/'out'/'g03_projective_report.json').read_text())
    assert data['state']=='MEASURED'
    assert data['holdout']['count']==2


def test_g03_cross_ratio_zero_noise_not_false_positive():
    p=projected_points(range(4))
    res=analyze_repeated_landmarks(p, pixel_sigma=0., bootstrap_samples=40)
    assert res['state']=='MEASURED'


def test_g03_image_overlay(tmp_path):
    import cv2
    points=projected_points(range(5))
    img=np.full((350,600,3),140,dtype=np.uint8)
    image=tmp_path/'source.png';cv2.imwrite(str(image),img)
    path=tmp_path/'points.json'
    path.write_text(json.dumps({'points_xy':points.tolist(),'bootstrap_samples':0}))
    main(['analyze-g03','--input',str(path),'--image',str(image),'--out',str(tmp_path/'annotated')])
    assert (tmp_path/'annotated'/'g03_landmarks_overlay.png').is_file()
    j=json.loads((tmp_path/'annotated'/'g03_projective_report.json').read_text())
    assert len(j['image_sha256'])==64
