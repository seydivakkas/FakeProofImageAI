"""Deterministic known-truth synthetic P4-O01 lens fixtures."""
from __future__ import annotations
import cv2
import numpy as np
from .lens_distortion import distort_pixels


def synthetic_lens_scene(seed=41,noise_px=.16,corrupt_holdout=0,model_order=5):
    rng=np.random.default_rng(seed)
    h,w=720,1280
    K=np.array([[860.,0.,636.],[0.,850.,359.],[0.,0.,1.]])
    coeffs=np.array([-.23,.075,.004,-.0035,-.012])
    if model_order==4:coeffs[-1]=0.
    grid_x=np.linspace(75,1205,12)
    grid_y=np.linspace(55,665,8)
    training=np.array([(x,y) for y in grid_y for x in grid_x],float)
    # Independent holdouts not used to fit parameters; shifted grid positions.
    hold=np.array([(x,y) for y in np.linspace(103,638,7)
                           for x in np.linspace(103,1177,10)],float)
    def observe(points):
        return distort_pixels(points,K,coeffs)+rng.normal(0,noise_px,size=points.shape)
    train_obs=observe(training)
    hold_obs=observe(hold)
    if corrupt_holdout:
        hold_obs[:corrupt_holdout]+=np.array([16.,-12.])
    records=[]
    for kind,ideal,seen in [('train',training,train_obs),('holdout',hold,hold_obs)]:
        records.extend({'id':f'{kind}-{i:03d}','role':kind,
             'ideal_xy_px':p.tolist(),'observed_xy_px':q.tolist()}
             for i,(p,q) in enumerate(zip(ideal,seen)))
    lines=[]
    line_ideals=[]
    for i,y in enumerate([140.,300.,520.]):
        line_ideals.append((f'h-{i}',np.column_stack([np.linspace(90.,1180.,35),np.full(35,y)])))
    for i,x in enumerate([180.,520.,1000.]):
        line_ideals.append((f'v-{i}',np.column_stack([np.full(35,x),np.linspace(70.,650.,35)])))
    canvas=np.full((h,w,3),(31,37,48),dtype=np.uint8)
    for identifier,ideal_line in line_ideals:
        distorted=observe(ideal_line)
        lines.append({'id':identifier,'externally_verified_straight':True,
            'observed_points_xy_px':distorted.tolist()})
        pts=np.rint(distorted).astype(np.int32)
        cv2.polylines(canvas,[pts],False,(90,185,245),2,cv2.LINE_AA)
    for p in train_obs:
        cv2.circle(canvas,tuple(np.rint(p).astype(int)),3,(80,230,110),-1,cv2.LINE_AA)
    for p in hold_obs:
        cv2.circle(canvas,tuple(np.rint(p).astype(int)),3,(245,205,80),-1,cv2.LINE_AA)
    cv2.putText(canvas,'CONTROLLED BROWN-CONRADY SCENE - NOT REAL CAMERA DATA',(20,35),
        cv2.FONT_HERSHEY_SIMPLEX,.72,(245,245,245),2,cv2.LINE_AA)
    fixture={'scenario':'controlled known-K Brown-Conrady point grid and independent straight lines',
             'data_provenance':'SYNTHETIC_KNOWN_TRUTH', 'K':K.tolist(),
             'point_pairs':records,'independent_straight_lines':lines}
    truth={'coefficients':coeffs.tolist(),'train_count':len(training),
           'holdout_count':len(hold),'noise_px_sigma':noise_px,
           'corrupted_holdout_count':corrupt_holdout,'seed':seed}
    return fixture,canvas,truth
