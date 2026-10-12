"""P7-S01 analytical, stochastic, provenance, train/holdout, CLI tests."""
from __future__ import annotations
import copy,json,math,subprocess,sys
from pathlib import Path
import numpy as np
import pytest
from aiforensics.sensor_noise import (SensorParameters,SensorNoiseConfig,
    SensorNoiseError, ideal_moments,sample_sensor,summarize_codes,
    analyze_sensor_manifest,run_sensor_manifest)
from aiforensics.sensor_synthetic import synthetic_sensor_fixture


@pytest.fixture(scope='module')
def known():return synthetic_sensor_fixture(seed=3101,mode='known_parameters')[0]


@pytest.fixture(scope='module')
def fit():return synthetic_sensor_fixture(seed=3101,mode='fit_train_parameters')[0]


def test_zero_dark_mean_and_variance():
    s=SensorParameters(gain_e_per_adu=2.,read_noise_e=4.,dark_current_e_per_s=0,black_level_adu=100)
    m=ideal_moments(0,0,s)
    assert m['expected_mean_adu']==100
    assert abs(m['expected_variance_adu2']-(4+1/12))<1e-12


def test_poisson_shot_noise_variance():
    s=SensorParameters(gain_e_per_adu=2.,read_noise_e=0.,dark_current_e_per_s=0)
    m=ideal_moments(800,0,s)
    assert abs(m['variance_e2']-800)<1e-12
    assert abs(m['expected_variance_adu2']-(200+1/12))<1e-12


def test_dark_current_contributes_to_mean_and_shot_variance():
    s=SensorParameters(gain_e_per_adu=2.,read_noise_e=3.,dark_current_e_per_s=4.)
    a=ideal_moments(100,1,s);b=ideal_moments(100,3,s)
    assert abs((b['expected_mean_adu']-a['expected_mean_adu'])-4.)<1e-12
    assert abs((b['expected_variance_adu2']-a['expected_variance_adu2'])-2.)<1e-12


def test_gain_electron_per_adu_orientation():
    a=ideal_moments(500,1,SensorParameters(gain_e_per_adu=2))
    b=ideal_moments(500,1,SensorParameters(gain_e_per_adu=4))
    assert b['expected_mean_adu']-128 == pytest.approx((a['expected_mean_adu']-128)/2)


def test_snr_equation_electrons():
    s=SensorParameters(read_noise_e=3,dark_current_e_per_s=2)
    m=ideal_moments(100,2,s)
    assert m['snr_electrons']==pytest.approx(100/math.sqrt(113))


def test_snr_shot_noise_limit():
    s=SensorParameters(read_noise_e=0,dark_current_e_per_s=0)
    assert ideal_moments(900,0,s)['snr_electrons']==pytest.approx(30.)


def test_zero_signal_snr_when_read_present():
    s=SensorParameters()
    assert ideal_moments(0,0,s)['snr_electrons']==0


def test_sampling_dtype_and_adc_range():
    s=SensorParameters(full_well_e=1000.,adc_max_adu=1023)
    raw=sample_sensor(3000,0,s,size=10000,seed=1)
    assert raw.dtype==np.uint16 and raw.min()>=0 and raw.max()<=1023


def test_deterministic_rng():
    s=SensorParameters()
    assert np.array_equal(sample_sensor(500,1,s,size=2000,seed=91),
                          sample_sensor(500,1,s,size=2000,seed=91))


def test_sampling_moments_match_analytical_large_n():
    s=SensorParameters(gain_e_per_adu=2.,read_noise_e=4.5,dark_current_e_per_s=1.65)
    samples=sample_sensor(420,2,s,size=150000,seed=88)
    observed=summarize_codes(samples,s)
    expected=ideal_moments(420,2,s)
    assert abs(observed['observed_mean_adu']-expected['expected_mean_adu'])<.10
    assert abs(observed['observed_variance_adu2']-expected['expected_variance_adu2'])<4


def test_statistics_sample_variance_ddof1():
    d=summarize_codes(np.array([2,4,6]),SensorParameters())
    assert d['observed_mean_adu']==4 and d['observed_variance_adu2']==4


def test_known_fixture_mismatch_detected(known):
    f,t=synthetic_sensor_fixture(seed=3101)
    r=analyze_sensor_manifest(f)
    found={x['id']:x['state'] for x in r['observations']}
    assert all(found[k]=='INCONSISTENT_UNDER_ASSUMPTIONS' for k,v in t['expected_states'].items()
               if v=='INCONSISTENT_UNDER_ASSUMPTIONS')
    assert r['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3


def test_fit_train_parameters_recovers_truth(fit):
    r=analyze_sensor_manifest(fit)
    assert r['parameters']['gain_e_per_adu']==pytest.approx(2.,abs=.02)
    assert r['parameters']['read_noise_e']==pytest.approx(4.5,abs=.5)
    assert r['parameters']['dark_current_e_per_s']==pytest.approx(1.65,abs=.35)
    assert r['counts']['INCONSISTENT_UNDER_ASSUMPTIONS']==3


def test_holdout_never_affects_fit(fit):
    f=copy.deepcopy(fit)
    a=analyze_sensor_manifest(f)['parameters']
    for item in f['measurements']:
        if item['role']=='holdout':
            item['observed_mean_adu']+=200
            item['observed_variance_adu2']+=1000
    b=analyze_sensor_manifest(f)['parameters']
    assert a==b


def test_known_calibration_does_not_use_train_measurements(known):
    f=copy.deepcopy(known)
    expected=analyze_sensor_manifest(f)['parameters']
    f['measurements']=[r for r in f['measurements'] if r['role']=='holdout']
    assert analyze_sensor_manifest(f)['parameters']==expected


def test_photon_transfer_variance_rises_with_signal():
    s=SensorParameters(read_noise_e=4)
    a=ideal_moments(20,0,s);b=ideal_moments(2000,0,s)
    assert b['expected_variance_adu2']>a['expected_variance_adu2']


def test_insufficient_holdout_rejected(known):
    f=copy.deepcopy(known)
    f['measurements']=[r for r in f['measurements'] if r['role']=='train']
    with pytest.raises(SensorNoiseError,match='holdout'):analyze_sensor_manifest(f)


def test_fit_not_identifiable_without_multiple_illumination_levels(fit):
    f=copy.deepcopy(fit)
    f['measurements']=[r for r in f['measurements'] if r['kind']=='dark']
    with pytest.raises(SensorNoiseError):analyze_sensor_manifest(f)


def test_fit_requires_zero_duration_dark_reference(fit):
    f=copy.deepcopy(fit)
    f['measurements']=[r for r in f['measurements'] if not (r['role']=='train' and r['kind']=='dark' and r['exposure_s']==0)]
    with pytest.raises(SensorNoiseError):analyze_sensor_manifest(f)


def test_fit_rejects_unverified_train(fit):
    f=copy.deepcopy(fit)
    f['measurements'][0]['sample_provenance']='unknown'
    with pytest.raises(SensorNoiseError):analyze_sensor_manifest(f)


def test_unknown_photon_flux_abstains(known):
    f=copy.deepcopy(known)
    f['measurements'][-1]['photoelectron_provenance']='inferred_from_jpeg'
    assert analyze_sensor_manifest(f)['observations'][-1]['state']=='INDETERMINATE'


def test_jpeg_input_abstains(known):
    f=copy.deepcopy(known);f['input_domain']='gamma_encoded_jpeg'
    assert analyze_sensor_manifest(f)['state']=='INDETERMINATE'
    assert all(r['state']=='INDETERMINATE' for r in analyze_sensor_manifest(f)['observations'])


def test_unknown_sensor_provenance_abstains(known):
    f=copy.deepcopy(known);f['sensor_provenance']='metadata_guess'
    assert analyze_sensor_manifest(f)['state']=='INDETERMINATE'


@pytest.mark.parametrize('flag',['stable_temperature','temporally_independent',
    'uniform_flat_field','fixed_gain_mode','prnu_or_fpn_controlled'])
def test_acquisition_violations_abstain(known,flag):
    f=copy.deepcopy(known);f[flag]=False
    assert analyze_sensor_manifest(f)['state']=='INDETERMINATE'


def test_saturation_measurement_abstains(known):
    f=copy.deepcopy(known);f['measurements'][-1]['saturation_fraction']=.1
    assert analyze_sensor_manifest(f)['observations'][-1]['state']=='INDETERMINATE'


def test_sensor_fullwell_predicted_abstains(known):
    f=copy.deepcopy(known);f['sensor']['full_well_e']=2000
    assert all(x['state']=='INDETERMINATE' for x in analyze_sensor_manifest(f)['observations']
               if x['expected_mean_adu']-128>=1000)


def test_insufficient_samples_abstains(known):
    f=copy.deepcopy(known);f['measurements'][-1]['n_samples']=16
    assert analyze_sensor_manifest(f)['observations'][-1]['state']=='INDETERMINATE'


def test_quantization_approximation_abstains(known):
    f=copy.deepcopy(known);f['sensor']['read_noise_e']=.01
    assert all(r['state']=='INDETERMINATE' for r in analyze_sensor_manifest(f)['observations'])


def test_corrupt_variance_detected(known):
    f=copy.deepcopy(known)
    r=next(r for r in f['measurements'] if r['role']=='holdout' and r['kind']=='flat')
    r['observed_variance_adu2']*=3
    outcome=analyze_sensor_manifest(f)
    matching=next(x for x in outcome['observations'] if x['id']==r['id'])
    assert matching['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_corrupt_mean_detected(known):
    f=copy.deepcopy(known)
    r=next(r for r in f['measurements'] if r['role']=='holdout' and r['kind']=='flat')
    r['observed_mean_adu']+=100
    outcome=analyze_sensor_manifest(f)
    matching=next(x for x in outcome['observations'] if x['id']==r['id'])
    assert matching['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_no_ai_origin_conclusion(known):
    r=analyze_sensor_manifest(known)
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert r['module']=='P7_S01_SENSOR_SHOT_READ_DARK_GAIN'


def test_invalid_negative_photo_rejected(known):
    f=copy.deepcopy(known);f['measurements'][0]['expected_photoelectrons']=-10
    with pytest.raises(SensorNoiseError):analyze_sensor_manifest(f)


def test_dark_frame_with_photons_rejected(known):
    f=copy.deepcopy(known);f['measurements'][0]['expected_photoelectrons']=20
    with pytest.raises(SensorNoiseError):analyze_sensor_manifest(f)


def test_duplicate_observation_ids_rejected(known):
    f=copy.deepcopy(known);f['measurements'][0]['id']=f['measurements'][1]['id']
    with pytest.raises(SensorNoiseError):analyze_sensor_manifest(f)


def test_nonfinite_sensor_parameter_rejected():
    with pytest.raises(SensorNoiseError):SensorParameters(gain_e_per_adu=float('nan'))


def test_bad_photon_rate_rejected():
    with pytest.raises(SensorNoiseError):ideal_moments(-1,0,SensorParameters())


def test_bad_adc_range_rejected():
    with pytest.raises(SensorNoiseError):SensorParameters(black_level_adu=2000,adc_max_adu=1023)


def test_config_negative_guard_band_rejected():
    with pytest.raises(SensorNoiseError):SensorNoiseConfig(consistent_sigma=5,inconsistent_sigma=3)


def test_json_report_roundtrip(tmp_path,known):
    inp=tmp_path/'fixture.json'
    inp.write_text(json.dumps(known),encoding='utf-8')
    r=run_sensor_manifest(inp,tmp_path/'out')
    file=tmp_path/'out'/'p7_s01_report.json'
    assert file.exists()
    assert json.loads(file.read_text())['counts']==r['counts']


def test_cli_analyze_and_demo(tmp_path,known):
    data=tmp_path/'fixture.json';data.write_text(json.dumps(known),encoding='utf-8')
    cmd=[sys.executable,'-m','aiforensics','analyze-sensor-noise','--input',str(data),'--out',str(tmp_path/'analysis')]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
    assert p.returncode==0,p.stderr
    assert (tmp_path/'analysis'/'p7_s01_report.json').exists()
    cmd=[sys.executable,'-m','aiforensics','demo-sensor-noise','--out',str(tmp_path/'demo')]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
    assert p.returncode==0,p.stderr
    assert (tmp_path/'demo'/'p7_s01_photon_transfer.png').exists()


def test_temporal_raw_avoids_spatial_fpn_variance_inflation():
    from aiforensics.sensor_noise import summarize_temporal_raw_stack
    rng=np.random.default_rng(77)
    # A fixed 10 ADU spatial pattern must not inflate temporal noise variance.
    base=rng.integers(100,130,size=(12,12))
    noise=rng.normal(0,2,size=(60,12,12))
    stack=np.rint(400+base[None,:,:]+noise).astype(np.uint16)
    result=summarize_temporal_raw_stack(stack,SensorParameters())
    pooled=float(stack.astype(float).var(ddof=1))
    assert result['observed_variance_adu2'] < 6
    assert pooled > 50


def test_temporal_stack_roi():
    from aiforensics.sensor_noise import summarize_temporal_raw_stack
    data=np.full((4,5,5),129,dtype=np.uint16)
    data[:,:,0]=145
    report=summarize_temporal_raw_stack(data,SensorParameters(),(1,1,5,5))
    assert report['observed_mean_adu']==129
    assert report['roi_pixel_count']==16
    assert report['n_samples']==64


def test_temporal_stack_rejects_noninteger():
    from aiforensics.sensor_noise import summarize_temporal_raw_stack
    with pytest.raises(SensorNoiseError):
        summarize_temporal_raw_stack(np.full((4,4,4),.33),SensorParameters())


def test_temporal_stack_rejects_out_of_bounds_roi():
    from aiforensics.sensor_noise import summarize_temporal_raw_stack
    with pytest.raises(SensorNoiseError):
        summarize_temporal_raw_stack(np.full((4,4,4),100),SensorParameters(),(0,0,5,4))


def test_temporal_stack_rejects_too_few_frames():
    from aiforensics.sensor_noise import summarize_temporal_raw_stack
    with pytest.raises(SensorNoiseError):
        summarize_temporal_raw_stack(np.full((3,4,4),100),SensorParameters())


def test_cli_temporal_stack(tmp_path):
    data=np.full((6,8,9),128,dtype=np.uint16)
    np.save(tmp_path/'frames.npy',data)
    p=subprocess.run([sys.executable,'-m','aiforensics','summarize-raw-stack',
        '--npy',str(tmp_path/'frames.npy'),'--roi','2','3','6','7',
        '--out',str(tmp_path/'stats.json')],capture_output=True,text=True,timeout=25)
    assert p.returncode==0,p.stderr
    r=json.loads((tmp_path/'stats.json').read_text())
    assert r['roi_pixel_count']==16
    assert r['origin_verdict']=='NOT_EVALUATED'
