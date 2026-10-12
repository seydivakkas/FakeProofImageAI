"""P4-O03 deterministic physical pinhole 3D projection fixtures, no real camera claims."""
from __future__ import annotations
import numpy as np
from scipy.spatial.transform import Rotation
from .optical_consistency import project_points, native_to_output_K


def synthetic_optical_fixture(seed=1503,*,fit_focal=False,corrupt=3,noise_px=.25,
                              distortion=None):
    rng=np.random.default_rng(seed)
    native_K=np.array([[1200.,0.,770.],[0.,1200.,450.],[0.,0.,1.]])
    wh=[1280,720]
    K=native_to_output_K(native_K,[1600,1000],[140,100,1280,720],wh)
    R=Rotation.from_euler('xyz',[3.,-5.,4.],degrees=True).as_matrix()
    t=np.array([.22,-.14,.42])
    samples=[];truth={'K':K.tolist(),'corrupted_ids':[],'focal_length_mm':4.8}
    for i in range(56):
        z=float(rng.uniform(5,13))
        nx=float(rng.uniform(-.32,.32));ny=float(rng.uniform(-.23,.23))
        camera=np.array([nx*z,ny*z,z])
        world=(camera-t)@R
        observed=project_points([world],K,R,t,distortion)[0] + rng.normal(0,noise_px,2)
        role='train' if i<24 else 'holdout'
        if role=='holdout' and i<24+corrupt:
            observed += [9.,-7.]
            truth['corrupted_ids'].append(f'point_{i:02d}')
        samples.append({'id':f'point_{i:02d}','role':role,'world_xyz':world.tolist(),
                        'observed_xy_px':observed.tolist(), 'observed_sigma_px':max(.25,2*noise_px),
                        'measurement_provenance':'synthetic_known_correspondence'})
    data={'schema_version':'p4-o03-v1','image_size_wh':wh,
          'data_provenance':'SYNTHETIC_KNOWN_TRUTH',
          'pose':{'R_world_to_camera':R.tolist(),'t_world_to_camera':t.tolist()},
          'calibration_mode':'fit_focal_from_train' if fit_focal else 'known_K',
          'sensor_metadata':{'pixel_pitch_x_um':4.,'pixel_pitch_y_um':4.,'focal_length_mm':4.8},
          'samples':samples,'independent_claims':{}}
    if fit_focal:
        data['principal_point_xy_px']=K[:2,2].tolist()
    else:data['K']=K.tolist()
    if distortion is not None:
        data['brown_conrady_coefficients']=list(distortion)
    if not fit_focal:
        data['image_transform']={'native_K':native_K.tolist(),
                                'native_image_size_wh':[1600,1000],
                                'crop_xywh':[140,100,1280,720]}
    # Independently supplied direction and segment geometry in known-truth fixture.
    if distortion is None:
        direction=R.T@np.array([.06,.10,1.])
        vp=project_points([direction],K,R,np.zeros(3))[0]
        data['vanishing_point_holdouts']=[{'id':'vp_holdout','direction_world':direction.tolist(),
           'observed_xy_px':(vp+rng.normal(0,.14,2)).tolist(),
           'observed_sigma_px':.4,'measurement_provenance':'independent_direction_and_vp'}]
    endpoints_cam=np.array([[-.3,0.,8.],[.5,0.,8.]])
    endpoints_world=(endpoints_cam-t)@R
    pp=project_points(endpoints_world,K,R,t,distortion)
    data['segment_holdouts']=[{'id':'segment_holdout',
        'world_endpoints':endpoints_world.tolist(),
        'observed_endpoints_xy_px':(pp+rng.normal(0,.10,(2,2))).tolist(),
        'observed_sigma_px':.3,'measurement_provenance':'independent_3d_segment'}]
    return data,truth


def render_optical_overlay(data,report):
    """Technical plot of independently held-out synthetic 3D correspondences."""
    import cv2
    w,h=data['image_size_wh']
    img=np.full((h,w,3),(28,34,39),dtype=np.uint8)
    # Deterministic guide lines are graphical aids, not camera observations.
    for x in range(0,w,80):cv2.line(img,(x,0),(x,h-1),(42,47,51),1,cv2.LINE_AA)
    for y in range(0,h,80):cv2.line(img,(0,y),(w-1,y),(42,47,51),1,cv2.LINE_AA)
    for p in report['holdout_results']:
        if 'predicted_xy_px' not in p:continue
        pred=tuple(int(round(z)) for z in p['predicted_xy_px'])
        obs=tuple(int(round(z)) for z in p['observed_xy_px'])
        valid=(0<=pred[0]<w and 0<=pred[1]<h and 0<=obs[0]<w and 0<=obs[1]<h)
        if not valid:continue
        bad=p['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
        color=(30,155,255) if bad else (90,225,110)
        cv2.line(img,pred,obs,color,2,cv2.LINE_AA)
        cv2.circle(img,pred,6,(245,190,70),2,cv2.LINE_AA)
        cv2.circle(img,obs,4,color,-1,cv2.LINE_AA)
    cv2.rectangle(img,(0,0),(w,95),(24,30,36),-1)
    cv2.putText(img,'P4-O03 | synthetic camera holdout projections',(30,34),
                cv2.FONT_HERSHEY_SIMPLEX,.82,(235,239,241),2,cv2.LINE_AA)
    cv2.putText(img,'BLUE: predicted   GREEN: consistent   ORANGE: corrupted',(30,67),
                cv2.FONT_HERSHEY_SIMPLEX,.58,(210,220,220),1,cv2.LINE_AA)
    return img
