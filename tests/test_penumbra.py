"""P2-S05 forward physics, inverse fit, ambiguity and fail-closed regression."""
import json
from copy import deepcopy
import numpy as np
import pytest
from aiforensics.penumbra import (
    PenumbraError, PenumbraConfig, source_visibility, edge_irradiance,
    angular_diameter_from_width, penumbra_width_from_angle,
    fit_edge_profile, analyze_penumbra_manifest, coaxial_circular_shadow_regions,
    run_penumbra_manifest)
from aiforensics.penumbra_synthetic import synthetic_penumbra_fixture


def test_disk_cdf_boundary_and_symmetry():
    x=np.linspace(-2,2,501)
    cdf=source_visibility(x)
    assert np.all(np.diff(cdf)>=-1e-12)
    assert np.allclose(cdf+source_visibility(-x),1,atol=1e-12)
    assert np.allclose(source_visibility([-2,-1,0,1,2]),[0,0,.5,1,1])
    assert abs(float(source_visibility(.5)) -(.5+(np.arcsin(.5)+.5*np.sqrt(.75))/np.pi))<1e-12


def test_strip_cdf_is_linear():
    assert np.allclose(source_visibility([-5,-1,-.5,0,.5,1,5],'UNIFORM_STRIP'),[0,0,.25,.5,.75,1,1])


def test_shape_rejection():
    with pytest.raises(PenumbraError):source_visibility([0], 'UNSUPPORTED')
    with pytest.raises(PenumbraError):edge_irradiance([1,2],0,-1,0,1)


def test_inverse_angular_conversion():
    for h in [.6,1.4,3.2]:
        for a in [.3,1.2,3.]:
            w=penumbra_width_from_angle(a,120.,h)
            assert abs(angular_diameter_from_width(w,120.,h)-a)<1e-10


def test_angular_bad_contract():
    for vals in [(0,100,1),(2,0,1),(2,100,-1)]:
        with pytest.raises(PenumbraError):angular_diameter_from_width(*vals)
    with pytest.raises(PenumbraError):penumbra_width_from_angle(179,100,1)


def test_coaxial_regions_and_source_size_geometry():
    result=coaxial_circular_shadow_regions(.05,.5,5.,1.)
    assert abs(result['outer_partial_shadow_radius_m']-.61)<1e-10
    assert abs(result['full_umbra_radius_m']-.59)<1e-10
    assert abs(result['penumbra_band_width_m']-.02)<1e-10
    assert result['axial_full_umbra_exists']
    assert abs(2*1*np.tan(np.deg2rad(result['source_angular_diameter_from_blocker_deg']/2))-.02)<1e-12


def test_coaxial_umbra_disappears():
    result=coaxial_circular_shadow_regions(.7,.1,.5,2.)
    assert not result['axial_full_umbra_exists']
    assert result['antumbra_possible']
    assert result['full_umbra_radius_m']==0
    assert result['penumbra_band_width_m'] is None


def test_coaxial_invalid():
    with pytest.raises(PenumbraError):coaxial_circular_shadow_regions(.1,.2,0,1)


def test_noise_free_disk_fit():
    m,t=synthetic_penumbra_fixture(noise_sigma=0.)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert len(r['evidence'])==4
    assert abs(r['angular_diameter_median_deg']-1.2)<.01
    assert all(p['fit_r2']>.999999 for p in r['evidence'])


def test_noisy_left_and_right_edges():
    m,t=synthetic_penumbra_fixture(seed=77,noise_sigma=.009)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='CONSISTENT_UNDER_ASSUMPTIONS',r
    assert abs(r['angular_diameter_median_deg']-1.2)<.06
    assert {p['edge_orientation_lit_side'] for p in r['evidence']}=={'left','right'}


def test_uniform_strip_profiles():
    m,_=synthetic_penumbra_fixture(shapes=('UNIFORM_STRIP',),noise_sigma=.003)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='CONSISTENT_UNDER_ASSUMPTIONS',r
    assert abs(r['angular_diameter_median_deg']-1.2)<.06


def test_mixed_disk_strip_without_shape_confusion():
    m,_=synthetic_penumbra_fixture(shapes=('UNIFORM_DISK','UNIFORM_STRIP'),noise_sigma=.004)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='CONSISTENT_UNDER_ASSUMPTIONS',r


def test_different_source_angles_flag_disagreement_not_ai():
    m,_=synthetic_penumbra_fixture(malformed_source=2,noise_sigma=.003)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_no_declared_same_source_abstains():
    m,_=synthetic_penumbra_fixture()
    del m['declared_common_source']
    r=analyze_penumbra_manifest(m)
    assert r['state']=='INDETERMINATE'


def test_one_edge_abstains_even_perfect_fit():
    m,_=synthetic_penumbra_fixture(noise_sigma=0.)
    m['edges']=m['edges'][:1]
    r=analyze_penumbra_manifest(m)
    assert r['state']=='INDETERMINATE'
    assert r['profiles_measured']==1


def test_missing_geometry_keeps_profile_but_no_angle():
    m,_=synthetic_penumbra_fixture(include_geometry=False)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='INDETERMINATE'
    assert all(p['state']=='MEASURED' and p['angular_diameter_deg'] is None for p in r['evidence'])


def test_unverified_geometry_is_not_a_physical_measurement():
    m,_=synthetic_penumbra_fixture()
    m['edges'][0]['metric_geometry']['verified']=False
    r=analyze_penumbra_manifest(m)
    assert r['evidence'][0]['angular_diameter_deg'] is None
    assert r['angular_edges_measured']==3


def test_optical_blur_makes_angle_unidentifiable():
    m,_=synthetic_penumbra_fixture(psf_sigma_px=5)
    r=analyze_penumbra_manifest(m)
    assert r['state']=='INDETERMINATE'
    assert all(p['angular_reason']=='OPTICAL_PSF_NOT_RESOLVED' for p in r['evidence'])


def test_flat_profile_abstains():
    m,_=synthetic_penumbra_fixture()
    m['edges'][0]['linear_irradiance']=[.5]*len(m['edges'][0]['x_px'])
    r=analyze_penumbra_manifest(m)
    assert r['evidence'][0]['state']=='INDETERMINATE'
    assert r['evidence'][0]['reason']=='INSUFFICIENT_IRRADIANCE_CONTRAST'


def test_undersampled_edge_abstains():
    m,_=synthetic_penumbra_fixture(heights=(.2,1.8,2.6,3.2),noise_sigma=0.)
    r=analyze_penumbra_manifest(m)
    assert r['evidence'][0]['state']=='INDETERMINATE'


def test_wrong_irradiance_space_rejected():
    m,_=synthetic_penumbra_fixture()
    m['edges'][0]['radiometric_space']='SRGB'
    with pytest.raises(PenumbraError):analyze_penumbra_manifest(m)


def test_duplicate_x_and_nonfinite_rejected():
    m,_=synthetic_penumbra_fixture()
    m['edges'][0]['x_px'][4]=m['edges'][0]['x_px'][3]
    with pytest.raises(PenumbraError):analyze_penumbra_manifest(m)
    m,_=synthetic_penumbra_fixture()
    m['edges'][0]['linear_irradiance'][2]=float('nan')
    with pytest.raises(PenumbraError):analyze_penumbra_manifest(m)


def test_bad_geometry_rejected():
    m,_=synthetic_penumbra_fixture()
    m['edges'][0]['metric_geometry']['occluder_receiver_separation_m']=-2
    with pytest.raises(PenumbraError):analyze_penumbra_manifest(m)


def test_duplicate_ids_rejected():
    m,_=synthetic_penumbra_fixture()
    m['edges'][1]['id']=m['edges'][0]['id']
    with pytest.raises(PenumbraError):analyze_penumbra_manifest(m)


def test_parametric_mc_repeats_and_explicitly_conditional():
    m,_=synthetic_penumbra_fixture(heights=(2.4,),noise_sigma=.008)
    p=fit_edge_profile(m['edges'][0],PenumbraConfig(bootstrap_samples=24,seed=12))
    assert p['state']=='MEASURED'
    assert len(p['conditional_parametric_mc_90pct_interval_deg'])==2
    assert 'NOT calibrated' in p['uncertainty_warning']
    p2=fit_edge_profile(m['edges'][0],PenumbraConfig(bootstrap_samples=24,seed=12))
    assert p==p2


def test_repeatable_analysis():
    m,_=synthetic_penumbra_fixture(seed=27)
    assert analyze_penumbra_manifest(m)==analyze_penumbra_manifest(m)


def test_manifest_cli_and_overlay(tmp_path):
    m,_=synthetic_penumbra_fixture(seed=15)
    inp=tmp_path/'profile.json';inp.write_text(json.dumps(m))
    report=run_penumbra_manifest(inp,tmp_path/'results')
    assert report['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert len(report['manifest_sha256'])==64
    assert (tmp_path/'results/p2_s05_report.json').exists()
    assert (tmp_path/'results/p2_s05_profiles.png').exists()


def test_bad_config_rejected():
    for config in [dict(min_samples=10),dict(min_contrast=0),dict(bootstrap_samples=300),
                   dict(min_edges_for_consistency=1),dict(max_relative_angular_spread=0)]:
        with pytest.raises(PenumbraError):PenumbraConfig(**config)
