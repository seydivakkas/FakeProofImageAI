"""P2-S03: calibrated ray--plane reconstruction and physically constrained light fitting.

All heights and positions are in the same declared world units. A known planar
receiver, a calibrated camera and the above-plane height of each *matched*
object point are mandatory. A finite lamp is only identifiable with 3-D parallax;
nearly parallel rays are directional / very distant and DO NOT identify depth.
No AI-origin classification is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


class Shadow3DError(ValueError):
    """Malformed/physically insufficient 3D shadow evidence."""


@dataclass(frozen=True)
class Shadow3DConfig:
    min_pairs: int = 4
    ransac_trials: int = 500
    point_tolerance_world: float = .22
    direction_tolerance_deg: float = 1.4
    min_support_fraction: float = .65
    min_identifiability_ratio: float = .0015
    max_source_to_scene_extent: float = 12.0
    seed: int = 2026

    def __post_init__(self):
        if self.min_pairs < 3 or self.ransac_trials < 1:
            raise Shadow3DError('min_pairs >= 3 and ransac_trials > 0 required')
        if self.point_tolerance_world <= 0 or not (0 < self.direction_tolerance_deg <= 15):
            raise Shadow3DError('invalid point/direction thresholds')
        if not (0 < self.min_support_fraction <= 1):
            raise Shadow3DError('min_support_fraction must be in (0,1]')
        if not (0 < self.min_identifiability_ratio < 1):
            raise Shadow3DError('invalid identifiability threshold')
        if self.max_source_to_scene_extent <= 1:
            raise Shadow3DError('invalid maximum source-to-scene extent')


def _vector(value: Any, n: int, name: str) -> np.ndarray:
    a = np.asarray(value, dtype=float)
    if a.shape != (n,) or not np.isfinite(a).all():
        raise Shadow3DError(f'{name} must contain {n} finite values')
    return a


def _camera_plane(data: dict):
    try:
        cam = data['camera']
        plane = data['ground_plane']
        shape = _vector(data['image_shape_hw'], 2, 'image_shape_hw')
        K = np.asarray(cam['K'], dtype=float)
        R = np.asarray(cam['R_world_to_camera'], dtype=float)
        t = _vector(cam['t_world_to_camera'], 3, 'camera.t_world_to_camera')
        n = _vector(plane['normal_world'], 3, 'ground_plane.normal_world')
        offset = float(plane['offset_world'])
    except (KeyError, ValueError, TypeError) as exc:
        raise Shadow3DError(f'invalid camera/plane manifest: {exc}') from exc
    if (K.shape != (3,3) or R.shape != (3,3) or not np.isfinite(K).all()
        or not np.isfinite(R).all()):
        raise Shadow3DError('K and R must be finite 3x3 matrices')
    if (np.any(shape <= 0) or np.any(shape != np.floor(shape)) or
        not np.isfinite(offset)):
        raise Shadow3DError('invalid image dimensions or plane offset')
    if (abs(np.linalg.det(K)) < 1e-10 or K[0,0] <= 0 or K[1,1] <= 0 or
        not np.allclose(K[2], [0,0,1], atol=1e-8)):
        raise Shadow3DError('K must be an invertible pinhole calibration matrix')
    if not np.allclose(R @ R.T, np.eye(3), atol=1e-5) or abs(np.linalg.det(R)-1) > 1e-5:
        raise Shadow3DError('R must be a proper rotation')
    norm = float(np.linalg.norm(n))
    if norm < 1e-10:
        raise Shadow3DError('ground plane normal is zero')
    n /= norm
    offset /= norm
    C = -R.T @ t
    return (int(shape[0]),int(shape[1])), K, R, C, n, offset


def _backproject_on_plane(xy: np.ndarray, level: float, K: np.ndarray,
                          R: np.ndarray, C: np.ndarray, n: np.ndarray,
                          offset: float) -> np.ndarray:
    ray = R.T @ np.linalg.solve(K, np.array([xy[0],xy[1],1.]))
    denominator = float(n @ ray)
    if abs(denominator) < 1e-11:
        raise Shadow3DError('view ray is parallel to required height plane')
    alpha = (level - offset - n @ C) / denominator
    if alpha <= 0 or not np.isfinite(alpha):
        raise Shadow3DError('ray-plane intersection is behind camera')
    return C + alpha * ray


def reconstruct_shadow_rays(data: dict):
    """Reconstruct Q (plane shadow) and P (elevated object) in world coordinates."""
    shape,K,R,C,n,offset = _camera_plane(data)
    if not isinstance(data.get('correspondences'), list) or not data['correspondences']:
        raise Shadow3DError('correspondences array is required')
    rows=[]; ids=set()
    for index, item in enumerate(data['correspondences']):
        if not isinstance(item, dict):
            raise Shadow3DError(f'correspondences[{index}] must be an object')
        ident = str(item.get('id',f'pair_{index:03d}'))
        if ident in ids: raise Shadow3DError('correspondence ids must be unique')
        ids.add(ident)
        try:
            obj=_vector(item['object_xy'],2,'object_xy')
            sha=_vector(item['shadow_xy'],2,'shadow_xy')
            h=float(item['height_above_plane'])
            confidence=float(item.get('confidence',1.))
        except (KeyError,TypeError,ValueError) as exc:
            raise Shadow3DError(f'invalid correspondence {ident}: {exc}') from exc
        if (min(obj[0],sha[0]) < 0 or max(obj[0],sha[0]) >= shape[1] or
            min(obj[1],sha[1]) < 0 or max(obj[1],sha[1]) >= shape[0]):
            raise Shadow3DError(f'{ident}: points must be inside image bounds')
        if not np.isfinite(h) or h <= 0 or not np.isfinite(confidence) or not 0 < confidence <= 1:
            raise Shadow3DError(f'{ident}: height > 0 and confidence in (0,1] required')
        P=_backproject_on_plane(obj,h,K,R,C,n,offset)
        # Wrong shadow annotations can point above the horizon: never treat such
        # pixels as valid receivers, but continue evaluating other correspondences.
        try:
            Q=_backproject_on_plane(sha,0,K,R,C,n,offset)
        except Shadow3DError as exc:
            if 'behind camera' in str(exc) or 'parallel to required height plane' in str(exc):
                continue
            raise
        d=P-Q
        length=float(np.linalg.norm(d))
        if length < 1e-8:
            raise Shadow3DError(f'{ident}: degenerate 3D object-shadow ray')
        rows.append({'id':ident,'P':P,'Q':Q,'u':d/length,'length':length,
                     'height':h,'confidence':confidence,
                     'family_id':str(item.get('family_id','unlabeled'))})
    return rows,shape


def _source_fit(rows, members):
    """Weighted shortest distances to 3D lines: sum w(I-uuT)(S-Q)=0."""
    A=np.zeros((3,3)); b=np.zeros(3)
    for j in members:
        r=rows[int(j)]
        proj=np.eye(3)-np.outer(r['u'],r['u'])
        A+=r['confidence']*proj
        b+=r['confidence']*proj@r['Q']
    eig=np.linalg.eigvalsh(A)
    ratio=float(eig[0]/max(eig[-1],1e-15))
    if ratio < 1e-9: return None,ratio
    try: source=np.linalg.solve(A,b)
    except np.linalg.LinAlgError:return None,ratio
    if not np.isfinite(source).all(): return None,ratio
    return source,ratio


def _point_residual(rows, S):
    Q=np.array([r['Q'] for r in rows]);u=np.array([r['u'] for r in rows]);length=np.array([r['length'] for r in rows])
    ahead=np.einsum('ij,ij->i',S-Q,u)
    dist=np.linalg.norm((S-Q)-ahead[:,None]*u,axis=1)
    return dist,ahead/length


def _direction_fit(rows,members):
    V=np.array([rows[int(i)]['u'] for i in members]);w=np.array([rows[int(i)]['confidence'] for i in members])
    v=np.sum(V*w[:,None],axis=0)
    norm=np.linalg.norm(v)
    return v/norm if norm>1e-10 else None


def _direction_residual(rows,v):
    U=np.asarray([r['u'] for r in rows])
    return np.rad2deg(np.arccos(np.clip(U@v,-1,1)))


def _fit_family(rows: list, config: Shadow3DConfig, rng: np.random.Generator) -> dict:
    ids=[r['id'] for r in rows]
    n=len(rows)
    base={'family_id':rows[0]['family_id'] if rows else 'none','pair_count':n,
          'state':'INDETERMINATE','model_class':'UNRESOLVED', 'inlier_ids':[],
          'excluded_ids':ids, 'source_xyz_world':None,'source_direction_world':None}
    if n < config.min_pairs:
        return {**base,'reason':'insufficient object-shadow pairs'}
    idx=np.arange(n)
    Q=np.array([r['Q'] for r in rows]);weights=np.array([r['confidence'] for r in rows])
    scene_extent=max(float(np.linalg.norm(np.ptp(Q,axis=0))),float(np.median([r['height'] for r in rows])),1e-6)
    # We must not call a very distant/poorly identified point source a precise 3D position.
    best=None
    samples=[idx]
    samples.extend(rng.choice(n,size=2,replace=False) for _ in range(config.ransac_trials))
    for pair in samples:
        source,cond=_source_fit(rows,pair)
        if source is None or cond < config.min_identifiability_ratio: continue
        if np.linalg.norm(source-np.median(Q,axis=0)) > config.max_source_to_scene_extent*scene_extent: continue
        dist,ahead=_point_residual(rows,source)
        mask=(dist<=config.point_tolerance_world)&(ahead>1.01)
        if mask.sum()<config.min_pairs:continue
        quality=(float(weights[mask].sum()),int(mask.sum()),-float(np.median(dist[mask])))
        if best is None or quality>best[0]:best=(quality,mask)
    point_result=None
    if best is not None:
        mask=best[1]
        for _ in range(4):
            source,cond=_source_fit(rows,np.flatnonzero(mask))
            if source is None or cond < config.min_identifiability_ratio:break
            dist,ahead=_point_residual(rows,source)
            fresh=(dist<=config.point_tolerance_world)&(ahead>1.01)
            if int(fresh.sum())<config.min_pairs: break
            mask=fresh
        else:
            source,cond=_source_fit(rows,np.flatnonzero(mask))
            if source is not None:
                dist,ahead=_point_residual(rows,source)
                mask=(dist<=config.point_tolerance_world)&(ahead>1.01)
                support=float(weights[mask].sum()/weights.sum())
                if (mask.sum()>=config.min_pairs and support>=config.min_support_fraction and
                    cond>=config.min_identifiability_ratio and
                    np.linalg.norm(source-np.median(Q,axis=0))<=config.max_source_to_scene_extent*scene_extent):
                    point_result=(source,cond,dist,mask,support)
    # Alternative parallel-ray hypothesis; angular residual identifies sufficiently aligned vectors.
    direction=None;direction_result=None
    for _ in range(3):
        if direction is None:
            direction=_direction_fit(rows,idx)
        if direction is None: break
        angle=_direction_residual(rows,direction)
        mask=angle<=config.direction_tolerance_deg
        if mask.sum()<config.min_pairs: break
        direction=_direction_fit(rows,np.flatnonzero(mask))
    if direction is not None:
        angle=_direction_residual(rows,direction)
        mask=angle<=config.direction_tolerance_deg
        support=float(weights[mask].sum()/weights.sum())
        if mask.sum()>=config.min_pairs and support>=config.min_support_fraction:
            direction_result=(direction,angle,mask,support)
    if point_result and direction_result:
        # Both explanations fit within measuring precision: refuse spurious light depth.
        return {**base,'reason':'finite-source and directional hypotheses both fit; depth is not uniquely supported',
                'alternative_models':['FINITE_POINT','DIRECTIONAL_OR_DISTANT'],
                'point_support_fraction':point_result[-1], 'direction_support_fraction':direction_result[-1]}
    if point_result:
        source,cond,dist,mask,support=point_result
        return {**base,'state':'MEASURED','model_class':'FINITE_POINT_LIGHT', 'reason':None,
                'source_xyz_world':source.tolist(), 'inlier_ids':[ids[i] for i in idx[mask]],
                'excluded_ids':[ids[i] for i in idx[~mask]], 'support_fraction':support,
                'rank_eigen_ratio':cond,'median_line_distance_world':float(np.median(dist[mask])),
                'p90_line_distance_world':float(np.percentile(dist[mask],90)),
                'scene_extent_world':scene_extent}
    if direction_result:
        vec,angle,mask,support=direction_result
        return {**base,'state':'MEASURED','model_class':'DIRECTIONAL_OR_DISTANT_LIGHT',
                'reason':'parallel-ray model fits; finite distance remains unidentifiable',
                'source_direction_world':vec.tolist(),
                'inlier_ids':[ids[i] for i in idx[mask]],
                'excluded_ids':[ids[i] for i in idx[~mask]],'support_fraction':support,
                'median_angular_error_deg':float(np.median(angle[mask])),
                'p90_angular_error_deg':float(np.percentile(angle[mask],90))}
    return {**base,'reason':'neither identifiable finite-source nor common-direction model supported'}


def analyze_shadow_3d(data: dict, config: Shadow3DConfig|None=None) -> dict:
    config=config or Shadow3DConfig()
    rows,shape=reconstruct_shadow_rays(data)
    accepted_ids={x['id'] for x in rows}
    rejected_before_fit=[str(item.get('id',f'pair_{i:03d}')) for i,item in enumerate(data['correspondences'])
                         if str(item.get('id',f'pair_{i:03d}')) not in accepted_ids]
    unique=sorted(set(x['family_id'] for x in rows))
    rng=np.random.default_rng(config.seed)
    groups=[_fit_family([x for x in rows if x['family_id']==name],config,rng) for name in unique]
    coverage_fraction=len(rows)/len(data['correspondences'])
    overall=('MEASURED' if groups and all(x['state']=='MEASURED' for x in groups)
             and coverage_fraction >= config.min_support_fraction else 'INDETERMINATE')
    return {'module':'P2_S03_3D_LIGHT_GEOMETRY','state':overall,
            'image_shape_hw':list(shape),'world_units':str(data.get('world_units','m')),
            'camera_convention':'x_camera = R_world_to_camera @ X_world + t_world_to_camera',
            'plane_convention':'unit_n.dot(X_world) + normalized_offset_world = 0; object height is +along unit_n',
            'model_groups':groups,'group_count':len(groups),
            'invalid_ray_plane_intersection_ids':rejected_before_fit,
            'valid_3d_reconstruction_fraction':coverage_fraction,
            'assumptions':['calibrated pinhole camera including extrinsics',
                           'known metric receiver plane and point heights along plane normal',
                           'same physical cast-shadow point correspondence per measurement',
                           'light rays are straight in a homogeneous medium',
                           'family_id values are externally declared, not learned source identities'],
            'limits':['camera or height/plane errors can generate 3D false residuals',
                      'parallel rays cannot identify finite 3D source distance',
                      'no automatic shadow segmentation or correspondence recovery',
                      'geometric light compatibility is not evidence of AI origin'],
            'decision':'NO_AI_ORIGIN_CONCLUSION','real_validation':'DEFERRED'}



def attach_s02_families(data: dict, s02_report: dict) -> tuple[dict,dict]:
    """Optional S02 -> S03 bridge; memberships are hypotheses, not source proof."""
    if (s02_report.get('module')!='P2_S02_MULTIPLE_PROJECTED_SHADOW_CONVERGENCES'
        or s02_report.get('state')!='MEASURED'):
        raise Shadow3DError('S02 report must contain MEASURED projected families')
    if s02_report.get('image_shape_hw')!=data.get('image_shape_hw'):
        raise Shadow3DError('S02/S03 image shape mismatch')
    mapping=s02_report.get('assignment_by_id')
    valid={m['model_id'] for m in s02_report.get('models',[])}
    if not isinstance(mapping,dict) or not valid:
        raise Shadow3DError('S02 report has no valid family assignments')
    result=deepcopy(data); kept=[]; rejected=[]
    for j,item in enumerate(result['correspondences']):
        ident=str(item.get('id',f'pair_{j:03d}'))
        if mapping.get(ident) in valid:
            item['family_id']=mapping[ident]
            kept.append(item)
        else:
            rejected.append(ident)
    result['correspondences']=kept
    if not kept:
        raise Shadow3DError('S02 did not assign any accepted object-shadow pairs')
    return result,{'bridge':'S02_PROJECTED_FAMILY_HYPOTHESES',
                   'pre_fit_excluded_ids':rejected,
                   'pre_fit_excluded_count':len(rejected),
                   'warning':'S02 groups are image-ray hypotheses, not certified distinct 3D lights'}


def run_shadow3d_manifest(manifest: Path, out: Path, image_path: Path|None=None,
                          config: Shadow3DConfig|None=None,
                          s02_report_path: Path|None=None) -> dict:
    data=json.loads(manifest.read_text(encoding='utf-8'))
    bridge=None
    if s02_report_path is not None:
        report_source=json.loads(s02_report_path.read_text(encoding='utf-8'))
        data,bridge=attach_s02_families(data,report_source)
    report=analyze_shadow_3d(data,config)
    if bridge is not None:
        report['s02_bridge']=bridge
        report['s02_report_sha256']=hashlib.sha256(s02_report_path.read_bytes()).hexdigest()
    out.mkdir(parents=True,exist_ok=True)
    report['input_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
    if image_path is not None:
        frame=cv2.imread(str(image_path),cv2.IMREAD_COLOR)
        if frame is None or list(frame.shape[:2])!=data['image_shape_hw']:
            raise Shadow3DError('overlay image unreadable or dimensions mismatch')
        report['image_sha256']=hashlib.sha256(image_path.read_bytes()).hexdigest()
        colors=[(80,205,80),(225,175,55),(185,70,210)]
        for gidx, group in enumerate(report['model_groups']):
            members=set(group['inlier_ids'])
            for j,item in enumerate(data['correspondences']):
                if str(item.get('family_id','unlabeled'))!=group['family_id']:continue
                item_id=str(item.get('id',f'pair_{j:03d}'))
                color=colors[gidx%len(colors)] if item_id in members else (70,70,220)
                a=tuple(np.rint(item['object_xy']).astype(int)); b=tuple(np.rint(item['shadow_xy']).astype(int))
                cv2.line(frame,a,b,color,2,cv2.LINE_AA)
                cv2.circle(frame,a,4,(235,235,235),-1);cv2.circle(frame,b,3,color,-1)
        cv2.imwrite(str(out/'p2_s03_overlay.png'),frame)
        report['overlay']='p2_s03_overlay.png'
    (out/'p2_s03_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return report
