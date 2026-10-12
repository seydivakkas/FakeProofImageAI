"""Known-truth 3D pinhole fixtures for P2-S03, never real-photo validation."""
from __future__ import annotations
import cv2
import numpy as np


def synthetic_shadow3d_scene(*, n=16, seed=21, noise_px=.0, bad_pairs=0,
                             directional=False, sources=None, shape=(720,1280)):
    """Return (manifest, visualization, truth), with declared true source families.

    Object heights are geometric distances along normal (0,0,+1) above z=0.
    """
    if n < 5 or bad_pairs<0 or bad_pairs >= n:
        raise ValueError('invalid fixture counts')
    rng=np.random.default_rng(seed)
    C=np.array([0.,-13.,4.8]); target=np.array([0.,1.,1.])
    forward=(target-C)/np.linalg.norm(target-C)
    right=np.cross(forward,[0,0,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    R=np.vstack([right,-up,forward]);t=-R@C
    f=850.;h,w=shape
    K=np.array([[f,0.,w/2],[0.,f,h/2],[0.,0.,1.]])
    def project(x):
        camera_pts=(R@np.asarray(x).T).T+t
        if np.any(camera_pts[:,2]<=0):raise ValueError('fixture points behind camera')
        hom=(K@camera_pts.T).T
        return hom[:,:2]/hom[:,2,None]
    if sources is None: sources=[[-2.2,3.,7.5]]
    if directional and len(sources)!=1:raise ValueError('directional fixture supports one source vector')
    items=[];truth={}
    for k,s in enumerate(sources):
        family=f'fixture_{k+1:02d}'
        source=np.array(s,float)
        if directional:
            u=source/np.linalg.norm(source)
            if u[2]<=0:raise ValueError('direction must point upward to source')
            truth[family]={'type':'DIRECTIONAL_OR_DISTANT_LIGHT','direction':u.tolist()}
        else:
            truth[family]={'type':'FINITE_POINT_LIGHT','position':source.tolist()}
        points=np.column_stack((rng.uniform(-2.6,2.6,n),rng.uniform(-1.,3.8,n),rng.uniform(.75,1.9,n)))
        if directional:
            shadows=points-points[:,2,None]*u/u[2]
        else:
            scale=-source[2]/(points[:,2]-source[2])
            shadows=source+scale[:,None]*(points-source)
        po=project(points);ps=project(shadows)
        po+=rng.normal(0,noise_px,po.shape);ps+=rng.normal(0,noise_px,ps.shape)
        for j in range(bad_pairs):
            # Deliberately corrupt otherwise valid one-to-one ground correspondence.
            ps[n-1-j]+=np.array([110.,(1 if j%2==0 else -1)*85.])
        for i,(a,b) in enumerate(zip(po,ps)):
            if not (0<=a[0]<w and 0<=a[1]<h and 0<=b[0]<w and 0<=b[1]<h):
                raise ValueError('fixture pixel left canvas; adjust source or scene')
            items.append({'id':f'{family}_pair_{i:02d}','family_id':family,
                          'object_xy':a.tolist(),'shadow_xy':b.tolist(),
                          'height_above_plane':float(points[i,2])})
    canvas=np.full((*shape,3), (32,41,52),dtype=np.uint8)
    colors=[(80,190,80),(220,165,70),(185,80,215)]
    for item in items:
        k=int(item['family_id'].split('_')[-1])-1
        a=tuple(np.rint(item['object_xy']).astype(int));b=tuple(np.rint(item['shadow_xy']).astype(int))
        cv2.line(canvas,a,b,colors[k%3],1,cv2.LINE_AA)
        cv2.circle(canvas,a,4,(215,227,235),-1,cv2.LINE_AA)
        cv2.circle(canvas,b,3,colors[k%3],-1,cv2.LINE_AA)
    data={'image_shape_hw':[h,w], 'world_units':'m',
          'camera':{'K':K.tolist(),'R_world_to_camera':R.tolist(), 't_world_to_camera':t.tolist()},
          'ground_plane':{'normal_world':[0.,0.,1.], 'offset_world':0.},
          'correspondences':items}
    return data,canvas,truth
