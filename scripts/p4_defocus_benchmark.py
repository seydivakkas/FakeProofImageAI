"""P4-O02 synthetic, reproducible train/holdout and noise stress benchmark."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.defocus import analyze_defocus, DefocusError
from aiforensics.defocus_synthetic import synthetic_defocus_fixture


def run_benchmark(trials=80, *, seed=2026):
    if trials<1 or trials>10000:
        raise ValueError('trials must be 1..10000')
    rng=np.random.default_rng(int(seed))
    rows=[]
    for i in range(trials):
        fit=(i%2==1)
        sigma=float(rng.uniform(.07,.20))
        fixture,truth=synthetic_defocus_fixture(seed=int(rng.integers(0,2**31-1)),
            fit_focus=fit,corrupt=3,noise_px=sigma)
        try:
            r=analyze_defocus(fixture,seed=seed+i,mc_samples=128)
        except DefocusError as exc:
            rows.append({'trial':i,'state':'INDETERMINATE','reason':str(exc),
                'fit_focus':fit,'error_mm':None,'true_positive':0,'false_positive':0})
            continue
        judged=[x for x in r['results'] if x['state']!='INDETERMINATE']
        actual=set(truth['corrupted_ids'])
        anomalies=set(x['id'] for x in judged if x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS')
        err=abs(r['lens']['focus_distance_mm']-truth['focus_distance_mm'])
        rows.append({'trial':i,'state':r['state'],'fit_focus':fit,'focus_abs_error_mm':err,
                     'true_positive':len(actual&anomalies),'false_positive':len(anomalies-actual),
                     'false_negative':len(actual-anomalies),'test_count':len(judged)})
    completed=[r for r in rows if 'test_count' in r]
    failures=len(rows)-len(completed)
    e=[r['focus_abs_error_mm'] for r in completed if r['fit_focus']]
    return {'module':'P4_O02_THIN_LENS_DEFOCUS','experiment':'synthetic, known camera/depths and calibrated CoC simulator',
        'seed':seed,'trials':trials,'completed':len(completed),'failed_or_indeterminate':failures,
        'noise_px_range':[.07,.20],'injected_corrupt_holdout_per_trial':3,
        'total_tp':sum(r['true_positive'] for r in completed),
        'total_fp':sum(r['false_positive'] for r in completed),
        'total_fn':sum(r['false_negative'] for r in completed),
        'estimated_focus_trials':len(e),
        'focus_abs_error_mm_median_estimated':float(np.median(e)) if e else None,
        'focus_abs_error_mm_p90_estimated':float(np.percentile(e,90)) if e else None,
        'per_trial':rows,
        'not_measured':['real optical PSF deconvolution','real lens acceptance','real scene depth accuracy',
            'AI-generated image detection metrics','real Windows user acceptance']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o02_benchmark.json'))
    a=p.parse_args()
    result=run_benchmark(a.trials,seed=a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('per_trial','not_measured')},ensure_ascii=False))

if __name__=='__main__':main()
