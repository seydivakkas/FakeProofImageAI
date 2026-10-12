"""Deterministic synthetic P4-O03 benchmark. Not a real-camera validation."""
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.optical_synthetic import synthetic_optical_fixture
from aiforensics.optical_consistency import analyze_optical_manifest


def run(trials=80):
    if trials<1:raise ValueError('trials must be positive')
    rows=[]
    for i in range(trials):
        fit=(i%2==1)
        fixture,truth=synthetic_optical_fixture(seed=31000+i,fit_focal=fit,corrupt=3)
        result=analyze_optical_manifest(fixture)
        bad=[r['id'] for r in result['holdout_results'] if r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS']
        errors=[r['residual_px'] for r in result['holdout_results'] if r['state']=='CONSISTENT']
        rows.append({'seed':31000+i,'fit_focal_from_train':fit,'state':result['state'],
                     'known_corrupt':truth['corrupted_ids'],'detected_corrupt':bad,
                     'correct_corrupt_ids':set(bad)==set(truth['corrupted_ids']),
                     'focal_fx_error_px':abs(result['K'][0][0]-truth['K'][0][0]),
                     'focal_fy_error_px':abs(result['K'][1][1]-truth['K'][1][1]),
                     'clean_holdout_rmse_px':float(np.sqrt(np.mean(np.square(errors)))) if errors else None})
    fit_errors=[r['focal_fx_error_px'] for r in rows if r['fit_focal_from_train']]
    rmses=[r['clean_holdout_rmse_px'] for r in rows if r['clean_holdout_rmse_px'] is not None]
    return {'module':'P4_O03','model':'controlled known-pose pinhole camera and annotated pixel points',
            'trials':trials,'exact_corruption_detection_trials':sum(r['correct_corrupt_ids'] for r in rows),
            'fit_trials':sum(r['fit_focal_from_train'] for r in rows),
            'known_K_trials':sum(not r['fit_focal_from_train'] for r in rows),
            'fitted_fx_absolute_error_median_px':float(np.median(fit_errors)) if fit_errors else None,
            'fitted_fx_absolute_error_p90_px':float(np.percentile(fit_errors,90)) if fit_errors else None,
            'clean_holdout_rmse_median_px':float(np.median(rmses)) if rmses else None,
            'rows':rows,'status':'SYNTHETIC_ONLY','decision':'NO_AI_ORIGIN_CONCLUSION'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o03_benchmark.json'))
    args=p.parse_args()
    result=run(args.trials);args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
