"""P8-E01 statistical evidence: synthetic-only tests, no origin inference."""
import copy
import json
import math
from pathlib import Path
import pytest
from aiforensics.evidence_contract import (
    analyze_evidence_record, analyze_evidence_manifest, EvidenceContractError,
    normalize_legacy_report, run_evidence_manifest, MODULES, SCHEMA_VERSION,
)


def good_record():
    return dict(module_id='P4-O01', observation_id='holdout_px_01',
                measured=100.3, predicted=100.0, unit='px',
                assumptions=[{'name':'camera geometry','status':'supported','source':'synthetic ground truth'}],
                provenance={'source_id':'synthetic-frame-1','calibration_id':'disjoint calibration batch',
                            'split':'holdout','independent_of_training':True,
                            'external_reference_verified':True},
                uncertainty={'measurement_std':0.5,'prediction_std':0.2,'error_correlation':0.0},
                test={'null_distribution':'normal_zero_mean_residual', 'alpha':0.01,
                      'pre_registered':True,'distribution_independently_checked':True})


def result(r, scope='synthetic_controlled'):
    return analyze_evidence_record(r, dataset_scope=scope)


def test_all_modules_registered():
    assert len(MODULES)==24
    assert 'P7-S02' in MODULES and 'P1-G01' in MODULES


def test_consistent_small_error():
    x=result(good_record())
    assert x['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert 0<x['p_value_two_sided']<1
    assert x['uncertainty']['residual_std']==pytest.approx(math.sqrt(0.29))
    assert x['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_large_error_rejects_normal_null():
    r=good_record();r['measured']=105
    x=result(r)
    assert x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert x['standardized_effect']>9
    assert x['p_value_two_sided']<0.01


def test_zero_effect_p_one():
    r=good_record();r['measured']=r['predicted']
    assert result(r)['p_value_two_sided']==1.0


def test_correlation_adjustment():
    r=good_record();r['uncertainty']['error_correlation']=0.5
    assert result(r)['uncertainty']['residual_std']==pytest.approx(math.sqrt(0.19))


def test_unknown_correlation_abstains():
    r=good_record();r['uncertainty']['error_correlation']=None
    x=result(r)
    assert x['state']=='INDETERMINATE' and x['p_value_two_sided'] is None

@pytest.mark.parametrize('key,value', [('split','train'),('independent_of_training',False),
                                      ('external_reference_verified',False)])
def test_provenance_gate(key,value):
    r=good_record();r['provenance'][key]=value
    assert result(r)['state']=='INDETERMINATE'


def test_real_unverified_abstains():
    assert result(good_record(),'real_unverified')['state']=='INDETERMINATE'


def test_unknown_assumption_abstains():
    r=good_record();r['assumptions'][0]['status']='unknown'
    assert result(r)['state']=='INDETERMINATE'


def test_missing_distribution_check_abstains():
    r=good_record();r['test']['distribution_independently_checked']=False
    assert result(r)['p_value_two_sided'] is None


def test_unregistered_null_abstains():
    r=good_record();r['test']['null_distribution']='t-test'
    assert result(r)['state']=='INDETERMINATE'


def test_not_preregistered_abstains():
    r=good_record();r['test']['pre_registered']=False
    assert result(r)['state']=='INDETERMINATE'

@pytest.mark.parametrize('field,val', [('measured',float('nan')),('predicted',float('inf')),
                                       ('measured','nonsense')])
def test_invalid_value_raises(field,val):
    r=good_record();r[field]=val
    with pytest.raises(EvidenceContractError):result(r)

@pytest.mark.parametrize('sigma', [-1,0])
def test_invalid_sigma(sigma):
    r=good_record();r['uncertainty']['measurement_std']=sigma
    r['uncertainty']['prediction_std']=0 if sigma==0 else 1
    if sigma<0:
        with pytest.raises(EvidenceContractError):result(r)
    else:
        assert result(r)['state']=='INDETERMINATE'

@pytest.mark.parametrize('rho', [-1.1,1.1])
def test_invalid_correlation(rho):
    r=good_record();r['uncertainty']['error_correlation']=rho
    with pytest.raises(EvidenceContractError):result(r)

@pytest.mark.parametrize('alpha', [-0.01,0,1,1.5])
def test_invalid_alpha(alpha):
    r=good_record();r['test']['alpha']=alpha
    with pytest.raises(EvidenceContractError):result(r)


def test_bool_not_numeric():
    r=good_record();r['measured']=True
    with pytest.raises(EvidenceContractError):result(r)


def test_missing_assumptions_rejected():
    r=good_record();r['assumptions']=[]
    with pytest.raises(EvidenceContractError):result(r)


def test_unknown_module_rejected():
    r=good_record();r['module_id']='P9-UNKNOWN'
    with pytest.raises(EvidenceContractError):result(r)


def test_duplicate_evidence_rejected():
    r=good_record()
    with pytest.raises(EvidenceContractError):
        analyze_evidence_manifest({'schema_version':SCHEMA_VERSION,'dataset_scope':'synthetic_controlled','records':[r,r]})


def test_manifest_not_fusing_p_values():
    r=good_record();r2=copy.deepcopy(r);r2['module_id']='P7-S02';r2['observation_id']='corr_1';r2['unit']='correlation'
    x=analyze_evidence_manifest({'schema_version':SCHEMA_VERSION,'dataset_scope':'synthetic_controlled','records':[r,r2]})
    assert x['record_count']==2 and x['fusion_state']=='NOT_PERFORMED'
    assert x['multiple_testing_state']=='NOT_CALIBRATED'


def test_incomplete_real_manifest_defaults_abstain():
    x=analyze_evidence_manifest({'schema_version':SCHEMA_VERSION,'records':[good_record()]})
    assert x['records'][0]['state']=='INDETERMINATE'


def test_duplicate_assumptions_rejected():
    r=good_record();r['assumptions'].append(copy.deepcopy(r['assumptions'][0]))
    with pytest.raises(EvidenceContractError):result(r)


def test_legacy_bridge_does_not_upgrade_pass():
    x=normalize_legacy_report('P6-M03',{'state':'CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS','value':3},report_id='legacy-1')
    assert x['state']=='INDETERMINATE' and x['legacy_report_sha256']
    assert x['p_value_two_sided'] is None


def test_legacy_bridge_hash_is_order_invariant():
    a=normalize_legacy_report('P1-G02',{'x':1,'y':2},report_id='a')
    b=normalize_legacy_report('P1-G02',{'y':2,'x':1},report_id='a')
    assert a['legacy_report_sha256']==b['legacy_report_sha256']


def test_cli_entry_roundtrip(tmp_path):
    src=tmp_path/'manifest.json';out=tmp_path/'results'
    src.write_text(json.dumps({'schema_version':SCHEMA_VERSION,'dataset_scope':'synthetic_controlled','records':[good_record()]}))
    r=run_evidence_manifest(src,out)
    assert r['source_manifest_sha256']
    disk=json.loads((out/'p8_e01_evidence_report.json').read_text())
    assert disk['summary_counts']['CONSISTENT_UNDER_ASSUMPTIONS']==1


def test_evidence_roundtrip_risk_statement(tmp_path):
    src=tmp_path/'manifest.json';out=tmp_path/'results'
    r=good_record();r['measured']=105
    src.write_text(json.dumps({'schema_version':SCHEMA_VERSION,'dataset_scope':'synthetic_controlled','records':[r]}))
    x=run_evidence_manifest(src,out)
    assert x['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert 'AI-origin' in x['warnings'][0]


def test_all_statuses_known():
    from aiforensics.evidence_contract import STATES
    assert len(set(STATES))==4
