"""P3-R02 calibrated planar refraction, parallel transparent slab and apparent position.

The user supplies independent calibrated K/R/t, planar interfaces, refractive
indices, known 3D points and observed corresponding pixels. This checks the
stated scene hypothesis; it neither detects glass automatically nor proves
image origin. 3D units remain those of the supplied world coordinate system.

World: X_camera = R @ X_world + t; the interface normal points TOWARD the
camera-side medium. Single interface: medium1(camera) -> medium2(object).
Slab: medium1(camera) -> medium2(plate) -> medium3(object). Both surfaces
parallel and separated by a measured positive physical thickness.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import brentq

from .mirror_geometry import (
    CalibratedCamera, MirrorGeometryError, MirrorPlane,
    TotalInternalReflection, refract_direction, unit,
)


class RefractionGeometryError(ValueError):
    """Invalid or unobservable refraction hypothesis / manifest."""


def _v3(v, label):
    a = np.asarray(v, dtype=float)
    if a.shape != (3,) or not np.isfinite(a).all():
        raise RefractionGeometryError(f'{label} requires three finite numbers')
    return a


def _v2(v, label):
    a = np.asarray(v, dtype=float)
    if a.shape != (2,) or not np.isfinite(a).all():
        raise RefractionGeometryError(f'{label} requires two finite numbers')
    return a


def _index(v, label):
    try:
        x = float(v)
    except (TypeError, ValueError) as ex:
        raise RefractionGeometryError(f'{label} must be a positive finite index') from ex
    if not np.isfinite(x) or x <= 0:
        raise RefractionGeometryError(f'{label} must be a positive finite index')
    return x


@dataclass(frozen=True)
class RefractiveInterface:
    point: np.ndarray
    normal: np.ndarray
    n_camera: float
    n_layer: float
    model: str
    thickness: float = 0.0
    n_beyond: float | None = None
    polygon: np.ndarray | None = None

    @classmethod
    def from_manifest(cls, data):
        if not isinstance(data, dict):
            raise RefractionGeometryError('interface must be an object')
        p = _v3(data.get('point_world'), 'point_world')
        n = unit(_v3(data.get('normal_toward_camera_world'), 'normal_toward_camera_world'))
        model = data.get('model')
        if model not in ('single_interface', 'parallel_slab'):
            raise RefractionGeometryError('model must be single_interface or parallel_slab')
        ni = _index(data.get('n_camera'), 'n_camera')
        nm = _index(data.get('n_layer'), 'n_layer')
        thickness = 0.
        beyond = None
        if model == 'parallel_slab':
            thickness = float(data.get('thickness_world', np.nan))
            if not np.isfinite(thickness) or thickness <= 1e-8:
                raise RefractionGeometryError('parallel slab requires positive physical thickness_world')
            beyond = _index(data.get('n_beyond'), 'n_beyond')
        if 'polygon_world' in data:
            poly = np.asarray(data['polygon_world'], dtype=float)
            plane = MirrorPlane.from_manifest({'normal_world': n.tolist(), 'offset_world':-float(n@p),
                                               'polygon_world':poly.tolist()})
            poly = plane.polygon
        else:
            poly = None
        return cls(p, n, ni, nm, model, thickness, beyond, poly)

    def signed(self, x):
        return float(self.normal@(_v3(x,'world point')-self.point))

    def aperture_contains(self, x, second=False):
        if self.polygon is None:
            return True
        support = MirrorPlane.from_manifest({'normal_world':self.normal.tolist(),
            'offset_world':-float(self.normal@self.point),
            'polygon_world':self.polygon.tolist()})
        return bool(support.contains(_v3(x,'intersection')+(self.thickness*self.normal if second else 0.)))

    def depth_intervals(self, camera_xyz, object_xyz):
        c = self.signed(camera_xyz)
        p = self.signed(object_xyz)
        if c <= 1e-9:
            raise RefractionGeometryError('camera must be strictly on incident side of interface')
        if self.model == 'single_interface':
            if p >= -1e-9:
                raise RefractionGeometryError('object must be strictly in the transmitted medium')
            return (c, -p), (self.n_camera,self.n_layer)
        if p >= -self.thickness-1e-9:
            raise RefractionGeometryError('object must be strictly beyond the rear slab surface')
        return (c, self.thickness, -p-self.thickness), (self.n_camera,self.n_layer,self.n_beyond)


def solve_planar_refraction(camera: CalibratedCamera, interface: RefractiveInterface, xyz):
    """Return exact ray from camera to point under isotropic parallel-layer optics.

    This exploits conserved tangential optical momentum p=n*sin(theta).
    Lateral travel across layer i = h_i*p/sqrt(n_i^2-p^2).
    For finite lateral displacement, the scalar equation is monotonic.
    No optimization using observed image locations is performed.
    """
    P=_v3(xyz,'object_world_xyz')
    C=camera.center
    heights, indices=interface.depth_intervals(C,P)
    n=interface.normal
    d=P-C
    tang=d-float(d@n)*n
    rho=float(np.linalg.norm(tang))
    lateral=tang/rho if rho>1e-12 else np.zeros(3)
    if rho<=1e-12:
        optical_p=0.
    else:
        def f(momentum):
            return sum(float(h)*momentum/np.sqrt(float(ni)**2-momentum**2)
                       for h,ni in zip(heights,indices)) - rho
        upper=float(min(indices))*(1.-1e-13)
        optical_p=float(brentq(f,0.,upper,xtol=1e-13,rtol=1e-13))
    runs=[float(h)*optical_p/np.sqrt(float(ni)**2-optical_p**2)
          for h,ni in zip(heights,indices)]
    hit1=C-heights[0]*n+runs[0]*lateral
    if not interface.aperture_contains(hit1):
        raise RefractionGeometryError('expected incident hit is outside supplied aperture polygon')
    if interface.model=='parallel_slab':
        hit2=hit1-interface.thickness*n+runs[1]*lateral
        if not interface.aperture_contains(hit2,second=True):
            raise RefractionGeometryError('expected rear hit is outside supplied aperture polygon')
    else:
        hit2=None
    # The first medium ray determines the observed pixel for the refracted path.
    first_ray=unit(hit1-C,'first camera ray')
    expected=camera.project(C+first_ray)
    naive=camera.project(P)
    if interface.model=='parallel_slab':
        waypoints=[C,hit1,hit2,P]
    else:
        waypoints=[C,hit1,P]
    angle_deg=[float(np.rad2deg(np.arcsin(np.clip(optical_p/ni,0.,1.)))) for ni in indices]
    return {'expected_xy':expected,'naive_straight_xy':naive,
            'pixel_shift_xy':expected-naive,
            'pixel_shift_norm_px':float(np.linalg.norm(expected-naive)),
            'ray_points_world':[x.tolist() for x in waypoints],
            'interface_incidence_angles_deg':angle_deg,
            'tangential_optical_momentum':optical_p,
            'snell_residual':float(max(abs(indices[i]*np.sin(np.deg2rad(angle_deg[i]))-
                                           indices[i+1]*np.sin(np.deg2rad(angle_deg[i+1])))
                                        for i in range(len(indices)-1)))}


def trace_observed_ray(camera: CalibratedCamera, interface: RefractiveInterface,
                       observed_xy, target_world_xyz):
    """Independent observed ray trace through layers to known target-depth plane.

    The difference from the target world point is correlated with pixel
    reprojection residual, and MUST NOT be counted as a second evidence test.
    """
    C=camera.center
    P=_v3(target_world_xyz,'object')
    interface.depth_intervals(C,P)
    d=camera.ray(_v2(observed_xy,'observed_xy'))
    n=interface.normal
    def intersect(X,v,depth):
        denom=float(v@n)
        if denom>=-1e-12:
            raise RefractionGeometryError('ray parallel to or away from the interface')
        distance=(depth-interface.signed(X))/denom
        if distance<=1e-9:
            raise RefractionGeometryError('ray intersection is not in its forward direction')
        return X+distance*v
    hit1=intersect(C,d,0.)
    if not interface.aperture_contains(hit1):
        raise RefractionGeometryError('observed ray hits outside supplied aperture polygon')
    try:
        in_layer=refract_direction(d,n,interface.n_camera,interface.n_layer)
    except TotalInternalReflection:
        raise
    except MirrorGeometryError as exc:
        raise RefractionGeometryError(str(exc)) from exc
    if interface.model=='parallel_slab':
        hit2=intersect(hit1,in_layer,-interface.thickness)
        if not interface.aperture_contains(hit2,second=True):
            raise RefractionGeometryError('rear refraction hit is outside supplied aperture polygon')
        transmitted=refract_direction(in_layer,n,interface.n_layer,interface.n_beyond)
        obj_at_depth=intersect(hit2,transmitted,interface.signed(P))
        points=[C,hit1,hit2,obj_at_depth]
    else:
        obj_at_depth=intersect(hit1,in_layer,interface.signed(P))
        points=[C,hit1,obj_at_depth]
    straight_ray=camera.ray(observed_xy)
    t=(interface.signed(P)-interface.signed(C))/float(straight_ray@n)
    apparent=C+t*straight_ray
    return {'observed_ray_points_world':[x.tolist() for x in points],
            'traced_xyz_at_target_depth':obj_at_depth.tolist(),
            'traced_world_error':float(np.linalg.norm(obj_at_depth-P)),
            'apparent_unrefracted_xyz_at_target_depth':apparent.tolist(),
            'apparent_position_shift_world':float(np.linalg.norm(apparent-P))}


def analyze_refraction_manifest(data, tolerance_px=3., min_pairs=3):
    if not isinstance(data,dict):
        raise RefractionGeometryError('manifest must be a JSON object')
    try:
        cam=CalibratedCamera.from_manifest(data['camera'])
    except (KeyError,MirrorGeometryError) as exc:
        raise RefractionGeometryError(f'invalid calibrated camera: {exc}') from exc
    interface=RefractiveInterface.from_manifest(data.get('interface'))
    if interface.signed(cam.center)<=1e-9:
        raise RefractionGeometryError('normal_toward_camera_world does not face camera')
    shape=data.get('image_shape_hw')
    if not (isinstance(shape,list) and len(shape)==2 and all(type(v) is int and v>0 for v in shape)):
        raise RefractionGeometryError('image_shape_hw must be positive integers [height,width]')
    threshold=float(tolerance_px)
    if not np.isfinite(threshold) or threshold<=0:
        raise RefractionGeometryError('tolerance_px must be finite and positive')
    pairs=data.get('correspondences')
    if not isinstance(pairs,list) or not pairs:
        raise RefractionGeometryError('correspondences must be nonempty list')
    ids=set();out=[]
    for i,entry in enumerate(pairs):
        if not isinstance(entry,dict):
            raise RefractionGeometryError('every correspondence must be an object')
        ident=str(entry.get('id',f'refracted_{i:03d}'))
        if ident in ids:
            raise RefractionGeometryError('duplicate correspondence id: '+ident)
        ids.add(ident)
        P=_v3(entry.get('object_world_xyz'),ident+' object_world_xyz')
        obs=_v2(entry.get('observed_xy'),ident+' observed_xy')
        conf=float(entry.get('confidence',1.))
        if not np.isfinite(conf) or not 0<conf<=1:
            raise RefractionGeometryError('confidence must be finite in (0,1]')
        record={'id':ident,'object_world_xyz':P.tolist(),'observed_xy':obs.tolist(),
                'confidence':conf}
        if not (0<=obs[0]<shape[1] and 0<=obs[1]<shape[0]):
            record.update(state='INDETERMINATE',reason='annotated pixel lies outside image bounds')
            out.append(record);continue
        try:
            pred=solve_planar_refraction(cam,interface,P)
            if not (0<=pred['expected_xy'][0]<shape[1] and 0<=pred['expected_xy'][1]<shape[0]):
                raise RefractionGeometryError('modeled point lies outside image field of view')
            traced=trace_observed_ray(cam,interface,obs,P)
            error=float(np.linalg.norm(pred['expected_xy']-obs))
            record.update(state='CONSISTENT_UNDER_ASSUMPTIONS' if error<=threshold else 'INCONSISTENT_UNDER_ASSUMPTIONS',
                          reprojection_residual_px=error,
                          expected_xy=pred['expected_xy'].tolist(),
                          naive_straight_xy=pred['naive_straight_xy'].tolist(),
                          modeled_pixel_shift_xy=pred['pixel_shift_xy'].tolist(),
                          modeled_pixel_shift_norm_px=pred['pixel_shift_norm_px'],
                          expected_interface_angles_deg=pred['interface_incidence_angles_deg'],
                          snell_law_numerical_residual=pred['snell_residual'],
                          ray_points_world=pred['ray_points_world'],
                          observed_ray_diagnostics=traced)
        except (RefractionGeometryError,MirrorGeometryError,TotalInternalReflection) as exc:
            record.update(state='INDETERMINATE',reason=str(exc))
        out.append(record)
    good=sum(x['state']=='CONSISTENT_UNDER_ASSUMPTIONS' for x in out)
    bad=sum(x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for x in out)
    uncertain=len(out)-good-bad
    observable=good+bad
    if observable<min_pairs:
        state='INDETERMINATE'; reason='fewer than required observable independently labeled matches'
    elif bad:
        state='INCONSISTENT_UNDER_ASSUMPTIONS';reason='at least one measured correspondence disagrees with the supplied refractive model'
    else:
        state='CONSISTENT_UNDER_ASSUMPTIONS';reason='observable matches agree within stated pixel tolerance'
    errors=[r['reprojection_residual_px'] for r in out if 'reprojection_residual_px' in r]
    return {'module':'P3-R02','ai_origin_decision':'NOT_ESTIMATED','state':state,'reason':reason,'image_shape_hw':shape,
            'interface':{'model':interface.model,'point_world':interface.point.tolist(),
                         'normal_toward_camera_world':interface.normal.tolist(),
                         'n_camera':interface.n_camera,'n_layer':interface.n_layer,
                         'thickness_world':interface.thickness if interface.model=='parallel_slab' else None,
                         'n_beyond':interface.n_beyond,
                         'polygon_world':None if interface.polygon is None else interface.polygon.tolist()},
            'tolerance_px':threshold,'total':len(out),'consistent_count':good,
            'inconsistent_count':bad,'indeterminate_count':uncertain,
            'rmse_all_observable_px':float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            'correspondences':out,
            'assumptions':['independent metric K/R/t camera calibration (distortion removed beforehand)',
                'externally measured planar interface location, orientation and refractive indices',
                'independently labeled 3D object points and observed pixel correspondences',
                'homogeneous isotropic nondispersive media, geometric ray optics',
                'parallel, plane-parallel faces and measured thickness for slab',
                'no lens distortion, inter-reflections, waves, roughness or curved surfaces in model'],
            'limitations':['point correspondence reprojection is correlated with traced world residual; count only once',
                'wrong geometry, calibration or annotation can produce inconsistency; not a proof of AI origin',
                'TIR produces no transmitted ray in forward tracing',
                'absolute refractive indices require independent determination; not fitted from these observations',
                'confidence is metadata only and does not automatically weight or calibrate scores',
                'real-image validation deferred to project final acceptance']}


def overlay_refraction(image, report):
    h,w=report['image_shape_hw']
    if image.shape[:2]!=(h,w):
        raise RefractionGeometryError('supplied image dimensions disagree with manifest')
    canvas=image.copy()
    if canvas.ndim==2:
        canvas=cv2.cvtColor(canvas,cv2.COLOR_GRAY2BGR)
    if canvas.dtype!=np.uint8:
        raise RefractionGeometryError('overlay image must be uint8')
    for r in report['correspondences']:
        a=np.round(r['observed_xy']).astype(int)
        if r['state']=='INDETERMINATE':
            cv2.circle(canvas,tuple(a),6,(0,180,255),1,cv2.LINE_AA);continue
        b=np.round(r['expected_xy']).astype(int)
        color=(80,220,70) if r['state']=='CONSISTENT_UNDER_ASSUMPTIONS' else (0,80,240)
        cv2.line(canvas,tuple(a),tuple(b),color,1,cv2.LINE_AA)
        cv2.circle(canvas,tuple(a),4,color,-1,cv2.LINE_AA)
        cv2.drawMarker(canvas,tuple(b),(255,255,0),cv2.MARKER_CROSS,8,1,cv2.LINE_AA)
        baseline=np.round(r['naive_straight_xy']).astype(int)
        if 0<=baseline[0]<w and 0<=baseline[1]<h:
            cv2.circle(canvas,tuple(baseline),3,(210,150,80),1,cv2.LINE_AA)
    return canvas


def run_refraction_manifest(input_path:Path,out:Path,image_path:Path|None=None,tolerance_px=3.):
    data=json.loads(Path(input_path).read_text(encoding='utf-8'))
    result=analyze_refraction_manifest(data,tolerance_px=tolerance_px)
    result['input_manifest_sha256']=hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    result_path=out/'p3_r02_report.json'
    result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if image_path is not None:
        im=cv2.imread(str(image_path),cv2.IMREAD_COLOR)
        if im is None:raise RefractionGeometryError('failed to read image')
        cv2.imwrite(str(out/'p3_r02_overlay.png'),overlay_refraction(im,result))
    return result
