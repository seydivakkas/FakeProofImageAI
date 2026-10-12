"""Controlled parametric sensitivity; not independent photographic validation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np

from aiforensics.static_equilibrium import evaluate_static_equilibrium
from aiforensics.static_equilibrium_synthetic import synthetic_equilibrium_fixture


def benchmark(n=80, noise_newton=1., seed=2503):
    rng=np.random.default_rng(seed)
    all_true=0; valid=0; counts={}; failed=[]
    for trial in range(n):
        sub_seed=int(rng.integers(0,2**31-1))
        d,truth=synthetic_equilibrium_fixture(seed=sub_seed,noise_newton=noise_newton)
        result=evaluate_static_equilibrium(d)
        predictions={x['id']:x['state'] for x in result['objects']}
        errors={k:dict(expected=truth[k],predicted=predictions[k]) for k in truth if truth[k]!=predictions[k]}
        if errors: failed.append({'trial':trial,'errors':errors})
        else:valid+=1
        for k in truth:
            counts[k]=counts.get(k,0)+int(predictions[k]==truth[k])
        all_true+=len(truth)
    return {'scenario':'controlled 3D rigid-body statics with independent known metric truth; stochastic horizontal force perturbations',
            'trials':n,'trial_exact_matches':valid,'observations':all_true,
            'observation_exact_matches':sum(counts.values()),
            'per_scenario_exact_matches':counts,'failures':failed[:30],
            'never_inferred':['true mass from image','friction from photo','AI image origin'],
            'deferred':['real photographs','real force plates','Windows device acceptance']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--noise-newton',type=float,default=1.)
    p.add_argument('--seed',type=int,default=2503)
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d03_benchmark.json'))
    a=p.parse_args()
    if a.trials<=0 or not np.isfinite(a.noise_newton) or a.noise_newton<0:
        p.error('trials must be positive and noise-newton finite nonnegative')
    r=benchmark(a.trials,a.noise_newton,a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'trials':r['trials'],'trial_exact_matches':r['trial_exact_matches'],
                      'observations':r['observations'],'observation_exact_matches':r['observation_exact_matches'],
                      'out':str(a.out)},ensure_ascii=False))
    if r['trial_exact_matches'] != r['trials']:sys.exit(2)

if __name__=='__main__':main()
