"""Deterministic known-truth 3D solar shadow fixtures (not real photographs)."""
from __future__ import annotations
import numpy as np
import cv2
from .solar_geometry import sun_direction_from_angles,solar_position_noaa,cast_shadow_to_plane


def synthetic_solar_scene(*, n=18, seed=37, azimuth_deg=132., elevation_deg=43.,
                          noise_px=.0, wrong_pairs=0, slope_x=0., slope_y=0.,
                          solar_claim=None, shape=(720,1280)):
    if n<5 or wrong_pairs<0 or wrong_pairs>=n:
        raise ValueError('5 or more points and 0 <= wrong_pairs < n required')
    rng=np.random.default_rng(seed)
    if solar_claim is not None:
        d=solar_position_noaa(**solar_claim)
        azimuth_deg=d['azimuth_deg_clockwise_from_true_north'];elevation_deg=d['elevation_deg']
    if not 9<elevation_deg<85:
        raise ValueError('synthetic Sun elevation must be in (9,85) degrees')
    sun=sun_direction_from_angles(azimuth_deg,elevation_deg)
    C=np.array([0.,-13.,5.]);target=np.array([0.,.4,1.])
    forward=(target-C)/np.linalg.norm(target-C)
    right=np.cross(forward,[0.,0.,1.]);right/=np.linalg.norm(right)
    up=np.cross(right,forward)
    R=np.vstack([right,-up,forward]);t=-R@C
    height,width=shape
    K=np.array([[850.,0.,width/2],[0.,850.,height/2],[0.,0.,1.]])
    normal=np.array([-slope_x,-slope_y,1.])
    normal/=np.linalg.norm(normal)
    offset=0.
    def project(P):
        a=R@(P-C)
        if a[2]<=0:raise ValueError('point behind camera')
        uv=K@a
        return uv[:2]/uv[2]
    observations=[]
    frame=np.full((height,width,3),(34,42,52),dtype=np.uint8)
    for j in range(n):
        for trial in range(100):
            xy=rng.uniform([-2.0,-.5],[2.0,3.4])
            H=float(rng.uniform(.65,1.6))
            B=np.array([xy[0],xy[1],slope_x*xy[0]+slope_y*xy[1]])
            P=B+np.array([0,0,H])
            Q=cast_shadow_to_plane(P,sun,normal,offset)
            b,p,q=project(B),project(P),project(Q)
            if all(18<=z[0]<width-18 and 42<=z[1]<height-18 for z in (b,p,q)):
                break
        else:raise ValueError('unable to create fully visible solar-shadow fixture')
        b+=rng.normal(0,noise_px,2)
        p+=rng.normal(0,noise_px,2)
        q+=rng.normal(0,noise_px,2)
        if j>=n-wrong_pairs:
            q=q+np.array([float(rng.choice([-1,1]))*42.,float(rng.choice([-1,1]))*39.])
        if not (0<=q[0]<width and 0<=q[1]<height):
            raise ValueError('outlier shadow left image bounds')
        pair={'id':f'sun_pair_{j:03d}','base_xy':b.tolist(),
              'tip_xy':p.tolist(),'shadow_xy':q.tolist(),
              'object_height_m':H,'confidence':1.0}
        observations.append(pair)
        A=tuple(np.rint(b).astype(int));T=tuple(np.rint(p).astype(int));Z=tuple(np.rint(q).astype(int))
        cv2.line(frame,A,T,(225,210,155),2,cv2.LINE_AA)
        cv2.line(frame,A,Z,(120,170,225),1,cv2.LINE_AA)
        cv2.circle(frame,T,3,(245,245,245),-1,cv2.LINE_AA)
        cv2.circle(frame,Z,3,(130,205,80),-1,cv2.LINE_AA)
    manifest={'world_frame':'ENU_TRUE_NORTH','world_units':'m',
              'image_shape_hw':[height,width],
              'camera':{'K':K.tolist(),'R_world_to_camera':R.tolist(),
                        't_world_to_camera':t.tolist()},
              'ground_plane':{'normal_world':normal.tolist(), 'offset_world':0.},
              'correspondences':observations}
    if solar_claim is not None:manifest['solar_claim']=solar_claim
    truth={'sun_direction_enu':sun.tolist(),'sun_azimuth_deg':azimuth_deg,
           'sun_elevation_deg':elevation_deg,'slope_x':slope_x,'slope_y':slope_y,
           'known_good':n-wrong_pairs,'corrupted':wrong_pairs,
           'method':'3D RAY / PLANAR RECEIVER SHADOW SYNTHESIS'}
    return manifest,frame,truth
