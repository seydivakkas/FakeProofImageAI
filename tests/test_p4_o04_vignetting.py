"""P4-O04 controlled test suite. Nothing here constitutes field validation."""
from copy import deepcopy
import json
import numpy as np
import pytest
from aiforensics.vignetting import (
    VignettingError, VignettingConfig,camera_K,normalized_coordinates,cos4_gain,
    relative_illumination,predict_irradiance,analyze_vignetting_manifest,
    run_vignetting_manifest,sample_linear_regions,correct_linear_field)
from aiforensics.vignetting_synthetic import synthetic_vignetting_fixture,render_vignetting_demo

K=[[900.,0,350.],[0,900.,250.],[0,0,1.]]

def test_cos4_at_axis_and_offaxis():
    assert cos4_gain([350.,250.],K)==pytest.approx(1.)
    x=350+900
    assert cos4_gain([x,250.],K)==pytest.approx(.25)
    assert relative_illumination([x,250.],K)==pytest.approx(.25)

def test_cos4_unequal_pitch_skew_and_principal_point():
    k=[[1000.,10.,423.],[0.,800.,201.],[0,0,1.]]
    pts=np.array([[423.,201.],[433.,1001.]])
    xy=normalized_coordinates(pts,k)
    assert np.allclose(xy[0],[0,0])
    assert np.allclose(xy[1],[0,1])
    assert np.allclose(cos4_gain(pts,k),[1.,.25])

def test_full_gain_center_normalization():
    assert relative_illumination([350.,250.],K,-1.,-.2,(.04,-.05))==pytest.approx(1.)

def test_relative_illumination_positive():
    arr=relative_illumination([[100,100],[450,550]],K,-.4,-.2)
    assert np.all((arr>0)&np.isfinite(arr))

def test_known_parameter_prediction():
    p=predict_irradiance(np.array([[350.,250.],[1250.,250.]]),K,1.,np.log(.8))
    assert p[0]==pytest.approx(.8)
    assert p[1]==pytest.approx(.2)

@pytest.mark.parametrize('input_k', [np.eye(2),np.zeros((3,3)),[[0,0,1],[0,100,1],[0,0,1]],
                                    [[10,0,0],[0,10,0],[1,0,1]]])
def test_bad_intrinsics(input_k):
    with pytest.raises(VignettingError):camera_K(input_k)

def test_nonfinite_coords():
    with pytest.raises(VignettingError):cos4_gain([np.nan,5],K)

def test_invalid_exponential():
    with pytest.raises(VignettingError):relative_illumination([100000.,200000.],K,10,12)

@pytest.mark.parametrize('mode', ['fit_radial','fit_radial_and_center'])
def test_recover_coefficients_and_corrupt_holdouts(mode):
    data,truth=synthetic_vignetting_fixture(seed=246,mode=mode,corrupt=3)
    report=analyze_vignetting_manifest(data)
    assert report['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    detected={r['id'] for r in report['holdout_results'] if r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'}
    assert detected==set(truth['corrupted_ids'])
    params=report['parameters']
    assert params['radial_log_a2']==pytest.approx(truth['a2'],abs=.09)
    assert params['radial_log_a4']==pytest.approx(truth['a4'],abs=.14)
    if mode=='fit_radial_and_center':
        assert params['radial_center_offset_normalized_xy']==pytest.approx(truth['center_xy'],abs=.027)
    assert report['decision']=='NO_AI_ORIGIN_CONCLUSION'

def test_healthy_holdouts_consistent():
    d,_=synthetic_vignetting_fixture(seed=123,corrupt=0)
    r=analyze_vignetting_manifest(d)
    assert r['state']=='CONSISTENT' and r['inconsistent_count']==0

def test_cos4_only_fails_when_radial_falloff_exists():
    d,_=synthetic_vignetting_fixture(corrupt=0)
    d['calibration_mode']='cos4_only'
    result=analyze_vignetting_manifest(d)
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'

def test_missing_flatfield_provenance_indeterminate():
    d,_=synthetic_vignetting_fixture()
    d['photometric_provenance']='jpeg_with_unknown_tone_curve'
    r=analyze_vignetting_manifest(d)
    assert r['state']=='INDETERMINATE'

def test_unregistered_brown_conrady_pixel_domain_indeterminate():
    d,_=synthetic_vignetting_fixture()
    d['pixel_coordinate_domain']='distorted_image_pixels'
    assert analyze_vignetting_manifest(d)['state']=='INDETERMINATE'

def test_unverified_measurement_provenance_indeterminate():
    d,_=synthetic_vignetting_fixture()
    d['samples'][0]['measurement_provenance']='unknown'
    assert analyze_vignetting_manifest(d)['state']=='INDETERMINATE'

def test_train_and_holdout_ids_cannot_overlap():
    d,_=synthetic_vignetting_fixture()
    d['samples'][1]['id']=d['samples'][0]['id']
    with pytest.raises(VignettingError,match='unique'):analyze_vignetting_manifest(d)

def test_insufficient_holdout_indeterminate():
    d,_=synthetic_vignetting_fixture()
    d['samples']=[r for r in d['samples'] if r['role']=='train']
    assert analyze_vignetting_manifest(d)['state']=='INDETERMINATE'

def test_degenerate_train_radii_indeterminate():
    d,_=synthetic_vignetting_fixture()
    for r in d['samples']:
        if r['role']=='train':r['xy_px']=[620.,390.]
    r=analyze_vignetting_manifest(d)
    assert r['state']=='INDETERMINATE'

def test_out_of_bounds_pixel_rejected():
    d,_=synthetic_vignetting_fixture()
    d['samples'][0]['xy_px']=[9999,9999]
    with pytest.raises(VignettingError):analyze_vignetting_manifest(d)

def test_saturation_rejected():
    d,_=synthetic_vignetting_fixture()
    d['samples'][0]['observed_linear']=1.
    with pytest.raises(VignettingError):analyze_vignetting_manifest(d)

def test_negative_sigma_rejected():
    d,_=synthetic_vignetting_fixture()
    d['samples'][0]['sigma_linear']=-.1
    with pytest.raises(VignettingError):analyze_vignetting_manifest(d)

def test_unsafe_gain_is_indeterminate():
    d,_=synthetic_vignetting_fixture(corrupt=0)
    r=analyze_vignetting_manifest(d,VignettingConfig(max_inverse_gain=1.1))
    assert r['state']=='INDETERMINATE'

def test_correction_divides_only_relative_gain():
    k=[[80.,0.,30.],[0.,80.,20.],[0,0,1.]]
    yy,xx=np.indices((40,60),float)
    g=relative_illumination(np.stack((xx,yy),axis=-1),k,-.2,-.1)
    linear=.72*g
    restored=correct_linear_field(linear,k,-.2,-.1)
    assert np.max(abs(restored-.72))<1e-10

def test_correction_refuses_excessive_gain():
    k=[[10.,0.,30.],[0.,10.,20.],[0,0,1.]]
    with pytest.raises(VignettingError):correct_linear_field(np.ones((40,60))*.4,k,0,0)

def test_run_manifest_and_image(tmp_path):
    d,_=synthetic_vignetting_fixture(corrupt=0)
    fixture=tmp_path/'fixture.json';fixture.write_text(json.dumps(d))
    r=run_vignetting_manifest(fixture,tmp_path/'results')
    assert (tmp_path/'results'/'p4_o04_report.json').exists()
    im=render_vignetting_demo(d,r)
    assert im.shape==(800,2560,3)

def test_roi_sampler_nonoverlap(tmp_path):
    im=np.full((80,100),.67,dtype=np.float32)
    fname=tmp_path/'irradiance.npy';np.save(fname,im)
    template={'K':K,'pixel_coordinate_domain':'undistorted_pinhole','photometric_provenance':'SYNTHETIC_LINEAR_DARK_CORRECTED_FLAT_FIELD',
              'regions':[{'id':'a','role':'train','xywh':[1,1,9,9], 'reference_linear':1.,'sigma_linear':.02,'measurement_provenance':'synthetic_known_flat_field'},
                         {'id':'b','role':'holdout','xywh':[20,20,10,10], 'reference_linear':1.,'sigma_linear':.02,'measurement_provenance':'synthetic_known_flat_field'}]}
    jp=tmp_path/'roi.json';jp.write_text(json.dumps(template))
    out=sample_linear_regions(fname,jp,tmp_path/'out.json')
    assert out['samples'][0]['observed_linear']==pytest.approx(.67,abs=1e-6)
    assert out['samples'][0]['xy_px']==[5.,5.]
    assert out['image_size_wh']==[100,80]
    template['regions'][1]['xywh']=[2,2,10,10];jp.write_text(json.dumps(template))
    with pytest.raises(VignettingError,match='overlapping'):sample_linear_regions(fname,jp,tmp_path/'bad.json')

def test_roi_saturated_input_rejected(tmp_path):
    image=np.full((50,50),1.,np.float32)
    np.save(tmp_path/'img.npy',image)
    roi={'regions':[{'xywh':[0,0,10,10],'id':'s','role':'train','reference_linear':1.,'sigma_linear':.1,'measurement_provenance':'synthetic_known_flat_field'}]}
    (tmp_path/'regions.json').write_text(json.dumps(roi))
    with pytest.raises(VignettingError):sample_linear_regions(tmp_path/'img.npy',tmp_path/'regions.json',tmp_path/'out.json')

def test_deterministic_same_fixture():
    a,_=synthetic_vignetting_fixture(seed=321)
    b,_=synthetic_vignetting_fixture(seed=321)
    assert json.dumps(a)==json.dumps(b)
    assert analyze_vignetting_manifest(a)['parameters']==analyze_vignetting_manifest(b)['parameters']

def test_bad_fit_center_training_insufficient():
    d,_=synthetic_vignetting_fixture(mode='fit_radial_and_center')
    d['samples']=[r for r in d['samples'] if r['role']=='holdout']+ [r for r in d['samples'] if r['role']=='train'][:45]
    r=analyze_vignetting_manifest(d)
    assert r['state']=='INDETERMINATE'

def test_excessively_large_gain_refusal_persisted():
    assert VignettingConfig().max_inverse_gain==8.

def test_benchmark_seed_reproducibility():
    from scripts.p4_vignetting_benchmark import run
    a=run(4);b=run(4)
    assert a==b
    assert a['exact_corruption_detection_trials']==4


def test_vignetting_cli_demo_analysis(tmp_path):
    from aiforensics.cli import main
    a=tmp_path/'demo'
    main(['demo-vignetting','--out',str(a)])
    assert (a/'p4_o04_fixture.json').exists()
    assert (a/'p4_o04_flatfield_comparison.png').exists()
    assert (a/'p4_o04_radial_profile.png').exists()
    main(['analyze-vignetting','--input',str(a/'p4_o04_fixture.json'),'--out',str(tmp_path/'analysis')])
    r=json.loads((tmp_path/'analysis'/'p4_o04_report.json').read_text())
    assert r['inconsistent_count']==3
