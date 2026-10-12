"""Controlled 3D pinhole shadow scenes for S01 mathematical regression tests."""
from __future__ import annotations
import numpy as np
import cv2


def _project(points, camera, target, shape, focal=850.0):
    forward=(target-camera)/np.linalg.norm(target-camera)
    right=np.cross(forward,[0.,0.,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    p=np.asarray(points,float)-camera
    depth=p@forward
    if np.any(depth<=0): raise ValueError('fixture point behind camera')
    h,w=shape
    return np.column_stack([w/2+focal*(p@right)/depth,
                            h/2-focal*(p@up)/depth])


def synthetic_shadow_scene(n=12, *, seed=77, noise_px=.0,
                           outliers=0, shape=(720,1280), directional=False,
                           light_source_world=None):
    """Project 3D object points and cast shadows on z=0; known source for finite case."""
    rng=np.random.default_rng(seed)
    camera=np.array([0.,-13.,4.8]); target=np.array([0.,1.,1.])
    source=np.array([-2.2,3.,7.5] if light_source_world is None else light_source_world,dtype=float)
    light_direction=np.array([.3,-.4,-1.0])
    objects=np.column_stack([rng.uniform(-3.,3.,n), rng.uniform(-1.5,4.,n),
                             rng.uniform(.7,2.1,n)])
    if directional:
        shadows=objects-objects[:,2,None]*light_direction/light_direction[2]
    else:
        t=-source[2]/(objects[:,2]-source[2])
        shadows=source[None,:]+t[:,None]*(objects-source[None,:])
    p=_project(objects,camera,target,shape)
    q=_project(shadows,camera,target,shape)
    if noise_px:
        p+=rng.normal(0,noise_px,p.shape);q+=rng.normal(0,noise_px,q.shape)
    # Choose changed shadow positions away from expected ray, still within image.
    for j in range(outliers):
        ix=n-1-j
        q[ix]+=np.array([105.,(-1 if j%2 else 1)*75.])
    for i in range(n):
        if not (0<=p[i,0]<shape[1] and 0<=p[i,1]<shape[0] and
                0<=q[i,0]<shape[1] and 0<=q[i,1]<shape[0]):
            raise ValueError('synthetic fixture point outside canvas; adjust camera/scene')
    frame=np.full((*shape,3), (42,45,51),dtype=np.uint8)
    for i,(a,b) in enumerate(zip(p,q)):
        a=tuple(np.rint(a).astype(int)); b=tuple(np.rint(b).astype(int))
        cv2.line(frame,a,b,(88,108,120),1,cv2.LINE_AA)
        cv2.circle(frame,a,6,(225,212,172),-1,cv2.LINE_AA)
        cv2.circle(frame,b,4,(90,130,210),-1,cv2.LINE_AA)
    correspondences=[{'id':f'shadow_{i:02d}','object_xy':list(map(float,a)),
                      'shadow_xy':list(map(float,b))}
                     for i,(a,b) in enumerate(zip(p,q))]
    truth=(None if directional else _project(source[None,:],camera,target,shape)[0].tolist())
    return {'image_shape_hw':list(shape),'correspondences':correspondences},frame,truth
