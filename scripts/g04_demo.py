"""Deterministic controlled plane-to-image synthetic fixture for G04.
Does not simulate real camera data or AI generations.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from aiforensics.homography import analyze_g04_manifest
from aiforensics.imaging import write_image


def main():
    out=ROOT/'outputs'/'g04_demo';out.mkdir(parents=True,exist_ok=True)
    world=np.array([[float(x),float(y)] for y in range(5) for x in range(7)])
    H=np.array([[120.,24.,100.],[7.,75.,85.],[.018,.047,1.]])
    homo=np.column_stack([world,np.ones(len(world))])@H.T
    image=homo[:,:2]/homo[:,2:]
    # Create a simple geometrical diagram with known correspondences.
    canvas=np.zeros((560,880,3),np.uint8);canvas[:]=(30,38,46)
    for row in range(5):
        for col in range(6):
            a=tuple(np.round(image[row*7+col]).astype(int));b=tuple(np.round(image[row*7+col+1]).astype(int))
            cv2.line(canvas,a,b,(90,135,190),1,cv2.LINE_AA)
    for col in range(7):
        for row in range(4):
            a=tuple(np.round(image[row*7+col]).astype(int));b=tuple(np.round(image[(row+1)*7+col]).astype(int))
            cv2.line(canvas,a,b,(90,135,190),1,cv2.LINE_AA)
    input_image=out/'synthetic_plane.png';write_image(input_image,canvas)
    training=[j for j in range(len(world)) if j%4!=0]
    manifest={'world_points_xy':world.tolist(),'image_points_xy':image.tolist(),
              'training_indices':training,'holdout_threshold_px':3.0,
              'provenance':'SYNTHETIC coordinate-transform fixture, no actual photograph'}
    p=out/'g04_example_input.json'
    p.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    res=analyze_g04_manifest(p,out,image_path=input_image)
    # Corrupt a HELD-OUT measurement, not the image pixels. This tests geometric
    # rejection under an intentionally inconsistent annotation scenario.
    disturbed=json.loads(p.read_text(encoding='utf-8'))
    holdout=[j for j in range(len(world)) if j not in set(training)]
    disturbed['image_points_xy'][holdout[0]][0]+=28.0
    disturbed['image_points_xy'][holdout[0]][1]+=16.0
    q=out/'g04_disturbed_holdout.json'
    q.write_text(json.dumps(disturbed,indent=2),encoding='utf-8')
    disturbed_result=analyze_g04_manifest(q,out/'disturbed_case',image_path=input_image)
    print('disturbed held-out point:',disturbed_result['state'],
          'RMSE=',disturbed_result.get('holdout_reprojection_rmse_px'))
    print(json.dumps({'state':res['state'],'holdout_rmse_px':res['holdout_reprojection_rmse_px'],
                      'training_count':len(training),'holdout_count':len(res['holdout_indices'])},indent=2))

if __name__=='__main__':main()
