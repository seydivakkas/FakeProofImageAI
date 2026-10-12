"""Repeatable synthetic P4-O04 stress tests (NOT real-photo validation)."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
from aiforensics.vignetting_synthetic import synthetic_vignetting_fixture
from aiforensics.vignetting import analyze_vignetting_manifest

def run(trials=80):
    if trials<1:raise ValueError('trials must be >=1')
    rows=[]
    for i in range(trials):
        mode='fit_radial_and_center' if i%2 else 'fit_radial'
        data,truth=synthetic_vignetting_fixture(seed=18000+i,mode=mode,corrupt=3,noise_sigma=.0015)
        result=analyze_vignetting_manifest(data)
        params=result.get('parameters')
        bad={x['id'] for x in result.get('holdout_results',[]) if x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'}
        rows.append({'seed':18000+i,'mode':mode,'state':result['state'],
                     'exact_corrupt_ids':bad==set(truth['corrupted_ids']),
                     'true_corrupt_ids':sorted(truth['corrupted_ids']),'detected_corrupt_ids':sorted(bad),
                     'a2_error':abs(params['radial_log_a2']-truth['a2']) if params else None,
                     'a4_error':abs(params['radial_log_a4']-truth['a4']) if params else None,
                     'shift_error_norm':float(np.linalg.norm(np.asarray(params['radial_center_offset_normalized_xy'])-truth['center_xy'])) if params else None,
                     'holdout_rmse_linear':result.get('holdout_linear_rmse')})
    a2=[r['a2_error'] for r in rows if r['a2_error'] is not None]
    centers=[r['shift_error_norm'] for r in rows if r['mode']=='fit_radial_and_center' and r['shift_error_norm'] is not None]
    return {'module':'P4_O04','validation':'SYNTHETIC_ONLY',
            'trials':trials,'successful_model_fits':sum(r['state'] in ('CONSISTENT','INCONSISTENT_UNDER_ASSUMPTIONS') for r in rows),
            'exact_corruption_detection_trials':sum(r['exact_corrupt_ids'] for r in rows),
            'corrupt_samples_per_trial':3,
            'median_absolute_a2_error':float(np.median(a2)) if a2 else None,
            'p90_absolute_a2_error':float(np.percentile(a2,90)) if a2 else None,
            'median_normalized_center_error_shift_fit':float(np.median(centers)) if centers else None,
            'rows':rows,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'limitations':['same synthetic generator and fit model','real cameras, false positive rate, ISP, unknown exposure not measured']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o04_benchmark.json'))
    args=p.parse_args();r=run(args.trials)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(r,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k!='rows'},indent=2))
if __name__=='__main__':main()
