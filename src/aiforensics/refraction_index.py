"""P3-R02 optional conditional Snell index estimate, with explicit disjoint holdout.

Only a SINGLE planar interface and known 3D point correspondences are supported.
No estimation from an uncalibrated photograph; the held-out points alone
validate the fitted index. A training residual is NOT independent evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np

from .mirror_geometry import CalibratedCamera, unit
from .refraction_geometry import (
    RefractiveInterface, RefractionGeometryError, _v2, _v3,
    analyze_refraction_manifest,
)


def pointwise_index(camera, face, object_world_xyz, pixel, min_incidence_deg=4.,
                    azimuth_tolerance_deg=3.):
    """From observed incoming ray and known target 3D point infer n_target.

    Enforce tangential incidence/transmission ray coplanarity BEFORE using a
    scalar Snell index. At normal incidence index is unobservable.
    """
    C=camera.center
    P=_v3(object_world_xyz,'object_world_xyz')
    face.depth_intervals(C,P)
    d=camera.ray(_v2(pixel,'observed_xy'))
    n=face.normal
    cosine=float(d@n)
    if cosine>=-1e-10:
        raise RefractionGeometryError('observed ray does not face the interface')
    distance=-face.signed(C)/cosine
    if distance<=1e-9:
        raise RefractionGeometryError('interface is not in front of camera')
    M=C+distance*d
    if not face.aperture_contains(M):
        raise RefractionGeometryError('observed ray hits outside aperture polygon')
    outgoing=unit(P-M,'transmitted ray to known object')
    if float(outgoing@n)>=-1e-10:
        raise RefractionGeometryError('target ray must enter transmitted side')
    ti=d-float(d@n)*n
    tt=outgoing-float(outgoing@n)*n
    si=float(np.linalg.norm(ti));st=float(np.linalg.norm(tt))
    if np.rad2deg(np.arcsin(np.clip(si,0,1)))<min_incidence_deg or st<1e-4:
        raise RefractionGeometryError('near-normal incidence does not identify index stably')
    azimuth=float(np.rad2deg(np.arccos(np.clip(np.dot(ti,tt)/(si*st),-1,1))))
    if azimuth>azimuth_tolerance_deg:
        raise RefractionGeometryError('observed rays violate Snell plane of incidence')
    n_target=face.n_camera*si/st
    if not np.isfinite(n_target) or n_target<=0:
        raise RefractionGeometryError('index estimate is not physically valid')
    return {'estimated_n_transmitted':float(n_target),
            'incidence_deg':float(np.rad2deg(np.arcsin(np.clip(si,0,1)))),
            'transmitted_deg':float(np.rad2deg(np.arcsin(np.clip(st,0,1)))),
            'ray_plane_azimuth_error_deg':azimuth,'interface_hit_world':M.tolist()}


def estimate_index_manifest(data, tolerance_px=3., min_train=3, min_holdout=3):
    if not isinstance(data,dict) or not isinstance(data.get('interface'),dict):
        raise RefractionGeometryError('manifest and interface must be JSON objects')
    info=data['interface']
    if info.get('model')!='single_interface':
        raise RefractionGeometryError('index estimation currently supports only single_interface')
    import copy
    model=copy.deepcopy(info)
    model['n_layer']=1.0 # only a structurally valid placeholder, NEVER a fitted value
    face=RefractiveInterface.from_manifest(model)
    camera=CalibratedCamera.from_manifest(data['camera'])
    if face.signed(camera.center)<=1e-9:
        raise RefractionGeometryError('interface normal must face camera')
    fit=data.get('index_fit')
    if not isinstance(fit,dict):
        raise RefractionGeometryError('explicit index_fit train_ids and holdout_ids required')
    train=fit.get('train_ids');holdout=fit.get('holdout_ids')
    if not isinstance(train,list) or not isinstance(holdout,list) or not all(isinstance(x,str) for x in train+holdout):
        raise RefractionGeometryError('fit indices must be lists of string IDs')
    if len(set(train))!=len(train) or len(set(holdout))!=len(holdout) or set(train)&set(holdout):
        raise RefractionGeometryError('train and holdout IDs must be unique and disjoint')
    if len(train)<min_train or len(holdout)<min_holdout:
        raise RefractionGeometryError('insufficient explicitly separated train or holdout count')
    shape=data.get('image_shape_hw')
    if not (isinstance(shape,list) and len(shape)==2 and all(type(v) is int and v>0 for v in shape)):
        raise RefractionGeometryError('image_shape_hw must contain positive height and width')
    obs=data.get('correspondences')
    if not isinstance(obs,list) or any(not isinstance(x,dict) for x in obs):
        raise RefractionGeometryError('correspondences must be a list of objects')
    ids=[str(x.get('id')) for x in obs]
    if len(ids)!=len(set(ids)):
        raise RefractionGeometryError('duplicate correspondence id')
    byid={str(x['id']):x for x in obs if 'id' in x}
    if not set(train+holdout).issubset(byid):
        raise RefractionGeometryError('all train/holdout IDs must be present in correspondences')
    per_point=[];good=[]
    for ident in train:
        row=byid[ident]
        try:
            uv=_v2(row['observed_xy'],'observed_xy')
            if not (0<=uv[0]<shape[1] and 0<=uv[1]<shape[0]):
                raise RefractionGeometryError('training observation is outside image bounds')
            estimate=pointwise_index(camera,face,row['object_world_xyz'],row['observed_xy'])
            estimate['id']=ident;estimate['state']='MEASURED_TRAIN_ONLY'
            good.append(estimate['estimated_n_transmitted'])
        except (RefractionGeometryError,ValueError) as exc:
            estimate={'id':ident,'state':'INDETERMINATE','reason':str(exc)}
        per_point.append(estimate)
    if len(good)<min_train:
        return {'module':'P3-R02-INDEX','state':'INDETERMINATE',
                'reason':'insufficient observable oblique training rays',
                'train_count':len(train),'train_measurable_count':len(good),
                'holdout_count':len(holdout),'train_diagnostics':per_point,
                'estimated_n_layer':None,'holdout_validation':None,
                'ai_origin_decision':'NOT_ESTIMATED'}
    values=np.log(np.asarray(good))
    center=float(np.median(values));mad=float(np.median(np.abs(values-center)))
    # Fixed 3.5% floor for measurement noise; reject grossly erroneous training indices.
    band=max(.035,3.*1.4826*mad)
    accepted=values[np.abs(values-center)<=band]
    if len(accepted)<min_train:
        return {'module':'P3-R02-INDEX','state':'INDETERMINATE',
                'reason':'insufficient internally consistent training indices',
                'train_count':len(train),'train_measurable_count':len(good),
                'holdout_count':len(holdout),'train_diagnostics':per_point,
                'estimated_n_layer':None,'holdout_validation':None,
                'ai_origin_decision':'NOT_ESTIMATED'}
    n_hat=float(np.exp(np.median(accepted)))
    evaluated=copy.deepcopy(data)
    evaluated['interface']['n_layer']=n_hat
    evaluated['correspondences']=[byid[k] for k in holdout]
    validation=analyze_refraction_manifest(evaluated,tolerance_px=tolerance_px,min_pairs=min_holdout)
    return {'module':'P3-R02-INDEX','state':validation['state'],
            'reason':'estimated from disjoint training points; status comes exclusively from holdout points',
            'train_count':len(train),'train_measurable_count':len(good),
            'train_robust_inlier_count':len(accepted),
            'holdout_count':len(holdout),'estimated_n_layer':n_hat,
            'train_index_log_mad':mad,'train_diagnostics':per_point,
            'holdout_validation':validation,'ai_origin_decision':'NOT_ESTIMATED',
            'limitations':['camera, plane and metric point data are externally supplied and unverified',
                           'training points are never used to claim independent holdout fit',
                           'two-interface slab index is not identifiable by this procedure',
                           'holdout pixel thresholds are not calibrated on natural images']}


def run_index_manifest(input_path:Path,out:Path,tolerance_px=3.):
    payload=Path(input_path).read_bytes()
    data=json.loads(payload)
    report=estimate_index_manifest(data,tolerance_px=tolerance_px)
    report['input_manifest_sha256']=hashlib.sha256(payload).hexdigest()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'p3_r02_index_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report
