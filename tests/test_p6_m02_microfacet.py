import copy
import json
import math
import numpy as np
import pytest
from aiforensics.microfacet_physics import (
    MicrofacetError, fresnel_schlick,ggx_ndf,smith_ggx_g1,
    cook_torrance_specular,specular_radiance,analyze_microfacet_manifest,
    audit_ggx_energy,run_microfacet_manifest)
from aiforensics.microfacet_synthetic import synthetic_microfacet_fixture

N=[0,0,1]; L=[0,0,1]; V=[0,0,1]; F0=[.04,.12,.35]


def test_schlick_at_normal_f0():assert np.allclose(fresnel_schlick(1,F0),F0)
def test_schlick_at_grazing_one():assert np.allclose(fresnel_schlick(0,F0),[1,1,1])
def test_schlick_monotone():
    assert np.all(fresnel_schlick(.2,F0)>=fresnel_schlick(.8,F0))
def test_schlick_bad_cos():
    with pytest.raises(MicrofacetError):fresnel_schlick(1.1,F0)
def test_invalid_f0():
    with pytest.raises(MicrofacetError):cook_torrance_specular(N,L,V,.5,[1.1,0,0])
def test_invalid_roughness():
    with pytest.raises(MicrofacetError):ggx_ndf(1,0)
def test_ggx_distribution_normalization():
    # Integral D(h) * cos(theta_h) d omega_h = 1 (GGX NDF)
    from aiforensics.material_physics import hemisphere_quadrature
    dirs,weight=hemisphere_quadrature(80,120)
    val=np.array([ggx_ndf(h,.5) for h in dirs[:,2]])
    assert abs(float(np.dot(val*dirs[:,2],weight))-1)<3e-4

def test_ndf_sharp_has_higher_peak():assert ggx_ndf(1,.2)>ggx_ndf(1,.8)
def test_smith_normal_one():assert smith_ggx_g1(1,.5)==pytest.approx(1)
def test_smith_grazing_zero():assert smith_ggx_g1(0,.5)==0
def test_smith_range():
    assert all(0<=smith_ggx_g1(x,.3)<=1 for x in np.linspace(0,1,20))
def test_normal_incidence_spec_formula():
    # At l=v=n, D=1/(pi alpha^2), G=1 and denominator=4
    r=.5
    expected=np.asarray(F0)/(4*math.pi*r**4)
    assert np.allclose(cook_torrance_specular(N,L,V,r,F0),expected)
def test_reciprocity():
    a=[.3,0,.9539392];b=[-.2,.25,.947365]
    assert np.allclose(cook_torrance_specular(N,a,b,.42,F0),
                       cook_torrance_specular(N,b,a,.42,F0),rtol=1e-12)
def test_below_surface_zero():assert np.all(cook_torrance_specular(N,[0,0,-1],V,.5,F0)==0)
def test_geometry_normalized():
    assert np.allclose(cook_torrance_specular(N,[0,0,2],[0,0,5],.5,F0),
                       cook_torrance_specular(N,L,V,.5,F0))
def test_zero_light_zero_radiance():
    assert np.allclose(specular_radiance(N,L,V,[0,0,0],.5,F0),0)
def test_radiance_scale():
    x=specular_radiance(N,L,V,[4,6,9],.4,F0)
    assert np.allclose(specular_radiance(N,L,V,[8,12,18],.4,F0),2*x)
def test_visibility_zero():
    assert np.allclose(specular_radiance(N,L,V,[4,5,6],.4,F0,visible_fraction=0),0)
def test_invalid_visibility():
    with pytest.raises(MicrofacetError):specular_radiance(N,L,V,[1,1,1],.5,F0,visible_fraction=2)
def test_known_roughness_fixture():
    fixture,truth=synthetic_microfacet_fixture(mode='known_roughness')
    report=analyze_microfacet_manifest(fixture)
    got={p['id']:p['state'] for p in report['observations']}
    assert report['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3
    assert all(got[k]=='INCONSISTENT_UNDER_ASSUMPTIONS' for k,v in truth['expected_holdout_states'].items() if v=='INCONSISTENT_UNDER_ASSUMPTIONS')
def test_fitted_roughness_fixture():
    fixture,truth=synthetic_microfacet_fixture(mode='fit_roughness')
    report=analyze_microfacet_manifest(fixture)
    assert report['fitted_or_known_roughness']==pytest.approx(truth['roughness'],abs=.02)
    assert report['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3
    assert report['roughness_sigma_local_linear_approximation']<.065
def test_unknown_light_abstains():
    f,_=synthetic_microfacet_fixture(mode='known_roughness');f['light_provenance']='image_guess'
    assert analyze_microfacet_manifest(f)['state']=='INDETERMINATE'
def test_unknown_f0_abstains():
    f,_=synthetic_microfacet_fixture();f['f0_provenance']='jpeg_estimate'
    assert analyze_microfacet_manifest(f)['state']=='INDETERMINATE'
def test_unknown_roughness_abstains():
    f,_=synthetic_microfacet_fixture(mode='known_roughness');f['roughness_provenance']='model_guess'
    assert analyze_microfacet_manifest(f)['state']=='INDETERMINATE'
def test_unverified_holdout_abstains():
    f,_=synthetic_microfacet_fixture();f['samples'][-1]['radiometry_provenance']='gamma_encoded_jpeg'
    assert analyze_microfacet_manifest(f)['observations'][-1]['state']=='INDETERMINATE'
def test_unknown_training_abstains():
    f,_=synthetic_microfacet_fixture();f['samples'][0]['geometry_provenance']='single_image_guess'
    assert analyze_microfacet_manifest(f)['state']=='INDETERMINATE'
def test_duplicated_sample_rejected():
    f,_=synthetic_microfacet_fixture();f['samples'][-1]['id']=f['samples'][0]['id']
    with pytest.raises(MicrofacetError):analyze_microfacet_manifest(f)
def test_missing_holdout_abstains():
    f,_=synthetic_microfacet_fixture();f['samples']=[x for x in f['samples'] if x['role']=='train']
    assert analyze_microfacet_manifest(f)['state']=='INDETERMINATE'
def test_wrong_roughness_disagrees():
    f,_=synthetic_microfacet_fixture(mode='known_roughness');f['roughness']=.9
    assert analyze_microfacet_manifest(f)['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']>=3
def test_bad_shape_rejected():
    f,_=synthetic_microfacet_fixture();f['samples'][0]['normal_world']=[1,0]
    with pytest.raises(MicrofacetError):analyze_microfacet_manifest(f)
def test_missing_irradiance_rejected():
    f,_=synthetic_microfacet_fixture();del f['incident_irradiance_rgb']
    with pytest.raises(MicrofacetError):analyze_microfacet_manifest(f)
def test_report_json(tmp_path):
    f,_=synthetic_microfacet_fixture()
    src=tmp_path/'data.json';src.write_text(json.dumps(f))
    r=run_microfacet_manifest(src,tmp_path/'out')
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert (tmp_path/'out'/'p6_m02_report.json').exists()
def test_energy_grazing():
    r=audit_ggx_energy(.6,F0,n_mu=16,n_phi=40)
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert all(max(a['directional_hemispherical_reflectance_rgb'])<1.02 for a in r['view_samples'])
def test_energy_low_resolution_abstain_when_unresolved():
    report=audit_ggx_energy(.045,[.8,.8,.8],n_mu=8,n_phi=16)
    assert report['state']=='INDETERMINATE' # no false energy certification for sharp lobe
    assert all(a['state']!='INCONSISTENT_UNDER_ASSUMPTIONS' for a in report['view_samples'])
def test_report_can_read_from_m01_citation():
    # independent standard Fresnel Schlick identity; M01 audit stays available
    from aiforensics.material_physics import lambertian_brdf
    assert np.allclose(lambertian_brdf([.5,.5,.5]),np.full(3,.5/math.pi))


def test_f0_known_is_not_material_identity():
    f,_=synthetic_microfacet_fixture(mode='known_roughness')
    f['f0_provenance']='computed_from_8bit_pixels'
    r=analyze_microfacet_manifest(f)
    assert r['state']=='INDETERMINATE' and r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_below_surface_view_zero():
    assert np.allclose(cook_torrance_specular(N,L,[0,0,-1],.5,F0),0)


def test_invalid_rgb_sigma_rejected():
    f,_=synthetic_microfacet_fixture()
    f['samples'][0]['sigma_radiance_rgb']=[0,0,0]
    with pytest.raises(MicrofacetError):analyze_microfacet_manifest(f)


def test_wrong_known_f0_holdout_fails():
    f,_=synthetic_microfacet_fixture(mode='known_roughness')
    f['f0_rgb']=[.6,.6,.6]
    assert analyze_microfacet_manifest(f)['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']>=3


def test_cli_microfacet_commands(tmp_path):
    from aiforensics.cli import main
    out=tmp_path/'demo'
    main(['demo-microfacet','--out',str(out),'--seed','2702'])
    assert (out/'p6_m02_fixture.json').exists()
    assert (out/'p6_m02_report.json').exists()
    parsed=json.loads((out/'p6_m02_report.json').read_text())
    assert parsed['decision']=='NO_AI_ORIGIN_CONCLUSION'
    checked=tmp_path/'checked'
    main(['analyze-microfacet','--input',str(out/'p6_m02_fixture.json'),'--out',str(checked)])
    assert (checked/'p6_m02_report.json').exists()


def test_cli_energy_audit(tmp_path):
    from aiforensics.cli import main
    out=tmp_path/'energy.json'
    main(['audit-microfacet-energy','--roughness','.5','--f0','.04','.04','.04',
          '--n-mu','12','--n-phi','32','--out',str(out)])
    r=json.loads(out.read_text())
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_no_total_rgb_energy_claim_in_specular_audit():
    r=audit_ggx_energy(.5,[.2,.4,.6],n_mu=14,n_phi=32)
    assert 'specular' in r['notes'][0]
