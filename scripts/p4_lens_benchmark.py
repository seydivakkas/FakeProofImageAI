"""Run repeatable known-truth synthetic Brown–Conrady tests; no field accuracy claims."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.lens_synthetic import synthetic_lens_scene
from aiforensics.lens_distortion import analyze_manifest


def run(trials=60):
    errors=[];rmse=[];failures=[]
    for seed in range(int(trials)):
        fixture,_,truth=synthetic_lens_scene(seed=seed,noise_px=.18)
        report=analyze_manifest(fixture)
        if report['state']!='CONSISTENT_UNDER_ASSUMPTIONS':
            failures.append({'seed':seed,'state':report['state'],'reason':report.get('reason')})
            continue
        errors.append(np.abs(np.array(report['coefficients'])-np.array(truth['coefficients'])))
        rmse.append(report['holdout_rmse_px'])
    return {'module':'P4_O01','evaluation':'SYNTHETIC_ONLY','trials':trials,
            'successful':len(errors),'failed':len(failures),'failure_details':failures,
            'holdout_rmse_median_px':float(np.median(rmse)) if rmse else None,
            'holdout_rmse_p90_px':float(np.percentile(rmse,90)) if rmse else None,
            'coefficient_abs_error_median_by_component':np.median(errors,axis=0).tolist() if errors else None,
            'not_measured':['real-camera calibration','AI detection performance','false positive rate']}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--trials',type=int,default=60)
    ap.add_argument('--out',type=Path,default=Path('outputs/p4_o01_benchmark.json'))
    ns=ap.parse_args()
    if ns.trials<1:ap.error('trials must be positive')
    report=run(ns.trials)
    ns.out.parent.mkdir(parents=True,exist_ok=True)
    ns.out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':main()
