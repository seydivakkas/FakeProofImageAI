"""P7-S02 physical PRNU/DSNU and controlled independent-sensor holdout tests."""
from __future__ import annotations
import copy,json,subprocess,sys
from pathlib import Path
import numpy as np
import pytest
from aiforensics.sensor_noise import SensorParameters
from aiforensics.sensor_fingerprint import (
    FingerprintConfig,FingerprintError,validate_stack,estimate_fingerprint,
    pearson_map,compare_fingerprints,analyze_fingerprint_manifest,run_fingerprint_manifest)
from aiforensics.sensor_fingerprint_synthetic import (
    sensor_pattern,synthetic_raw_stacks,write_synthetic_fingerprint_fixture)


@pytest.fixture(scope='module')
def sample(tmp_path_factory):
    path=tmp_path_factory.mktemp('p7s02')
    file,truth=write_synthetic_fingerprint_fixture(path,seed=4202)
    manifest=json.loads(file.read_text())
    return path,manifest,truth


@pytest.fixture(scope='module')
def result(sample):
    path,manifest,_=sample
    return analyze_fingerprint_manifest(manifest,base_dir=path,controlled_synthetic_evaluation=True)


def test_reference_and_query_independent_frames(sample):
    path,_,_=sample
    with np.load(path/'reference.npz') as a,np.load(path/'same_sensor.npz') as b:
        assert not np.array_equal(a['dark'],b['dark'])
        assert not np.array_equal(a['flat'],b['flat'])


def test_no_ai_origin_decision(result):
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert all(q['decision']=='NO_AI_ORIGIN_CONCLUSION' for q in result['queries'])


def test_correct_match(result):
    q=result['queries'][0]
    assert q['state']=='CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS'
    assert q['prnu_pearson_r']>.90 and q['dsnu_pearson_r']>.85


def test_wrong_sensor_rejected(result):
    q=result['queries'][1]
    assert q['state']=='INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS'
    assert q['prnu_pearson_r']<.2 and q['dsnu_pearson_r']<.2


def test_counts(result):
    assert result['counts']=={'CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS':1,
                              'INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS':1,'INDETERMINATE':0}


def test_dsnu_prnu_shapes(result):
    a=result['reference_diagnostics']
    assert a['shape_hw']==[32,32] and a['dark_frame_count']==20 and a['flat_frame_count']==20


def test_dsnu_prnu_truth_scale(result):
    a=result['reference_diagnostics']
    assert .025<a['prnu_rms_fraction']<.05
    assert 6.<a['dsnu_rms_e']<10.


def test_mean_subtracted_maps(sample):
    path,manifest,_=sample
    s=SensorParameters(**manifest['sensor'])
    with np.load(path/'reference.npz') as z:
        e=estimate_fingerprint(z['dark'],z['flat'],s)
    assert abs(e['prnu_map'].mean())<1e-12
    assert abs(e['dsnu_map_e'].mean())<1e-10


def test_spatial_variance_differs_from_temporal_variance(sample):
    path,manifest,_=sample
    with np.load(path/'reference.npz') as z:
        dark=z['dark'].astype(float)
    temporal=dark.var(axis=0,ddof=1).mean()
    spatial=dark.mean(axis=0).var(ddof=1)
    assert spatial>temporal/len(dark)


def test_same_sensor_response_independent_light_strength(sample):
    path,manifest,_=sample
    s=SensorParameters(**manifest['sensor'])
    patt=sensor_pattern(4202)
    d,f=synthetic_raw_stacks(patt,seed=790,photoelectrons=3500,frames=24)
    with np.load(path/'reference.npz') as z:
        ref=estimate_fingerprint(z['dark'],z['flat'],s)
    q=estimate_fingerprint(d,f,s)
    assert pearson_map(ref['prnu_match_map'],q['prnu_match_map'])>.90


def test_wrong_sensor_independent_pattern():
    a=sensor_pattern(23);b=sensor_pattern(24)
    assert abs(pearson_map(a[0],b[0]))<.2


def test_pearson_map_exact():
    a=np.arange(9).reshape(3,3)
    assert pearson_map(a,a)==pytest.approx(1)
    assert pearson_map(a,-a)==pytest.approx(-1)


def test_pearson_constant_returns_none():
    assert pearson_map(np.ones((5,5)),np.ones((5,5))) is None


def test_pearson_mismatch_returns_none():
    assert pearson_map(np.ones((2,3)),np.ones((3,2))) is None


def test_pearson_nan_returns_none():
    assert pearson_map(np.array([1.,np.nan]),np.array([2.,3.])) is None


def test_real_provenance_not_calibrated(sample):
    root,m,_=sample
    other=copy.deepcopy(m);other['provenance']='independent_raw_observation'
    r=analyze_fingerprint_manifest(other,base_dir=root)
    assert r['counts']['INDETERMINATE']==2
    assert r['queries'][0]['prnu_pearson_r']>.90


@pytest.mark.parametrize('key',[ 'uniform_flat_field','matched_exposure_and_gain',
    'matched_temperature','spatial_alignment_verified','independent_capture_stacks',
    'unprocessed_native_raw'])
def test_missing_physical_assumption_remains_indeterminate(sample,key):
    root,m,_=sample
    altered=copy.deepcopy(m);altered[key]=False
    r=analyze_fingerprint_manifest(altered,base_dir=root,controlled_synthetic_evaluation=True)
    assert r['state']=='INDETERMINATE'
    assert r['counts']['INDETERMINATE']==2


@pytest.mark.parametrize('domain',['jpeg','gamma_rgb','demosaiced','raw_crop'])
def test_processed_image_rejected(sample,domain):
    root,m,_=sample;altered=copy.deepcopy(m)
    altered['input_domain']=domain
    with pytest.raises(FingerprintError):analyze_fingerprint_manifest(altered,base_dir=root)


def test_duplicate_query_id_rejected(sample):
    root,m,_=sample;altered=copy.deepcopy(m)
    altered['queries'].append(copy.deepcopy(altered['queries'][0]))
    with pytest.raises(FingerprintError,match='duplicate'):analyze_fingerprint_manifest(altered,base_dir=root)


def test_empty_query_rejected(sample):
    root,m,_=sample;altered=copy.deepcopy(m);altered['queries']=[]
    with pytest.raises(FingerprintError):analyze_fingerprint_manifest(altered,base_dir=root)


def test_train_holdout_leakage_rejected(sample):
    root,m,_=sample;altered=copy.deepcopy(m)
    altered['queries'][0]['npz']=altered['reference_npz']
    r=analyze_fingerprint_manifest(altered,base_dir=root,controlled_synthetic_evaluation=True)
    assert r['queries'][0]['state']=='INDETERMINATE'
    assert 'leakage' in r['queries'][0]['reason']


def test_missing_query_fails_safely(sample):
    root,m,_=sample;altered=copy.deepcopy(m)
    altered['queries'][0]['npz']='no_file.npz'
    r=analyze_fingerprint_manifest(altered,base_dir=root,controlled_synthetic_evaluation=True)
    assert r['queries'][0]['state']=='INDETERMINATE'


def test_misaligned_grids_indeterminate():
    s=SensorParameters()
    a=sensor_pattern(123,(32,32));b=sensor_pattern(123,(40,40))
    d1,f1=synthetic_raw_stacks(a,seed=1);d2,f2=synthetic_raw_stacks(b,seed=2)
    x=estimate_fingerprint(d1,f1,s);y=estimate_fingerprint(d2,f2,s)
    assert compare_fingerprints(x,y,synthetic_independent_pixels=True)['state']=='INDETERMINATE'


def test_too_few_frames_rejected():
    d,f=synthetic_raw_stacks(sensor_pattern(5),seed=10,frames=3)
    with pytest.raises(FingerprintError,match='min_frames'):estimate_fingerprint(d,f,SensorParameters())


def test_too_few_pixels_rejected():
    d,f=synthetic_raw_stacks(sensor_pattern(5,(8,8)),seed=10,frames=12)
    with pytest.raises(FingerprintError,match='spatial'):estimate_fingerprint(d,f,SensorParameters())


def test_saturation_rejected(sample):
    path,m,_=sample
    with np.load(path/'reference.npz') as z:d=z['dark'].copy();f=z['flat'].copy()
    f[:,:,:]=m['sensor']['adc_max_adu']
    with pytest.raises(FingerprintError,match='clipped'):estimate_fingerprint(d,f,SensorParameters(**m['sensor']))


def test_zero_flat_signal_rejected(sample):
    path,m,_=sample
    with np.load(path/'reference.npz') as z:d=z['dark'].copy()
    with pytest.raises(FingerprintError):estimate_fingerprint(d,d.copy(),SensorParameters(**m['sensor']))


def test_nan_rejected():
    d=np.ones((10,32,32))*150;f=np.ones_like(d)*1500
    f[0,0,0]=np.nan
    with pytest.raises(FingerprintError):estimate_fingerprint(d,f,SensorParameters())


def test_invalid_adc_rejected():
    d=np.ones((10,32,32))*150;f=np.ones_like(d)*1500
    f[0,0,0]=-1
    with pytest.raises(FingerprintError):estimate_fingerprint(d,f,SensorParameters())


def test_low_response_rejected():
    rng=np.random.default_rng(5)
    d=np.rint(rng.normal(140,2,(12,32,32)))
    f=np.rint(rng.normal(150,2,(12,32,32)))
    with pytest.raises(FingerprintError,match='weak'):estimate_fingerprint(d,f,SensorParameters())


def test_no_fingerprint_snr_results_indeterminate(sample):
    path,m,_=sample
    with np.load(path/'reference.npz') as z:d=z['dark'];f=z['flat']
    ref=estimate_fingerprint(d,f,SensorParameters(**m['sensor']))
    q=compare_fingerprints(ref,ref,FingerprintConfig(min_pattern_snr=1e6),synthetic_independent_pixels=True)
    assert q['state']=='INDETERMINATE'


def test_static_correlation_no_independent_calibration(sample):
    root,m,_=sample
    r=analyze_fingerprint_manifest(dict(m,provenance='user_uploaded_raw'),base_dir=root)
    assert r['queries'][1]['state']=='INDETERMINATE'


def test_report_file_written(sample,tmp_path):
    root,m,_=sample
    src=root/'p7_s02_fixture.json'
    r=run_fingerprint_manifest(src,tmp_path)
    report=json.loads((tmp_path/'p7_s02_report.json').read_text())
    assert report['counts']==r['counts']


def test_cli_demo(tmp_path):
    from aiforensics.cli import main
    main(['demo-sensor-fingerprint','--out',str(tmp_path)])
    assert (tmp_path/'p7_s02_maps.png').is_file()
    assert (tmp_path/'p7_s02_report.json').is_file()


def test_cli_analyze(sample,tmp_path):
    from aiforensics.cli import main
    root,m,_=sample
    main(['analyze-sensor-fingerprint','--input',str(root/'p7_s02_fixture.json'),'--out',str(tmp_path)])
    assert (tmp_path/'p7_s02_report.json').is_file()


def test_benchmark_small():
    from scripts.p7_fingerprint_benchmark import run
    r=run(trials=3,seed=4141)
    assert r['counts']['true_match']==3
    assert r['counts']['true_nonmatch']==3
    assert r['counts']['wrong_definitive']==0


def test_seed_reproducible():
    a=sensor_pattern(45);b=sensor_pattern(45)
    assert np.array_equal(a[0],b[0]) and np.array_equal(a[1],b[1])


def test_reproducible_frames():
    a=sensor_pattern(47)
    r1=synthetic_raw_stacks(a,seed=17)
    r2=synthetic_raw_stacks(a,seed=17)
    assert np.array_equal(r1[0],r2[0]) and np.array_equal(r1[1],r2[1])


def test_json_provenance_claim_never_trusts_unknown_input(sample):
    root,m,_=sample
    r=analyze_fingerprint_manifest(m,base_dir=root)
    assert r['controlled_synthetic_evaluation'] is False
    assert r['counts']['INDETERMINATE']==2


def test_cli_analyze_is_descriptive_only(sample,tmp_path):
    from aiforensics.cli import main
    root,m,_=sample
    main(['analyze-sensor-fingerprint','--input',str(root/'p7_s02_fixture.json'),'--out',str(tmp_path)])
    r=json.loads((tmp_path/'p7_s02_report.json').read_text())
    assert r['counts']['INDETERMINATE']==2
