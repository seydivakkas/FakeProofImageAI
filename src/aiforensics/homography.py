"""G04: independently evaluated planar homography with explicitly supplied
world-plane and image point correspondences.

Unlike fitting four points and checking the same four, holdout uses points
excluded from estimation. Failure does NOT establish AI image origin.
"""
from __future__ import annotations
import json
from pathlib import Path
import hashlib
import numpy as np
import cv2
from .imaging import load_bgr,write_image


class HomographyError(ValueError):pass


def _input_points(points,label):
    p=np.asarray(points,float)
    if p.ndim!=2 or p.shape[1]!=2 or p.shape[0]<6 or not np.isfinite(p).all():
        raise HomographyError(f'{label}: expected at least six finite 2D points')
    if len(np.unique(p,axis=0))!=len(p):raise HomographyError(f'{label}: duplicate points')
    return p


def _noncollinear(pts):
    centered=pts-np.mean(pts,axis=0)
    singular=np.linalg.svd(centered,compute_uv=False)
    return bool(singular[1]>1e-5*singular[0] and singular[1]>1e-8)


def _project(H,pts):
    pts_h=np.column_stack([pts,np.ones(len(pts))])
    tr=(H@pts_h.T).T
    if np.any(abs(tr[:,2])<1e-11) or not np.isfinite(tr).all():
        raise HomographyError('Non-finite homography projection')
    return tr[:,:2]/tr[:,2:3]


def validate_planar_homography(world_xy, image_xy, train_indices, *,
        ransac_threshold_px:float=2.5, anomaly_threshold_px:float=3.0)->dict:
    world=_input_points(world_xy,'world_xy');image=_input_points(image_xy,'image_xy')
    if world.shape!=image.shape:raise HomographyError('World-image correspondence shape mismatch')
    idx=np.asarray(train_indices)
    if idx.ndim!=1 or len(idx)<4 or not np.issubdtype(idx.dtype,np.integer) or len(set(idx.tolist()))!=len(idx):
        raise HomographyError('Four or more distinct train indices required')
    if np.min(idx)<0 or np.max(idx)>=len(world):raise HomographyError('Training index out of bounds')
    other=np.array([i for i in range(len(world)) if i not in set(idx.tolist())],int)
    if len(other)<2:raise HomographyError('At least two independent holdout points required')
    if ransac_threshold_px<=0 or anomaly_threshold_px<=0:raise HomographyError('Positive thresholds required')
    if not _noncollinear(world[idx]) or not _noncollinear(image[idx]):
        return {'module':'G04_PLANAR_HOMOGRAPHY','state':'INDETERMINATE',
                'reason':'Training correspondences are (nearly) collinear.',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    # RANSAC for >4 pairs; four points exactly determine a homography and
    # leave no fitting degrees of freedom, making holdout even more important.
    method=cv2.RANSAC if len(idx)>4 else 0
    H, mask=cv2.findHomography(world[idx],image[idx],method, ransacReprojThreshold=ransac_threshold_px)
    if H is None or mask is None or not np.isfinite(H).all():
        return {'module':'G04_PLANAR_HOMOGRAPHY','state':'INDETERMINATE',
                'reason':'Homography fitting failed','decision':'NO_AI_ORIGIN_CONCLUSION'}
    if abs(np.linalg.det(H))<1e-12:
        return {'module':'G04_PLANAR_HOMOGRAPHY','state':'INDETERMINATE',
                'reason':'Singular fitted homography','decision':'NO_AI_ORIGIN_CONCLUSION'}
    try:
        predict_train=_project(H,world[idx]);predict_hold=_project(H,world[other]);
        # Symmetric transfer error is another useful diagnostic.
        inv_pred_hold=_project(np.linalg.inv(H),image[other])
    except (HomographyError,np.linalg.LinAlgError) as e:
        return {'module':'G04_PLANAR_HOMOGRAPHY','state':'INDETERMINATE','reason':str(e),
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    train_error=np.linalg.norm(predict_train-image[idx],axis=1)
    hold_error=np.linalg.norm(predict_hold-image[other],axis=1)
    inv_error=np.linalg.norm(inv_pred_hold-world[other],axis=1)
    if len(idx)>4 and int(np.sum(mask))<4:
        return {'module':'G04_PLANAR_HOMOGRAPHY','state':'INDETERMINATE',
                'reason':'Insufficient inlier correspondences', 'decision':'NO_AI_ORIGIN_CONCLUSION'}
    # This is a user-declared, uncalibrated engineering threshold, not a p-value.
    is_anomalous=float(np.sqrt(np.mean(hold_error**2)))>anomaly_threshold_px
    return {'module':'G04_PLANAR_HOMOGRAPHY',
            'state':'INCONSISTENT_UNDER_ASSUMPTIONS' if is_anomalous else 'MEASURED',
            'reason':'Holdout reprojection exceeds user-defined threshold.' if is_anomalous else 'Holdout error does not exceed threshold.',
            'H_world_plane_to_image':(H/H[2,2]).tolist(),
            'train_indices':idx.tolist(),'holdout_indices':other.tolist(),
            'train_inliers':int(np.sum(mask)),
            'train_reprojection_rmse_px':float(np.sqrt(np.mean(train_error**2))),
            'holdout_reprojection_errors_px':hold_error.tolist(),
            'holdout_reprojection_rmse_px':float(np.sqrt(np.mean(hold_error**2))),
            'holdout_inverse_world_rmse':float(np.sqrt(np.mean(inv_error**2))),
            'holdout_predictions_xy':predict_hold.tolist(),
            'holdout_threshold_px':float(anomaly_threshold_px),
            'assumption':'All world-image point pairs are matched on ONE physical planar surface; world coordinates are independently measured.',
            'limits':['User-supplied plane and correspondences; no automatic plane segmentation.',
                      'Metric error is in image pixels; an arbitrary plane coordinate scale affects inverse-world error.',
                      'Holdout threshold is not statistically calibrated.',
                      'A physical discrepancy does not identify AI generation.'],
            'decision':'NO_AI_ORIGIN_CONCLUSION'}


def analyze_g04_manifest(path:Path,out:Path,image_path:Path|None=None)->dict:
    d=json.loads(path.read_text(encoding='utf-8'))
    result=validate_planar_homography(d['world_points_xy'],d['image_points_xy'],d['training_indices'],
            ransac_threshold_px=d.get('ransac_threshold_px',2.5),
            anomaly_threshold_px=d.get('holdout_threshold_px',3.0))
    if image_path is not None:
        img=load_bgr(image_path)
        points=np.asarray(d['image_points_xy'],float)
        if np.any(points[:,0]<0) or np.any(points[:,0]>=img.shape[1]) or np.any(points[:,1]<0) or np.any(points[:,1]>=img.shape[0]):
            raise HomographyError('Image point outside image dimensions')
        ids=set(d['training_indices'])
        for j,(x,y) in enumerate(points):
            cv2.circle(img,(round(x),round(y)),5,(40,200,45) if j in ids else (30,160,255),-1)
        if result['state'] in ['MEASURED','INCONSISTENT_UNDER_ASSUMPTIONS']:
            for j,pred in zip(result['holdout_indices'],result['holdout_predictions_xy']):
                obs=tuple(np.round(points[j]).astype(int)); p=tuple(np.round(pred).astype(int))
                cv2.line(img,obs,p,(0,50,255),2,cv2.LINE_AA)
                cv2.drawMarker(img,p,(0,50,255),cv2.MARKER_CROSS,12,2)
        out.mkdir(parents=True,exist_ok=True)
        write_image(out/'g04_holdout_overlay.png',img)
        result['image_sha256']=hashlib.sha256(image_path.read_bytes()).hexdigest()
        result['overlay']='g04_holdout_overlay.png'
    out.mkdir(parents=True,exist_ok=True)
    (out/'g04_homography_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result
