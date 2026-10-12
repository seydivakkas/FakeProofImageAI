"""P6-M01 controlled synthetic stress, not photographic validation.

Usage: python scripts/p6_material_benchmark.py --trials 80
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.material_physics import analyze_material_manifest
from aiforensics.material_synthetic import synthetic_material_fixture


def benchmark(trials: int=80):
    if not 1<=trials<=10000:raise ValueError('trials must be between 1 and 10000')
    episodes=[]
    for seed in range(trials):
        mode='fit_albedo' if seed%2 else 'known_albedo'
        fixture,truth=synthetic_material_fixture(seed=260100+seed,mode=mode,
                                                  noise_sigma=.018 if seed%3 else .032)
        report=analyze_material_manifest(fixture)
        observed={r['id']:r['state'] for r in report['observations']}
        missed=sum(1 for k,v in truth['expected_holdout_states'].items()
                   if v=='INCONSISTENT_UNDER_ASSUMPTIONS' and observed[k]!='INCONSISTENT_UNDER_ASSUMPTIONS')
        false_alarm=sum(1 for k,v in truth['expected_holdout_states'].items()
                        if v=='CONSISTENT' and observed[k]=='INCONSISTENT_UNDER_ASSUMPTIONS')
        ambiguous=sum(1 for k,v in truth['expected_holdout_states'].items()
                      if v=='CONSISTENT' and observed[k]=='INDETERMINATE')
        err=float(np.linalg.norm(np.asarray(report['fitted_or_known_albedo_rgb'])-np.asarray(truth['albedo_rgb'])))
        episodes.append({'seed':seed,'calibration_mode':mode,'missed_corrupted':missed,
                         'false_inconsistency_clean':false_alarm,'ambiguous_clean':ambiguous,
                         'albedo_rgb_l2_error':err,'state':report['state']})
    errs=[r['albedo_rgb_l2_error'] for r in episodes if r['calibration_mode']=='fit_albedo']
    return {'module':'P6_M01','dataset':'controlled synthetic known-Lambertian generator',
            'trials':trials,'known_albedo_cases':sum(r['calibration_mode']=='known_albedo' for r in episodes),
            'fitted_albedo_cases':len(errs),'corrupted_per_trial':3,
            'total_corrupted':3*trials,'total_clean':21*trials,
            'missed_corrupted_total':sum(r['missed_corrupted'] for r in episodes),
            'false_inconsistency_clean_total':sum(r['false_inconsistency_clean'] for r in episodes),
            'ambiguous_clean_total':sum(r['ambiguous_clean'] for r in episodes),
            'estimated_albedo_l2_error_median':float(np.median(errs)) if errs else None,
            'estimated_albedo_l2_error_p90':float(np.percentile(errs,90)) if errs else None,
            'episodes':episodes,
            'limitations':['Same forward Lambertian model is used to create and fit data.',
                           'Not a check for real-world material identity.',
                           'No real camera, no spectral or scene illumination ground truth.',
                           'A clean measurement can be indeterminate without being a false alarm.',
                           'Cannot estimate AI origin, sensitivity or real-world false positive rate.']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m01_benchmark.json'))
    args=p.parse_args()
    res=benchmark(args.trials)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(res,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in res.items() if k not in ('episodes','limitations')},ensure_ascii=False))

if __name__=='__main__':main()
