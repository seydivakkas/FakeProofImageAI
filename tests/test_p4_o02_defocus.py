"""P4-O02 physical forward model, holdout, invalid geometry and CLI checks."""
from __future__ import annotations
import copy
import json
import math
import subprocess
import sys
import numpy as np
import cv2
import pytest
from aiforensics.defocus import (
    ThinLens,DefocusError,circular_psf,analyze_defocus,run_defocus_manifest)
from aiforensics.defocus_synthetic import synthetic_defocus_fixture,render_defocus_comparison


@pytest.fixture
def lens(): return ThinLens(50.,2.8,4.,2000.)


def test_thin_lens_equation(lens):
    v=lens.image_distance_mm(2000.)
    assert (1/lens.focal_mm) == pytest.approx(1/2000.+1/v)
    assert lens.sensor_distance_mm==pytest.approx(v)


def test_aperture_diameter(lens):
    assert lens.aperture_diameter_mm==pytest.approx(50/2.8)


def test_focus_zero_coc(lens):
    assert lens.coc_px(2000.)==pytest.approx(0.)


def test_coc_depth_closed_form(lens):
    z=4000
    c=lens.focal_mm**2*abs(z-lens.focus_distance_mm)/(
        lens.f_number*z*(lens.focus_distance_mm-lens.focal_mm))
    assert lens.coc_mm(z)==pytest.approx(c)
    assert lens.coc_px(z)==pytest.approx(c/0.004)


def test_near_and_far_blur_asymmetry(lens):
    assert lens.coc_px(1000)>lens.coc_px(3000)


def test_infinity_object_limit(lens):
    truth=lens.focal_mm**2/(lens.f_number*(lens.focus_distance_mm-lens.focal_mm))
    assert lens.coc_mm(float('inf'))==pytest.approx(truth)


def test_infinity_focus_limit():
    x=ThinLens(35.,4.,4.,float('inf'))
    assert x.sensor_distance_mm==pytest.approx(35.)
    assert x.coc_mm(1000.)==pytest.approx(35**2/(4*1000))
    assert x.coc_mm(float('inf'))==0


def test_inverse_dof_boundaries(lens):
    near,far=lens.dof_limits_mm(2.)
    assert near<lens.focus_distance_mm<far
    assert lens.coc_px(near)==pytest.approx(2,rel=1e-11)
    assert lens.coc_px(far)==pytest.approx(2,rel=1e-11)


def test_hyperfocal_far_inf():
    x=ThinLens(35.,11.,4.,3000.)
    hyper=x.hyperfocal_mm(2.)
    y=ThinLens(35.,11.,4.,hyper)
    assert y.dof_limits_mm(2.)[1]==float('inf')
    assert y.coc_px(float('inf'))==pytest.approx(2.)


def test_infinity_focus_near_exact():
    x=ThinLens(50,8,4,float('inf'))
    near,far=x.dof_limits_mm(2.)
    assert x.coc_px(near)==pytest.approx(2.)
    assert math.isinf(far)


@pytest.mark.parametrize('params',[(0,2,4,1000),(-20,2,4,1000),(30,0,4,1000),
  (30,2,0,1000),(30,2,4,29),(30,2,4,30),(30,2,4,0),(30,2,4,float('nan'))])
def test_invalid_lens_parameters(params):
    with pytest.raises(DefocusError):ThinLens(*params)


@pytest.mark.parametrize('z',[0,-1,50,float('nan')])
def test_reject_nonphysical_depth(lens,z):
    with pytest.raises(DefocusError):lens.coc_px(z)


def test_pixel_pitch_scaling():
    a=ThinLens(50,4,2,2500).coc_px(1900)
    b=ThinLens(50,4,4,2500).coc_px(1900)
    assert a==pytest.approx(2*b)


def test_aperture_blur_scaling():
    a=ThinLens(50,2,4,2500).coc_px(3500)
    b=ThinLens(50,8,4,2500).coc_px(3500)
    assert a==pytest.approx(4*b)


def test_psf_energy_conserved_and_symmetric():
    p=circular_psf(13.5)
    assert p.sum()==pytest.approx(1.,abs=1e-12)
    assert np.allclose(p,p[::-1,:]); assert np.allclose(p,p[:,::-1])
    assert np.min(p)>=0


def test_psf_delta():
    assert circular_psf(0.).shape==(1,1)
    assert circular_psf(.15)[0,0]==1


def test_psf_refuse_truncation():
    with pytest.raises(DefocusError):circular_psf(500.)


def test_psf_invalid():
    for x in (float('nan'),-1):
        with pytest.raises(DefocusError):circular_psf(x)


def test_psf_constant_image_invariance():
    ker=circular_psf(7.3).astype(np.float32)
    im=np.full((60,60),.7,np.float32)
    assert np.max(np.abs(cv2.filter2D(im,-1,ker)-.7))<1e-5


def test_ground_truth_demo_flags_corruption():
    data,truth=synthetic_defocus_fixture()
    out=analyze_defocus(data)
    assert out['counts']=={'consistent':29,'inconsistent':3,'indeterminate':0}
    assert len(truth['corrupted_ids'])==3
    assert out['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    for row in out['results']:
        if row['id'] in truth['corrupted_ids']:
            assert row['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_clean_measured_group():
    data,_=synthetic_defocus_fixture(corrupt=0)
    report=analyze_defocus(data)
    assert report['counts']['inconsistent']==0
    assert report['state']=='CONSISTENT'


def test_conditional_uncertainty_broadens_interval():
    data,_=synthetic_defocus_fixture(corrupt=0)
    data['samples'][0]['depth_sigma_mm']=25.
    data['optics']['focus_sigma_mm']=30.
    result=analyze_defocus(data,mc_samples=2500)
    x=result['results'][0]
    assert x['predicted_coc_95pct_conditional_px'][1]>x['predicted_coc_95pct_conditional_px'][0]
    assert x['prediction_sigma_px']>0


def test_mc_deterministic():
    data,_=synthetic_defocus_fixture(corrupt=0)
    data['samples'][0]['depth_sigma_mm']=10
    assert analyze_defocus(data,seed=777)['results']==analyze_defocus(data,seed=777)['results']


def test_measurement_without_calibration_abstains():
    data,_=synthetic_defocus_fixture(corrupt=0)
    data['samples'][0].pop('measurement_provenance')
    r=analyze_defocus(data)
    assert r['results'][0]['state']=='INDETERMINATE'
    assert r['counts']['indeterminate']==1


def test_unobserved_point_is_predictive_only():
    data,_=synthetic_defocus_fixture(corrupt=0)
    data['samples'][0].pop('observed_coc_px')
    r=analyze_defocus(data)
    assert r['results'][0]['state']=='INDETERMINATE'


def test_fit_focus_disjoint_holdout():
    data,_=synthetic_defocus_fixture(fit_focus=True,corrupt=0)
    r=analyze_defocus(data)
    assert r['focus_estimated_from_train']
    assert abs(r['lens']['focus_distance_mm']-2500)<20
    assert r['counts']['indeterminate']==16
    assert r['counts']['inconsistent']==0
    assert r['focus_fit']['fit_train_count']==16


def test_fit_focus_does_not_use_holdout_leakage():
    data,_=synthetic_defocus_fixture(fit_focus=True,corrupt=0)
    a=analyze_defocus(data)['lens']['focus_distance_mm']
    for row in data['samples']:
        if row['role']=='holdout':row['observed_coc_px']+=100
    b=analyze_defocus(data)['lens']['focus_distance_mm']
    assert a==b


def test_fit_refuses_weak_depth_diversity():
    data,_=synthetic_defocus_fixture(fit_focus=True)
    for row in data['samples']:
        if row['role']=='train':row['depth_mm']=2400
    with pytest.raises(DefocusError):analyze_defocus(data)


def test_fit_refuses_missing_holdout():
    data,_=synthetic_defocus_fixture(fit_focus=True)
    data['samples']=[r for r in data['samples'] if r['role']=='train']
    with pytest.raises(DefocusError):analyze_defocus(data)


def test_reject_duplicate_ids():
    data,_=synthetic_defocus_fixture()
    data['samples'][1]['id']=data['samples'][0]['id']
    with pytest.raises(DefocusError):analyze_defocus(data)


def test_reject_uncertain_observation_missing_sigma():
    data,_=synthetic_defocus_fixture()
    data['samples'][0].pop('observed_sigma_px')
    with pytest.raises(DefocusError):analyze_defocus(data)


def test_reject_nonfinite_measurement():
    data,_=synthetic_defocus_fixture()
    data['samples'][0]['observed_coc_px']=float('nan')
    with pytest.raises(DefocusError):analyze_defocus(data)


def test_invalid_mc_budget():
    data,_=synthetic_defocus_fixture()
    with pytest.raises(DefocusError):analyze_defocus(data,mc_samples=10)


def test_report_does_not_invent_ai_origin():
    data,_=synthetic_defocus_fixture()
    r=analyze_defocus(data)
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert 'NO_AI_ORIGIN_CONCLUSION' in json.dumps(r)


def test_runner_writes_valid_json(tmp_path):
    data,_=synthetic_defocus_fixture()
    source=tmp_path/'data.json'
    source.write_text(json.dumps(data),encoding='utf-8')
    r=run_defocus_manifest(source,tmp_path/'results')
    loaded=json.loads((tmp_path/'results'/'p4_o02_report.json').read_text())
    assert loaded['counts']==r['counts']
    assert len(loaded['manifest_sha256'])==64


def test_demo_image_dimensions():
    img=render_defocus_comparison()
    assert img.shape==(375,1200,3)
    assert np.any(img[75:]!=0)


def test_cli_demo(tmp_path):
    from aiforensics.cli import main
    main(['demo-defocus','--out',str(tmp_path)])
    assert (tmp_path/'p4_o02_report.json').exists()
    assert (tmp_path/'p4_o02_depth_comparison.png').exists()


def test_cli_analyze(tmp_path):
    from aiforensics.cli import main
    fixture,_=synthetic_defocus_fixture()
    source=tmp_path/'input.json'
    source.write_text(json.dumps(fixture),encoding='utf-8')
    main(['analyze-defocus','--input',str(source),'--out',str(tmp_path/'report')])
    assert (tmp_path/'report'/'p4_o02_report.json').exists()
