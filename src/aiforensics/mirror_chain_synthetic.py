"""Independent deterministic geometric fixture (NOT independent observed imagery)."""
from __future__ import annotations
import cv2
import numpy as np
from .mirror_chain import parse_mirrors, predict_mirror_chain
from .mirror_geometry import CalibratedCamera,MirrorGeometryError


def synthetic_two_mirror_scene(n=20,corrupt=3,noise_px=.4,seed=43,shape=(720,1280)):
    if n<4 or corrupt<0 or corrupt>=n or noise_px<0:
        raise ValueError('n>=4, 0<=corrupt<n, noise_px>=0 required')
    rng=np.random.default_rng(seed)
    h,w=shape
    K=np.array([[700.,0.,w/2],[0.,700.,h/2],[0.,0.,1.]])
    cam_data={'K':K.tolist(),'R_world_to_camera':np.eye(3).tolist(),
              't_world_to_camera':[0.,0.,0.]}
    mirrors=[
      {'id':'side', 'normal_world':[1,0,0], 'offset_world':1.6,
       'polygon_world':[[-1.6,-2,0],[-1.6,2,0],[-1.6,2,4],[-1.6,-2,4]],
       'reflective_side':'positive'},
      {'id':'back','normal_world':[0,0,1], 'offset_world':-4.,
       'polygon_world':[[-1.57,-2,4],[3,-2,4],[3,2,4],[-1.57,2,4]],
       'reflective_side':'negative'}]
    ms=parse_mirrors({'mirrors':mirrors})
    sides={x['id']:x['reflective_side'] for x in mirrors}
    cam=CalibratedCamera.from_manifest(cam_data)
    frame=np.full((h,w,3),(43,52,63),dtype=np.uint8)
    observations=[]
    for i in range(n):
        for attempt in range(500):
            P=np.array([rng.uniform(-1.48,-1.1),rng.uniform(-1.2,1.2),rng.uniform(.65,1.65)])
            try:
                predicted=predict_mirror_chain(cam,ms,['side','back'],P,sides)
            except MirrorGeometryError:continue
            uv=np.asarray(predicted['expected_reflection_xy'])
            if 80<uv[0]<w-80 and 60<uv[1]<h-60:break
        else:raise ValueError('cannot sample a valid visible synthetic two-mirror ray')
        obs=uv+rng.normal(0,noise_px,2)
        if i>=n-corrupt:
            obs+=np.array([rng.choice((-1.,1.))*24.,rng.choice((-1.,1.))*18.])
        observations.append({'id':f'chain_{i:03d}','object_world_xyz':P.tolist(),
                             'reflection_xy':obs.tolist(),'confidence':1.})
        cv2.circle(frame,tuple(np.rint(uv).astype(int)),3,(168,210,110),-1,cv2.LINE_AA)
    manifest={'image_shape_hw':[h,w],'camera':cam_data,'mirrors':mirrors,
              'reflection_order_object_to_camera':['side','back'],
              'correspondences':observations}
    return manifest,frame,{'known_good':n-corrupt,'known_corrupt':corrupt,
                           'source':'controlled exact ray geometry; not photographed mirrors'}


def render_chain_xz_diagram(manifest, width=960, height=720):
    """Explain the *actual computed* two-mirror path in a projected X-Z view.

    The Y-coordinate is omitted: this drawing is a diagnostic projection,
    not a full 3D rendering or real photo.
    """
    if width<400 or height<350:raise ValueError('diagram too small')
    ms=parse_mirrors(manifest)
    cam=CalibratedCamera.from_manifest(manifest['camera'])
    P=np.asarray(manifest['correspondences'][0]['object_world_xyz'])
    order=manifest['reflection_order_object_to_camera']
    sides={m['id']:m.get('reflective_side','both') for m in manifest['mirrors']}
    predicted=predict_mirror_chain(cam,ms,order,P,sides)
    canvas=np.full((height,width,3),(34,42,49),dtype=np.uint8)
    def loc(point):
        p=np.asarray(point)
        x,z=float(p[0]),float(p[2])
        return (int((x+4.6)/8.5*(width-100)+50),int(height-75-z/8.2*(height-125)))
    def line(a,b,color,thick=2):
        cv2.line(canvas,loc(a),loc(b),color,thick,cv2.LINE_AA)
    for mirror in manifest['mirrors']:
        poly=np.asarray(mirror['polygon_world'])
        # project polygon edges along XZ; overlapping parallel edges are expected
        for i in range(len(poly)):
            line(poly[i],poly[(i+1)%len(poly)],(160,165,170),3)
        c=np.mean(poly,axis=0)
        x,y=loc(c)
        cv2.putText(canvas,mirror['id'],(x+12,y+55 if mirror['id']=='side' else y-12),cv2.FONT_HERSHEY_SIMPLEX,.65,(220,220,220),2)
    path=predicted['path_world']
    for a,b in zip(path[:-1],path[1:]):line(a,b,(85,215,120),3)
    chain=predicted['virtual_image_chain_world']
    for a,b in zip(chain[:-1],chain[1:]):line(a,b,(230,155,75),2)
    labels=[('C',path[0])]+[(f'H{i+1}',p) for i,p in enumerate(path[1:-1])]+[('P',path[-1])]
    for label,p in labels:
        x,y=loc(p);cv2.circle(canvas,(x,y),5,(130,245,135),-1,cv2.LINE_AA)
        cv2.putText(canvas,label,(x+10,y-9),cv2.FONT_HERSHEY_SIMPLEX,.6,(210,255,215),2)
    for i,v in enumerate(chain[1:]):
        x,y=loc(v);cv2.circle(canvas,(x,y),4,(235,160,80),-1,cv2.LINE_AA)
        cv2.putText(canvas,f'V{i+1}',(x+9,y+15),cv2.FONT_HERSHEY_SIMPLEX,.55,(180,215,255),1)
    cv2.putText(canvas,'P3-R03 | COMPUTED X-Z PROJECTION OF A TWO-MIRROR PATH',(20,30),
                cv2.FONT_HERSHEY_SIMPLEX,.63,(235,235,235),2,cv2.LINE_AA)
    cv2.putText(canvas,'Green: physical light path   Blue: virtual-image chain   Y omitted',(20,height-25),
                cv2.FONT_HERSHEY_SIMPLEX,.55,(220,220,220),1,cv2.LINE_AA)
    return canvas
