"""Produce deterministic projected equally-spaced 3D floor markers and overlays."""
from pathlib import Path
import json
import sys
import numpy as np
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aiforensics.synthetic import render_corridor
from aiforensics.cross_ratio import analyze_repeated_landmarks

def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'outputs'/'g03_demo';out.mkdir(parents=True,exist_ok=True)
    im,_=render_corridor()
    depth=np.array([5.,7.,9.,11.,13.,15.]) # known equal world-depth intervals
    # x=0, floor y=1.65, camera has K with fy=850, cy=360.
    p=np.column_stack([np.full(len(depth),640.), 360.+850.*1.65/depth])
    demo={'points_xy':p.tolist(),'lattice_indices':list(range(len(p))),
          'training_indices':[0,1,2,3], 'pixel_sigma':.35,
          'bootstrap_samples':500,'seed':2026,
          'provenance':'Synthetic pinhole projected floor marks, equal 2m world-depth steps.'}
    (out/'g03_input.json').write_text(json.dumps(demo,indent=2),encoding='utf-8')
    result=analyze_repeated_landmarks(p,lattice_indices=demo['lattice_indices'],
             training_indices=demo['training_indices'],pixel_sigma=.35,bootstrap_samples=500)
    (out/'g03_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    for j,(x,y) in enumerate(p):
        cv2.circle(im,(round(x),round(y)),6,(0,205,255),-1,cv2.LINE_AA)
        cv2.putText(im,f'P{j}',(round(x)+13,round(y)+4),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,245,245),1,cv2.LINE_AA)
    cv2.rectangle(im,(0,0),(960,82),(25,33,39),-1)
    cv2.putText(im,'G03: Projective cross-ratio | SYNTHETIC example',
                (25,32),cv2.FONT_HERSHEY_SIMPLEX,.67,(235,240,245),2,cv2.LINE_AA)
    cv2.putText(im,'Known equidistant 3D points; yellow markers are measured image projections',
                (25,64),cv2.FONT_HERSHEY_SIMPLEX,.49,(235,240,245),1,cv2.LINE_AA)
    cv2.imwrite(str(out/'g03_marked_corridor.png'),im)
    print(json.dumps({'state':result['state'],'cross_ratio':result['cross_ratio_observed'],
        'expected':result['cross_ratio_expected'],'holdout_rmse_px':result['holdout']['reprojection_rmse_px']},indent=2))

if __name__=='__main__':main()
