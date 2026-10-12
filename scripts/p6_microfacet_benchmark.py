"""P6-M02 controlled synthetic specular GGX stress; not real images.

Usage: python scripts/p6_microfacet_benchmark.py --trials 80
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.microfacet_physics import analyze_microfacet_manifest
from aiforensics.microfacet_synthetic import synthetic_microfacet_fixture


def benchmark(trials=80):
    if not 1<=trials<=10000:raise ValueError('trials must be in [1,10000]')
    episodes=[]
    for i in range(trials):
        mode='known_roughness' if i%2==0 else 'fit_roughness'
        manifest,truth=synthetic_microfacet_fixture(seed=270200+i,mode=mode,
            noise_sigma=.012 if i%3 else .023)
        report=analyze_microfacet_manifest(manifest)
        actual={r['id']:r['state'] for r in report['observations']}
        missed=sum(1 for k,v in truth['expected_holdout_states'].items()
                   if v=='INCONSISTENT_UNDER_ASSUMPTIONS' and actual[k]!='INCONSISTENT_UNDER_ASSUMPTIONS')
        false_alarms=sum(1 for k,v in truth['expected_holdout_states'].items()
                         if v=='CONSISTENT' and actual[k]=='INCONSISTENT_UNDER_ASSUMPTIONS')
        indeterminate=sum(1 for k,v in truth['expected_holdout_states'].items()
                          if v=='CONSISTENT' and actual[k]=='INDETERMINATE')
        estimate=report['fitted_or_known_roughness']
        episodes.append({'seed':i,'mode':mode,'roughness_error':abs(estimate-truth['roughness']) if estimate is not None else None,
                         'missed_corrupted':missed,'false_inconsistency_clean':false_alarms,
                         'indeterminate_clean':indeterminate,'state':report['state']})
    errors=[row['roughness_error'] for row in episodes if row['mode']=='fit_roughness' and row['roughness_error'] is not None]
    return {'module':'P6_M02_GGX_COOK_TORRANCE','dataset':'same-family controlled synthetic specular generator',
            'trials':trials,'known_roughness_cases':sum(e['mode']=='known_roughness' for e in episodes),
            'fit_roughness_cases':sum(e['mode']=='fit_roughness' for e in episodes),
            'solved_cases':sum(e['roughness_error'] is not None for e in episodes),
            'corrupted_per_trial':3,'total_corrupted':3*trials,'total_clean':21*trials,
            'missed_corrupted_total':sum(e['missed_corrupted'] for e in episodes),
            'false_inconsistency_clean_total':sum(e['false_inconsistency_clean'] for e in episodes),
            'indeterminate_clean_total':sum(e['indeterminate_clean'] for e in episodes),
            'roughness_fit_abs_error_median':float(np.median(errors)) if errors else None,
            'roughness_fit_abs_error_p90':float(np.percentile(errors,90)) if errors else None,
            'episodes':episodes,
            'limitations':['Ground truth generator and estimator share GGX/Schlick/Smith forward model.',
                           'No independent real camera radiometry, no measured material standards.',
                           'Conditional geometric/photometric consistency does not identify AI origin.',
                           'Only single-scattering specular lobe; no diffuse/multiple scattering.']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--trials',type=int,default=80)
    parser.add_argument('--out',type=Path,default=Path('outputs/p6_m02_benchmark.json'))
    args=parser.parse_args()
    report=benchmark(args.trials)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('episodes','limitations')},ensure_ascii=False))

if __name__=='__main__':main()
