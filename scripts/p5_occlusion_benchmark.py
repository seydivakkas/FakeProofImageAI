"""Controlled P5-D02 benchmark; synthetic only. Negative and abstention accounting."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.depth_occlusion import evaluate_occlusion
from aiforensics.depth_occlusion_synthetic import synthetic_occlusion_fixture


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--trials', type=int, default=80)
    parser.add_argument('--out', type=Path, default=Path('outputs/p5_d02_benchmark.json'))
    args = parser.parse_args(argv)
    if not 1 <= args.trials <= 10000:
        parser.error('trials must be between 1 and 10000')
    predicted_correct = 0
    counts = {s:0 for s in ['CONSISTENT','INCONSISTENT_UNDER_ASSUMPTIONS','INDETERMINATE']}
    errors = []
    disagreements = []
    for seed in range(args.trials):
        noise=0.05+0.40*(seed%9)/8.0
        scene, truth=synthetic_occlusion_fixture(seed=202600+seed, noise_px=noise)
        result=evaluate_occlusion(scene)
        current={r['id']:r['state'] for r in result['observations']}
        for key,expect in truth.items():
            observed=current[key]
            counts[observed]+=1
            predicted_correct+=int(observed==expect)
            if observed!=expect:
                disagreements.append({'trial':seed,'id':key,'expected':expect,'actual':observed})
        for r in result['observations']:
            if r['kind']=='visibility' and len(r['ray_intersections'])>1:
                errors.append(r['ray_intersections'][1]['ray_depth_world']-r['ray_intersections'][0]['ray_depth_world'])
    total=7*args.trials
    summary={'module':'P5_D02_MULTIPLANE_OCCLUSION',
             'benchmark_type':'controlled synthetic calibrated camera, two opaque planes, independent annotations simulated',
             'trials':args.trials,'observations':total,'expected_classifications_correct':predicted_correct,
             'mismatches':len(disagreements),'examples_mismatched':disagreements[:25],
             'state_counts':counts,
             'median_two_plane_separation_along_ray_world':float(np.median(errors)) if errors else None,
             'synthetic_noise_px_range':[0.05,0.45],
             'real_photo_accuracy':'NOT_MEASURED',
             'ai_origin_attribution':'NOT_APPLICABLE'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return summary


if __name__=='__main__':
    main()
