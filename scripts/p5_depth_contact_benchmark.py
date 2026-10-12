"""Controlled synthetic benchmark only, not calibrated real-image FPR."""
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.depth_contact import evaluate_contact
from aiforensics.depth_contact_synthetic import synthetic_depth_contact_fixture


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d01_benchmark.json'))
    args=p.parse_args()
    if args.trials < 1: p.error('--trials must be positive')
    count=0; total=0
    statuses={}
    failures=[]
    true_positive_reprojection_errors=[]
    for i in range(args.trials):
        sigma=.15+.75*(i%10)/9
        d,truth=synthetic_depth_contact_fixture(seed=700+i,noise_px=sigma)
        result=evaluate_contact(d)
        est={r['id']:r for r in result['observations']}
        trial_success=True
        for name,expected in truth.items():
            total+=1
            actual=est[name]['state']
            statuses.setdefault(expected,{}).setdefault(actual,0)
            statuses[expected][actual]+=1
            correct=actual==expected
            count+=int(correct)
            trial_success&=correct
            if not correct:
                failures.append({'trial':i,'id':name,'expected':expected,'actual':actual,'sigma_px':sigma})
            if expected=='CONSISTENT':
                true_positive_reprojection_errors.append(est[name].get('upright_top_reprojection_error_px',np.nan))
    arr=np.array(true_positive_reprojection_errors,float)
    wrong_physical_verdicts=sum(
        v for expected, actual in statuses.items() for state,v in actual.items()
        if ((expected=='CONSISTENT' and state=='INCONSISTENT_UNDER_ASSUMPTIONS')
            or (expected=='INCONSISTENT_UNDER_ASSUMPTIONS' and state=='CONSISTENT')))
    extra_abstentions=sum(v for expected, actual in statuses.items() for state,v in actual.items()
                          if expected!='INDETERMINATE' and state=='INDETERMINATE')
    output={'scenario':'synthetic independently known K/R/t, support polygon, metric heights and anchors',
            'trials':args.trials,'observations_per_trial':9,'total_observation_checks':total,
            'correct_conditional_classifications':count,
            'incorrect_conditional_classifications':total-count,
            'all_correct_trials':args.trials-len(set(e['trial'] for e in failures)),
            'wrong_physical_verdicts':wrong_physical_verdicts,
            'additional_ambiguity_abstentions':extra_abstentions,
            'labels':{'consistent':'independently constrained','inconsistent':'deliberately changed geometry','indeterminate':'no independent contact evidence'},
            'by_expected_actual':statuses,
            'valid_upright_top_median_error_px':float(np.nanmedian(arr)),
            'valid_upright_top_p90_error_px':float(np.nanpercentile(arr,90)),
            'failures':failures[:100],
            'not_measured':['real photo 3D ground truth', 'real object contact FPR', 'AI provenance', 'Windows end-user acceptance'],
            'decision':'NO_AI_ORIGIN_CONCLUSION'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:output[k] for k in ['trials','correct_conditional_classifications','total_observation_checks','all_correct_trials','wrong_physical_verdicts','additional_ambiguity_abstentions','valid_upright_top_median_error_px']},indent=2))

if __name__=='__main__':main()
