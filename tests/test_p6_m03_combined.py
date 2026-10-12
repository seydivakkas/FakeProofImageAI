"""P6-M03 physics, input provenance, identifiability and disjoint-surface regression."""
from __future__ import annotations
import copy,json,math
import numpy as np
import pytest
from aiforensics.combined_material import (CombinedMaterialError,combined_brdf,
    combined_radiance,analyze_combined_manifest,run_combined_manifest,audit_combined_energy)
from aiforensics.combined_material_synthetic import synthetic_combined_fixture

N=[0,0,1];L=[.3,0,.9539392];V=[-.2,.3,.9327379]
RHO=[.5,.3,.25];F0=[.04,.06,.08]


def fixture(mode='fit_diffuse_albedo'):
    return synthetic_combined_fixture(mode=mode)[0]


def test_zero_spec_recovers_lambert():
    val=combined_brdf(N,L,V,RHO,.45,F0,specular_weight=0)
    assert np.allclose(val,np.array(RHO)/math.pi)


def test_all_spec_recovers_m02():
    from aiforensics.microfacet_physics import cook_torrance_specular
    val=combined_brdf(N,L,V,RHO,.45,F0,specular_weight=1)
    assert np.allclose(val,cook_torrance_specular(N,L,V,.45,F0))


def test_convex_mixture_exact():
    a=combined_brdf(N,L,V,RHO,.55,F0,specular_weight=.35)
    d=combined_brdf(N,L,V,RHO,.55,F0,specular_weight=0)
    s=combined_brdf(N,L,V,RHO,.55,F0,specular_weight=1)
    assert np.allclose(a,.65*d+.35*s)


def test_reciprocity():
    assert np.allclose(combined_brdf(N,L,V,RHO,.45,F0),
                       combined_brdf(N,V,L,RHO,.45,F0))


def test_visibility_and_light_scaling():
    x=combined_radiance(N,L,V,[5,6,7],RHO,.45,F0,visible_fraction=.4)
    y=combined_radiance(N,L,V,[10,12,14],RHO,.45,F0,visible_fraction=.4)
    assert np.allclose(y,2*x)
    assert np.allclose(combined_radiance(N,L,V,[5,6,7],RHO,.45,F0,visible_fraction=0),0)


def test_below_surface_zero():
    assert np.allclose(combined_brdf(N,[0,0,-1],V,RHO,.45,F0),0)


def test_invalid_lobe_weights_rejected():
    with pytest.raises(CombinedMaterialError):
        combined_brdf(N,L,V,RHO,.5,F0,specular_weight=.9,multiscatter_proxy_weight=.2)


def test_negative_weight_rejected():
    with pytest.raises(CombinedMaterialError):combined_brdf(N,L,V,RHO,.5,F0,specular_weight=-.01)


def test_invalid_albedo_rejected():
    with pytest.raises(CombinedMaterialError):combined_brdf(N,L,V,[1.2,.3,.2],.5,F0)


def test_proxy_term_is_convex_and_symmetric():
    rho2=[.25,.35,.45]
    x=combined_brdf(N,L,V,RHO,.5,F0,specular_weight=.4,multiscatter_proxy_weight=.15,multiscatter_proxy_albedo_rgb=rho2)
    y=.45*combined_brdf(N,L,V,RHO,.5,F0,specular_weight=0)+.4*combined_brdf(N,L,V,RHO,.5,F0,specular_weight=1)+.15*np.array(rho2)/math.pi
    assert np.allclose(x,y)


def test_known_material_fixture():
    report=analyze_combined_manifest(fixture('known_material'))
    assert report['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3
    assert report['counts']['CONSISTENT']>=15
    assert set(report['surfaces_by_material']['paint01'])=={'panel_A','panel_B'}


def test_fitted_albedo_with_disjoint_surfaces():
    report=analyze_combined_manifest(fixture())
    assert np.allclose(report['albedo_rgb_by_material']['paint01'],[.52,.38,.27],atol=.013)
    assert report['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3
    assert report['counts']['CONSISTENT']>=15


def test_negative_corrupted_ids():
    f,truth=synthetic_combined_fixture()
    got={r['id']:r['state'] for r in analyze_combined_manifest(f)['observations']}
    assert all(got[k]=='INCONSISTENT_UNDER_ASSUMPTIONS' for k,t in truth['expected_holdout_states'].items() if t=='INCONSISTENT_UNDER_ASSUMPTIONS')


def test_wrong_irradiance_indicates_disagreement():
    f=fixture('known_material');f['incident_irradiance_rgb']=[1.,1.,1.]
    assert analyze_combined_manifest(f)['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']>3


def test_unknown_light_is_indeterminate():
    f=fixture();f['light_provenance']='estimated_from_single_8bit_photo'
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_unknown_material_is_indeterminate():
    f=fixture();f['materials']['paint01']['material_provenance']='AI_guess'
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_unknown_multiscattering_abstains():
    f=fixture('known_material');f['materials']['paint01']['multiscattering_policy']='unknown'
    r=analyze_combined_manifest(f)
    assert r['state']=='INDETERMINATE'
    assert all(x['state']=='INDETERMINATE' for x in r['observations'])


def test_proxy_requires_independent_provenance():
    f,_=synthetic_combined_fixture(mode='known_material',policy='bounded_diffuse_proxy')
    assert analyze_combined_manifest(f)['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3
    del f['materials']['paint01']['multiscatter_proxy_provenance']
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_train_holdout_not_mixed():
    f=fixture()
    f['samples'][-1]['id']=f['samples'][0]['id']
    with pytest.raises(CombinedMaterialError):analyze_combined_manifest(f)


def test_unverified_holdout_abstains():
    f=fixture();f['samples'][-1]['radiometry_provenance']='tone_mapped_jpeg'
    assert analyze_combined_manifest(f)['observations'][-1]['state']=='INDETERMINATE'


def test_unverified_train_abstains():
    f=fixture();f['samples'][0]['geometry_provenance']='unknown'
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_single_holdout_surface_abstains():
    f=fixture()
    for r in f['samples']:
        if r['role']=='holdout':r['surface_id']='one_surface'
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_insufficient_training_abstains():
    f=fixture();f['samples']=[r for r in f['samples'] if r['role']!='train']
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_no_diffuse_parameter_information_abstains():
    f=fixture();f['materials']['paint01']['specular_weight']=1
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_missing_holdouts_abstains():
    f=fixture();f['samples']=[r for r in f['samples'] if r['role']=='train']
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_extra_material_without_data_abstains():
    f=fixture();f['materials']['unused']=copy.deepcopy(f['materials']['paint01'])
    assert analyze_combined_manifest(f)['state']=='INDETERMINATE'


def test_wrong_semantic_geometry_rejected():
    f=fixture();f['samples'][0]['normal_world']=[1,2]
    with pytest.raises(CombinedMaterialError):analyze_combined_manifest(f)


def test_too_large_noise_rejected():
    f=fixture();f['samples'][0]['sigma_radiance_rgb']=[0,0,0]
    with pytest.raises(CombinedMaterialError):analyze_combined_manifest(f)


def test_bounded_proxy_energy_audit():
    f,_=synthetic_combined_fixture(policy='bounded_diffuse_proxy')
    r=audit_combined_energy(f['materials']['paint01'],mu_view=(.5,.9),n_mu=16,n_phi=36)
    assert all(np.max(x['integrated_reflectance_rgb'])<=1.02 for x in r['view_samples'])


def test_energy_audit_marks_sharp_lobe_uncertain():
    f=fixture();f['materials']['paint01']['roughness']=.05
    r=audit_combined_energy(f['materials']['paint01'],n_mu=8,n_phi=16)
    assert r['state']=='INDETERMINATE'


def test_energy_audit_unknown_multi_abstains():
    f=fixture();f['materials']['paint01']['multiscattering_policy']='unknown'
    assert audit_combined_energy(f['materials']['paint01'],n_mu=12,n_phi=24)['state']=='INDETERMINATE'


def test_json_output(tmp_path):
    f=fixture();p=tmp_path/'fixture.json';p.write_text(json.dumps(f))
    report=run_combined_manifest(p,tmp_path/'out')
    assert report['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert (tmp_path/'out'/'p6_m03_report.json').exists()


def test_cli_demo_and_analysis(tmp_path):
    from aiforensics.cli import main
    out=tmp_path/'demo'
    main(['demo-combined-material','--out',str(out)])
    assert (out/'p6_m03_fixture.json').exists()
    check=tmp_path/'recheck'
    main(['analyze-combined-material','--input',str(out/'p6_m03_fixture.json'),'--out',str(check)])
    assert (check/'p6_m03_report.json').exists()


def test_holdout_is_not_optimized_to_match_corruption():
    f=fixture()
    before=analyze_combined_manifest(f)['albedo_rgb_by_material']['paint01']
    for r in f['samples']:
        if r['role']=='holdout':r['observed_radiance_rgb']=[1.5,1.5,1.5]
    after=analyze_combined_manifest(f)['albedo_rgb_by_material']['paint01']
    assert np.allclose(before,after)


def test_changed_second_surface_is_detected():
    f=fixture('known_material')
    for r in f['samples']:
        if r['role']=='holdout' and r['surface_id']=='panel_B':
            r['observed_radiance_rgb']=(np.array(r['observed_radiance_rgb'])+.3).tolist()
    report=analyze_combined_manifest(f)
    assert report['surfaces_by_material']['paint01']['panel_B']['inconsistent']>=10


def test_fit_mode_does_not_read_placeholder_albedo():
    f=fixture()
    f['materials']['paint01']['diffuse_albedo_rgb']=[.75,.73,.68]
    a=analyze_combined_manifest(f)
    b=analyze_combined_manifest(fixture())
    assert np.allclose(a['albedo_rgb_by_material']['paint01'],b['albedo_rgb_by_material']['paint01'])


def test_invalid_material_fraction_manifest_rejected():
    f=fixture();f['materials']['paint01']['specular_weight']=1.1
    with pytest.raises(CombinedMaterialError):analyze_combined_manifest(f)


def test_bounded_proxy_known_material_resolves():
    f,_=synthetic_combined_fixture(mode='known_material',policy='bounded_diffuse_proxy')
    r=analyze_combined_manifest(f)
    assert r['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3


def test_cli_energy_command(tmp_path):
    from aiforensics.cli import main
    f=fixture();p=tmp_path/'fixture.json';p.write_text(json.dumps(f))
    out=tmp_path/'energy.json'
    main(['audit-combined-energy','--input',str(p),'--out',str(out),'--n-mu','12','--n-phi','28'])
    assert json.loads(out.read_text())['decision']=='NO_AI_ORIGIN_CONCLUSION'
