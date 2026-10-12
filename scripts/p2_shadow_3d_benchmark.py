"""P2-S03 controlled, repeatable 3D source-error trials; no real images."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.shadow_3d import analyze_shadow_3d, Shadow3DConfig
from aiforensics.shadow_3d_synthetic import synthetic_shadow3d_scene


def run_benchmark(trials=60,seed=518):
    if trials<1:raise ValueError('trials must be >=1')
    rng=np.random.default_rng(seed)
    details=[];errors=[]
    for i in range(trials):
        noise=float(rng.uniform(.0,.30))
        bad=int(rng.integers(0,4))
        scene,_,truth=synthetic_shadow3d_scene(n=19,seed=int(rng.integers(0,2**25)),noise_px=noise,bad_pairs=bad)
        result=analyze_shadow_3d(scene,Shadow3DConfig(seed=seed+i))
        g=result['model_groups'][0]
        ok=g['state']=='MEASURED' and g['model_class']=='FINITE_POINT_LIGHT'
        error=float(np.linalg.norm(np.asarray(g['source_xyz_world'])-truth['fixture_01']['position'])) if ok else None
        if error is not None:errors.append(error)
        details.append({'trial':i,'noise_sigma_px':noise,'wrong_pairs':bad,
                        'fit_measured':bool(ok),'source_position_error_world':error,
                        'inliers':len(g['inlier_ids'])})
    return {'module':'P2_S03_SYNTHETIC_3D_BENCHMARK','trials':trials,
            'finite_light_recoveries':len(errors),
            'median_world_position_error_on_recovery':float(np.median(errors)) if errors else None,
            'p90_world_position_error_on_recovery':float(np.percentile(errors,90)) if errors else None,
            'world_units':'m', 'independent_real_validation':'DEFERRED',
            'decision':'NO_AI_ORIGIN_CONCLUSION','seed':seed,'details':details}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=60)
    p.add_argument('--seed',type=int,default=518)
    p.add_argument('--out',type=Path,default=Path('outputs/p2_s03_benchmark.json'))
    a=p.parse_args()
    r=run_benchmark(a.trials,a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k!='details'},ensure_ascii=False))
if __name__=='__main__':main()
