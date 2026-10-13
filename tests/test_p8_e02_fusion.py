"""P8-E02 synthetic dependency/multiplicity regression tests; no AI origin verdict."""
import copy
import json
import math
import subprocess
import sys
import pytest

from aiforensics.evidence_contract import EvidenceContractError, SCHEMA_VERSION
from aiforensics.evidence_fusion import (
    FUSION_SCHEMA_VERSION, analyze_fusion_manifest, run_fusion_manifest,
)


def record(module='P4-O01', obs='1', diff=0, asset='asset-a', cal='cal-a',
           reference='ref-a', batch='batch-a', family='family-a', model='model-a'):
    return {
        'module_id': module, 'observation_id': obs,
        'measured': 20.0 + diff, 'predicted': 20.0, 'unit': 'px',
        'assumptions': [{'name': 'physical geometry', 'status': 'supported',
                         'source': 'controlled ground truth'}],
        'provenance': {'source_id': asset, 'calibration_id': cal,
                       'split': 'holdout', 'independent_of_training': True,
                       'external_reference_verified': True},
        'uncertainty': {'measurement_std': 1., 'prediction_std': 0.,
                        'error_correlation': 0.},
        'test': {'null_distribution': 'normal_zero_mean_residual',
                 'alpha': .01, 'pre_registered': True,
                 'distribution_independently_checked': True},
        'lineage': {'raw_asset_id': asset, 'calibration_asset_id': cal,
                    'reference_id': reference, 'holdout_batch_id': batch,
                    'feature_family_id': family, 'model_family_id': model},
    }


def distinct(module, obs, diff):
    return record(module, obs, diff, f'asset-{obs}', f'cal-{obs}',
                  f'ref-{obs}', f'batch-{obs}', f'family-{obs}', f'model-{obs}')


def manifest(*records, alpha=.01, prereg=True, audit=True, unknown=False,
             edges=(), scope='synthetic_controlled'):
    return {'schema_version': SCHEMA_VERSION, 'dataset_scope': scope,
            'records': list(records),
            'fusion': {'familywise_alpha': alpha,
                       'plan_pre_registered': prereg,
                       'dependency_audit_verified': audit,
                       'dependence_unknown': unknown,
                       'declared_edges': list(edges)}}


def test_module_cli_registered():
    from aiforensics.cli import main
    assert callable(main)


def test_one_marginal_rejects_and_no_origin_claim():
    x = analyze_fusion_manifest(manifest(record(diff=4.)))
    assert x['schema_version'] == FUSION_SCHEMA_VERSION
    assert x['rejected_component_ids'] == ['dependency_001']
    assert x['decision'] == 'NO_AI_ORIGIN_CONCLUSION'
    assert x['multiplicity_control']['arbitrary_dependence_valid'] is True


def test_non_rejection_not_proof():
    x = analyze_fusion_manifest(manifest(record(diff=.1)))
    assert x['overall_state'] == 'NO_COMPONENT_NULL_REJECTED'
    assert x['rejected_component_ids'] == []


def test_common_raw_source_creates_dependency():
    a = record(diff=4.)
    b = record(module='P7-S01', obs='2', diff=2.)
    x = analyze_fusion_manifest(manifest(a, b))
    assert x['component_count'] == 1
    assert x['dependency_components'][0]['member_count'] == 2
    assert x['dependency_components'][0]['p_value_union_bound'] == pytest.approx(
        2 * math.erfc(4 / math.sqrt(2)))
    assert 'raw_asset_id' in x['dependency_components'][0]['lineage_reuse']


def test_shared_calibration_only_creates_dependency():
    a = distinct('P1-G01', 'a', 3.)
    b = distinct('P4-O01', 'b', 3.)
    b['lineage']['calibration_asset_id'] = a['lineage']['calibration_asset_id']
    assert analyze_fusion_manifest(manifest(a,b))['component_count'] == 1


def test_shared_reference_only_creates_dependency():
    a, b = distinct('P1-G01', 'a', 3.), distinct('P4-O01', 'b', 3.)
    b['lineage']['reference_id'] = a['lineage']['reference_id']
    assert analyze_fusion_manifest(manifest(a,b))['component_count'] == 1


def test_explicit_edges_transitive():
    a,b,c = [distinct('P1-G0'+str(j), 'o'+str(j), 3.) for j in range(1,4)]
    edges = [
        {'left':'P1-G01/o1','right':'P1-G02/o2','reason':'same latent pose'},
        {'left':'P1-G02/o2','right':'P1-G03/o3','reason':'common optimization'},
    ]
    x = analyze_fusion_manifest(manifest(a,b,c,edges=edges))
    assert x['component_count'] == 1
    assert x['dependency_components'][0]['member_count'] == 3


def test_holm_adjusted_values_monotone_and_exact():
    a,b,c = (distinct('P1-G01','a',4.), distinct('P1-G02','b',3.),
             distinct('P1-G03','c',1.))
    x = analyze_fusion_manifest(manifest(a,b,c))
    ordered = sorted(x['dependency_components'],
                     key=lambda comp: comp['p_value_union_bound'])
    adjusted = [comp['holm_adjusted_p_value'] for comp in ordered]
    assert adjusted == sorted(adjusted)
    assert adjusted[0] == pytest.approx(3*math.erfc(4/math.sqrt(2)))
    assert adjusted[1] == pytest.approx(2*math.erfc(3/math.sqrt(2)))
    assert ordered[-1]['rejects_component_intersection_null'] is False
    assert x['multiplicity_control']['tested_component_count'] == 3


def test_group_bonferroni_can_prevent_claim():
    a = distinct('P1-G01','a',2.8)
    b = distinct('P1-G02','b',2.8)
    b['lineage']['reference_id'] = a['lineage']['reference_id']
    x = analyze_fusion_manifest(manifest(a,b))
    assert x['rejected_component_ids'] == []
    assert x['dependency_components'][0]['p_value_union_bound'] > 0.01


def test_missing_lineage_blocks_entire_shared_component():
    a,b = record(diff=4),record(module='P7-S01',obs='b',diff=4)
    del b['lineage']
    x = analyze_fusion_manifest(manifest(a,b))
    assert x['overall_state'] == 'INDETERMINATE'
    assert x['dependency_components'][0]['state'] == 'NOT_TESTED'
    assert x['rejected_component_ids'] == []


def test_unknown_e01_distribution_blocks():
    a = record(diff=4)
    a['uncertainty']['error_correlation'] = None
    x = analyze_fusion_manifest(manifest(a))
    assert x['dependency_components'][0]['p_value_union_bound'] is None
    assert x['individual_records'][0]['eligible'] is False


def test_real_unverified_blocks():
    x = analyze_fusion_manifest(manifest(record(diff=6),
                                         scope='real_unverified'))
    assert x['overall_state'] == 'INDETERMINATE'


@pytest.mark.parametrize('params',[
    {'prereg':False}, {'audit':False}, {'unknown':True},
])
def test_global_dependency_gates(params):
    x = analyze_fusion_manifest(manifest(record(diff=5),**params))
    assert x['fusion_state'] == 'NOT_PERFORMED'
    assert x['overall_state'] == 'INDETERMINATE'
    assert x['rejected_component_ids'] == []


def test_invalid_alpha_raises():
    with pytest.raises(EvidenceContractError):
        analyze_fusion_manifest(manifest(record(),alpha=1.))


def test_bool_alpha_rejected():
    with pytest.raises(EvidenceContractError):
        analyze_fusion_manifest(manifest(record(),alpha=True))


def test_missing_config_raises():
    x = manifest(record())
    del x['fusion']
    with pytest.raises(EvidenceContractError):
        analyze_fusion_manifest(x)


def test_bad_edge_unknown_record_rejected():
    edges = [{'left':'P4-O01/1','right':'P3-R03/missing','reason':'common'}]
    with pytest.raises(EvidenceContractError):
        analyze_fusion_manifest(manifest(record(),edges=edges))


def test_malformed_edge_rejected():
    edges = [{'left':'P4-O01/1','right':'P4-O01/1','reason':'same'}]
    with pytest.raises(EvidenceContractError):
        analyze_fusion_manifest(manifest(record(),edges=edges))


def test_dependent_ineligible_middle_blocks_whole_cluster():
    a = distinct('P1-G01','a',4)
    b = distinct('P1-G02','b',4)
    c = distinct('P1-G03','c',4)
    b['test']['pre_registered'] = False
    edges = [
        {'left':'P1-G01/a','right':'P1-G02/b','reason':'shared latent parameter'},
        {'left':'P1-G02/b','right':'P1-G03/c','reason':'shared latent parameter'},
    ]
    x = analyze_fusion_manifest(manifest(a,b,c,edges=edges))
    assert x['component_count'] == 1
    assert x['rejected_component_ids'] == []


def test_provenance_duplicate_even_with_fake_distinct_lineages():
    a,b = distinct('P1-G01','a',3),distinct('P1-G02','b',3)
    b['provenance']['source_id'] = a['provenance']['source_id']
    assert analyze_fusion_manifest(manifest(a,b))['component_count'] == 1


def test_output_json_roundtrip(tmp_path):
    source = tmp_path/'input.json'
    source.write_text(json.dumps(manifest(record(diff=3))),encoding='utf-8')
    report = run_fusion_manifest(source,tmp_path/'report')
    saved = json.loads((tmp_path/'report'/'p8_e02_fusion_report.json').read_text())
    assert saved['source_manifest_sha256'] == report['source_manifest_sha256']


def test_manifest_duplicate_ids_still_blocked():
    a = record()
    with pytest.raises(EvidenceContractError):
        analyze_fusion_manifest(manifest(a,copy.deepcopy(a)))


def test_cli_output(tmp_path):
    source = tmp_path/'in.json'
    source.write_text(json.dumps(manifest(record(diff=5))))
    cmd = [sys.executable, '-m', 'aiforensics', 'analyze-fusion',
           '--input',str(source),'--out',str(tmp_path/'result')]
    done = subprocess.run(cmd,capture_output=True,text=True,check=False)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)['decision'] == 'NO_AI_ORIGIN_CONCLUSION'
