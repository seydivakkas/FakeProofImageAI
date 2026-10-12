"""P2-S04. Solar ephemeris (NOAA approximate) and calibrated 3D solar-shadow constraints.

The physical hypothesis is *claimed direct sunlight*, not AI origin. Coordinates
are right-handed local ENU: X=East, Y=North, Z=Up; azimuth clockwise from North.
All timestamps are explicit UTC ISO-8601; a naive date is never silently UTC.
The NOAA fractional-year series is approximate, not NREL's high-precision SPA.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import math

import cv2
import numpy as np
from .shadow_3d import _camera_plane, _backproject_on_plane, Shadow3DError, _vector


class SolarGeometryError(ValueError):
    """Invalid coordinate frame, camera or annotation."""


@dataclass(frozen=True)
class SolarConfig:
    min_pairs: int = 4
    direction_tolerance_deg: float = 2.0
    min_support_fraction: float = .70
    min_horizontal_shadow_m: float = .025
    tip_reprojection_tolerance_px: float = 3.0
    ephemeris_consistency_tolerance_deg: float = 2.0
    ransac_trials: int = 300
    bootstrap_samples: int = 200
    seed: int = 2026

    def __post_init__(self):
        if self.min_pairs < 3 or self.ransac_trials < 1 or self.bootstrap_samples < 0:
            raise SolarGeometryError('min_pairs >= 3 and ransac_trials >= 1 are required')
        if not (0 < self.direction_tolerance_deg <= 20 and 0 < self.ephemeris_consistency_tolerance_deg <= 20):
            raise SolarGeometryError('angular tolerances outside supported range')
        if not 0 < self.min_support_fraction <= 1:
            raise SolarGeometryError('min_support_fraction must be in (0,1]')
        if self.min_horizontal_shadow_m <= 0 or self.tip_reprojection_tolerance_px <= 0:
            raise SolarGeometryError('nonpositive geometric tolerance')


def _finite(v, name):
    if not np.isfinite(v).all():
        raise SolarGeometryError(f'{name}: values must be finite')
    return v


def sun_direction_from_angles(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """Unit vector from object toward Sun, in ENU coordinates."""
    if not np.isfinite([azimuth_deg,elevation_deg]).all() or not -90 <= elevation_deg <= 90:
        raise SolarGeometryError('azimuth/elevation must be finite and elevation within [-90,90]')
    a,e=np.deg2rad([azimuth_deg,elevation_deg])
    return np.array([math.cos(e)*math.sin(a),math.cos(e)*math.cos(a),math.sin(e)])


def angles_from_sun_direction(u: np.ndarray):
    u=_vector(u,3,'sun direction')
    r=np.linalg.norm(u)
    if r < 1e-12:raise SolarGeometryError('zero sun direction')
    u=u/r
    elevation=float(np.rad2deg(np.arctan2(u[2],np.linalg.norm(u[:2]))))
    azimuth=(float(np.rad2deg(np.arctan2(u[0],u[1])))%360) if np.linalg.norm(u[:2])>1e-9 else None
    return azimuth,elevation


def solar_position_noaa(latitude_deg: float, longitude_deg: float, timestamp_utc: str) -> dict:
    """Approximate geometric Sun position, not refraction/altitude-corrected SPA.

    Adapted from NOAA's published fractional-year equation-of-time and
    declination trigonometric series. Longitude positive East, UTC aware input.
    """
    if (not np.isfinite([latitude_deg, longitude_deg]).all() or
        not -90 <= latitude_deg <= 90 or not -180 <= longitude_deg <= 180):
        raise SolarGeometryError('latitude [-90,90] and longitude [-180,180] required')
    try:
        dt=datetime.fromisoformat(timestamp_utc.replace('Z','+00:00'))
    except (ValueError,TypeError,AttributeError) as exc:
        raise SolarGeometryError('timestamp_utc must be ISO-8601 with timezone') from exc
    if dt.tzinfo is None or dt.utcoffset() is None or dt.utcoffset().total_seconds()!=0:
        raise SolarGeometryError('timestamp_utc must have explicit UTC offset +00:00 or Z')
    dt=dt.astimezone(timezone.utc)
    doy=dt.timetuple().tm_yday
    days=366 if (dt.year%4==0 and (dt.year%100!=0 or dt.year%400==0)) else 365
    minute=dt.hour*60+dt.minute+dt.second/60+dt.microsecond/60_000_000
    gamma=2*math.pi/days*(doy-1+(minute/60-12)/24)
    eqtime=229.18*(.000075+.001868*math.cos(gamma)-.032077*math.sin(gamma)
                  -.014615*math.cos(2*gamma)-.040849*math.sin(2*gamma))
    decl=(.006918-.399912*math.cos(gamma)+.070257*math.sin(gamma)
          -.006758*math.cos(2*gamma)+.000907*math.sin(2*gamma)
          -.002697*math.cos(3*gamma)+.00148*math.sin(3*gamma))
    hour_angle=math.radians(((minute+eqtime+4*longitude_deg)/4-180+180)%360-180)
    phi=math.radians(latitude_deg)
    # East, North, Up components; avoids the acos azimuth sign ambiguity.
    east=-math.cos(decl)*math.sin(hour_angle)
    north=math.cos(phi)*math.sin(decl)-math.sin(phi)*math.cos(decl)*math.cos(hour_angle)
    up=math.sin(phi)*math.sin(decl)+math.cos(phi)*math.cos(decl)*math.cos(hour_angle)
    sun=_finite(np.array([east,north,up]), 'solar position')
    sun/=np.linalg.norm(sun)
    az,el=angles_from_sun_direction(sun)
    return {'method':'NOAA_FRACTIONAL_YEAR_APPROXIMATION',
            'timestamp_utc':dt.isoformat().replace('+00:00','Z'),
            'latitude_deg':float(latitude_deg),'longitude_deg':float(longitude_deg),
            'azimuth_deg_clockwise_from_true_north':az,'elevation_deg':el,
            'direction_enu':sun.tolist(),'sun_above_geometric_horizon':bool(el>0),
            'equation_of_time_minutes':eqtime,'declination_deg':math.degrees(decl),
            'limitations':['approximate fractional-year ephemeris, NOT NREL SPA',
                           'no refraction, elevation, skyline, or terrain occlusion correction',
                           'time/location and true-North alignment are external assertions']}


def _project_world(P,K,R,C):
    camera=R@(P-C)
    if camera[2] <= 1e-10:raise SolarGeometryError('projected object tip behind camera')
    h=K@camera
    return h[:2]/h[2]


def cast_shadow_to_plane(P, sun_direction, plane_normal, plane_offset):
    """Point-to-infinite-plane directional shadow intersection Q=P-lambda*u."""
    P=_vector(P,3,'P')
    u=_vector(sun_direction,3,'sun direction')
    n=_vector(plane_normal,3,'ground plane normal')
    offset=float(plane_offset)
    if not np.isfinite(offset):raise SolarGeometryError('ground plane offset must be finite')
    un=float(np.linalg.norm(u));nn=float(np.linalg.norm(n))
    if un<=1e-12 or nn<=1e-12:raise SolarGeometryError('nonzero unit vectors are required')
    u=u/un;n=n/nn;offset/=nn
    if u[2]<=0:raise SolarGeometryError('sun must be above geometric horizon')
    denom=float(n@u)
    if denom<=1e-9:raise SolarGeometryError('sun ray does not intersect illuminated side of receiver plane')
    lam=(float(n@P)+offset)/denom
    if lam<=0:raise SolarGeometryError('object point is not above receiver plane along sun ray')
    return P-lam*u


def _angular_dist_deg(U, v):
    return np.rad2deg(np.arccos(np.clip(U@v,-1.,1.)))


def _consensus(rows,config):
    if len(rows)<config.min_pairs:
        return None,'too few valid object-base-shadow correspondences'
    Bs=np.array([r['B'] for r in rows]);
    if np.linalg.norm(np.ptp(Bs,axis=0))<1e-4:
        return None,'insufficient distinct object base locations'
    U=np.array([r['sun_unit'] for r in rows]);w=np.array([r['confidence'] for r in rows]);rng=np.random.default_rng(config.seed)
    candidates=list(range(len(rows)))
    candidates.extend(int(i) for i in rng.integers(0,len(rows),config.ransac_trials))
    best=None
    for j in candidates:
        v=U[j]
        mask=_angular_dist_deg(U,v)<=config.direction_tolerance_deg
        if mask.sum()<config.min_pairs:continue
        quality=(float(w[mask].sum()),int(mask.sum()),-float(np.median(_angular_dist_deg(U[mask],v))))
        if best is None or quality>best[0]:best=(quality,mask)
    if best is None:
        return None,'no angularly consistent sun-direction family'
    mask=best[1]
    for _ in range(5):
        v=np.sum(U[mask]*w[mask,None],axis=0)
        if np.linalg.norm(v)<1e-10:return None,'ambiguous opposing light directions'
        v=v/np.linalg.norm(v)
        newmask=_angular_dist_deg(U,v)<=config.direction_tolerance_deg
        if np.array_equal(mask,newmask):break
        mask=newmask
        if mask.sum()<config.min_pairs:return None,'insufficient stable consensus'
    v=np.sum(U[mask]*w[mask,None],axis=0)
    v/=np.linalg.norm(v)
    dist=_angular_dist_deg(U,v)
    mask=dist<=config.direction_tolerance_deg
    support=float(w[mask].sum()/w.sum())
    if mask.sum()<config.min_pairs or support<config.min_support_fraction:
        return None, 'angular consensus does not meet minimum support'
    # One set of world points should not be counted many times as independent observations.
    if np.linalg.norm(np.ptp(Bs[mask],axis=0))<1e-4:
        return None, 'consensus has no spatial diversity'
    return {'direction_enu':v.tolist(), 'inlier_ids':[r['id'] for r,m in zip(rows,mask) if m],
            'excluded_ids':[r['id'] for r,m in zip(rows,mask) if not m],
            'median_angular_error_deg':float(np.median(dist[mask])),
            'max_inlier_angular_error_deg':float(np.max(dist[mask])),
            'weighted_support_fraction':support, 'inlier_count':int(mask.sum())},None


def analyze_solar_geometry(data: dict, config: SolarConfig | None=None) -> dict:
    config=config or SolarConfig()
    if data.get('world_frame')!='ENU_TRUE_NORTH':
        raise SolarGeometryError('world_frame must explicitly be ENU_TRUE_NORTH')
    if data.get('world_units') not in ('m','meter','meters'):
        raise SolarGeometryError('world_units must be meters for S04')
    try:
        shape,K,R,C,n,offset=_camera_plane(data)
    except Shadow3DError as exc:raise SolarGeometryError(str(exc)) from exc
    if not isinstance(data.get('correspondences'),list) or not data['correspondences']:
        raise SolarGeometryError('correspondences must be a nonempty array')
    rows=[];rejected=[];ids=set()
    for i,item in enumerate(data['correspondences']):
        if not isinstance(item,dict):raise SolarGeometryError(f'correspondence {i} not an object')
        ident=str(item.get('id',f'pair_{i:03d}'))
        if ident in ids:raise SolarGeometryError('duplicate correspondence id')
        ids.add(ident)
        try:
            base=_vector(item['base_xy'],2,'base_xy')
            shadow=_vector(item['shadow_xy'],2,'shadow_xy')
            h=float(item['object_height_m'])
            confidence=float(item.get('confidence',1.))
            tip=_vector(item['tip_xy'],2,'tip_xy') if 'tip_xy' in item else None
        except (KeyError,ValueError,TypeError,Shadow3DError) as exc:
            raise SolarGeometryError(f'invalid correspondence {ident}: {exc}') from exc
        if not np.isfinite([h,confidence]).all() or h<=0 or not (0<confidence<=1):
            raise SolarGeometryError(f'{ident}: positive height and confidence in (0,1] required')
        coords=[base,shadow]+([tip] if tip is not None else [])
        if any(p[0]<0 or p[0]>=shape[1] or p[1]<0 or p[1]>=shape[0] for p in coords):
            raise SolarGeometryError(f'{ident}: all pixels must lie within image bounds')
        try:
            B=_backproject_on_plane(base,0.,K,R,C,n,offset)
            Q=_backproject_on_plane(shadow,0.,K,R,C,n,offset)
        except Shadow3DError as exc:
            rejected.append({'id':ident,'reason':f'backprojection failure: {exc}'})
            continue
        # "height" is vertical Z displacement, not signed distance along normal.
        P=B+np.array([0,0,h])
        tip_error=None
        if tip is not None:
            try:tip_error=float(np.linalg.norm(_project_world(P,K,R,C)-tip))
            except SolarGeometryError as exc:
                rejected.append({'id':ident,'reason':str(exc)});continue
            if tip_error>config.tip_reprojection_tolerance_px:
                rejected.append({'id':ident,'reason':'tip reprojection mismatch','tip_error_px':tip_error})
                continue
        d=P-Q
        ground_xy=float(np.linalg.norm((Q-B)[:2]))
        if ground_xy<config.min_horizontal_shadow_m:
            rejected.append({'id':ident,'reason':'vanishing horizontal shadow / unstable azimuth'});continue
        if d[2]<=0:
            rejected.append({'id':ident,'reason':'shadow requires sun below the horizon'});continue
        u=d/np.linalg.norm(d)
        azi,ele=angles_from_sun_direction(u)
        rows.append({'id':ident,'B':B,'P':P,'Q':Q,'sun_unit':u,
                     'sun_azimuth_deg':azi,'sun_elevation_deg':ele,
                     'horizontal_shadow_m':ground_xy,'ground_surface_shadow_m':float(np.linalg.norm(Q-B)),
                     'object_height_m':h,'vertical_height_difference_m':float(P[2]-Q[2]),
                     'elevation_from_shadow_length_deg':float(np.rad2deg(np.arctan2(P[2]-Q[2],ground_xy))),
                     'tip_reprojection_error_px':tip_error,'confidence':confidence})
    estimated,reason=_consensus(rows,config)
    result={'module':'P2_S04_SOLAR_SHADOW_GEOMETRY',
            'state':'MEASURED' if estimated else 'INDETERMINATE',
            'model_class':'DIRECTIONAL_LIGHT_HYPOTHESIS',
            'world_frame':'ENU_TRUE_NORTH','world_units':'m','input_pairs':len(data['correspondences']),
            'valid_pairs':len(rows),'rejected_pairs':rejected,
            'direction_fit':estimated,'reason':reason,
            'sun_shadow_samples':[{k:v for k,v in r.items() if k not in ('B','P','Q','sun_unit')}
                                  for r in rows],
            'decision':'NO_AI_ORIGIN_CONCLUSION','real_validation':'DEFERRED',
            'assumptions':['world axes aligned with true East/North/Up',
                           'correct K/R/t and receiver plane',
                           'stationary vertically erected measured objects',
                           'single direct directional-light hypothesis across accepted pairs',
                           'known height and correct base-shadow correspondence'],
            'limitations':['direction consensus alone does not prove light is Sun rather than distant artificial source',
                           'timestamps, location, camera pose and world orientation are externally asserted',
                           'tip pixel is optional; no independent height check when omitted',
                           'no automatic shadow detection; no real-world origin verdict']}
    if estimated:
        az,el=angles_from_sun_direction(np.asarray(estimated['direction_enu']))
        result['measured_sun_azimuth_deg']=az
        result['measured_sun_elevation_deg']=el
        inliers=set(estimated['inlier_ids'])
        good=[r for r in rows if r['id'] in inliers]
        result['median_horizontal_shadow_m']=float(np.median([r['horizontal_shadow_m'] for r in good]))
        result['median_object_height_m']=float(np.median([r['object_height_m'] for r in good]))
        result['shadow_azimuth_deg']=float((az+180)%360) if az is not None else None
        # Exploratory resampling precision; not a calibrated camera/height uncertainty interval.
        if config.bootstrap_samples > 0:
            rng=np.random.default_rng(config.seed+71)
            vectors=np.array([r['sun_unit'] for r in good]);weights=np.array([r['confidence'] for r in good]);angular=[]
            for _ in range(config.bootstrap_samples):
                ids=rng.integers(0,len(good),len(good))
                v=np.sum(vectors[ids]*weights[ids,None],axis=0)
                if np.linalg.norm(v)>1e-12:
                    v=v/np.linalg.norm(v)
                    angular.append(float(_angular_dist_deg(np.asarray([v]),np.asarray(estimated['direction_enu']))[0]))
            result['bootstrap_direction_change_p90_deg']=float(np.percentile(angular,90)) if angular else None
            result['bootstrap_samples']=config.bootstrap_samples
    else:
        result['measured_sun_azimuth_deg']=None
        result['measured_sun_elevation_deg']=None
        result['shadow_azimuth_deg']=None
    claim=data.get('solar_claim')
    if claim is not None:
        if not isinstance(claim,dict):raise SolarGeometryError('solar_claim must be an object')
        try:
            eph=solar_position_noaa(float(claim['latitude_deg']),float(claim['longitude_deg']),claim['timestamp_utc'])
        except (KeyError,TypeError,ValueError) as exc:
            raise SolarGeometryError(f'invalid solar_claim: {exc}') from exc
        result['ephemeris']=eph
        if not eph['sun_above_geometric_horizon']:
            result['ephemeris_comparison']={'state':'INDETERMINATE','reason':'Sun below geometric horizon; artificial illumination/incorrect claim unresolved'}
        elif estimated is None:
            result['ephemeris_comparison']={'state':'INDETERMINATE','reason':'shadow direction not identifiable'}
        else:
            delta=float(_angular_dist_deg(np.asarray([estimated['direction_enu']]),np.array(eph['direction_enu']))[0])
            # Independent predicted shadow endpoints from claimed Sun direction.
            # This requires the annotated receivers and calibrations, not image brightness.
            predicted_offsets=[]
            for r in rows:
                if r['id'] not in set(estimated['inlier_ids']):continue
                try:
                    predicted_q=cast_shadow_to_plane(r['P'],eph['direction_enu'],n,offset)
                    predicted_offsets.append(float(np.linalg.norm(predicted_q-r['Q'])))
                except SolarGeometryError:pass
            result['ephemeris_comparison']={
                'shadow_endpoint_median_world_error_m':float(np.median(predicted_offsets)) if predicted_offsets else None,
                'state':'CONSISTENT_UNDER_ASSUMPTIONS' if delta<=config.ephemeris_consistency_tolerance_deg else 'INCONSISTENT_UNDER_ASSUMPTIONS',
                'direction_angle_difference_deg':delta,
                'tolerance_deg':config.ephemeris_consistency_tolerance_deg,
                'reason':'Comparison of measured directional hypothesis with approximate ephemeris, not AI proof'}
    else:
        result['ephemeris_comparison']={'state':'NOT_REQUESTED',
                                       'reason':'timestamp/location not supplied; do not infer date, true North, or sun identity'}
    return result


def run_solar_manifest(manifest: Path, out: Path, image_path: Path|None=None,
                       config:SolarConfig|None=None) -> dict:
    data=json.loads(Path(manifest).read_text(encoding='utf-8'))
    report=analyze_solar_geometry(data,config)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report['input_sha256']=hashlib.sha256(Path(manifest).read_bytes()).hexdigest()
    if image_path is not None:
        img=cv2.imread(str(image_path),cv2.IMREAD_COLOR)
        if img is None or img.shape[:2]!=tuple(data['image_shape_hw']):
            raise SolarGeometryError('overlay image missing or inconsistent shape')
        accepted=set(report['direction_fit']['inlier_ids']) if report['direction_fit'] else set()
        rejected={x['id'] for x in report['rejected_pairs']}
        for i,item in enumerate(data['correspondences']):
            ident=str(item.get('id',f'pair_{i:03d}'))
            c=(75,210,100) if ident in accepted else ((95,95,240) if ident in rejected else (55,165,230))
            a=tuple(np.rint(item['base_xy']).astype(int));b=tuple(np.rint(item['shadow_xy']).astype(int))
            cv2.line(img,a,b,c,2,cv2.LINE_AA)
            cv2.circle(img,a,3,(240,245,245),-1,cv2.LINE_AA)
            cv2.circle(img,b,3,c,-1,cv2.LINE_AA)
        cv2.putText(img,'P2-S04 / ENU SUN-SHADOW GEOMETRY / SYNTHETIC OR ANNOTATED',
                    (15,28),cv2.FONT_HERSHEY_SIMPLEX,.55,(230,230,230),2,cv2.LINE_AA)
        cv2.imwrite(str(out/'p2_s04_overlay.png'),img)
        report['overlay']='p2_s04_overlay.png'
        report['image_sha256']=hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    (out/'p2_s04_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
