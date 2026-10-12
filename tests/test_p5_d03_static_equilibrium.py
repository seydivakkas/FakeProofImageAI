"""Static mechanics regressions: analytical cases, negative controls, abstention and CLI."""
import copy
import json
import numpy as np
import pytest

from aiforensics.static_equilibrium import (
    evaluate_static_equilibrium, StaticEquilibriumError, EquilibriumConfig,run_static_manifest)
from aiforensics.static_equilibrium_synthetic import synthetic_equilibrium_fixture


def _item(name):
    data,truth=synthetic_equilibrium_fixture()
    data['objects']=[next(x for x in data['objects'] if x['id']==name)]
    return data


def test_all_fixture_ground_truth():
    data,truth=synthetic_equilibrium_fixture()
    report=evaluate_static_equilibrium(data)
    assert {r['id']:r['state'] for r in report['objects']}==truth
    assert report['counts']=={'CONSISTENT':2,'INCONSISTENT_UNDER_ASSUMPTIONS':4,'INDETERMINATE':3}
    assert report['decision']=='NO_AI_ORIGIN_CONCLUSION'

@pytest.mark.parametrize('name,expected',[
    ('balanced','CONSISTENT'),('horizontal_load_feasible','CONSISTENT'),
    ('no_friction_slide','INCONSISTENT_UNDER_ASSUMPTIONS'),
    ('tipping','INCONSISTENT_UNDER_ASSUMPTIONS'),
    ('com_outside','INCONSISTENT_UNDER_ASSUMPTIONS'),
    ('no_provenance','INDETERMINATE'),('missing_contacts','INDETERMINATE'),
    ('unknown_com','INDETERMINATE'),('contact_outside_support','INCONSISTENT_UNDER_ASSUMPTIONS')])
def test_cases(name,expected):
    assert evaluate_static_equilibrium(_item(name))['objects'][0]['state']==expected


def test_force_and_moment_witness():
    report=evaluate_static_equilibrium(_item('horizontal_load_feasible'))
    row=report['objects'][0]
    assert row['state']=='CONSISTENT'
    forces=np.asarray(row['diagnostics']['witness_contact_forces_world_newton'])
    assert forces.shape==(4,3)
    assert all(f[2]>=-1e-7 and np.linalg.norm(f[:2]) <=0.6*f[2]+1e-7 for f in forces)
    assert row['diagnostics']['balance_residual']<1e-6


def test_zero_friction_prevents_horizontal_static_balance():
    data=_item('horizontal_load_feasible')
    for c in data['objects'][0]['contacts']:c['friction_coefficient']=0
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_edge_contact_can_support_com_if_inside():
    data=_item('balanced')
    data['objects'][0]['center_of_mass_world_xyz']=[0.5,0,1]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='CONSISTENT'


def test_internal_force_not_fake_extra_support():
    data=_item('balanced')
    data['objects'][0]['contacts']=[]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'


def test_unproven_contact_disables_verdict():
    data=_item('no_friction_slide')
    data['objects'][0]['all_contacts_declared']=False
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'


def test_independent_evidence_requirement():
    data=_item('tipping')
    data['objects'][0].pop('geometry_provenance')
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'


def test_support_normal_downwards_is_physics_not_data_error():
    data=_item('balanced')
    for c in data['objects'][0]['contacts']:
        c['reaction_normal_world']=[0,0,-1]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_invalid_normal_rejected():
    data=_item('balanced')
    data['objects'][0]['contacts'][0]['reaction_normal_world']=[1,0,0]
    with pytest.raises(StaticEquilibriumError, match='reaction normal'):
        evaluate_static_equilibrium(data)


def test_invalid_friction_rejected():
    data=_item('balanced')
    data['objects'][0]['contacts'][0]['friction_coefficient']=-0.2
    with pytest.raises(StaticEquilibriumError, match='friction coefficient'):
        evaluate_static_equilibrium(data)


def test_duplicate_ids_rejected():
    data=_item('balanced')
    data['objects'].append(copy.deepcopy(data['objects'][0]))
    with pytest.raises(StaticEquilibriumError, match='unique'):
        evaluate_static_equilibrium(data)


def test_stable_under_gravity_scaling():
    data=_item('balanced')
    data['gravity_acceleration_world_m_s2']=[0,0,-3.71]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='CONSISTENT'


def test_rounded_cone_gap_abstains_or_recovers_correctly():
    data=_item('horizontal_load_feasible')
    out=evaluate_static_equilibrium(data,EquilibriumConfig(cone_sides=8))['objects'][0]
    assert out['state'] in ('CONSISTENT','INDETERMINATE')
    assert out['state'] != 'INCONSISTENT_UNDER_ASSUMPTIONS'


def test_applied_pure_couple_defeats_small_contact_polygon():
    data=_item('balanced')
    data['objects'][0]['external_torque_world_newton_metre']=[0,1000,0]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_separate_pillar_supports():
    data=_item('balanced')
    old=data['support_surfaces'][0]
    other=copy.deepcopy(old)
    other['id']='ground2'
    data['support_surfaces'].append(other)
    data['objects'][0]['contacts'][1]['support_id']='ground2'
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='CONSISTENT'


def test_json_roundtrip_and_hash(tmp_path):
    data,truth=synthetic_equilibrium_fixture()
    inp=tmp_path/'fixture.json';inp.write_text(json.dumps(data),encoding='utf-8')
    result=run_static_manifest(inp,tmp_path/'result')
    assert result['input_sha256']
    assert (tmp_path/'result'/'p5_d03_report.json').exists()
    assert {r['id']:r['state'] for r in result['objects']}==truth


def test_deterministic_and_no_ai_claims():
    data,_=synthetic_equilibrium_fixture()
    x=evaluate_static_equilibrium(data)
    y=evaluate_static_equilibrium(data)
    assert x==y
    assert 'AI' not in x['module']


def test_mass_distribution_derives_true_center_of_mass():
    data=_item('balanced')
    obj=data['objects'][0]
    obj['mass_components']=[
        {'mass_kg':6., 'center_world_xyz':[.2,0,1]},
        {'mass_kg':4., 'center_world_xyz':[-.3,0,1]}]
    obj.pop('mass_kg');obj.pop('center_of_mass_world_xyz')
    result=evaluate_static_equilibrium(data)['objects'][0]
    assert result['state']=='CONSISTENT'
    assert abs(result['diagnostics']['mass_distribution_derived_mass_kg'] - 10.)<1e-8
    assert np.allclose(result['diagnostics']['mass_distribution_derived_center_of_mass_xyz'],[0,0,1])


def test_mass_distribution_outside_support_unstable():
    data=_item('balanced');obj=data['objects'][0]
    obj['mass_components']=[{'mass_kg':5.,'center_world_xyz':[1.3,0,1]},
                             {'mass_kg':5.,'center_world_xyz':[1.5,0,1]}]
    obj.pop('mass_kg');obj.pop('center_of_mass_world_xyz')
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_claimed_com_conflict_fails_closed():
    data=_item('balanced');obj=data['objects'][0]
    obj['mass_components']=[{'mass_kg':10.,'center_world_xyz':[0.2,0,1]}]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_claimed_mass_conflict_fails_closed():
    data=_item('balanced');obj=data['objects'][0]
    obj['mass_components']=[{'mass_kg':9.,'center_world_xyz':[0,0,1]}]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_unverified_mass_distribution_conflict_abstains():
    data=_item('no_provenance');obj=data['objects'][0]
    obj['mass_components']=[{'mass_kg':10.,'center_world_xyz':[0.2,0,1]}]
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'


def test_near_boundary_with_com_uncertainty_abstains():
    data=_item('com_outside')
    data['objects'][0]['center_of_mass_uncertainty_radius_world']=0.05
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'


def test_force_uncertainty_abstains():
    data=_item('no_friction_slide')
    data['objects'][0]['external_force_uncertainty_newton']=5.
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'


def test_invalid_uncertainty_is_error():
    data=_item('balanced')
    data['objects'][0]['external_force_uncertainty_newton']=-1
    with pytest.raises(StaticEquilibriumError): evaluate_static_equilibrium(data)


def test_cli_demo_and_analysis(tmp_path, capsys):
    from aiforensics.cli import main
    target=tmp_path/'demo'
    main(['demo-static','--out',str(target)])
    assert json.loads(capsys.readouterr().out)['ground_truth_exact_match'] is True
    result=tmp_path/'check'
    main(['analyze-static','--input',str(target/'p5_d03_fixture.json'),
          '--out',str(result)])
    row=json.loads(capsys.readouterr().out)
    assert row['counts']=={'CONSISTENT':2,'INCONSISTENT_UNDER_ASSUMPTIONS':4,'INDETERMINATE':3}
    assert (result/'p5_d03_report.json').exists()


def test_invalid_gravity_rejected():
    data=_item('balanced')
    data['gravity_acceleration_world_m_s2']=[0,0,0]
    with pytest.raises(StaticEquilibriumError,match='gravity'):
        evaluate_static_equilibrium(data)


def test_invalid_component_mass_rejected():
    data=_item('balanced')
    data['objects'][0]['mass_components']=[{'mass_kg':-2.,'center_world_xyz':[0,0,1]}]
    with pytest.raises(StaticEquilibriumError,match='component mass'):
        evaluate_static_equilibrium(data)


def test_missing_support_id_rejected():
    data=_item('balanced')
    data['objects'][0]['contacts'][0]['support_id']='unknown'
    with pytest.raises(StaticEquilibriumError,match='contact definition'):
        evaluate_static_equilibrium(data)


def test_synthetic_label_must_not_substitute_real_provenance():
    data=_item('balanced')
    data['objects'][0]['geometry_provenance']='auto_estimated_from_single_photo'
    assert evaluate_static_equilibrium(data)['objects'][0]['state']=='INDETERMINATE'
