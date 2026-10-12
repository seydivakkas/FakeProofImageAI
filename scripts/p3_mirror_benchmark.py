"""Synthetic stress study of a calibrated finite planar mirror, with reproducible seeds."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.mirror_geometry import analyze_mirror_manifest
from aiforensics.mirror_synthetic import synthetic_mirror_scene


def run(trials=80, out=Path('outputs/p3_r01_benchmark.json')):
    if trials<1:raise ValueError('trials must be positive')
    counts=[];errors=[];failed=[]
    for seed in range(trials):
        manifest,_,truth=synthetic_mirror_scene(n=18,noise_px=.45,corrupt=3,seed=seed)
        rep=analyze_mirror_manifest(manifest,tolerance_px=3)
        good=rep['consistent_count']; bad=rep['inconsistent_count']
        errors.extend(row['reprojection_residual_px'] for row in rep['correspondences'] if
                      row['status']=='CONSISTENT_UNDER_ASSUMPTIONS')
        success=(good==truth['known_good'] and bad==truth['known_corrupted'] and rep['indeterminate_count']==0)
        counts.append({'seed':seed,'consistent':good,'inconsistent':bad,
                       'indeterminate':rep['indeterminate_count'],'exact_known_assignment':success})
        if not success:failed.append(seed)
    result={'scenario':'controlled known-K/R/t planar mirror 18 point pairs, 0.45px Gaussian noise and 3 deliberate corruptions',
            'trials':trials,'correct_assignments':trials-len(failed),'failed_seeds':failed,
            'median_consistent_reprojection_error_px':float(np.median(errors)) if errors else None,
            'p90_consistent_reprojection_error_px':float(np.percentile(errors,90)) if errors else None,
            'threshold_px':3,'records':counts,
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'limitations':['same synthetic generator for every trial; no independent real photography',
                           'test does not estimate K, mirror plane or independent 3D object points from pixels',
                           'not a test of automatic correspondence discovery or scene occlusion']}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p3_r01_benchmark.json'))
    args=p.parse_args()
    result=run(args.trials,args.out)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2))
