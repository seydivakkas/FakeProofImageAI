"""Conditional forward/inverse reproducibility benchmark, NEVER real-data accuracy."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.penumbra import analyze_penumbra_manifest, PenumbraConfig
from aiforensics.penumbra_synthetic import synthetic_penumbra_fixture


def benchmark(trials:int=80)->dict:
    if trials < 1:raise ValueError('trials >= 1 required')
    errors=[];fails=[];negative=[]; shapes=('UNIFORM_DISK', 'UNIFORM_STRIP')
    for seed in range(trials):
        truth_angle=.5+(seed%11)*.19
        fixture,truth=synthetic_penumbra_fixture(
            angle_deg=truth_angle,seed=seed+900,noise_sigma=.003+(seed%4)*.002,
            heights=(1.6,2.4,3.2,4.0),px_per_meter=125,
            shapes=(shapes[seed%2],))
        result=analyze_penumbra_manifest(fixture)
        if result['state']=='CONSISTENT_UNDER_ASSUMPTIONS':
            errors.append(abs(result['angular_diameter_median_deg']-truth_angle))
        else:
            fails.append({'seed':seed,'state':result['state'],'reason':result['reason']})
        # Two true source angular sizes forced into the same alleged group.
        if seed%5==0:
            mixed,_=synthetic_penumbra_fixture(
                angle_deg=1.1, seed=seed+1200,noise_sigma=.002,malformed_source=1,
                heights=(1.6,2.4,3.2,4.0))
            outcome=analyze_penumbra_manifest(mixed)
            negative.append({'seed':seed,'state':outcome['state']})
    return {'module':'P2_S05','scenario':'uniform extended-source near-normal knife-edge 1D linear irradiance; known per-edge geometric scales; synthetic Gaussian measurement noise',
            'trials':trials,'successful_consistent_cases':len(errors),
            'failures':fails,'absolute_angle_error_median_deg_on_success':float(np.median(errors)) if errors else None,
            'absolute_angle_error_p90_deg_on_success':float(np.percentile(errors,90)) if errors else None,
            'negative_mixed_source_cases':len(negative),
            'negative_mixed_source_flagged':sum(x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for x in negative),
            'negative_case_outcomes':negative,
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'not_measured':['real camera photometric response and PSF',
                            'field detector localization/recall',
                            'real sun angular-size error',
                            'AI origin or manipulation diagnosis']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p2_s05_benchmark.json'))
    args=p.parse_args()
    r=benchmark(args.trials)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k not in ('failures','negative_case_outcomes')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
