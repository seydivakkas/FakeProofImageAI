"""P2-S01: projected light-convergence constraints from object/cast-shadow correspondences.

No 3D light location, AI-origin probability, or physical inconsistency verdict is inferred.
The 2D collinearity constraint holds for a point source AND for parallel 3D rays
under rectilinear perspective. Observations must be genuine point-to-shadow
correspondences belonging to a single direct illumination hypothesis.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


class ShadowEvidenceError(ValueError):
    """Invalid or degenerate P2-S01 measurements."""


@dataclass(frozen=True)
class ShadowConfig:
    angle_threshold_deg: float = 2.5
    ransac_trials: int = 900
    min_pairs: int = 3
    min_support_fraction: float = 0.60
    min_pair_separation_px: float = 5.0
    bootstrap_trials: int = 250
    seed: int = 2026

    def __post_init__(self):
        if not (0 < self.angle_threshold_deg <= 20):
            raise ShadowEvidenceError('angle_threshold_deg must be in (0,20]')
        if self.ransac_trials < 1 or self.bootstrap_trials < 0 or self.min_pairs < 3:
            raise ShadowEvidenceError('invalid trial count or min_pairs < 3')
        if not (0 < self.min_support_fraction <= 1):
            raise ShadowEvidenceError('min_support_fraction must be in (0,1]')
        if self.min_pair_separation_px <= 0:
            raise ShadowEvidenceError('min_pair_separation_px must be positive')


def _cross2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a[..., 0]*b[..., 1]-a[..., 1]*b[..., 0]


def _parse_pairs(data: dict, config: ShadowConfig):
    shape = np.asarray(data.get('image_shape_hw'), dtype=float)
    if shape.shape != (2,) or not np.isfinite(shape).all() or (shape <= 0).any():
        raise ShadowEvidenceError('image_shape_hw must contain positive [height,width]')
    hw = (int(shape[0]), int(shape[1]))
    if any(int(n) != n for n in shape):
        raise ShadowEvidenceError('image_shape_hw must be integers')
    raw = data.get('correspondences')
    if not isinstance(raw, list) or len(raw) < config.min_pairs:
        raise ShadowEvidenceError(f'at least {config.min_pairs} correspondences required')
    p, q, confidence, labels = [], [], [], []
    for i, pair in enumerate(raw):
        if not isinstance(pair, dict):
            raise ShadowEvidenceError(f'correspondences[{i}] must be an object')
        try:
            a = np.asarray(pair['object_xy'], dtype=float)
            b = np.asarray(pair['shadow_xy'], dtype=float)
            c = float(pair.get('confidence', 1.0))
        except (ValueError, KeyError, TypeError) as exc:
            raise ShadowEvidenceError(f'invalid correspondence #{i}: {exc}') from exc
        if a.shape != (2,) or b.shape != (2,) or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ShadowEvidenceError(f'correspondence #{i} coordinates must be finite [x,y]')
        if not (0 <= a[0] < hw[1] and 0 <= b[0] < hw[1] and 0 <= a[1] < hw[0] and 0 <= b[1] < hw[0]):
            raise ShadowEvidenceError(f'correspondence #{i} is outside the image')
        if np.linalg.norm(a-b) < config.min_pair_separation_px:
            raise ShadowEvidenceError(f'correspondence #{i} is too short for stable direction')
        if not np.isfinite(c) or not (0 < c <= 1):
            raise ShadowEvidenceError(f'correspondence #{i} confidence must be in (0,1]')
        p.append(a);q.append(b);confidence.append(c)
        labels.append(str(pair.get('id', f'pair_{i:02d}')))
    if len(labels) != len(set(labels)):
        raise ShadowEvidenceError('correspondence id values must be unique')
    return hw, np.asarray(p), np.asarray(q), np.asarray(confidence), labels


def _normalised_lines(p: np.ndarray, q: np.ndarray, hw: tuple[int,int]):
    h,w = hw
    center = np.array([w/2, h/2], dtype=float)
    scale = float(max(h,w))
    a = (p-center)/scale
    b = (q-center)/scale
    dirs = b-a
    lengths = np.linalg.norm(dirs,axis=1)
    unit = dirs/lengths[:,None]
    normal = np.column_stack([-unit[:,1],unit[:,0]])
    mid = 0.5*(a+b)
    lines = np.column_stack([normal,-np.sum(normal*mid, axis=1)])
    return lines, unit, mid, center, scale


def _canonical_homogeneous(v: np.ndarray) -> np.ndarray | None:
    norm = float(np.linalg.norm(v))
    if norm < 1e-12 or not np.isfinite(norm):
        return None
    v = v/norm
    if abs(v[2]) > 1e-12 and v[2] < 0: v = -v
    return v


def _angular_residuals_deg(v: np.ndarray, directions: np.ndarray, mids: np.ndarray) -> np.ndarray:
    v = _canonical_homogeneous(v)
    if v is None:
        return np.full(len(directions),90.)
    # Coordinates are normalised by image maximum dimension.
    # A large finite VP is explicitly treated as effectively at infinity.
    if abs(v[2]) > 1e-8 and np.linalg.norm(v[:2]/v[2]) < 50:
        vec = v[:2]/v[2] - mids
        norms = np.linalg.norm(vec,axis=1)
        valid = norms > 1e-10
        expected = np.divide(vec,norms[:,None],out=np.zeros_like(vec),where=valid[:,None])
        cosine_error = np.clip(np.abs(_cross2(expected,directions)),0,1)
        result = np.rad2deg(np.arcsin(cosine_error))
        result[~valid] = 90.
        return result
    vec = v[:2]
    vec /= max(float(np.linalg.norm(vec)),1e-12)
    return np.rad2deg(np.arcsin(np.clip(np.abs(_cross2(directions,vec)),0,1)))


def _fit_nullspace(lines: np.ndarray, weights: np.ndarray) -> np.ndarray | None:
    if len(lines) < 2:
        return None
    try:
        _,_,vt=np.linalg.svd(lines*np.sqrt(weights[:,None]),full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    return _canonical_homogeneous(vt[-1])


def _convergence_label(v: np.ndarray, center: np.ndarray, scale: float):
    if abs(v[2]) <= 1e-8:
        direction = v[:2]/np.linalg.norm(v[:2])
        return 'EFFECTIVELY_AT_INFINITY',None,direction.tolist()
    pt = v[:2]/v[2]
    if np.linalg.norm(pt) > 50:
        d=pt/np.linalg.norm(pt)
        return 'EFFECTIVELY_AT_INFINITY',None,d.tolist()
    coord=pt*scale + center
    return 'FINITE_PROJECTED_POINT',coord.tolist(),None


def fit_projected_light(data: dict, config: ShadowConfig | None = None) -> dict:
    """Estimate an apparent common projected ray intersection using robust consensus.

    RANSAC samples line pairs; an SVD nullspace refines the homogeneous
    intersection over inliers. Residual is *unoriented angular mismatch*,
    measured in degrees, allowing finite AND far-field convergence.
    """
    config = config or ShadowConfig()
    hw,p,q,weights,labels = _parse_pairs(data,config)
    lines,dirs,mid,center,scale = _normalised_lines(p,q,hw)
    rng=np.random.default_rng(config.seed)
    N=len(lines)
    candidates=[]
    # Include a global fit, useful for near-parallel directions.
    all_candidate=_fit_nullspace(lines,weights)
    if all_candidate is not None:
        candidates.append(all_candidate)
    for _ in range(config.ransac_trials):
        ix=rng.choice(N,2,replace=False)
        v=_canonical_homogeneous(np.cross(lines[ix[0]],lines[ix[1]]))
        if v is not None:
            candidates.append(v)
    best=None
    best_key=None
    for v in candidates:
        residual=_angular_residuals_deg(v,dirs,mid)
        ok=residual<=config.angle_threshold_deg
        n=int(ok.sum())
        if n<config.min_pairs: continue
        score=(float(weights[ok].sum()),n,-float(np.median(residual[ok])))
        if best_key is None or score>best_key:
            best=v;best_key=score
    if best is None:
        return {
            'module':'P2_S01_PROJECTED_SHADOW_LIGHT_CONVERGENCE',
            'state':'INDETERMINATE','reason':'No supported common convergence among input correspondences',
            'correspondence_count':N,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'assumptions':['object-to-cast-shadow correspondences are correct',
                           'rectilinear central perspective projection',
                           'one dominant direct illumination hypothesis'],
        }
    current=best
    # Refine consensus twice, then evaluate all observations against the final model.
    for _ in range(2):
        residual=_angular_residuals_deg(current,dirs,mid)
        ok=residual<=config.angle_threshold_deg
        if int(ok.sum())<config.min_pairs:break
        refined=_fit_nullspace(lines[ok],weights[ok])
        if refined is not None:
            current=refined
    residual=_angular_residuals_deg(current,dirs,mid)
    inliers=residual<=config.angle_threshold_deg
    count=int(inliers.sum())
    support=float(np.sum(weights[inliers])/np.sum(weights))
    label,point,direction=_convergence_label(current,center,scale)
    # Identical/coincident projected lines have infinitely many common points:
    # two independent line constraints are required to identify a convergence.
    _, singular, _ = np.linalg.svd(lines[inliers] * np.sqrt(weights[inliers,None]),
                                   full_matrices=False) if count >= 2 else (None,np.zeros(3),None)
    identifiable=bool(len(singular)>1 and singular[1]>1e-7*singular[0])
    stable=count>=config.min_pairs and support>=config.min_support_fraction and identifiable
    sigma=None
    # Exploratory resampling dispersion, NOT confidence interval / calibrated accuracy.
    if stable and label=='FINITE_PROJECTED_POINT' and config.bootstrap_trials:
        points=[]
        ids=np.flatnonzero(inliers)
        for _ in range(config.bootstrap_trials):
            sub=rng.choice(ids,len(ids),replace=True)
            v=_fit_nullspace(lines[sub],weights[sub])
            if v is None:continue
            kind,xy,_=_convergence_label(v,center,scale)
            if kind=='FINITE_PROJECTED_POINT' and np.linalg.norm(np.asarray(xy)-point)<max(hw)*10:
                points.append(xy)
        if len(points)>=3:
            sigma=np.std(np.asarray(points),axis=0,ddof=1).tolist()
    reason=(None if stable else ('Coincident/degenerate projected rays do not determine a unique convergence'
         if not identifiable else 'Insufficient consensus for a dominant common projected convergence; do not infer physics violation'))
    return {
        'module':'P2_S01_PROJECTED_SHADOW_LIGHT_CONVERGENCE',
        'state':'MEASURED' if stable else 'INDETERMINATE',
        'reason':reason,
        'model':'homogeneous projected-ray concurrence (finite or effectively at infinity)',
        'image_shape_hw':list(hw),
        'correspondence_count':N,'inlier_count':count,'outlier_count':int(N-count),
        'inlier_ids':[a for a,ok in zip(labels,inliers) if ok],
        'outlier_ids':[a for a,ok in zip(labels,inliers) if not ok],
        'inlier_weight_fraction':support,
        'convergence_identifiable':identifiable,
        'model_class':label,'projected_convergence_xy_px':point,
        'image_direction_at_infinity_xy':direction,
        'bootstrap_dispersion_xy_px_exploratory':sigma,
        'angular_threshold_deg':config.angle_threshold_deg,
        'angular_residual_deg_per_pair':{key:float(value) for key,value in zip(labels,residual)},
        'angular_residual_median_deg_inliers':float(np.median(residual[inliers])) if count else None,
        'angular_residual_p90_deg_inliers':float(np.percentile(residual[inliers],90)) if count else None,
        'assumptions':['each input pair is a verified 2D correspondence of a physical object point and its cast-shadow point',
                       'both points and apparent light lie on a projected straight ray',
                       'one dominant illumination/ray-concurrence hypothesis',
                       'no nonlinear lens or panorama warping without prior correction'],
        'limitations':['2D convergence is NOT a 3D light location, height, or source distance',
                       '2D convergence alone cannot determine point light vs distant parallel light',
                       'a secondary source, bad correspondence, weak geometry, and reflections can create outliers',
                       'the inlier threshold is exploratory and not calibrated to real-image false alarms',
                       'independently verified correspondences and real-scene calibration are not yet available',
                       'no automatic shadow detection, semantic shadow matching, or AI-origin conclusion'],
        'decision':'NO_AI_ORIGIN_CONCLUSION',
    }


def draw_shadow_overlay(image: np.ndarray, data: dict, report: dict) -> np.ndarray:
    """Draw only supplied correspondence observations and fitted convergence."""
    canvas=image.copy()
    inlier=set(report.get('inlier_ids',[]))
    for i,entry in enumerate(data['correspondences']):
        start=tuple(np.rint(entry['object_xy']).astype(int)) if isinstance(entry['object_xy'],np.ndarray) else tuple(int(round(c)) for c in entry['object_xy'])
        end=tuple(int(round(c)) for c in entry['shadow_xy'])
        name=str(entry.get('id',f'pair_{i:02d}'))
        color=(60,195,90) if name in inlier else (45,65,230)
        cv2.line(canvas,start,end,color,2,cv2.LINE_AA)
        cv2.circle(canvas,start,4,(255,230,100),-1,cv2.LINE_AA)
        cv2.circle(canvas,end,4,color,-1,cv2.LINE_AA)
    pt=report.get('projected_convergence_xy_px')
    if pt is not None:
        x,y=map(lambda t:int(round(t)),pt)
        # Avoid giant outside-canvas drawing operations.
        if -5000<x<canvas.shape[1]+5000 and -5000<y<canvas.shape[0]+5000:
            cv2.drawMarker(canvas,(x,y),(60,230,255),cv2.MARKER_CROSS,32,2,cv2.LINE_AA)
    if pt is not None and (not 0 <= pt[0] < canvas.shape[1] or not 0 <= pt[1] < canvas.shape[0]):
        sx=int(np.clip(round(pt[0]),18,canvas.shape[1]-18))
        sy=int(np.clip(round(pt[1]),44,canvas.shape[0]-18))
        cv2.drawMarker(canvas,(sx,sy),(50,210,255),cv2.MARKER_DIAMOND,16,2,cv2.LINE_AA)
        cv2.putText(canvas,f'Light VP outside: ({pt[0]:.0f}, {pt[1]:.0f})',
                    (12,64),cv2.FONT_HERSHEY_SIMPLEX,.62,(80,240,245),2,cv2.LINE_AA)
    caption='P2-S01 PROJECTED LIGHT CONVERGENCE - NOT AN AI VERDICT'
    cv2.rectangle(canvas,(0,0),(min(image.shape[1],1100),32),(22,33,42),-1)
    cv2.putText(canvas,caption,(12,22),cv2.FONT_HERSHEY_SIMPLEX,.56,(230,230,230),1,cv2.LINE_AA)
    return canvas


def run_shadow_manifest(path: Path, out: Path, image_path: Path | None = None,
                        config: ShadowConfig | None = None) -> dict:
    data=json.loads(path.read_text(encoding='utf-8'))
    report=fit_projected_light(data,config)
    out.mkdir(parents=True,exist_ok=True)
    report['input_file']=str(path)
    if image_path is not None:
        raw=image_path.read_bytes()
        image=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
        if image is None:
            raise ShadowEvidenceError('image could not be decoded')
        if tuple(image.shape[:2])!=tuple(report.get('image_shape_hw',data['image_shape_hw'])):
            raise ShadowEvidenceError('image dimensions and manifest image_shape_hw disagree')
        report['image_sha256']=hashlib.sha256(raw).hexdigest()
        overlay=draw_shadow_overlay(image,data,report)
        overlay_filename='p2_s01_shadow_overlay.png'
        if not cv2.imwrite(str(out/overlay_filename),overlay):
            raise ShadowEvidenceError('could not write shadow overlay')
        report['overlay_file']=overlay_filename
    (out/'p2_s01_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
