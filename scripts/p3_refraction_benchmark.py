"""P3-R02 controlled repeatable ray-optics study (NOT a field validation)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.refraction_geometry import analyze_refraction_manifest
from aiforensics.refraction_synthetic import synthetic_refraction_scene


def run(trials=80,out=Path('outputs/p3_r02_benchmark.json')):
    if trials<2:
        raise ValueError('trials must be >=2')
    counts=[];all_errors=[];all_shifts=[];failures=[]
    for seed in range(trials):
        model='single_interface' if seed%2==0 else 'parallel_slab'
        params={'n_camera':1.,'n_layer':1.333} if model=='single_interface' else {
            'n_camera':1.,'n_layer':1.5,'n_beyond':1.}
        manifest,_,truth=synthetic_refraction_scene(model=model,n=22,corrupt=4,
                noise_px=.38,seed=seed,**params)
        result=analyze_refraction_manifest(manifest,tolerance_px=3.)
        good,bad,un=result['consistent_count'],result['inconsistent_count'],result['indeterminate_count']
        exact=(good==truth['known_good'] and bad==truth['known_corrupted'] and un==0)
        if not exact:failures.append(seed)
        counts.append({'seed':seed,'model':model,'known_good':truth['known_good'],
                       'known_corrupted':truth['known_corrupted'],
                       'measured_good':good,'measured_corrupted':bad,'indeterminate':un,
                       'exact_assignment':exact})
        for r in result['correspondences']:
            if r['state']=='CONSISTENT_UNDER_ASSUMPTIONS':
                all_errors.append(r['reprojection_residual_px'])
                all_shifts.append(r['modeled_pixel_shift_norm_px'])
    report={'scenario':'known-K/R/t, planar interface and parallel slab, 22 annotated object points, 4 shifted corruptions, 0.38px Gaussian noise',
        'trials':trials,'single_interface_trials':(trials+1)//2,'parallel_slab_trials':trials//2,
        'exact_assignment_trials':trials-len(failures),'failed_seeds':failures,
        'median_good_reprojection_error_px':float(np.median(all_errors)) if all_errors else None,
        'p90_good_reprojection_error_px':float(np.percentile(all_errors,90)) if all_errors else None,
        'median_predicted_optical_pixel_shift_px':float(np.median(all_shifts)) if all_shifts else None,
        'report_class':'SYNTHETIC_CONTROLLED_ONLY','ai_origin_decision':'NOT_ESTIMATED',
        'limitations':['Synthetic fixed-geometry camera and surfaces; no independent real photographs',
                       'Refractive index values and true point correspondences provided externally',
                       'No automatic transparent-object segmentation, lens-distortion calibration or uncertainty-calibrated threshold',
                       'Predicted optical shift is a model result, not an independent optical measurement'],
        'records':counts}
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--trials',type=int,default=80)
    p.add_argument('--out',type=Path,default=Path('outputs/p3_r02_benchmark.json'))
    opts=p.parse_args()
    result=run(opts.trials,opts.out)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2))
