"""P4-O01: conditional Brown–Conrady plumb-line and holdout calibration.

Coordinates are pixel observations and *independently supplied* ideal pinhole
coordinates. Neither physical scene authenticity nor AI generation is inferred.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class LensGeometryError(ValueError):
    """Invalid input or unidentifiable optical geometry."""


def _points(points, name="points"):
    a = np.asarray(points, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != 2 or len(a) < 1 or not np.all(np.isfinite(a)):
        raise LensGeometryError(f"{name} must contain finite Nx2 points")
    return a


def _camera(K):
    k = np.asarray(K, dtype=np.float64)
    if (k.shape != (3, 3) or not np.isfinite(k).all() or k[0,0] <= 0 or
            k[1,1] <= 0 or not np.allclose(k[2], [0,0,1], atol=1e-9) or
            abs(k[0,1]) > 1e-9 or abs(k[1,0]) > 1e-9 or
            abs(k[2,0]) > 1e-9 or abs(k[2,1]) > 1e-9):
        raise LensGeometryError("K must be finite zero-skew pinhole calibration with positive fx,fy")
    return k


def _coefficients(coeffs):
    d = np.asarray(coeffs, dtype=np.float64).reshape(-1)
    if len(d) not in (4, 5) or not np.isfinite(d).all():
        raise LensGeometryError("coefficients must be [k1,k2,p1,p2,(k3)]")
    if len(d) == 4:
        d = np.r_[d, 0.0]
    return d


def to_normalized(points_px, K):
    p, k = _points(points_px), _camera(K)
    return (p - k[:2, 2]) / np.array([k[0,0],k[1,1]])


def to_pixel(normalized, K):
    a,k = _points(normalized), _camera(K)
    return a * np.array([k[0,0],k[1,1]]) + k[:2,2]


def _features(normalized):
    n = _points(normalized, "normalized coordinates")
    x,y = n[:,0], n[:,1]
    r2=x*x+y*y
    r4=r2*r2
    r6=r4*r2
    # x/y distortion is exactly linear in [k1,k2,p1,p2,k3] if K and ideal points are KNOWN.
    dx=np.column_stack([x*r2, x*r4, 2*x*y, r2+2*x*x, x*r6])
    dy=np.column_stack([y*r2, y*r4, r2+2*y*y, 2*x*y, y*r6])
    return np.stack([dx,dy], axis=1)


def distort_normalized(normalized, coefficients):
    n=_points(normalized, "normalized coordinates")
    return n + np.einsum('ncp,p->nc', _features(n), _coefficients(coefficients))


def distort_pixels(ideal_px,K,coefficients):
    return to_pixel(distort_normalized(to_normalized(ideal_px,K),coefficients),K)


def radial_monotonicity(coefficients, radius_max=1.0, samples=256):
    """Radial derivative; for tangential terms validate the full Jacobian separately."""
    k1,k2,_,_,k3=_coefficients(coefficients)
    r=np.linspace(0.0,float(radius_max),int(samples))
    derivative=1 + 3*k1*r*r + 5*k2*r**4 + 7*k3*r**6
    return bool(np.all(derivative > 1e-6))


def jacobian_min_determinant(coefficients, radius_max=1.0, n_r=25, n_theta=32):
    d=_coefficients(coefficients)
    k1,k2,p1,p2,k3=d
    r=np.linspace(0,max(0.,float(radius_max)),n_r)
    theta=np.arange(n_theta)*2*np.pi/n_theta
    x=(r[:,None]*np.cos(theta)[None,:]).ravel()
    y=(r[:,None]*np.sin(theta)[None,:]).ravel()
    rr=x*x+y*y
    g=1+k1*rr+k2*rr**2+k3*rr**3
    h=2*k1+4*k2*rr+6*k3*rr**2
    j11=g+h*x*x + 2*p1*y + 6*p2*x
    j22=g+h*y*y + 6*p1*y + 2*p2*x
    j12=h*x*y + 2*p1*x + 2*p2*y
    return float(np.min(j11*j22-j12*j12))


def undistort_pixels(observed_px,K,coefficients, iterations=25, atol=1e-10):
    """Damped numeric inverse with explicit roundtrip and injectivity checks."""
    src=to_normalized(observed_px,K)
    d=_coefficients(coefficients)
    if np.max(np.linalg.norm(src,axis=1)) > 3.0:
        raise LensGeometryError("points outside supported normalized field")
    # cv2.undistortPointsIter is the independent upstream 5-coefficient solver.
    # Explicit round-trip verifies convergence, unlike a fixed iteration guess.
    k=_camera(K)
    uv=cv2.undistortPointsIter(np.asarray(observed_px,dtype=np.float64).reshape(-1,1,2),
        k,d.reshape(-1,1),None,None,
        (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS,int(iterations),float(atol)))
    n=np.asarray(uv,dtype=np.float64).reshape(-1,2)
    if not np.isfinite(n).all():
        raise LensGeometryError("undistortion did not converge to finite points")
    inverse_residual=np.linalg.norm(distort_normalized(n,d)-src,axis=1)
    if np.max(inverse_residual) > 1e-6:
        raise LensGeometryError("undistortion roundtrip residual exceeds tolerance")
    return to_pixel(n,k)


def plumb_line_rmse(points):
    """Orthogonal-distance RMS to total-least-squares line in pixels."""
    a=_points(points)
    if len(a)<3 or np.linalg.norm(a-a.mean(axis=0),axis=1).max()<1e-7:
        raise LensGeometryError("at least 3 geometrically distinct line points required")
    ac=a-a.mean(axis=0)
    _,s,vt=np.linalg.svd(ac,full_matrices=False)
    if s[0]<1e-8:
        raise LensGeometryError("degenerate line")
    return float(np.sqrt(np.mean((ac@vt[1])**2)))


def _matrix(ideal,K,order):
    n=to_normalized(ideal,K)
    f=_features(n)[:,:,:order]
    k=_camera(K)
    f[:,0,:]*=k[0,0]
    f[:,1,:]*=k[1,1]
    return f.reshape(-1,order)


def fit_coefficients(train_ideal,train_observed,K,order=5, max_condition=2e7):
    """Robust linear inverse; requires independent ideal pixel coordinates and known K."""
    ideal=_points(train_ideal,"train ideal")
    observed=_points(train_observed,"train observed")
    if ideal.shape!=observed.shape or len(ideal)<max(10,3*order):
        raise LensGeometryError("insufficient known point pairs for calibration")
    if order not in (4,5):
        raise LensGeometryError("Brown-Conrady order must be 4 or 5")
    A=_matrix(ideal,K,order)
    target=(observed-ideal).ravel()
    singular=np.linalg.svd(A,compute_uv=False)
    condition=float(singular[0]/singular[-1]) if singular[-1]>0 else float('inf')
    if not np.isfinite(condition) or condition>max_condition:
        raise LensGeometryError(f"ill-conditioned optical calibration design (condition={condition:.3g})")
    coeffs=np.linalg.lstsq(A,target,rcond=None)[0]
    # IRLS with scalar per-POINT weights for outliers (not independent x/y downweighting).
    for _ in range(14):
        e=((A@coeffs-target).reshape(-1,2))
        norms=np.linalg.norm(e,axis=1)
        med=float(np.median(norms))
        sigma=max(0.05,1.4826*float(np.median(np.abs(norms-med))))
        cutoff=max(.5,2.5*sigma)
        weights=np.minimum(1.,cutoff/np.maximum(norms,1e-9))
        w=np.repeat(np.sqrt(weights),2)
        newer=np.linalg.lstsq(A*w[:,None],target*w,rcond=None)[0]
        if np.linalg.norm(newer-coeffs) < 1e-12:
            coeffs=newer;break
        coeffs=newer
    if order==4: coeffs=np.r_[coeffs,0.]
    if not np.all(np.isfinite(coeffs)) or np.max(np.abs(coeffs)) > 2.0:
        raise LensGeometryError("unstable fitted distortion coefficients")
    return coeffs, condition


@dataclass(frozen=True)
class LensConfig:
    order: int=5
    holdout_threshold_px:float=2.0
    line_threshold_px:float=1.5
    min_holdout:int=8


def analyze_manifest(data,config:LensConfig=LensConfig()):
    """Sole calibration interface. Rejects train/holdout leakage by explicit IDs."""
    if not isinstance(data,dict): raise LensGeometryError("manifest must be an object")
    K=_camera(data.get('K'))
    provenance=data.get('data_provenance')
    if provenance not in ('SYNTHETIC_KNOWN_TRUTH','INDEPENDENT_MEASURED_GEOMETRY'):
        return {'module':'P4_O01','state':'INDETERMINATE',
                'reason':'ideal-coordinate provenance must be declared and independently justified',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    observations=data.get('point_pairs')
    if not isinstance(observations,list) or not observations:
        raise LensGeometryError("point_pairs with train and holdout roles required")
    ids=set(); groups={"train":[],"holdout":[]}
    for record in observations:
        if not isinstance(record,dict): raise LensGeometryError("invalid point record")
        id_=str(record.get('id',''))
        role=record.get('role')
        if not id_ or id_ in ids or role not in groups:
            raise LensGeometryError("point IDs must be unique, and role must be train or holdout")
        ids.add(id_)
        ideal=_points([record.get('ideal_xy_px')],"ideal point")[0]
        seen=_points([record.get('observed_xy_px')],"observed point")[0]
        groups[role].append((id_,ideal,seen))
    if len(groups['train'])<max(10,config.order*3) or len(groups['holdout'])<config.min_holdout:
        return {'module':'P4_O01','state':'INDETERMINATE','reason':'insufficient disjoint training/holdout points',
                'train_count':len(groups['train']),'holdout_count':len(groups['holdout']),
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    train=groups['train']; holdout=groups['holdout']
    try:
        coeff,cond=fit_coefficients(np.array([x[1] for x in train]),
                                      np.array([x[2] for x in train]),K,config.order)
    except LensGeometryError as exc:
        return {'module':'P4_O01','state':'INDETERMINATE',
                'reason':str(exc),'train_count':len(train),'holdout_count':len(holdout),
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    all_ideal=np.array([x[1] for x in train+holdout])
    sampled_radius=float(np.max(np.linalg.norm(to_normalized(all_ideal,K),axis=1)))
    monotonous=radial_monotonicity(coeff,sampled_radius*1.02)
    min_jac=jacobian_min_determinant(coeff,sampled_radius*1.02)
    if not monotonous or min_jac<=1e-5:
        return {'module':'P4_O01','state':'INDETERMINATE',
            'reason':'fitted mapping is noninvertible or nonmonotonic over sampled image field',
            'coefficients':coeff.tolist(),'radial_monotonic':monotonous,
            'jacobian_min_determinant':min_jac,'decision':'NO_AI_ORIGIN_CONCLUSION'}
    def errors(collection):
        ideal=np.array([x[1] for x in collection]);observed=np.array([x[2] for x in collection])
        residual=np.linalg.norm(distort_pixels(ideal,K,coeff)-observed,axis=1)
        return residual
    train_err=errors(train);hold_err=errors(holdout)
    holdout_ideal=np.array([x[1] for x in holdout])
    holdout_seen=np.array([x[2] for x in holdout])
    holdout_no_correction_rmse=float(np.sqrt(np.mean(
        np.sum((holdout_ideal-holdout_seen)**2,axis=1))))
    lines=[]
    for i,line in enumerate(data.get('independent_straight_lines',[])):
        if not isinstance(line,dict) or not line.get('externally_verified_straight',False):
            continue
        raw=_points(line.get('observed_points_xy_px'),f'line {i}')
        if len(raw)<5: continue
        try:
            after=undistort_pixels(raw,K,coeff)
            before_rmse=plumb_line_rmse(raw)
            after_rmse=plumb_line_rmse(after)
        except LensGeometryError:
            lines.append({'id':line.get('id',str(i)),'state':'INDETERMINATE','reason':'non-invertible / degenerate sampled line'})
            continue
        lines.append({'id':line.get('id',str(i)),'state':'MEASURED',
                      'before_rmse_px':before_rmse,'after_rmse_px':after_rmse,
                      'after_consistent':bool(after_rmse<=config.line_threshold_px),
                      'sample_count':len(raw)})
    any_bad_line=any(x['state']=='MEASURED' and not x['after_consistent'] for x in lines)
    held_out_good=float(np.sqrt(np.mean(hold_err**2)))<=config.holdout_threshold_px
    status=('CONSISTENT_UNDER_ASSUMPTIONS' if held_out_good and not any_bad_line
            else 'INCONSISTENT_UNDER_ASSUMPTIONS')
    return {'module':'P4_O01_BROWN_CONRADY','state':status,'model':'5_coefficient_brown_conrady',
        'coefficients_order':'k1,k2,p1,p2,k3','coefficients':coeff.tolist(),
        'K':K.tolist(),'data_provenance':provenance,
        'train_count':len(train),'holdout_count':len(holdout),
        'train_rmse_px':float(np.sqrt(np.mean(train_err**2))),
        'holdout_rmse_px':float(np.sqrt(np.mean(hold_err**2))),
        'holdout_uncorrected_rmse_px':holdout_no_correction_rmse,
        'holdout_median_px':float(np.median(hold_err)),
        'holdout_p90_px':float(np.percentile(hold_err,90)),
        'holdout_residuals':[{'id':x[0],'error_px':float(e)} for x,e in zip(holdout,hold_err)],
        'condition_number':cond,'radial_monotonic':monotonous,
        'jacobian_min_determinant':min_jac,'radius_max_normalized':sampled_radius,
        'line_holdouts':lines,
        'assumptions':['K externally calibrated and corresponds to same resolution/crop',
          'ideal pixel correspondences independently measured from verified geometry',
          'same lens settings throughout image','single central perspective Brown-Conrady lens',
          'line holdouts independently verified straight in 3D',
          'distortion fit and holdout IDs disjoint'],
        'limitations':['distortion is normal camera optics, never proof of AI or manipulation',
          '5 coefficient model excludes fisheye, rolling shutter, local warp, decentered complex lenses',
          'line goodness only evaluated for explicitly verified straight edges',
          'train fit and holdout use same claimed K; calibration uncertainty not propagated'],
        'decision':'NO_AI_ORIGIN_CONCLUSION'}


def run_lens_manifest(path,out,image=None,config:LensConfig=LensConfig()):
    path=Path(path); out=Path(out)
    data=json.loads(path.read_text(encoding='utf-8'))
    result=analyze_manifest(data,config)
    result['manifest_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    out.mkdir(parents=True,exist_ok=True)
    if image is not None:
        image=Path(image)
        canvas=cv2.imread(str(image))
        if canvas is None: raise LensGeometryError('could not read supplied image')
        result['image_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
        result['image_dimensions_hw']=list(canvas.shape[:2])
        for point in data.get('point_pairs',[]):
            xy=np.rint(point['observed_xy_px']).astype(int)
            color=(0,190,0) if point.get('role')=='train' else (20,190,255)
            cv2.circle(canvas,tuple(xy),3,color,-1,cv2.LINE_AA)
        for line in data.get('independent_straight_lines',[]):
            pts=np.rint(line.get('observed_points_xy_px',[])).astype(np.int32)
            if len(pts)>=2:cv2.polylines(canvas,[pts],False,(255,120,0),2,cv2.LINE_AA)
        cv2.putText(canvas,'SYNTHETIC OR ANNOTATED OPTICAL MEASUREMENTS - NO AI ORIGIN CLAIM',
            (16,canvas.shape[0]-18),cv2.FONT_HERSHEY_SIMPLEX,.54,(255,255,255),1,cv2.LINE_AA)
        cv2.imwrite(str(out/'p4_o01_overlay.png'),canvas)
        result['overlay']='p4_o01_overlay.png'
        if 'coefficients' in result and result['state'] in (
                'CONSISTENT_UNDER_ASSUMPTIONS','INCONSISTENT_UNDER_ASSUMPTIONS'):
            # Descriptive rectification only. No automatic authenticity verdict.
            rectified=cv2.undistort(cv2.imread(str(image)),
                                    _camera(data['K']),np.asarray(result['coefficients'],dtype=float))
            if not cv2.imwrite(str(out/'p4_o01_rectified.png'),rectified):
                raise LensGeometryError('could not write optical rectification preview')
            result['rectified_preview']='p4_o01_rectified.png'
    (out/'p4_o01_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result
