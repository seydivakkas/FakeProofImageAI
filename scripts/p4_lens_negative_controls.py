"""Synthetic negative controls: independent residuals and post-correction straightness."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from aiforensics.lens_synthetic import synthetic_lens_scene
from aiforensics.lens_distortion import analyze_manifest


def run():
    scene,_,_=synthetic_lens_scene(seed=67,noise_px=.14)
    good=analyze_manifest(scene)
    bad_holdout=copy.deepcopy(scene)
    h=[x for x in bad_holdout['point_pairs'] if x['role']=='holdout']
    for x in h[:10]: x['observed_xy_px'][0]+=20
    bad_line=copy.deepcopy(scene)
    line=bad_line['independent_straight_lines'][0]['observed_points_xy_px']
    line[14][1]+=35
    bad_provenance=copy.deepcopy(scene);bad_provenance.pop('data_provenance')
    cases={'baseline':good,'corrupted_holdout':analyze_manifest(bad_holdout),
        'corrupted_line':analyze_manifest(bad_line),
        'missing_provenance':analyze_manifest(bad_provenance)}
    return {'evaluation':'SYNTHETIC_ONLY','scenarios':{
            k:{'state':v['state'],'holdout_rmse_px':v.get('holdout_rmse_px'),
               'line_holdouts':v.get('line_holdouts'), 'reason':v.get('reason')}
            for k,v in cases.items()},
        'expected_states':{'baseline':'CONSISTENT_UNDER_ASSUMPTIONS',
           'corrupted_holdout':'INCONSISTENT_UNDER_ASSUMPTIONS',
           'corrupted_line':'INCONSISTENT_UNDER_ASSUMPTIONS',
           'missing_provenance':'INDETERMINATE'}}

if __name__=='__main__':
    report=run();out=Path('outputs/p4_o01_negative_controls.json')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v['state'] for k,v in report['scenarios'].items()},indent=2))
