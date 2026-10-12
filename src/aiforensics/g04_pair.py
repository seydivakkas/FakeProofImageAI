"""G04 photo-to-photo homography with *held-out descriptor matches*.

A fitted transformation is not proof both images show a planar scene: only
externally annotated surface correspondence or independently known H can
validate a physical plane. Holdout matches are withheld from parameter fitting
but not from initial correspondence discovery.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import cv2
import numpy as np
from .homography import validate_planar_homography
from .imaging import load_bgr, write_image


def match_photo_pair(im_a:np.ndarray, im_b:np.ndarray, *,
                     roi_a:np.ndarray|None=None, roi_b:np.ndarray|None=None,
                     ratio:float=.72, seed:int=25)->dict:
    if im_a.ndim!=3 or im_b.ndim!=3:raise ValueError('Expected BGR photograph pair')
    if not (0<ratio<1):raise ValueError('Ratio must be between 0 and 1')
    sift=cv2.SIFT_create(nfeatures=2600)
    ga=cv2.cvtColor(im_a,cv2.COLOR_BGR2GRAY)
    gb=cv2.cvtColor(im_b,cv2.COLOR_BGR2GRAY)
    ka,da=sift.detectAndCompute(ga,roi_a)
    kb,db=sift.detectAndCompute(gb,roi_b)
    result={'module':'G04_PHOTO_PAIR_HOMOGRAPHY',
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'status':'INDETERMINATE',
            'assumptions':['Correspondences represent a single plane for physical interpretation.',
                           'Images are pinhole/rectified or distortion is negligible.'],
            'limitations':['No independently measured scene geometry is established by SIFT features.',
                           'Holdout matches are independently withheld from homography fit, not from feature extraction.',
                           'Without externally supplied ground truth or plane ROI this is only geometric consistency.']}
    if da is None or db is None or len(ka)<12 or len(kb)<12:
        result['reason']='Insufficient SIFT features';return result
    nn=cv2.BFMatcher(cv2.NORM_L2).knnMatch(da,db,k=2)
    matches=[m for m,n in nn if m.distance<ratio*n.distance]
    result['ratio_test_matches']=len(matches)
    if len(matches)<16:
        result['reason']='Insufficient 2D correspondences';return result
    # SIFT gives multiple scales/orientations at the same pixel. Exact and
    # near-duplicate source/destination locations must not leak across split.
    unique=[];used_a=set();used_b=set()
    for m in sorted(matches,key=lambda m:m.distance):
        pa=ka[m.queryIdx].pt;pb=kb[m.trainIdx].pt
        key_a=(round(pa[0]/2),round(pa[1]/2))
        key_b=(round(pb[0]/2),round(pb[1]/2))
        if key_a in used_a or key_b in used_b:continue
        used_a.add(key_a);used_b.add(key_b);unique.append(m)
    if len(unique)<16:
        result['reason']='Insufficient spatially unique correspondences';return result
    a=np.array([ka[m.queryIdx].pt for m in unique],dtype=np.float64)
    b=np.array([kb[m.trainIdx].pt for m in unique],dtype=np.float64)
    result['spatially_unique_matches']=len(unique)
    rng=np.random.default_rng(seed)
    order=rng.permutation(len(a))
    train=sorted(order[:int(len(a)*.70)].tolist())
    if len(train)<8 or len(a)-len(train)<4:
        result['reason']='Not enough train or holdout matches';return result
    report=validate_planar_homography(a,b,train,ransac_threshold_px=2.5,anomaly_threshold_px=3.)
    result['status']=report['state'];result['train_count']=len(train);result['holdout_count']=len(a)-len(train)
    result['calibration_report']=report
    # Naive RMSE of noisy descriptor matches is not a geometric contradiction.
    # Separate correct-looking matches from gross mismatches without hiding any.
    err=np.asarray(report.get('holdout_reprojection_errors_px',[]),float)
    if len(err):
        threshold=3.0
        inlier=err<=threshold
        result['holdout_match_diagnostics']={
            'median_error_all_px':float(np.median(err)),
            'p90_error_all_px':float(np.percentile(err,90)),
            'max_error_all_px':float(np.max(err)),
            'inlier_fraction_at_3px':float(np.mean(inlier)),
            'inlier_count_at_3px':int(np.sum(inlier)),
            'outlier_count_over_3px':int(np.sum(~inlier)),
            'inlier_rmse_px':float(np.sqrt(np.mean(err[inlier]**2))) if inlier.any() else None}
        # Under automatic descriptor matching, significant outliers are an
        # association problem until separately verified: do not equate these
        # with a physical inconsistency in photographed scene geometry.
        result['status']='DESCRIPTIVE_PAIR_MATCHES_WITH_OUTLIERS' if (~inlier).any() else 'DESCRIPTIVE_PAIR_MATCHES'
        result['physical_consistency_verdict']='NOT_ASSESSED_WITH_INDEPENDENT_PLANE_MATCHES'
    result['matched_points_a']=a.tolist();result['matched_points_b']=b.tolist()
    result['source_H_known']=False
    # With no known, independently acquired H, mark original result descriptive only
    result['evidence_state']='PHOTO_PAIR_FIT_ONLY_NO_INDEPENDENT_PLANAR_GROUND_TRUTH'
    return result


def run_photo_pair(a_file:Path,b_file:Path,out:Path,*, known_h:np.ndarray|None=None)->dict:
    a=load_bgr(a_file);b=load_bgr(b_file)
    r=match_photo_pair(a,b)
    r['image_sha256_a']=hashlib.sha256(a_file.read_bytes()).hexdigest()
    r['image_sha256_b']=hashlib.sha256(b_file.read_bytes()).hexdigest()
    if known_h is not None and r['status'] not in ('INDETERMINATE',):
        H=np.asarray(known_h,float)
        if H.shape!=(3,3) or not np.isfinite(H).all() or abs(np.linalg.det(H))<1e-8:
            raise ValueError('Invalid known homography')
        hold=np.array(r['calibration_report']['holdout_indices'],int)
        p=np.array(r['matched_points_a'])[hold]
        truth=cv2.perspectiveTransform(p.astype(np.float64).reshape(-1,1,2),H).reshape(-1,2)
        observed=np.array(r['matched_points_b'])[hold]
        errs=np.linalg.norm(truth-observed,axis=1)
        r['independently_specified_H_holdout_rmse_px']=float(np.sqrt(np.mean(errs**2)))
        r['independently_specified_H_holdout_median_error_px']=float(np.median(errs))
        r['independently_specified_H_holdout_fraction_under_3px']=float(np.mean(errs<=3.))
        r['source_H_known']=True
        r['known_H']=H.tolist()
        r['evidence_state']='CONTROLLED_KNOWN_H_APPLIED_TO_PHOTOGRAPHIC_PIXELS'
    out.mkdir(parents=True,exist_ok=True)
    a_overlay=a.copy();b_overlay=b.copy()
    if r['status']!='INDETERMINATE':
        indices=r['calibration_report']['holdout_indices']
        pa=np.array(r['matched_points_a']);pb=np.array(r['matched_points_b'])
        for j in indices[:100]:
            ca=tuple(np.rint(pa[j]).astype(int));cb=tuple(np.rint(pb[j]).astype(int))
            cv2.circle(a_overlay,ca,2,(30,230,255),-1)
            cv2.circle(b_overlay,cb,2,(30,230,255),-1)
    write_image(out/'g04_pair_view_a.png',a_overlay)
    write_image(out/'g04_pair_view_b.png',b_overlay)
    r['overlays']=['g04_pair_view_a.png','g04_pair_view_b.png']
    (out/'g04_pair_report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False))
    return r
