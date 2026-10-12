"""P3-R03 controlled seed sweep; never interpreted as real-world classification."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.mirror_chain import evaluate_multi_mirror
from aiforensics.mirror_chain_synthetic import synthetic_two_mirror_scene


def run(trials=60,out=Path('outputs/p3_r03_benchmark.json')):
    if trials<1:raise ValueError('trials must be >= 1')
    records=[];successful_errors=[];failed=[]
    for seed in range(trials):
        manifest,_,truth=synthetic_two_mirror_scene(n=20,corrupt=3,noise_px=.45,seed=seed)
        report=evaluate_multi_mirror(manifest,tolerance_px=3.)
        correct=(report['consistent_count']==truth['known_good'] and
                 report['inconsistent_count']==truth['known_corrupt'] and
                 report['indeterminate_count']==0)
        if not correct:failed.append(seed)
        successful_errors.extend(item['reprojection_residual_px'] for item in report['correspondences']
                                 if item['status']=='CONSISTENT_UNDER_ASSUMPTIONS')
        records.append({'seed':seed,'correct_assignment':correct,'consistent':report['consistent_count'],
                        'inconsistent':report['inconsistent_count'],'indeterminate':report['indeterminate_count']})
    result={'module':'P3_R03_MULTI_MIRROR_RAY_CHAIN',
            'scenario':'fixed two finite perpendicular mirrors; known calibrated pinhole camera; '
                       '20 ideal 3D points, Gaussian .45px noise, 3 deliberately corrupted image correspondences',
            'trials':trials,'exact_known_assignments':trials-len(failed),'failed_seeds':failed,
            'median_inlier_reprojection_error_px':float(np.median(successful_errors)) if successful_errors else None,
            'p90_inlier_reprojection_error_px':float(np.percentile(successful_errors,90)) if successful_errors else None,
            'records':records,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'limitations':['all samples use a single simulated two-mirror arrangement',
                           'no independent real photos or fitted camera/mirror calibration',
                           'known object-to-camera bounce order, not estimated',
                           'synthetic precision is not real-world authenticity accuracy']}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--trials',type=int,default=60)
    parser.add_argument('--out',type=Path,default=Path('outputs/p3_r03_benchmark.json'))
    args=parser.parse_args()
    r=run(args.trials,args.out)
    print(json.dumps({k:v for k,v in r.items() if k!='records'},ensure_ascii=False,indent=2))
