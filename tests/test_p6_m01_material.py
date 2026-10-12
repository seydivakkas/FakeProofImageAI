import copy
import json
import math
import numpy as np
import pytest
from aiforensics.material_physics import (
 MaterialPhysicsError, MaterialConfig, lambertian_brdf, lambertian_radiance,
 hemisphere_quadrature, audit_brdf_matrix, analyze_material_manifest, run_material_manifest)
from aiforensics.material_synthetic import synthetic_material_fixture


def test_lambertian_brdf_units():
    assert np.allclose(lambertian_brdf([.2,.5,1]),np.array([.2,.5,1])/np.pi)


def test_energy_quadrature_exact_for_diffuse():
    dirs,weight=hemisphere_quadrature(7,16)
    val=np.ones((len(dirs),len(dirs)))*.72/np.pi
    audit=audit_brdf_matrix(val,dirs,weight)
    assert audit['state']=='CONSISTENT'
    assert abs(audit['max_hemispherical_reflectance']-.72)<1e-12


def test_violation_overenergy():
    dirs,weight=hemisphere_quadrature(4,8)
    audit=audit_brdf_matrix(np.full((len(dirs),len(dirs)),1.15/np.pi),dirs,weight)
    assert audit['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert audit['max_hemispherical_reflectance']>1


def test_reciprocity_violation():
    dirs,weight=hemisphere_quadrature(4,8)
    f=np.full((len(dirs),len(dirs)),.3/np.pi);f[0,1]+=.5
    assert 'reciprocity' in audit_brdf_matrix(f,dirs,weight)['reason']


def test_negative_brdf_violation():
    dirs,w=hemisphere_quadrature(4,8)
    f=np.full((len(dirs),len(dirs)),.2/np.pi);f[0,1]=-.1
    assert audit_brdf_matrix(f,dirs,w)['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_bad_quadrature_and_shape():
    dirs,w=hemisphere_quadrature(4,8)
    with pytest.raises(MaterialPhysicsError):audit_brdf_matrix(np.ones((2,2)),dirs,w)
    with pytest.raises(MaterialPhysicsError):audit_brdf_matrix(np.ones((len(w),len(w))),dirs,w*.1)


def test_grazing_and_backface_physics():
    v=lambertian_radiance([0,0,1],[0,0,1],[20]*3,[0]*3,[.5]*3)
    assert np.allclose(v,10/np.pi)
    assert np.allclose(lambertian_radiance([0,0,1],[0,0,-1],[20]*3,[0]*3,[.5]*3),0)
    assert np.allclose(lambertian_radiance([0,0,1],[1,0,0],[20]*3,[2]*3,[.5]*3),1/np.pi)


def test_visibility_modulates_direct_not_ambient():
    v=lambertian_radiance([0,0,1],[0,0,1],[10]*3,[3]*3,[.6]*3,visible_fraction=0)
    assert np.allclose(v,.6*3/np.pi)


@pytest.mark.parametrize('bad',[-1.,1.01,float('nan')])
def test_unphysical_albedo(bad):
    with pytest.raises(MaterialPhysicsError):lambertian_brdf([bad,.5,.3])


@pytest.mark.parametrize('visible',[-.01,1.01,float('nan')])
def test_invalid_visibility(visible):
    with pytest.raises(MaterialPhysicsError):lambertian_radiance([0,0,1],[0,0,1],[2]*3,[1]*3,[.5]*3,visible_fraction=visible)


def test_fit_albedo_and_holdout():
    fixture,truth=synthetic_material_fixture()
    report=analyze_material_manifest(fixture)
    got={o['id']:o['state'] for o in report['observations']}
    assert all(got[k] == 'INCONSISTENT_UNDER_ASSUMPTIONS' for k,v in truth['expected_holdout_states'].items() if v == 'INCONSISTENT_UNDER_ASSUMPTIONS')
    assert all(got[k] != 'INCONSISTENT_UNDER_ASSUMPTIONS' for k,v in truth['expected_holdout_states'].items() if v == 'CONSISTENT')
    assert report['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3
    assert np.linalg.norm(np.array(report['fitted_or_known_albedo_rgb'])-truth['albedo_rgb'])<.01


def test_known_albedo():
    fixture,truth=synthetic_material_fixture(mode='known_albedo')
    report=analyze_material_manifest(fixture)
    states={r['id']:r['state'] for r in report['observations']}
    assert all(states[k] == v for k,v in truth['expected_holdout_states'].items() if v == 'INCONSISTENT_UNDER_ASSUMPTIONS')
    assert all(states[k] != 'INCONSISTENT_UNDER_ASSUMPTIONS' for k,v in truth['expected_holdout_states'].items() if v == 'CONSISTENT')


def test_unknown_light_not_a_verdict():
    fixture,_=synthetic_material_fixture()
    fixture['light_provenance']='image_inferred'
    report=analyze_material_manifest(fixture)
    assert report['state']=='INDETERMINATE'
    assert all(r['state']=='INDETERMINATE' for r in report['observations'])


def test_unknown_albedo_not_a_verdict():
    fixture,_=synthetic_material_fixture(mode='known_albedo')
    fixture['albedo_provenance']='image_estimate'
    report=analyze_material_manifest(fixture)
    assert report['state']=='INDETERMINATE'


def test_unverified_holdout_no_violation():
    fixture,_=synthetic_material_fixture(mode='known_albedo')
    fixture['samples'][-1]['geometry_provenance']='image_only'
    report=analyze_material_manifest(fixture)
    assert report['observations'][-1]['state']=='INDETERMINATE'


def test_fit_requires_verified_train():
    fixture,_=synthetic_material_fixture()
    fixture['samples'][0]['radiometry_provenance']='jpg_pixel'
    report=analyze_material_manifest(fixture)
    assert report['state']=='INDETERMINATE'


def test_duplicate_leakage_fails():
    fixture,_=synthetic_material_fixture()
    fixture['samples'][-1]['id']=fixture['samples'][0]['id']
    with pytest.raises(MaterialPhysicsError):analyze_material_manifest(fixture)


def test_invalid_role_fails():
    fixture,_=synthetic_material_fixture()
    fixture['samples'][0]['role']='both'
    with pytest.raises(MaterialPhysicsError):analyze_material_manifest(fixture)


def test_insufficient_holdout_abstains():
    fixture,_=synthetic_material_fixture()
    fixture['samples']=[r for r in fixture['samples'] if r['role']=='train']+fixture['samples'][-3:]
    r=analyze_material_manifest(fixture)
    assert r['state']=='INDETERMINATE'


def test_mismatched_lighting_given_albedo():
    fixture,_=synthetic_material_fixture(mode='known_albedo')
    fixture['light_direction_world']=[-.7,-.3,.62]
    report=analyze_material_manifest(fixture)
    assert report['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']>4


def test_report_serializable_and_file(tmp_path):
    f,t=synthetic_material_fixture()
    path=tmp_path/'input.json';path.write_text(json.dumps(f),encoding='utf-8')
    report=run_material_manifest(path,tmp_path/'out')
    assert (tmp_path/'out'/'p6_m01_report.json').exists()
    assert report['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_unknown_normal_nonidentifiable():
    f,_=synthetic_material_fixture()
    f['samples'][0]['normal_world']=[0,0,0]
    with pytest.raises(MaterialPhysicsError):analyze_material_manifest(f)


def test_wrong_linear_units_negative():
    f,_=synthetic_material_fixture()
    f['samples'][0]['observed_radiance_rgb']=[float('nan')]*3
    with pytest.raises(MaterialPhysicsError):analyze_material_manifest(f)


def test_fit_training_corruption_cannot_infer_albedo():
    f,_=synthetic_material_fixture()
    for r in f['samples']:
        if r['role']=='train':r['observed_radiance_rgb']=[x*3 for x in r['observed_radiance_rgb']]
    assert analyze_material_manifest(f)['state']=='INDETERMINATE'


def test_expected_hemisphere_quadrature_weights():
    directions,weights=hemisphere_quadrature(7,24)
    assert np.isclose(sum(weights),2*math.pi)
    assert np.isclose(np.dot(weights,directions[:,2]),math.pi)


def test_known_albedo_light_scaling_problem():
    fixture,_=synthetic_material_fixture(mode='known_albedo')
    fixture['light_provenance']='unknown_from_photo'
    assert analyze_material_manifest(fixture)['state']=='INDETERMINATE'


def test_cli_audit_tabulated_energy(tmp_path):
    from aiforensics.cli import main
    p=tmp_path/'audit.json';out=tmp_path/'result.json'
    p.write_text(json.dumps({'use_builtin_quadrature':True,'brdf_model':'lambertian',
                              'diffuse_albedo':.7,'n_mu':4,'n_phi':8}),encoding='utf-8')
    main(['audit-brdf','--input',str(p),'--out',str(out)])
    result=json.loads(out.read_text(encoding='utf-8'))
    assert result['state']=='CONSISTENT'
    assert np.isclose(result['max_hemispherical_reflectance'],.7)


def test_cli_demo_material(tmp_path):
    from aiforensics.cli import main
    main(['demo-material','--out',str(tmp_path/'demo'),'--seed','2601'])
    assert (tmp_path/'demo'/'p6_m01_report.json').exists()


def test_known_external_albedo_only_holdout_sufficient():
    fixture,_=synthetic_material_fixture(mode='known_albedo')
    fixture['samples']=[r for r in fixture['samples'] if r['role']=='holdout']
    report=analyze_material_manifest(fixture)
    assert report['state']=='MIXED_CONDITIONAL_EVIDENCE'
    assert report['train_count']==0


def test_fit_albedo_without_train_abstains():
    fixture,_=synthetic_material_fixture(mode='fit_albedo')
    fixture['samples']=[r for r in fixture['samples'] if r['role']=='holdout']
    report=analyze_material_manifest(fixture)
    assert report['state']=='INDETERMINATE'
