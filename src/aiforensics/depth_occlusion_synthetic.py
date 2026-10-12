"""Controlled calibrated camera / two-plane P5-D02 scenes."""
from __future__ import annotations
import copy
import cv2
import numpy as np
from .depth_contact import PinholeCamera


def synthetic_occlusion_fixture(seed=2502, noise_px=0.0):
    if not (0 <= noise_px <= 2):
        raise ValueError('noise_px must be within [0,2]')
    from .depth_contact_synthetic import synthetic_depth_contact_fixture
    old, _ = synthetic_depth_contact_fixture(seed=seed)
    camera = old['camera']
    cam = PinholeCamera(camera, old['image_shape_hw'])
    def wall(name, y, width, bottom, top):
        return {'id':name,'normal_world':[0,1,0],'offset_world':-y,
                'polygon_world_xyz':[[-width,y,bottom],[width,y,bottom],
                                     [width,y,top],[-width,y,top]],
                'opaque':True,'double_sided':True,
                'geometry_provenance':'independent_metric'}
    surfaces = [wall('near_panel',2.,1.,0.3,2.9), wall('far_facade',4.,2.3,0.,3.6)]
    rng = np.random.default_rng(seed)
    overlap_xyz = [.10,4.,1.4]
    side_xyz = [1.60,4.,1.3]
    center_uv = cam.project(overlap_xyz)
    side_uv = cam.project(side_xyz)
    def p(name, uv, label, provenance=True, sig=noise_px):
        return {'id':name,'pixel_xy':(np.asarray(uv)+rng.normal(0,noise_px,2)).tolist(),
                'pixel_sigma_px':sig,'observed_front_surface_id':label,
                'visibility_provenance':'independent_annotation' if provenance else 'derived_from_same_model'}
    manifest = {'image_shape_hw':old['image_shape_hw'], 'camera':camera,
                'surfaces': surfaces,'declared_scene_complete':False,
                'visibility_probes':[
                    p('near_visible',center_uv,'near_panel'),
                    p('far_claimed_visible',center_uv,'far_facade'),
                    p('far_unblocked',side_uv,'far_facade'),
                    p('no_independent_annotation',center_uv,'near_panel',False)],
                'metric_anchors':[
                    {'id':'visible_near_anchor','surface_id':'near_panel',
                     'independent_world_xyz':[0.0,2.,1.85],
                     'pixel_xy':cam.project([0.,2.,1.85]).tolist(),
                     'anchor_provenance':'independent_metric',
                     'claimed_visible':True,'visibility_provenance':'independent_annotation'},
                    {'id':'hidden_far_anchor','surface_id':'far_facade',
                     'independent_world_xyz':overlap_xyz,'pixel_xy':center_uv.tolist(),
                     'anchor_provenance':'independent_metric',
                     'claimed_visible':True,'visibility_provenance':'independent_annotation'},
                    {'id':'anchor_not_independent','surface_id':'far_facade',
                     'independent_world_xyz':side_xyz,'pixel_xy':side_uv.tolist(),
                     'anchor_provenance':'inferred_from_same_image'},
                ],
                'provenance':'fully controlled 3D planes; not measured from real photographs'}
    truth = {'near_visible':'CONSISTENT',
             'far_claimed_visible':'INCONSISTENT_UNDER_ASSUMPTIONS',
             'far_unblocked':'CONSISTENT',
             'no_independent_annotation':'INDETERMINATE',
             'visible_near_anchor':'CONSISTENT',
             'hidden_far_anchor':'INCONSISTENT_UNDER_ASSUMPTIONS',
             'anchor_not_independent':'INDETERMINATE'}
    return manifest, truth


def render_occlusion_overlay(data, report):
    h, w = data['image_shape_hw']
    canvas = np.full((h,w,3), (28,34,40), dtype=np.uint8)
    camera=PinholeCamera(data['camera'],data['image_shape_hw'])
    for idx,surf in enumerate(data['surfaces']):
        corners=np.array([camera.project(p) for p in surf['polygon_world_xyz']]).round().astype(np.int32)
        color=(200,120,80) if idx==0 else (170,160,100)
        overlay=canvas.copy()
        cv2.fillConvexPoly(overlay,corners,color)
        canvas=cv2.addWeighted(overlay,.18,canvas,.82,0)
        cv2.polylines(canvas,[corners],True,color,2,cv2.LINE_AA)
    mapping={r['id']:r for r in report['observations']}
    observations=list(data.get('visibility_probes',[]))+list(data.get('metric_anchors',[]))
    # Disambiguate multiple physical assertions using the same image coordinate.
    for idx,row in enumerate(observations):
        px=tuple(np.asarray(row['pixel_xy']).round().astype(int))
        res=mapping[row['id']]
        color={'CONSISTENT':(70,210,95),
               'INCONSISTENT_UNDER_ASSUMPTIONS':(75,120,242),
               'INDETERMINATE':(50,210,230)}[res['state']]
        cv2.circle(canvas,px,5,color,-1,cv2.LINE_AA)
        angle=idx*2.39996
        label_xy=(int(px[0]+(18+idx%3*10)*np.cos(angle)),
                  int(px[1]+(18+idx%3*10)*np.sin(angle)))
        cv2.line(canvas,px,label_xy,color,1,cv2.LINE_AA)
        cv2.circle(canvas,label_xy,11,(25,28,35),-1,cv2.LINE_AA)
        cv2.circle(canvas,label_xy,11,color,1,cv2.LINE_AA)
        cv2.putText(canvas,str(idx+1),(label_xy[0]-4,label_xy[1]+5),
                    cv2.FONT_HERSHEY_SIMPLEX,.48,color,1,cv2.LINE_AA)
        # The numbered right-hand key preserves full names without overlaps.
        y=140+35*idx
        cv2.circle(canvas,(905,y-5),8,color,-1,cv2.LINE_AA)
        cv2.putText(canvas,f'{idx+1}  {row["id"]}',(924,y),
                    cv2.FONT_HERSHEY_SIMPLEX,.43,color,1,cv2.LINE_AA)
    cv2.putText(canvas,'P5-D02 - MULTIPLANE OCCLUSION - SYNTHETIC SCENE',
                (16,28),cv2.FONT_HERSHEY_SIMPLEX,.72,(240,242,242),2,cv2.LINE_AA)
    cv2.putText(canvas,'green: consistent | orange: inconsistent | yellow: unknown',
                (16,h-17),cv2.FONT_HERSHEY_SIMPLEX,.57,(235,235,235),1,cv2.LINE_AA)
    return canvas
