"""P4-O03: conditional focal length, field of view, perspective & sensor consistency.

Requires independently established 3D points, camera pose, provenance and optical
measurements. Neither fitting residuals nor metadata alone indicate AI origin.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from pathlib import Path
import numpy as np
from .lens_distortion import distort_pixels, LensGeometryError


class OpticalConsistencyError(ValueError):
    """Invalid/degenerate geometric constraints."""


def _positive(value, label):
    try: v=float(value)
    except (TypeError,ValueError,OverflowError) as e: raise OpticalConsistencyError(f'{label} must be finite positive') from e
    if not (np.isfinite(v) and v>0): raise OpticalConsistencyError(f'{label} must be finite positive')
    return v


def _vec(a, n, label):
    v=np.asarray(a,dtype=float)
    if v.shape!=(n,) or not np.isfinite(v).all():
        raise OpticalConsistencyError(f'{label} must contain {n} finite values')
    return v


def _size(a):
    v=_vec(a,2,'image_size_wh')
    if np.any(v<=0) or not np.allclose(v,np.rint(v)):
        raise OpticalConsistencyError('image_size_wh must be positive integer dimensions')
    return (int(v[0]),int(v[1]))


def _K(m):
    k=np.asarray(m,dtype=float)
    if (k.shape!=(3,3) or not np.isfinite(k).all() or k[0,0]<=0 or k[1,1]<=0 or
        not np.allclose(k[2,:],[0,0,1],atol=1e-10) or
        abs(k[0,1])>1e-9 or abs(k[1,0])>1e-9):
        raise OpticalConsistencyError('K must be finite, positive-focal, zero-skew 3x3 pinhole matrix')
    return k


def focal_to_fov(focal_px, principal_px, count_px):
    """Total angular FoV with off-center principal point (zero skew)."""
    f=_positive(focal_px,'focal length in pixels')
    c=float(principal_px)
    n=_positive(count_px,'sensor extent in pixels')
    if not np.isfinite(c) or not (0<=c<=n):
        raise OpticalConsistencyError('principal point outside image: FoV of full sensor not certified')
    return math.degrees(math.atan(c/f)+math.atan((n-c)/f))


def camera_fovs(K, image_size_wh):
    k=_K(K);w,h=_size(image_size_wh)
    def ray(x,y):
        r=np.array([(x-k[0,2])/k[0,0],(y-k[1,2])/k[1,1],1.],float)
        return r/np.linalg.norm(r)
    def angle(a,b):
        return float(math.degrees(math.acos(np.clip(np.dot(a,b),-1.,1.))))
    diagonal_1=angle(ray(0,0),ray(w,h))
    diagonal_2=angle(ray(w,0),ray(0,h))
    return {'horizontal_deg':focal_to_fov(k[0,0],k[0,2],w),
            'vertical_deg':focal_to_fov(k[1,1],k[1,2],h),
            'diagonal_spans_deg':[diagonal_1,diagonal_2],
            'principal_point_xy_px':k[:2,2].tolist()}


def native_to_output_K(native_K,native_wh,crop_xywh,resize_wh):
    """Crop then resize: fx/fy scale independently; principal point translates/scales."""
    k=_K(native_K);nw,nh=_size(native_wh)
    x,y,cw,ch=_vec(crop_xywh,4,'crop_xywh')
    ow,oh=_size(resize_wh)
    if cw<=0 or ch<=0 or min(x,y)<0 or x+cw>nw+1e-8 or y+ch>nh+1e-8:
        raise OpticalConsistencyError('invalid crop rectangle outside native sensor')
    sx,sy=ow/cw,oh/ch
    out=k.copy();out[0,0]*=sx;out[1,1]*=sy
    out[0,2]=(k[0,2]-x)*sx;out[1,2]=(k[1,2]-y)*sy
    return out


def _pose(obj):
    if not isinstance(obj,dict):raise OpticalConsistencyError('pose required')
    R=np.asarray(obj.get('R_world_to_camera'),dtype=float)
    t=_vec(obj.get('t_world_to_camera'),3,'pose translation')
    if (R.shape!=(3,3) or not np.isfinite(R).all() or
        np.linalg.norm(R.T@R-np.eye(3),ord='fro')>1e-5 or np.linalg.det(R)<0.99999 or np.linalg.det(R)>1.00001):
        raise OpticalConsistencyError('R must be a proper orthonormal 3D rotation')
    return R,t


def project_points(world_xyz,K,R,t,coefficients=None):
    p=np.asarray(world_xyz,dtype=float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all():
        raise OpticalConsistencyError('world_xyz must be finite Nx3')
    camera=p@R.T+t
    if np.any(camera[:,2]<=1e-7):
        raise OpticalConsistencyError('point behind or on camera focal plane')
    k=_K(K)
    ideal=camera[:,:2]/camera[:,2:3]*np.array([k[0,0],k[1,1]])+k[:2,2]
    if coefficients is None:return ideal
    try: return distort_pixels(ideal,k,coefficients)
    except LensGeometryError as e:raise OpticalConsistencyError(str(e)) from e


def _fit_focal(points, observations, R,t, principal):
    cam=points@R.T+t
    if np.any(cam[:,2]<=1e-7):raise OpticalConsistencyError('training point behind camera')
    n=cam[:,:2]/cam[:,2:3]
    if (len(n)<10 or np.std(n[:,0])<0.035 or np.std(n[:,1])<0.035 or
            np.ptp(n[:,0])<.15 or np.ptp(n[:,1])<.15):
        raise OpticalConsistencyError('insufficient focal calibration diversity')
    d=observations-principal
    f=[]
    for axis in (0,1):
        x=n[:,axis]; y=d[:,axis]
        val=float(np.dot(x,y)/np.dot(x,x))
        for _ in range(20):
            residual=y-x*val
            mad=1.4826*np.median(np.abs(residual-np.median(residual)))
            cutoff=max(.6,2.5*mad)
            weights=np.minimum(1.,cutoff/np.maximum(np.abs(residual),1.e-9))
            v=float(np.sum(weights*x*y)/np.sum(weights*x*x))
            if abs(v-val)<1e-10:break
            val=v
        if val<=0 or not np.isfinite(val):raise OpticalConsistencyError('focal calibration not physically positive')
        f.append(val)
    return np.array([[f[0],0,principal[0]],[0,f[1],principal[1]],[0,0,1.]],float)


@dataclass(frozen=True)
class OpticalConfig:
    tolerance_px:float=2.5
    tolerance_fov_deg:float=0.8
    tolerance_focal_mm:float=.12
    min_holdout:int=8


def analyze_optical_manifest(data,config=OpticalConfig()):
    if not isinstance(data,dict):raise OpticalConsistencyError('manifest must be JSON object')
    if any(not np.isfinite(x) or x<=0 for x in
           (config.tolerance_px,config.tolerance_fov_deg,config.tolerance_focal_mm)):
        raise OpticalConsistencyError('thresholds must be finite positive')
    wh=_size(data.get('image_size_wh'))
    if data.get('data_provenance') not in ('SYNTHETIC_KNOWN_TRUTH','INDEPENDENT_MEASURED_GEOMETRY'):
        return {'module':'P4_O03','state':'INDETERMINATE','reason':'independently justified geometry provenance required',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    R,t=_pose(data.get('pose'))
    records=data.get('samples')
    if not isinstance(records,list) or not records:
        raise OpticalConsistencyError('samples are required')
    seen=set();train=[];holdout=[]
    for item in records:
        if not isinstance(item,dict):raise OpticalConsistencyError('invalid sample')
        name=item.get('id');role=item.get('role')
        if not isinstance(name,str) or not name or name in seen or role not in ('train','holdout'):
            raise OpticalConsistencyError('unique IDs and train/holdout roles required')
        seen.add(name)
        xyz=_vec(item.get('world_xyz'),3,'world_xyz')
        observed=_vec(item.get('observed_xy_px'),2,'observed_xy_px')
        sigma=_positive(item.get('observed_sigma_px'),'measurement sigma')
        item_tuple=(name,xyz,observed,sigma,item.get('measurement_provenance'))
        (train if role=='train' else holdout).append(item_tuple)
    if len(holdout)<config.min_holdout:
        return {'module':'P4_O03','state':'INDETERMINATE','reason':'insufficient disjoint holdout points',
                'holdout_count':len(holdout),'decision':'NO_AI_ORIGIN_CONCLUSION'}
    mode=data.get('calibration_mode','known_K')
    if mode=='known_K':
        K=_K(data.get('K'))
        if not (0<=K[0,2]<=wh[0] and 0<=K[1,2]<=wh[1]):
            return {'module':'P4_O03','state':'INDETERMINATE',
                    'reason':'principal point off imaging crop; valid FoV not identified','decision':'NO_AI_ORIGIN_CONCLUSION'}
    elif mode=='fit_focal_from_train':
        if data.get('brown_conrady_coefficients') is not None:
            return {'module':'P4_O03','state':'INDETERMINATE',
                    'reason':'joint focal/distortion identification not implemented: undistort independently first',
                    'decision':'NO_AI_ORIGIN_CONCLUSION'}
        if len(train)<10:raise OpticalConsistencyError('at least 10 train points required for focal fit')
        if any(r[4] not in ('synthetic_known_correspondence','independent_measured_correspondence') for r in train):
            return {'module':'P4_O03','state':'INDETERMINATE',
                    'reason':'focal fitting requires independently verified training correspondences',
                    'decision':'NO_AI_ORIGIN_CONCLUSION'}
        pp=_vec(data.get('principal_point_xy_px'),2,'independently established principal point')
        if not (0<=pp[0]<=wh[0] and 0<=pp[1]<=wh[1]):
            raise OpticalConsistencyError('principal point outside crop')
        try:K=_fit_focal(np.array([a[1] for a in train]),np.array([a[2] for a in train]),R,t,pp)
        except OpticalConsistencyError as e:
            return {'module':'P4_O03','state':'INDETERMINATE','reason':str(e),'decision':'NO_AI_ORIGIN_CONCLUSION'}
    else:raise OpticalConsistencyError('unrecognized calibration_mode')
    coeff=data.get('brown_conrady_coefficients')
    if coeff is not None:
        coeff=np.asarray(coeff,dtype=float)
        if coeff.shape not in ((4,),(5,)) or not np.isfinite(coeff).all():
            raise OpticalConsistencyError('invalid Brown-Conrady distortion coefficients')
    fovs=camera_fovs(K,wh)
    checks=[]
    def check(name,actual,expected,tolerance,unit):
        error=abs(actual-expected)
        checks.append({'name':name,'expected':float(expected),'measured':float(actual),
                       'absolute_error':float(error),'tolerance':float(tolerance),'unit':unit,
                       'state':'CONSISTENT' if error<=tolerance else 'INCONSISTENT_UNDER_ASSUMPTIONS'})
    meta=data.get('sensor_metadata',{})
    if meta is None or not isinstance(meta,dict):raise OpticalConsistencyError('sensor_metadata must be object')
    native_k=None
    if data.get('image_transform'):
        trans=data['image_transform']
        native_k=_K(trans.get('native_K'))
        native_wh=_size(trans.get('native_image_size_wh'))
        computed=native_to_output_K(native_k,native_wh,trans.get('crop_xywh'),wh)
        for label,i,j in (('fx',0,0),('fy',1,1),('cx',0,2),('cy',1,2)):
            check('crop_resize_K_'+label,float(K[i,j]),float(computed[i,j]),config.tolerance_px,'px')
    if 'pixel_pitch_x_um' in meta or 'pixel_pitch_y_um' in meta:
        px=_positive(meta.get('pixel_pitch_x_um'),'native horizontal pitch')
        py=_positive(meta.get('pixel_pitch_y_um'),'native vertical pitch')
        ref=native_k if native_k is not None else K
        x=ref[0,0]*px/1000;y=ref[1,1]*py/1000
        check('horizontal_vs_vertical_focal_mm',x,y,config.tolerance_focal_mm,'mm')
        if 'focal_length_mm' in meta:
            expected=_positive(meta.get('focal_length_mm'),'measured focal_length_mm')
            check('horizontal_focal_vs_measured_mm',x,expected,config.tolerance_focal_mm,'mm')
            check('vertical_focal_vs_measured_mm',y,expected,config.tolerance_focal_mm,'mm')
    claims=data.get('independent_claims',{})
    if not isinstance(claims,dict):raise OpticalConsistencyError('independent_claims must be object')
    for field,angle in (('horizontal_fov_deg','horizontal_deg'),('vertical_fov_deg','vertical_deg')):
        if field in claims:
            claimed=_positive(claims[field],field)
            if claimed>=180:raise OpticalConsistencyError('FoV must be <180 degrees')
            check(field,fovs[angle],claimed,config.tolerance_fov_deg,'deg')
    results=[]
    for id_,xyz,observed,sigma,provenance in holdout:
        try:
            predicted=project_points(np.array([xyz]),K,R,t,coeff)[0]
            residual=float(np.linalg.norm(observed-predicted))
            within=0<=predicted[0]<wh[0] and 0<=predicted[1]<wh[1]
            supported=provenance in ('synthetic_known_correspondence','independent_measured_correspondence')
            state=('INDETERMINATE' if not within or not supported else
                   'CONSISTENT' if residual<=max(config.tolerance_px,3*sigma) else
                   'INCONSISTENT_UNDER_ASSUMPTIONS')
            reason=('unobservable outside image' if not within else
                    'unverified measured correspondence' if not supported else 'conditional reprojection residual')
            results.append({'id':id_,'predicted_xy_px':predicted.tolist(),'observed_xy_px':observed.tolist(),
                            'residual_px':residual,'sigma_px':sigma,'state':state,'reason':reason})
        except OpticalConsistencyError as e:
            results.append({'id':id_,'state':'INDETERMINATE','reason':str(e)})
    # Additional independently supplied VP directions from G01/G02 can be checked without refitting K.
    vp_results=[]; vp_ids=set()
    for item in data.get('vanishing_point_holdouts',[]):
        id_=item.get('id')
        if not isinstance(id_,str) or not id_ or id_ in vp_ids or id_ in seen:
            raise OpticalConsistencyError('unique independent VP IDs required')
        vp_ids.add(id_)
        direction=_vec(item.get('direction_world'),3,'vanishing direction')
        v=R@direction
        if np.linalg.norm(v)<1e-12:raise OpticalConsistencyError('zero vanishing direction')
        if abs(v[2])<1e-6:
            vp_results.append({'id':id_,'state':'INDETERMINATE','reason':'vanishing point at infinity'})
            continue
        p=K@(v/v[2]); px=p[:2]
        if coeff is not None:
            vp_results.append({'id':id_,'state':'INDETERMINATE','reason':'nonlinear distortion means a straight line has no single ideal VP; rectify first'})
            continue
        obs=_vec(item.get('observed_xy_px'),2,'observed VP')
        sigma=_positive(item.get('observed_sigma_px'),'VP sigma')
        e=float(np.linalg.norm(px-obs))
        verified=item.get('measurement_provenance')=='independent_direction_and_vp'
        state='INDETERMINATE' if not verified else ('CONSISTENT' if e<=max(config.tolerance_px,3*sigma) else 'INCONSISTENT_UNDER_ASSUMPTIONS')
        vp_results.append({'id':id_,'predicted_xy_px':px.tolist(),'observed_xy_px':obs.tolist(),
                           'residual_px':e,'state':state})
    segment_results=[]; segment_ids=set()
    for item in data.get('segment_holdouts',[]):
        seg_id=item.get('id')
        if not isinstance(seg_id,str) or not seg_id or seg_id in segment_ids or seg_id in seen or seg_id in vp_ids:
            raise OpticalConsistencyError('segment holdout ID must be unique')
        segment_ids.add(seg_id)
        endpoints=np.asarray(item.get('world_endpoints'),dtype=float)
        observed=np.asarray(item.get('observed_endpoints_xy_px'),dtype=float)
        if endpoints.shape!=(2,3) or observed.shape!=(2,2) or not np.isfinite(endpoints).all() or not np.isfinite(observed).all():
            raise OpticalConsistencyError('segment endpoints must be finite 2x3 and 2x2')
        sigma=_positive(item.get('observed_sigma_px'),'segment sigma')
        if np.linalg.norm(endpoints[0]-endpoints[1])<1e-5:
            raise OpticalConsistencyError('zero-length 3D segment')
        try:
            pred=project_points(endpoints,K,R,t,coeff)
            error=float(np.sqrt(np.mean(np.sum((pred-observed)**2,axis=1))))
            valid=np.all((pred[:,0]>=0)&(pred[:,0]<wh[0])&(pred[:,1]>=0)&(pred[:,1]<wh[1]))
            provenance=item.get('measurement_provenance')=='independent_3d_segment'
            state='INDETERMINATE' if not valid or not provenance else ('CONSISTENT' if error<=max(config.tolerance_px,3*sigma) else 'INCONSISTENT_UNDER_ASSUMPTIONS')
            segment_results.append({'id':seg_id,'expected_length_px':float(np.linalg.norm(pred[1]-pred[0])),
                'observed_length_px':float(np.linalg.norm(observed[1]-observed[0])),
                'endpoint_rmse_px':error,'state':state,'predicted_endpoints_xy_px':pred.tolist()})
        except OpticalConsistencyError as e:
            segment_results.append({'id':seg_id,'state':'INDETERMINATE','reason':str(e)})
    n_bad=sum(z['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for z in results+checks+vp_results+segment_results)
    n_good=sum(z['state']=='CONSISTENT' for z in results+checks+vp_results+segment_results)
    n_unknown=sum(z['state']=='INDETERMINATE' for z in results+vp_results+segment_results)
    result_state='INCONSISTENT_UNDER_ASSUMPTIONS' if n_bad else 'CONSISTENT' if n_good and not n_unknown else 'INDETERMINATE'
    errors=np.array([z['residual_px'] for z in results if z['state']=='CONSISTENT'],dtype=float)
    return {'module':'P4_O03','state':result_state,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'calibration_mode':mode,'K':K.tolist(),'camera_fovs':fovs,
            'holdout_count':len(holdout),'train_count':len(train),
            'counts':{'consistent':n_good,'inconsistent':n_bad,'indeterminate':n_unknown},
            'holdout_rmse_px_consistent_only':float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
            'sensor_and_claim_checks':checks,'holdout_results':results,'vanishing_point_holdouts':vp_results,
            'segment_holdouts':segment_results,
            'assumptions':['known camera pose and physical 3D correspondences',
               'zero skew and principal point known independently',
               'no panorama/rolling shutter/projective warp; Brown-Conrady only if provided',
               'sensor pixel pitch is native if crop/resize specified; focal length claim independent'],
            'limitations':['comparison is conditional on pose/3D measurements and metadata',
               'fitting uses only train, but may not identify skew or pose error',
               'field of view cannot prove photographic provenance or AI origin']}




def run_optical_manifest(path,out,config=OpticalConfig()):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    report=analyze_optical_manifest(data,config)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'p4_o03_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
