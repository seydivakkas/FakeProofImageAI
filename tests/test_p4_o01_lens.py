"""P4-O01 controlled Brown-Conrady unit, leakage, regression & fail-closed tests."""
import copy
import json
import numpy as np
import cv2
import pytest
from aiforensics.lens_distortion import (
    LensConfig, LensGeometryError, distort_pixels, distort_normalized, to_normalized,
    to_pixel, undistort_pixels, radial_monotonicity, jacobian_min_determinant,
    plumb_line_rmse, fit_coefficients, analyze_manifest, run_lens_manifest)
from aiforensics.lens_synthetic import synthetic_lens_scene


@pytest.fixture(scope='module')
def scene():
    return synthetic_lens_scene(seed=41)


def test_exact_zero_distortion():
    K=[[700,0,310],[0,710,240],[0,0,1]]
    pts=np.array([[310,240],[50,50],[300,450]],float)
    assert np.allclose(distort_pixels(pts,K,[0]*5),pts)


def test_radial_formula():
    n=[[.5,.0]]
    result=distort_normalized(n,[.1,.2,0,0,.3])
    expect=.5*(1+.1*.25+.2*.25**2+.3*.25**3)
    assert np.allclose(result,[[expect,0]])


def test_tangential_formula():
    x,y=.3,-.5
    p1,p2=.04,-.02
    dx=2*p1*x*y +p2*(x*x+y*y+2*x*x)
    dy=p1*(x*x+y*y+2*y*y)+2*p2*x*y
    assert np.allclose(distort_normalized([[x,y]],[0,0,p1,p2,0]),[[x+dx,y+dy]])


def test_against_opencv_project_points():
    K=np.array([[750.,0,640],[0,780.,360],[0,0,1]])
    d=np.array([-.2,.05,.006,-.002,-.01])
    points=np.array([[-.5,-.3],[0,0],[.4,.6],[.65,-.4]])
    p=to_pixel(points,K)
    expected=cv2.projectPoints(np.column_stack([points,np.ones(len(points))]),
        np.zeros(3),np.zeros(3),K,d)[0].reshape(-1,2)
    assert np.max(np.abs(distort_pixels(p,K,d)-expected))<1e-9


def test_inverse_recovers_ideal():
    K=np.array([[860,0,640],[0,850,360],[0,0,1]],float)
    xs=np.array([(x,y) for x in np.linspace(100,1150,15) for y in np.linspace(75,630,9)])
    d=[-.27,.065,.008,-.006,-.015]
    got=undistort_pixels(distort_pixels(xs,K,d),K,d)
    assert np.max(np.linalg.norm(got-xs,axis=1))<1e-5


def test_four_coefficient_backcompat():
    assert np.allclose(distort_normalized([[.6,.2]],[.1,.01,.002,.004]),
                       distort_normalized([[.6,.2]],[.1,.01,.002,.004,0]))


def test_nonmonotone_radial_rejected():
    assert not radial_monotonicity([-2,0,0,0,0],1.0)
    assert jacobian_min_determinant([-2,0,0,0,0],1.0)<0


def test_invalid_camera_and_coefficients():
    with pytest.raises(LensGeometryError):distort_pixels([[2,2]],np.eye(3)*0,[0]*5)
    with pytest.raises(LensGeometryError):distort_pixels([[2,2]],np.eye(3),[np.nan]*5)
    with pytest.raises(LensGeometryError):distort_pixels([[2,2]],np.eye(3),[1,2,3])
    with pytest.raises(LensGeometryError):distort_pixels([[2,2]],[[800,8,0],[0,800,0],[0,0,1]],[0]*5)


def test_plumb_line_zero_ideal():
    t=np.linspace(0,20,35)
    pts=np.stack([t,2*t+1],axis=1)
    assert plumb_line_rmse(pts)<1e-10


def test_plumb_line_rejects_degenerate():
    with pytest.raises(LensGeometryError):plumb_line_rmse([[1,2],[1,2],[1,2]])
    with pytest.raises(LensGeometryError):plumb_line_rmse([[1,2],[3,4]])


def test_fit_recovers_noiseless_five(scene):
    data,_,truth=scene
    rec=[x for x in data['point_pairs'] if x['role']=='train']
    ideal=np.array([x['ideal_xy_px'] for x in rec]);k=np.array(data['K'])
    perfect=distort_pixels(ideal,k,truth['coefficients'])
    got,condition=fit_coefficients(ideal,perfect,k,5)
    assert np.allclose(got,truth['coefficients'],atol=1e-8)
    assert np.isfinite(condition)


def test_rejects_unidentifiable_constant_radius(scene):
    data,_,truth=scene
    k=data['K']
    t=np.linspace(0,2*np.pi,80,endpoint=False)
    ideal=to_pixel(np.column_stack([.4*np.cos(t),.4*np.sin(t)]),k)
    seen=distort_pixels(ideal,k,truth['coefficients'])
    with pytest.raises(LensGeometryError,match='ill-conditioned'):
        fit_coefficients(ideal,seen,k)


def test_manifest_holds_out_independent_points(scene):
    data,_,truth=scene
    result=analyze_manifest(data)
    assert result['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert result['train_count']==96
    assert result['holdout_count']==70
    assert result['holdout_rmse_px']<.4
    assert abs(result['coefficients'][0]-truth['coefficients'][0])<.02
    assert result['radial_monotonic']
    assert all(x['after_consistent'] for x in result['line_holdouts'])
    assert len(result['line_holdouts'])==6
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_straight_lines_get_straighter(scene):
    result=analyze_manifest(scene[0])
    assert any(x['before_rmse_px']>1.5 for x in result['line_holdouts'])
    assert all(x['after_rmse_px']<x['before_rmse_px'] for x in result['line_holdouts'])


def test_holdout_tamper_detected(scene):
    data=copy.deepcopy(scene[0])
    h=[p for p in data['point_pairs'] if p['role']=='holdout']
    for p in h[:8]:p['observed_xy_px'][0]+=12
    result=analyze_manifest(data)
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert result['holdout_rmse_px']>2


def test_line_tamper_detected(scene):
    data=copy.deepcopy(scene[0])
    pts=data['independent_straight_lines'][0]['observed_points_xy_px']
    pts[len(pts)//2][1]+=23
    result=analyze_manifest(data)
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert not result['line_holdouts'][0]['after_consistent']


def test_unverified_line_never_called_physical_evidence(scene):
    data=copy.deepcopy(scene[0])
    data['independent_straight_lines'][0]['externally_verified_straight']=False
    result=analyze_manifest(data)
    assert len(result['line_holdouts'])==5


def test_insufficient_train_returns_indeterminate(scene):
    data=copy.deepcopy(scene[0]);data['point_pairs']=[x for x in data['point_pairs'] if x['role']=='holdout']
    result=analyze_manifest(data)
    assert result['state']=='INDETERMINATE'


def test_insufficient_holdout_returns_indeterminate(scene):
    data=copy.deepcopy(scene[0]);data['point_pairs']=[x for x in data['point_pairs'] if x['role']=='train']
    result=analyze_manifest(data)
    assert result['state']=='INDETERMINATE'


def test_duplicate_id_fails_closed(scene):
    data=copy.deepcopy(scene[0]);data['point_pairs'][1]['id']=data['point_pairs'][0]['id']
    with pytest.raises(LensGeometryError): analyze_manifest(data)


def test_train_role_invalid(scene):
    data=copy.deepcopy(scene[0]);data['point_pairs'][0]['role']='training'
    with pytest.raises(LensGeometryError): analyze_manifest(data)


def test_not_enough_radius_for_k3_fails(scene):
    d,_,_=scene
    k=np.array(d['K'])
    # Inadequate field coverage: near principal point all polynomial radial powers nearly identical.
    ideal=np.array([[636+i*.01,359+j*.01] for i in range(5) for j in range(5)])
    with pytest.raises(LensGeometryError):fit_coefficients(ideal,ideal,k)


def test_four_coefficient_fit_on_four_coefficient_fixture():
    fixture,_,truth=synthetic_lens_scene(model_order=4)
    result=analyze_manifest(fixture,LensConfig(order=4))
    assert result['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert result['coefficients'][-1]==0


def test_file_report_and_overlay(scene,tmp_path):
    fixture,canvas,_=scene
    p=tmp_path/'manifest.json';p.write_text(json.dumps(fixture))
    image=tmp_path/'scene.png';cv2.imwrite(str(image),canvas)
    r=run_lens_manifest(p,tmp_path/'out',image)
    assert r['image_sha256']
    assert r['manifest_sha256']
    assert (tmp_path/'out/p4_o01_overlay.png').is_file()
    disk=json.loads((tmp_path/'out/p4_o01_report.json').read_text())
    assert disk['holdout_rmse_px']==r['holdout_rmse_px']


def test_benchmark_determinism():
    from scripts.p4_lens_benchmark import run
    a,b=run(3),run(3)
    assert a==b
    assert a['trials']==3


def test_cli_demo(tmp_path):
    from aiforensics.cli import main
    main(['demo-lens','--out',str(tmp_path)])
    assert (tmp_path/'p4_o01_fixture.json').is_file()
    assert json.loads((tmp_path/'p4_o01_report.json').read_text())['state']=='CONSISTENT_UNDER_ASSUMPTIONS'


def test_inverse_nonconvergent_reports_failure():
    K=[[800,0,640],[0,800,360],[0,0,1]]
    with pytest.raises(LensGeometryError):
        undistort_pixels([[1800,800]],K,[-1.8,.0,0,0,0],iterations=4)


def test_missing_provenance_abstains(scene):
    data=copy.deepcopy(scene[0]);del data['data_provenance']
    result=analyze_manifest(data)
    assert result['state']=='INDETERMINATE'


def test_ill_conditioned_manifest_abstains(scene):
    data=copy.deepcopy(scene[0])
    k=np.asarray(data['K'])
    t=np.linspace(0,2*np.pi,96,endpoint=False)
    ideal=to_pixel(np.column_stack([.4*np.cos(t),.4*np.sin(t)]),k)
    for p,xy in zip([r for r in data['point_pairs'] if r['role']=='train'],ideal):
        p['ideal_xy_px']=xy.tolist()
        p['observed_xy_px']=xy.tolist()
    r=analyze_manifest(data)
    assert r['state']=='INDETERMINATE'


def test_rectified_preview_saved(scene,tmp_path):
    fixture,canvas,_=scene
    p=tmp_path/'manifest.json';p.write_text(json.dumps(fixture))
    image=tmp_path/'image.png';cv2.imwrite(str(image),canvas)
    r=run_lens_manifest(p,tmp_path/'out',image)
    assert r['rectified_preview']=='p4_o01_rectified.png'
    assert (tmp_path/'out/p4_o01_rectified.png').is_file()


def test_holdout_baseline_better_after_correction(scene):
    result=analyze_manifest(scene[0])
    assert result['holdout_uncorrected_rmse_px']>result['holdout_rmse_px']*15
