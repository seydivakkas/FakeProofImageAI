"""P6-M03 deterministic synthetic performance only. No real-photo claims."""
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.combined_material import analyze_combined_manifest
from aiforensics.combined_material_synthetic import synthetic_combined_fixture


def run(trials=80, seed=285000):
    counted={'CONSISTENT':0,'INCONSISTENT_UNDER_ASSUMPTIONS':0,'INDETERMINATE':0}
    true_good=0; true_bad=0; false_strict=0; detected_bad=0; uncertain_good=0
    albedo_errors=[];cases=[]
    for i in range(trials):
        mode='known_material' if i%2==0 else 'fit_diffuse_albedo'
        policy='bounded_diffuse_proxy' if i%4==2 else 'assumed_negligible'
        data,truth=synthetic_combined_fixture(seed=seed+i,mode=mode,policy=policy)
        report=analyze_combined_manifest(data)
        counted={key:counted[key]+report['counts'][key] for key in counted}
        if mode=='fit_diffuse_albedo':
            albedo_errors.append(float(np.linalg.norm(np.array(report['albedo_rgb_by_material']['paint01'])-
                                                       truth['true_diffuse_albedo_rgb'])))
        ids={r['id']:r['state'] for r in report['observations']}
        for sid,expected in truth['expected_holdout_states'].items():
            found=ids[sid]
            if expected=='CONSISTENT':
                true_good+=1
                false_strict+=(found=='INCONSISTENT_UNDER_ASSUMPTIONS')
                uncertain_good+=(found=='INDETERMINATE')
            else:
                true_bad+=1
                detected_bad+=(found=='INCONSISTENT_UNDER_ASSUMPTIONS')
        cases.append({'seed':seed+i,'mode':mode,'policy':policy,'state':report['state'],'counts':report['counts']})
    # Negative controls: provenance issues should never be turned into proof.
    negatives={}
    for key in ('unknown_light','unknown_multiscattering','unverified_proxy'):
        fixture,_=synthetic_combined_fixture(seed=seed+1000,mode='known_material',policy='bounded_diffuse_proxy')
        if key=='unknown_light':fixture['light_provenance']='inferred_from_JPEG'
        elif key=='unknown_multiscattering':fixture['materials']['paint01']['multiscattering_policy']='unknown';fixture['materials']['paint01']['multiscatter_proxy_weight']=0
        else:fixture['materials']['paint01']['multiscatter_proxy_provenance']='unverified'
        negatives[key]=analyze_combined_manifest(fixture)['state']
    return {'module':'P6_M03_CONTROLLED_SYNTHETIC_BENCHMARK','trials':trials,'random_seed_start':seed,
            'observations_per_trial':24,'intentionally_corrupted_per_trial':3,
            'counts':counted,'true_consistent':true_good,'true_corrupted':true_bad,
            'corrupted_detected':detected_bad,'false_strict_violations_on_clean':false_strict,
            'indeterminate_clean':uncertain_good,
            'albedo_error_l2_median_fit_only':float(np.median(albedo_errors)) if albedo_errors else None,
            'albedo_error_l2_p90_fit_only':float(np.quantile(albedo_errors,.9)) if albedo_errors else None,
            'negative_controls':negatives,'cases':cases,
            'scope':'same-family synthetic generator; not real material or AI detection validation'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--trials',type=int,default=80)
    parser.add_argument('--seed',type=int,default=285000)
    parser.add_argument('--out',type=Path,default=Path('outputs/p6_m03_benchmark.json'))
    args=parser.parse_args()
    report=run(args.trials,args.seed)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k in
                      ('trials','counts','corrupted_detected','true_corrupted',
                       'false_strict_violations_on_clean','indeterminate_clean',
                       'albedo_error_l2_median_fit_only')},ensure_ascii=False))
