"""P2-S01 repeatable *synthetic-only* quantitative stress benchmark."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.shadow_geometry import fit_projected_light, ShadowConfig
from aiforensics.shadow_synthetic import synthetic_shadow_scene


def run(trials:int=60):
    if trials<1: raise ValueError('trials must be positive')
    errors=[]; missing=0; supports=[]; misses=[]
    for seed in range(trials):
        data,_,true=synthetic_shadow_scene(n=20,seed=seed+1000,noise_px=.35,outliers=3)
        result=fit_projected_light(data,ShadowConfig(seed=seed+3000,bootstrap_trials=0))
        if result['state']!='MEASURED' or result['projected_convergence_xy_px'] is None:
            missing+=1
            continue
        errors.append(float(np.linalg.norm(np.asarray(result['projected_convergence_xy_px'])-true)))
        supports.append(result['inlier_count'])
        # Last 3 shadow pairs are deliberately mismatched.
        misses.append(len(set(result['outlier_ids']) & {f'shadow_{i:02d}' for i in range(17,20)}))
    return {
        'protocol':'3D point lights projected through synthetic pinhole camera; object-to-shadow pairs are provided',
        'seed_policy':'deterministic per-trial source and estimator seeds',
        'trials':trials, 'point_pairs_per_trial':20,'mismatched_pairs_per_trial':3,
        'endpoint_noise_gaussian_sigma_px':.35,
        'successful_2d_convergence_fits':len(errors), 'indeterminate':missing,
        'projected_source_error_median_px_successes':float(np.median(errors)) if errors else None,
        'projected_source_error_p90_px_successes':float(np.percentile(errors,90)) if errors else None,
        'projected_source_error_max_px_successes':float(np.max(errors)) if errors else None,
        'median_inliers_successes':float(np.median(supports)) if supports else None,
        'mean_correct_rejected_deliberately_mismatched_pairs_successes':float(np.mean(misses)) if misses else None,
        'not_measured':['real-world cameras','real cast-shadow pixel correspondences',
                        'automated shadow extraction','real-image false positive rate','AI detection accuracy'],
        'decision':'NO_AI_ORIGIN_CONCLUSION'
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--trials',type=int,default=60)
    ap.add_argument('--out',type=Path,default=Path('outputs/p2_s01_benchmark.json'))
    args=ap.parse_args()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    r=run(args.trials)
    args.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(r,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
