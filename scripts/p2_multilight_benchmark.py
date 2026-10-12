"""P2-S02 controlled multilight synthetic stress/quality report.

Not real-image evaluation; uses known 3D source and point/shadow ray geometry.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from aiforensics.shadow_multilight import MultiLightConfig, fit_multiple_projected_lights
from aiforensics.shadow_multi_synthetic import synthetic_multilight_scene


def run_benchmark(trials=60, seed=506, *, bootstrap=0):
    rng=np.random.default_rng(seed)
    errors=[];family_recalls=[];precision=[];wrong_rejection=[];results=[]
    for t in range(trials):
        local_seed=int(rng.integers(10,2**25))
        noise=float(rng.uniform(.1,.65))
        wrong=int(rng.integers(1,5))
        n=int(rng.integers(8,15))
        data,_,truth=synthetic_multilight_scene(per_light=n, seed=local_seed,
                             noise_px=noise,bad_pairs=wrong)
        report=fit_multiple_projected_lights(data,MultiLightConfig(seed=seed+t,bootstrap_trials=bootstrap))
        expected=np.asarray(list(truth['points_px'].values()),float)
        got=np.asarray([m['projected_convergence_xy_px'] for m in report['models']
                        if m['projected_convergence_xy_px'] is not None],float).reshape(-1,2)
        got_families=report['models']
        correct=(report['state']=='MEASURED' and len(got_families)==2 and len(got)==2)
        error=None
        if correct:
            dist=np.linalg.norm(got[:,None,:]-expected[None,:,:],axis=2)
            ix, jx=linear_sum_assignment(dist)
            error=float(np.median(dist[ix,jx]))
            errors.extend([float(z) for z in dist[ix,jx]])
            trueids=[set(x) for x in truth['groups'].values()]
            retrieved=[set(m['member_ids']) for m in got_families]
            recalls=[];precisions=[]
            for idx,jdx in zip(ix,jx):
                hit=len(retrieved[idx] & trueids[jdx]);recalls.append(hit/len(trueids[jdx]))
                precisions.append(hit/max(1,len(retrieved[idx])))
            family_recalls.extend(recalls)
            precision.extend(precisions)
            wrong_rejection.append(sum(f'wrong_{i:02d}' in report['unassigned_ids']
                                       for i in range(wrong))/wrong)
        results.append({'trial':t,'valid_two_family_recovery':correct,'model_count':len(got_families),
                        'noise_px':noise,'wrong_pair_count':wrong,'pairs_per_family':n,
                        'median_projected_point_error_px':error})
    recovered=sum(x['valid_two_family_recovery'] for x in results)
    def _med(v):return float(np.median(v)) if v else None
    def _p90(v):return float(np.percentile(v,90)) if v else None
    return {'module':'P2_S02_SYNTHETIC_MULTILIGHT_BENCHMARK', 'trials':trials,
            'two_source_recovery_count':recovered,
            'two_source_recovery_fraction':recovered/trials,
            'median_projected_light_point_error_px_when_recovered':_med(errors),
            'p90_projected_light_point_error_px_when_recovered':_p90(errors),
            'median_group_assignment_recall_when_recovered':_med(family_recalls),
            'median_group_assignment_precision_when_recovered':_med(precision),
            'median_wrong_pair_rejection_when_recovered':_med(wrong_rejection),
            'random_seed':seed,
            'independent_real_image_validation':'DEFERRED',
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'method_note':'Evaluation labels come from controlled 3D scene generation, not real photographs.',
            'trials_detail':results}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=60)
    p.add_argument('--seed',type=int,default=506)
    p.add_argument('--out',type=Path,default=Path('outputs/p2_s02_benchmark.json'))
    a=p.parse_args()
    if a.trials < 1: p.error('trials must be positive')
    r=run_benchmark(a.trials,a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k!='trials_detail'},ensure_ascii=False))

if __name__=='__main__':main()
