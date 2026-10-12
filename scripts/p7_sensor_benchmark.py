"""Same-family simulated RAW measurements; never a real-camera/AI detection benchmark."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
from aiforensics.sensor_noise import analyze_sensor_manifest
from aiforensics.sensor_synthetic import synthetic_sensor_fixture


def run(trials=80,seed=310100):
    if trials<1:raise ValueError('trials must be positive')
    counts={'CONSISTENT':0,'INCONSISTENT_UNDER_ASSUMPTIONS':0,'INDETERMINATE':0}
    total_good=total_bad=detected_bad=false_strict=unknown_good=0
    param_err=[];cases=[]
    for i in range(trials):
        mode='known_parameters' if i%2==0 else 'fit_train_parameters'
        data,truth=synthetic_sensor_fixture(seed=seed+i,mode=mode)
        rep=analyze_sensor_manifest(data)
        for key in counts: counts[key]+=rep['counts'][key]
        found={r['id']:r['state'] for r in rep['observations']}
        for sid,expected in truth['expected_states'].items():
            if expected=='CONSISTENT':
                total_good+=1
                false_strict+=found[sid]=='INCONSISTENT_UNDER_ASSUMPTIONS'
                unknown_good+=found[sid]=='INDETERMINATE'
            else:
                total_bad+=1
                detected_bad+=found[sid]=='INCONSISTENT_UNDER_ASSUMPTIONS'
        if mode=='fit_train_parameters':
            param_err.append(abs(rep['parameters']['gain_e_per_adu']-truth['true_sensor']['gain_e_per_adu']))
        cases.append({'seed':seed+i,'mode':mode,'counts':rep['counts'],
                      'state':rep['state']})
    negatives={}
    for key in ('jpeg_input','unknown_photon_flux','temperature_uncontrolled',
                'sensor_saturation','unverified_sensor','fixed_pattern_noise'):
        data,_=synthetic_sensor_fixture(seed=seed+5000)
        if key=='jpeg_input':data['input_domain']='jpeg_gamma_encoded'
        elif key=='unknown_photon_flux':data['measurements'][-1]['photoelectron_provenance']='estimated_from_jpeg'
        elif key=='temperature_uncontrolled':data['stable_temperature']=False
        elif key=='sensor_saturation':data['measurements'][-1]['saturation_fraction']=.3
        elif key=='unverified_sensor':data['sensor_provenance']='guess'
        elif key=='fixed_pattern_noise':data['prnu_or_fpn_controlled']=False
        rep=analyze_sensor_manifest(data)
        negatives[key]=rep['state'] if key not in ('unknown_photon_flux','sensor_saturation') else rep['observations'][-1]['state']
    return {'module':'P7_S01_SYNTHETIC_SENSOR_NOISE_BENCHMARK',
            'trials':trials,'random_seed_start':seed,
            'counts':counts,'true_clean':total_good,'true_corrupted':total_bad,
            'corrupted_detected':detected_bad,'false_strict_on_clean':false_strict,
            'indeterminate_clean':unknown_good,
            'gain_abs_error_e_per_adu_median_fit_only':float(np.median(param_err)) if param_err else None,
            'gain_abs_error_e_per_adu_p90_fit_only':float(np.quantile(param_err,.9)) if param_err else None,
            'negative_controls':negatives,'cases':cases,
            'scope':'known-truth Poisson+Gaussian linear sensor simulation; no PRNU, real-world acceptance or AI-origin detection'}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--seed',type=int,default=310100)
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s01_benchmark.json'))
    a=p.parse_args();r=run(a.trials,a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:r[k] for k in ('trials','counts','true_corrupted','corrupted_detected',
                                        'false_strict_on_clean','indeterminate_clean',
                                        'gain_abs_error_e_per_adu_median_fit_only')},ensure_ascii=False))
