"""P7-S02 synthetic fixed-pattern identification stress test, NOT camera FPR."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from aiforensics.sensor_fingerprint import analyze_fingerprint_manifest
from aiforensics.sensor_fingerprint_synthetic import write_synthetic_fingerprint_fixture


def run(trials:int=80,seed:int=420200,frames:int=20)->dict:
    if trials<1 or frames<8:raise ValueError('trials>=1 and frames>=8 required')
    counts={'true_match':0,'true_nonmatch':0,'unresolved':0,'wrong_definitive':0}
    good_r=[];bad_r=[];cases=[]
    with TemporaryDirectory(prefix='p7s02_bench_') as td:
        root=Path(td)
        for i in range(trials):
            path,truth=write_synthetic_fingerprint_fixture(root,seed=seed+i,frames=frames)
            data=json.loads(path.read_text(encoding='utf-8'))
            report=analyze_fingerprint_manifest(data,base_dir=root,controlled_synthetic_evaluation=True)
            outcomes={q['id']:q for q in report['queries']}
            a=outcomes['same_sensor'];b=outcomes['wrong_sensor']
            if a['state']=='CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS':counts['true_match']+=1
            elif a['state']=='INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS':counts['wrong_definitive']+=1
            else:counts['unresolved']+=1
            if b['state']=='INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS':counts['true_nonmatch']+=1
            elif b['state']=='CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS':counts['wrong_definitive']+=1
            else:counts['unresolved']+=1
            good_r.append(a['prnu_pearson_r']);bad_r.append(b['prnu_pearson_r'])
            cases.append({'seed':seed+i,'same':a['state'],'wrong':b['state']})
    return {'module':'P7_S02_SYNTHETIC_PRNU_DSNU_BENCHMARK',
            'trials':trials,'frames_per_stack':frames,'random_seed':seed,
            'counts':counts,'median_same_prnu_r':float(np.median(good_r)),
            'median_wrong_prnu_r':float(np.median(bad_r)),
            'cases':cases,'scope':'controlled independent-pixel synthetic RAW fixed patterns; no real-sensor error calibration, no AI-origin conclusion'}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--seed',type=int,default=420200)
    p.add_argument('--frames',type=int,default=20)
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s02_benchmark.json'))
    a=p.parse_args();r=run(a.trials,a.seed,a.frames)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({'trials':a.trials,**r['counts'],'median_same_prnu_r':r['median_same_prnu_r'],
                      'median_wrong_prnu_r':r['median_wrong_prnu_r']}))
