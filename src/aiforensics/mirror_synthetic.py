"""Controlled ideal planar-mirror camera fixtures; NOT independent field evidence."""
from __future__ import annotations
import numpy as np
import cv2
from .mirror_geometry import CalibratedCamera,MirrorPlane,expected_reflection


def synthetic_mirror_scene(n=14,noise_px=0.35,corrupt=2,seed=29, shape=(720,1280),
                           polygon=True):
    if n<4 or corrupt<0 or corrupt>=n or noise_px<0:
        raise ValueError('require n>=4, 0<=corrupt<n and nonnegative noise')
    rng=np.random.default_rng(seed)
    h,w=shape
    C=np.array([0.,-6.5,1.75])
    target=np.array([0.,0.,1.6]);forward=(target-C)/np.linalg.norm(target-C)
    right=np.cross(forward,[0.,0.,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    R=np.vstack([right,-up,forward]);t=-R@C
    K=np.array([[850.,0,w/2],[0.,850.,h/2],[0.,0.,1.]])
    camera=CalibratedCamera(K,R,t)
    plane_manifest={'normal_world':[0.,-1.,0.], 'offset_world':0.0}
    if polygon:
        plane_manifest['polygon_world']=[[-5.,0.,0.],[5.,0.,0.],[5.,0.,4.],[-5.,0.,4.]]
    plane=MirrorPlane.from_manifest(plane_manifest)
    frame=np.full((h,w,3),(48,59,69),np.uint8)
    points=[]
    for k in range(n):
        for _ in range(200):
            P=np.array([rng.uniform(-2.8,2.8),rng.uniform(-4.3,-1.1),rng.uniform(.5,2.5)])
            try:
                expected=expected_reflection(camera,plane,P)
                uv=expected['expected_reflection_xy'];real=camera.project(P)
            except ValueError:continue
            if all(15<p[0]<w-15 and 15<p[1]<h-15 for p in (uv,real)):
                break
        else:raise ValueError('could not sample valid synthetic mirror correspondence')
        observed=uv+rng.normal(0,noise_px,2)
        if k>=n-corrupt:
            observed+=np.array([rng.choice([-1,1])*32.,rng.choice([-1,1])*29.])
        points.append({'id':f'mirror_{k:03d}','object_world_xyz':P.tolist(),
                       'reflection_xy':observed.tolist(),'confidence':1.0})
        cv2.circle(frame,tuple(np.rint(real).astype(int)),4,(225,210,155),-1,cv2.LINE_AA)
        cv2.circle(frame,tuple(np.rint(uv).astype(int)),3,(165,220,80),-1,cv2.LINE_AA)
    manifest={'image_shape_hw':[h,w],
              'camera':{'K':K.tolist(),'R_world_to_camera':R.tolist(), 't_world_to_camera':t.tolist()},
              'mirror_plane':plane_manifest,'correspondences':points}
    truth={'known_good':n-corrupt,'known_corrupted':corrupt,'camera_center_xyz':C.tolist(),
           'mirror_plane_normal_world':plane.normal.tolist(),
           'scenario':'calibrated 3D points / planar specular virtual projection / controlled pixel perturbation'}
    return manifest,frame,truth
