"""Deterministic P3-R02 calibrated planar refraction fixtures; not real photos."""
from __future__ import annotations

import cv2
import numpy as np

from .mirror_geometry import CalibratedCamera
from .refraction_geometry import RefractiveInterface, solve_planar_refraction


def synthetic_refraction_scene(model='single_interface', n=16, noise_px=.23,
                               corrupt=3, seed=33, shape=(720,1280),
                               n_camera=1.,n_layer=1.333,n_beyond=1.):
    rng=np.random.default_rng(seed)
    K=np.array([[860.,0.,shape[1]/2],[0.,860.,shape[0]/2],[0.,0.,1.]])
    camera={'K':K.tolist(),'R_world_to_camera':np.eye(3).tolist(),
            't_world_to_camera':[0.,0.,0.]}
    interface={'model':model,'point_world':[0.,0.,3.],
            'normal_toward_camera_world':[0.,0.,-1.],
            'n_camera':n_camera,'n_layer':n_layer}
    if model=='parallel_slab':
        interface.update(thickness_world=.65,n_beyond=n_beyond)
    cam=CalibratedCamera.from_manifest(camera)
    inter=RefractiveInterface.from_manifest(interface)
    image=np.full((shape[0],shape[1],3),38,np.uint8)
    # Standalone reference pattern: algorithm checks annotated correspondences,
    # NOT object/edge detection from rendered pixels.
    for x in range(0,shape[1],80):cv2.line(image,(x,0),(x,shape[0]-1),(55,55,55),1)
    for y in range(0,shape[0],80):cv2.line(image,(0,y),(shape[1]-1,y),(55,55,55),1)
    correspondences=[];raw=[]
    for j in range(n):
        x=float(rng.uniform(-2.8,2.8));y=float(rng.uniform(-1.55,1.55));z=float(rng.uniform(6.2,8.4))
        P=np.array([x,y,z]);r=solve_planar_refraction(cam,inter,P)
        px=np.asarray(r['expected_xy'])+rng.normal(0,noise_px,2)
        altered=j>=n-corrupt
        if altered:
            px+=np.array([35.,-26.])
        assert 0<=px[0]<shape[1] and 0<=px[1]<shape[0]
        name=f'point_{j:03d}'
        correspondences.append({'id':name,'object_world_xyz':P.tolist(),
                                'observed_xy':px.tolist(),'confidence':1.})
        raw.append({'id':name,'truth_is_corrupted':altered,
                    'ideal_expected_xy':r['expected_xy'].tolist(),
                    'modeled_pixel_shift_norm_px':r['pixel_shift_norm_px']})
        v=tuple(np.round(px).astype(int))
        cv2.circle(image,v,6,(0,80,245) if altered else (75,220,80),-1,cv2.LINE_AA)
    manifest={'image_shape_hw':list(shape),'camera':camera,'interface':interface,
              'correspondences':correspondences}
    if model=='single_interface' and n>=10:
        manifest['index_fit']={'train_ids':[r['id'] for r in correspondences[:n//2]],
                               'holdout_ids':[r['id'] for r in correspondences[n//2:]]}
    truth={'known_good':n-corrupt,'known_corrupted':corrupt,'model':model,
           'note':'known camera and optical geometry; controlled synthetic only',
           'objects':raw}
    return manifest,image,truth
