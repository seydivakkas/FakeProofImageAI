"""P2-S05: 1-D extended-source edge profiles, never an AI-origin classifier.

Uniform-disk source edge-spread model, with irradiance-linear annotated scans.
Angular inversion is conditional on nearly normal incident *parallel* rays,
locally straight opaque blocker, planar diffuse receiver, known occluder height
and receiver metric pixel scale, with negligible or resolved camera PSF.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares


class PenumbraError(ValueError):
    """Invalid profile, unsupported physical contract, or numeric fit."""


@dataclass(frozen=True)
class PenumbraConfig:
    min_samples: int = 35
    min_contrast: float = 0.15
    min_width_px: float = 1.5
    min_fit_r2: float = 0.92
    min_edges_for_consistency: int = 3
    max_relative_angular_spread: float = 0.12
    bootstrap_samples: int = 0
    seed: int = 2026

    def __post_init__(self):
        if (self.min_samples < 16 or not 0 < self.min_contrast <= 1 or
            self.min_width_px <= 0 or not 0 < self.min_fit_r2 <= 1 or
            self.min_edges_for_consistency < 2 or
            self.max_relative_angular_spread <= 0 or not 0 <= self.bootstrap_samples <= 250):
            raise PenumbraError('invalid P2-S05 configuration')


def source_visibility(t: np.ndarray, shape: str = 'UNIFORM_DISK') -> np.ndarray:
    """Visible fraction of a uniform disk or strip translated over a sharp half-plane."""
    a = np.asarray(t, dtype=float)
    z = np.clip(a, -1.0, 1.0)
    if shape == 'UNIFORM_DISK':
        return np.where(a <= -1, 0., np.where(a >= 1, 1.,
            .5 + (np.arcsin(z) + z * np.sqrt(np.maximum(0., 1.-z*z))) / np.pi))
    if shape == 'UNIFORM_STRIP':
        return np.clip((a + 1.) / 2., 0., 1.)
    raise PenumbraError('source_shape must be UNIFORM_DISK or UNIFORM_STRIP')


def edge_irradiance(x, center_px: float, halfwidth_px: float,
                    shadow_level: float, lit_level: float,
                    light_side: str = 'right', source_shape: str = 'UNIFORM_DISK'):
    if not (np.isfinite(halfwidth_px) and halfwidth_px > 0):
        raise PenumbraError('halfwidth must be positive')
    if light_side not in ('right', 'left'):
        raise PenumbraError('light_side must be right or left')
    u = (np.asarray(x, dtype=float) - float(center_px)) / halfwidth_px
    if light_side == 'left':
        u = -u
    return shadow_level + (lit_level - shadow_level) * source_visibility(u, source_shape)


def angular_diameter_from_width(width_px: float, pixels_per_meter: float,
                                 blocker_height_m: float) -> float:
    """Conditional distant near-normal incidence: diameter=2 atan((W/2)/(h*px_per_m))."""
    if not all(np.isfinite(k) and k > 0 for k in (width_px, pixels_per_meter, blocker_height_m)):
        raise PenumbraError('width, image scale and blocker height must be positive')
    return float(np.rad2deg(2 * np.arctan(width_px / (2*pixels_per_meter*blocker_height_m))))


def penumbra_width_from_angle(angle_deg: float, pixels_per_meter: float,
                              blocker_height_m: float) -> float:
    if not 0 < angle_deg < 170:
        raise PenumbraError('angular diameter outside valid range')
    if not all(np.isfinite(k) and k > 0 for k in (pixels_per_meter, blocker_height_m)):
        raise PenumbraError('invalid scale or height')
    return float(2 * pixels_per_meter * blocker_height_m * np.tan(np.deg2rad(angle_deg/2)))


def _numbers(raw, name: str) -> np.ndarray:
    try:
        a = np.asarray(raw, dtype=float)
    except (ValueError, TypeError) as exc:
        raise PenumbraError(f'invalid numeric field: {name}') from exc
    if a.ndim != 1 or not np.all(np.isfinite(a)):
        raise PenumbraError(f'{name} must be a finite 1D numeric array')
    return a


def fit_edge_profile(item: dict, config: PenumbraConfig | None = None) -> dict:
    config = config or PenumbraConfig()
    uid = str(item.get('id', '')).strip()
    if not uid or len(uid) > 128:
        raise PenumbraError('each edge requires a short id')
    x = _numbers(item.get('x_px'), 'x_px')
    y = _numbers(item.get('linear_irradiance'), 'linear_irradiance')
    if len(x) != len(y) or len(x) < config.min_samples:
        raise PenumbraError('edge samples missing or too few')
    if not np.all(np.diff(x) > 0):
        raise PenumbraError('x_px must be strictly increasing; duplicate locations invalid')
    if np.any((y < 0) | (y > 1)):
        raise PenumbraError('linear_irradiance must be finite in [0,1]')
    if item.get('radiometric_space') != 'LINEAR_RELATIVE_IRRADIANCE':
        raise PenumbraError('radiometric_space must explicitly be LINEAR_RELATIVE_IRRADIANCE')
    if item.get('source_shape') not in ('UNIFORM_DISK', 'UNIFORM_STRIP'):
        raise PenumbraError('explicit source_shape required')
    shape = item['source_shape']
    side = item.get('light_side')
    if side not in ('left', 'right'):
        raise PenumbraError('explicit light_side left/right required')
    lo, hi = float(np.percentile(y, 8)), float(np.percentile(y, 92))
    contrast = hi - lo
    if contrast < config.min_contrast:
        return {'id': uid, 'state': 'INDETERMINATE', 'reason': 'INSUFFICIENT_IRRADIANCE_CONTRAST',
                'angular_diameter_deg': None}
    yy = y if side == 'right' else y[::-1]
    xx = x if side == 'right' else -x[::-1]
    # Solve all profiles in the common increasing-brightness coordinate system.
    q = np.clip((yy - lo) / max(1e-9, contrast), 0., 1.)
    mid = float(np.interp(.5, np.maximum.accumulate(q), xx))
    x10 = float(np.interp(.10, np.maximum.accumulate(q), xx))
    x90 = float(np.interp(.90, np.maximum.accumulate(q), xx))
    # Disk 10-90 width is about 1.374 halfwidth; strip is 1.6 halfwidth.
    mult = 1.374 if shape == 'UNIFORM_DISK' else 1.6
    initial_half = max(config.min_width_px, (x90-x10)/mult)
    span = float(xx[-1]-xx[0]); max_radius = span*.475
    if max_radius <= config.min_width_px:
        return {'id':uid, 'state':'INDETERMINATE', 'reason':'INSUFFICIENT_SPATIAL_SAMPLING',
                'angular_diameter_deg':None}
    def residual(params):
        a,b,c,r = params
        return edge_irradiance(xx,c,r,a,b, 'right',shape)-yy
    initial = [np.clip(lo,0,.98), np.clip(hi,.02,1), np.clip(mid,xx[0],xx[-1]),
               np.clip(initial_half,config.min_width_px+1e-4,max_radius-1e-4)]
    try:
        res=least_squares(residual,initial,loss='soft_l1',f_scale=.025,
                          bounds=([0.,0.,xx[0],config.min_width_px],
                                  [1.,1.,xx[-1],max_radius]),max_nfev=350)
    except ValueError as exc:
        raise PenumbraError(f'fit failed: {exc}') from exc
    dark,bright,center_w,radius = map(float,res.x)
    center = center_w if side == 'right' else -center_w
    pred = edge_irradiance(x,center,radius,dark,bright,side,shape)
    rmse = float(np.sqrt(np.mean((pred-y)**2)))
    r2 = float(1-np.sum((pred-y)**2)/max(1e-12, np.sum((y-y.mean())**2)))
    left = (x < center-radius) if side=='right' else (x > center+radius)
    right = (x > center+radius) if side=='right' else (x < center-radius)
    plateau_count = int(min(np.count_nonzero(left), np.count_nonzero(right)))
    reason = None
    if not res.success or bright-dark < config.min_contrast:
        reason='NO_STABLE_PHYSICAL_FIT'
    elif r2 < config.min_fit_r2:
        reason='POOR_EDGE_SHAPE_FIT'
    elif plateau_count < 3:
        reason='MISSING_UMBRA_OR_LIT_PLATEAU'
    elif abs(radius-max_radius)<1e-3 or radius <= config.min_width_px * 1.025:
        reason='WIDTH_AT_SEARCH_BOUND'
    elif 2*radius < 4*float(np.median(np.diff(x))):
        reason='INSUFFICIENT_EFFECTIVE_RESOLUTION'
    fit_state='MEASURED' if reason is None else 'INDETERMINATE'
    out={'id':uid,'state':fit_state,'reason':reason,'source_shape':shape,
         'edge_orientation_lit_side':side,'sample_count':len(x),
         'center_px':center,'penumbra_halfwidth_px':radius,
         'penumbra_fullwidth_px':2*radius,'shadow_irradiance':dark,
         'lit_irradiance':bright,'contrast':bright-dark,'fit_rmse':rmse,
         'fit_r2':r2, 'umbra_plateau_sample_count':int(np.count_nonzero(left)),
         'lit_plateau_sample_count':int(np.count_nonzero(right)),
         'edge_sample_range_px':[float(x[0]),float(x[-1])],
         'angular_diameter_deg':None, 'angular_state':'NOT_IDENTIFIED',
         'profile_is_direct_light_visibility_approximation':True}
    if fit_state!='MEASURED':
        return out
    geom=item.get('metric_geometry')
    if not isinstance(geom,dict) or geom.get('model')!='NEAR_NORMAL_PARALLEL_RAYS' or geom.get('verified') is not True:
        out['angular_reason']='UNVERIFIED_GEOMETRY_OR_SCALE'
        return out
    try:
        ppm=float(geom['receiver_pixels_per_meter'])
        height=float(geom['occluder_receiver_separation_m'])
        psf=float(geom.get('optical_psf_sigma_px',0.))
    except (TypeError, ValueError, KeyError) as exc:
        raise PenumbraError('invalid verified metric geometry') from exc
    if not (np.isfinite(psf) and psf>=0):
        raise PenumbraError('PSF sigma must be finite and nonnegative')
    if psf>radius*.15:
        out['angular_reason']='OPTICAL_PSF_NOT_RESOLVED'
        return out
    out['angular_diameter_deg'] = angular_diameter_from_width(2*radius,ppm,height)
    out['angular_state']='MEASURED_CONDITIONAL'
    out['angular_assumptions']=['distant uniform extended source','near-normal parallel incident rays',
        'locally straight opaque occluding edge', 'receiver planar and locally diffuse',
        'linearized irradiance samples','geometric scale and blocker height independently known',
        'unmodelled blur and ambient gradients negligible']
    if config.bootstrap_samples:
        # Parametric Monte Carlo: provisional interval conditional on i.i.d. Gaussian noise.
        rng=np.random.default_rng(config.seed + sum(uid.encode('utf-8')))
        angles=[]
        for _ in range(config.bootstrap_samples):
            noise=rng.normal(0,max(.001,rmse),size=len(x))
            sim=dict(item,linear_irradiance=np.clip(pred+noise,0,1).tolist())
            fitted=fit_edge_profile(sim,PenumbraConfig(
                min_samples=config.min_samples,min_contrast=config.min_contrast,
                min_width_px=config.min_width_px,min_fit_r2=config.min_fit_r2,
                min_edges_for_consistency=config.min_edges_for_consistency,
                max_relative_angular_spread=config.max_relative_angular_spread,
                bootstrap_samples=0,seed=config.seed))
            if fitted.get('angular_diameter_deg') is not None:
                angles.append(fitted['angular_diameter_deg'])
        if len(angles)>=max(10,config.bootstrap_samples*.8):
            out['conditional_parametric_mc_90pct_interval_deg']=[float(z) for z in np.percentile(angles,[5,95])]
            out['uncertainty_warning']='Conditional simulation interval, NOT calibrated frequentist coverage'
        else:
            out['uncertainty_warning']='Parametric Monte Carlo insufficient stable fits'
    return out


def analyze_penumbra_manifest(data: dict, config: PenumbraConfig | None=None) -> dict:
    cfg = config or PenumbraConfig()
    if data.get('schema')!='P2_S05_EDGE_PROFILES_V1':
        raise PenumbraError('unexpected manifest schema')
    edges=data.get('edges')
    if not isinstance(edges,list) or not edges or len(edges)>200:
        raise PenumbraError('edges must contain 1..200 profiles')
    ids=[x.get('id') for x in edges if isinstance(x,dict)]
    if len(ids)!=len(edges) or len(set(ids))!=len(ids):
        raise PenumbraError('unique edge IDs are required')
    reports=[fit_edge_profile(e,cfg) for e in edges]
    angles=[p['angular_diameter_deg'] for p in reports if p.get('angular_diameter_deg') is not None]
    result={'module':'P2_S05_UNIFORM_EXTENDED_SOURCE_EDGE','state':'INDETERMINATE',
            'reason':'INSUFFICIENT_INDEPENDENT_METRIC_EDGES_OR_NO_COMMON_SOURCE_CLAIM',
            'evidence':reports,'profiles_measured':sum(r['state']=='MEASURED' for r in reports),
            'angular_edges_measured':len(angles),'angular_diameter_median_deg':None,
            'relative_max_deviation':None,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'not_measured':['AI provenance','true 3D emitter size/distance separately',
                            'independent real-photo shadow detection accuracy','real-camera error rates'],
            'limitations':['annotated edge profiles; no automatic shadow boundary detection',
                           'profile fit does not prove source is a disk or strip',
                           'common camera/lighting processing or PSF may create correlated errors',
                           'one edge cannot identify emitter angular size without independent metric geometry',
                           'umbra plateau refers to no direct modeled light; ambient may remain nonzero']}
    if len(angles)>=cfg.min_edges_for_consistency and data.get('declared_common_source') is True:
        median=float(np.median(angles))
        relative=float(np.max(np.abs(np.asarray(angles)-median))/max(.00001,median))
        result['angular_diameter_median_deg']=median
        result['relative_max_deviation']=relative
        result['state']=('CONSISTENT_UNDER_ASSUMPTIONS' if relative <= cfg.max_relative_angular_spread
                         else 'INCONSISTENT_UNDER_ASSUMPTIONS')
        result['reason']=('CONSISTENT_APPARENT_ANGULAR_EXTENT' if relative <= cfg.max_relative_angular_spread
                          else 'DISAGREEING_APPARENT_ANGULAR_EXTENTS')
        result['comparison_threshold_relative']=cfg.max_relative_angular_spread
        result['statistical_warning']='Heuristic physical-consistency threshold, NOT an empirically calibrated hypothesis-test p-value'
    return result


def draw_penumbra_profiles(data:dict,report:dict,path:Path)->None:
    """Simple plotted visualization without matplotlib; uses native OpenCV."""
    width=1180;panelh=215;panelcount=min(6,len(data['edges']));height=panelh*panelcount+40
    frame=np.full((height,width,3),(22,31,40),np.uint8)
    for j,(edge,result) in enumerate(zip(data['edges'][:panelcount],report['evidence'][:panelcount])):
        x=np.asarray(edge['x_px'],dtype=float);y=np.asarray(edge['linear_irradiance'],dtype=float)
        y0=28+j*panelh; px0=65; span=width-120
        def to_xy(xx,yy):
            return (int(round(px0+(xx-x[0])/(x[-1]-x[0])*span)),
                    int(round(y0+165-np.clip(yy,0,1)*140)))
        cv2.line(frame,(px0,y0+165),(width-45,y0+165),(135,145,155),1)
        cv2.line(frame,(px0,y0+25),(px0,y0+165),(135,145,155),1)
        for i in range(len(x)-1):
            cv2.line(frame,to_xy(x[i],y[i]),to_xy(x[i+1],y[i+1]),(78,190,246),1,cv2.LINE_AA)
        if result.get('state')=='MEASURED':
            xp=np.linspace(x[0],x[-1],500)
            yp=edge_irradiance(xp,result['center_px'],result['penumbra_halfwidth_px'],
                    result['shadow_irradiance'],result['lit_irradiance'],
                    edge['light_side'],edge['source_shape'])
            coords=np.array([to_xy(a,b) for a,b in zip(xp,yp)],dtype=np.int32)
            cv2.polylines(frame,[coords],False,(100,235,142),2,cv2.LINE_AA)
            for edge_x in [result['center_px']-result['penumbra_halfwidth_px'],
                            result['center_px']+result['penumbra_halfwidth_px']]:
                px=to_xy(edge_x,.5)[0]
                cv2.line(frame,(px,y0+20),(px,y0+165),(65,145,210),1,cv2.LINE_AA)
        label=f'{result["id"]}: {result["state"]}, R2={result.get("fit_r2",0):.3f}'
        cv2.putText(frame,label,(px0,y0+14),cv2.FONT_HERSHEY_SIMPLEX,.53,(240,244,248),1,cv2.LINE_AA)
    path.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(path),frame):
        raise OSError(f'failed to write image: {path}')


def run_penumbra_manifest(input_path:Path,out:Path,config:PenumbraConfig|None=None)->dict:
    raw=input_path.read_bytes()
    data=json.loads(raw.decode('utf-8'))
    report=analyze_penumbra_manifest(data,config)
    report['manifest_sha256']=hashlib.sha256(raw).hexdigest()
    out.mkdir(parents=True,exist_ok=True)
    (out/'p2_s05_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    draw_penumbra_profiles(data,report,out/'p2_s05_profiles.png')
    return report


def coaxial_circular_shadow_regions(emitter_radius_m:float,blocker_radius_m:float,
                                    source_to_blocker_m:float,blocker_to_receiver_m:float)->dict:
    """Exact geometric extents for coaxial parallel source/blocker/receiver planes.

    Geometric optics only; no diffraction, transmission, finite camera PSF or
    indirect illumination. Returned values are radii on the receiver plane.
    """
    v=(emitter_radius_m,blocker_radius_m,source_to_blocker_m,blocker_to_receiver_m)
    if not all(np.isfinite(k) and k>0 for k in v):
        raise PenumbraError('all coaxial geometry distances/radii must be positive')
    magnification=1+blocker_to_receiver_m/source_to_blocker_m
    penumbra_component=emitter_radius_m*blocker_to_receiver_m/source_to_blocker_m
    outer=blocker_radius_m*magnification+penumbra_component
    inner=blocker_radius_m*magnification-penumbra_component
    return {'outer_partial_shadow_radius_m':float(outer),
            'full_umbra_radius_m':float(max(0,inner)),
            'signed_inner_boundary_radius_m':float(inner),
            'axial_full_umbra_exists':bool(inner>0),
            'antumbra_possible':bool(inner<0),
            'penumbra_band_width_m':float(outer-max(inner,0)) if inner>0 else None,
            'source_angular_diameter_from_blocker_deg':float(np.rad2deg(2*np.arctan(emitter_radius_m/source_to_blocker_m))),
            'assumptions':'coaxial circular opaque blocker and uniform disk source; parallel planes; geometric optics'}
