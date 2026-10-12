"""Run reproducible real-photograph *content* checks without internet.

Images come from scikit-image installed sample data, NOT external independent
camera ground truth. G04 second views are controlled warps, NOT real captures.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from skimage import data

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from aiforensics.region_patterns import PlaneRegion, analyze_regions
from aiforensics.g04_pair import run_photo_pair,match_photo_pair


def main(out:Path):
    out.mkdir(parents=True,exist_ok=True)
    brick=cv2.cvtColor(data.brick(),cv2.COLOR_GRAY2BGR)
    rocket=cv2.cvtColor(data.rocket(),cv2.COLOR_RGB2BGR)
    out_reports=[]
    for name,img,label in [('brick',brick,'wall'),('rocket',rocket,'unknown')]:
        h,w=img.shape[:2]
        region=PlaneRegion('full_frame',((2.,2.),(w-3.,2.),(w-3.,h-3.),(2.,h-3.)),
                           label, 'researcher_visual_annotation' if name=='brick' else 'unverified_candidate')
        r=analyze_regions(img,[region]);r['source']=f'skimage.data.{name}: published photographic content'
        r['no_camera_ground_truth']=True
        # Do not assert independently verified region labels: image is visually wall-like but dataset has no plane GT.
        r['plane_label_limitation']='Illustrative independent annotation, not original dataset ground-truth plane segmentation'
        (out/f'{name}_g03_report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False))
        cv2.imwrite(str(out/f'{name}_original.png'),img)
        out_reports.append({'photo':name,'rectangles':r['regions'][0]['rectangular_candidates'],
                            'appearance_groups':len(r['regions'][0]['appearance_repeat_groups']),
                            'line_groups':len(r['regions'][0]['line_intersection_candidates'])})
    # A known, deliberately generated planar coordinate transform, applied to real
    # captured photographic pixel content; NOT a second independent exposure.
    h,w=rocket.shape[:2]
    A=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    B=np.float32([[14,15],[w-22,5],[w-5,h-23],[18,h-9]])
    known=cv2.getPerspectiveTransform(A,B)
    transformed=cv2.warpPerspective(rocket,known,(w,h))
    cv2.imwrite(str(out/'rocket_photo_controlled_warp.png'),transformed)
    r=run_photo_pair(out/'rocket_original.png',out/'rocket_photo_controlled_warp.png',out/'g04_photo_controlled',known_h=known)
    # Independent physical exposures: scikit-image stereo motorcycle images.
    # This is an intentionally nonplanar, out-of-domain stress case, without
    # externally labeled planar regions or reference-K camera calibration.
    left,right,_=data.stereo_motorcycle()
    stereo=match_photo_pair(cv2.cvtColor(left,cv2.COLOR_RGB2BGR),cv2.cvtColor(right,cv2.COLOR_RGB2BGR))
    stereo_summary={'state':stereo['status'],'ratio_test_matches':stereo.get('ratio_test_matches'),
        'holdout_matches':stereo.get('holdout_count'),
        'holdout_diagnostics':stereo.get('holdout_match_diagnostics'),
        'note':'Two independently captured real stereo views of a multi-depth nonplanar scene; NO planar GT or K test.'}
    report={'photographic_sources':['skimage.data.brick','skimage.data.rocket','skimage.data.stereo_motorcycle'],
            'G03_photo_content_measurements':out_reports,
            'G04_photo_source_controlled_warp':{
               'state':r['status'],'matches':r.get('ratio_test_matches'),
               'train_n':r.get('train_count'),'holdout_n':r.get('holdout_count'),
               'raw_holdout_rmse_px':r.get('calibration_report',{}).get('holdout_reprojection_rmse_px'),
               'holdout_match_diagnostics':r.get('holdout_match_diagnostics'),
               'reference_warp_match_rmse_px':r.get('independently_specified_H_holdout_rmse_px'),
               'reference_warp_match_median_px':r.get('independently_specified_H_holdout_median_error_px')},
            'G04_real_stereo_multidepth_stress':stereo_summary,
            'G02_independently_calibrated_camera':'NOT_MEASURED',
            'P2_shadow_lighting':'NOT_STARTED',
            'critical_limitation':'Photo source is real but G04 viewpoint change is software-applied, not a second camera exposure.',
            'decision':'NO_AI_ORIGIN_CONCLUSION'}
    (out/'photographic_experiments_summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False))
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report

if __name__=='__main__':main(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'outputs'/'real_photo_experiments')
