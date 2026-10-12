"""Independent controlled 3D fixtures. Never use as real-world validation."""
from __future__ import annotations
import copy
import cv2
import numpy as np
from .depth_contact import PinholeCamera


def synthetic_depth_contact_fixture(seed: int=2026, noise_px: float=0.20):
    rng=np.random.default_rng(seed)
    C=np.array([0.,-8.,5.])
    target=np.array([0.,1.,1.])
    forward=(target-C);forward/=np.linalg.norm(forward)
    right=np.cross(forward,[0.,0.,1.]);right/=np.linalg.norm(right)
    down=np.cross(forward,right)
    R=np.array([right,down,forward]);t=-R@C
    camera={'K':[[920.,0.,640.],[0.,915.,360.],[0.,0.,1.]],
            'R_world_to_camera':R.tolist(),'t_world_to_camera':t.tolist()}
    plane={'id':'floor','normal_world':[0.,0.,1.],'offset_world':0.,
           'polygon_world_xyz':[[-3.,0.,0.],[3.,0.,0.],[3.,6.,0.],[-3.,6.,0.]]}
    fixture={'image_shape_hw':[720,1280],'camera':camera,'gravity_world':[0.,0.,-1.],
             'support_surfaces':[plane], 'observations':[],
             'provenance':'synthetic_known_camera_ground_geometry; no real-image measurement'}
    cam=PinholeCamera(camera,[720,1280])
    ground_truth={}
    for i,(x,y,h) in enumerate([(-1.7,1.7,1.9),(-.5,2.8,1.4),(.8,2.0,2.3),(1.8,3.8,1.6)]):
        base=np.array([x,y,0.]);top=base+np.array([0.,0.,h])
        bottom_pix=cam.project(base)+rng.normal(0.,noise_px,2)
        top_pix=cam.project(top)+rng.normal(0.,noise_px,2)
        row={'id':f'valid_{i}','support_id':'floor','base_pixel_xy':bottom_pix.tolist(),
             'top_pixel_xy':top_pix.tolist(),'known_height_world':h,
             'base_pixel_sigma_px':noise_px,'top_pixel_sigma_px':noise_px,
             'height_provenance':'independent_metric','upright_gravity_aligned':True,
             'independent_base_world_xyz':base.tolist(),'base_world_provenance':'independent_metric'}
        fixture['observations'].append(row)
        ground_truth[row['id']]='CONSISTENT'
    incorrect=copy.deepcopy(fixture['observations'][1]);incorrect['id']='wrong_top'
    incorrect['top_pixel_xy'][0]+=27.
    fixture['observations'].append(incorrect)
    ground_truth[incorrect['id']]='INCONSISTENT_UNDER_ASSUMPTIONS'
    floating=np.array([.3,4.,.55]);px=cam.project(floating)
    fixture['observations'].append({'id':'floating_anchor','support_id':'floor',
         'base_pixel_xy':px.tolist(),'independent_base_world_xyz':floating.tolist(),
         'base_world_provenance':'independent_metric'})
    ground_truth['floating_anchor']='INCONSISTENT_UNDER_ASSUMPTIONS'
    outside=cam.project(np.array([4.1,2.8,0.]))
    fixture['observations'].append({'id':'outside_polygon_candidate','support_id':'floor',
                                   'base_pixel_xy':outside.tolist()})
    ground_truth['outside_polygon_candidate']='INDETERMINATE'
    plain=cam.project(np.array([0.5,4.1,0.]))
    fixture['observations'].append({'id':'unverified_contact_candidate','support_id':'floor',
                                   'base_pixel_xy':plain.tolist()})
    ground_truth['unverified_contact_candidate']='INDETERMINATE'
    fixture['observations'].append({'id':'unstable_com','support_id':'floor',
         'base_pixel_xy':cam.project([1.,3.,0.]).tolist(),
         'center_of_mass_world_xyz':[4.5,3.,1.5],
         'com_provenance':'independent_metric', 'static_unanchored':True})
    ground_truth['unstable_com']='INCONSISTENT_UNDER_ASSUMPTIONS'
    return fixture,ground_truth


def render_depth_contact_overlay(data,report,background=None):
    h,w=data['image_shape_hw']
    if background is None:
        canvas=np.full((h,w,3),(27,32,38),dtype=np.uint8)
    else:
        canvas=np.asarray(background).copy()
        if canvas.shape != (h,w,3) or canvas.dtype != np.uint8:
            raise ValueError('background must match image_shape_hw and be uint8 BGR')
    cam=PinholeCamera(data['camera'],[h,w])
    for surface in data['support_surfaces']:
        xy=np.array([cam.project(p) for p in surface['polygon_world_xyz']]).round().astype(np.int32)
        cv2.polylines(canvas,[xy],True,(125,135,200),2,cv2.LINE_AA)
    lookup={r['id']:r for r in report['observations']}
    for item in data['observations']:
        r=lookup[item['id']]
        point=tuple(np.round(item['base_pixel_xy']).astype(int))
        color={'CONSISTENT':(50,215,100),'INCONSISTENT_UNDER_ASSUMPTIONS':(60,125,240),
               'INDETERMINATE':(35,215,235)}[r['state']]
        cv2.circle(canvas,point,7,color,-1,cv2.LINE_AA)
        if 'top_pixel_xy' in item:
            tip=tuple(np.round(item['top_pixel_xy']).astype(int))
            cv2.line(canvas,point,tip,color,2,cv2.LINE_AA)
            cv2.circle(canvas,tip,4,color,-1,cv2.LINE_AA)
        offset_x=min(point[0]+9,w-190)
        cv2.putText(canvas,item['id'],(offset_x,max(20,point[1]-8)),cv2.FONT_HERSHEY_SIMPLEX,.42,color,1,cv2.LINE_AA)
    cv2.putText(canvas,'P5-D01 CONTROLLED 3D GEOMETRY - NOT A REAL PHOTO',
                (18,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(228,230,232),2,cv2.LINE_AA)
    cv2.putText(canvas,'green: consistent | orange: conditional inconsistency | yellow: indeterminate',
                (18,h-17),cv2.FONT_HERSHEY_SIMPLEX,.55,(235,235,235),1,cv2.LINE_AA)
    return canvas
