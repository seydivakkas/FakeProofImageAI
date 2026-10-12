"""P3-R01: calibrated planar-mirror geometric consistency, not AI-origin detection.

Coordinate convention: X_camera=R_world_to_camera @ X_world+t_world_to_camera,
image p~K@X_camera. Plane n·X + d=0 with unit n. Mirror and object are
on camera's side of an ideal opaque planar mirror. 3D points and mirror
plane are independently supplied; no automatic correspondence discovery.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class MirrorGeometryError(ValueError):
    """Invalid/physically unobservable mirror geometry."""


class TotalInternalReflection(MirrorGeometryError):
    """No transmitted refracted ray exists for these indices/incident ray."""


def _vec(v, size: int, label: str) -> np.ndarray:
    a = np.asarray(v, dtype=np.float64)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise MirrorGeometryError(f'{label} must be {size} finite numbers')
    return a


def unit(v, label='vector'):
    v = _vec(v, 3, label)
    length = np.linalg.norm(v)
    if length < 1e-10:
        raise MirrorGeometryError(f'{label} has zero length')
    return v / length


@dataclass(frozen=True)
class CalibratedCamera:
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray

    @classmethod
    def from_manifest(cls, data):
        try:
            K = np.asarray(data['K'], float)
            R = np.asarray(data['R_world_to_camera'], float)
            t = _vec(data['t_world_to_camera'], 3, 't')
        except (KeyError, TypeError, ValueError) as exc:
            raise MirrorGeometryError('camera requires K, R_world_to_camera and t_world_to_camera') from exc
        if K.shape != (3,3) or R.shape != (3,3) or not np.isfinite(K).all() or not np.isfinite(R).all():
            raise MirrorGeometryError('K and R must be finite 3x3 matrices')
        if (not np.allclose(K[2], [0,0,1], atol=1e-8) or
            not np.allclose(K[np.tril_indices(3,-1)], 0, atol=1e-8) or
            K[0,0] <= 0 or K[1,1] <= 0):
            raise MirrorGeometryError('K must be upper triangular, K33=1, positive focal lengths')
        if not np.allclose(R.T@R, np.eye(3), atol=1e-5) or abs(np.linalg.det(R)-1)>1e-5:
            raise MirrorGeometryError('R must be a proper right-handed rotation')
        return cls(K,R,t)

    @property
    def center(self):
        return -self.R.T@self.t

    def project(self, xyz):
        p = _vec(xyz,3,'world point')
        cam = self.R@p+self.t
        if cam[2] <= 1e-8:
            raise MirrorGeometryError('point is behind camera or at the focal plane')
        result = self.K@cam
        return result[:2]/result[2]

    def ray(self, uv):
        p = _vec(uv,2,'image point')
        return unit(self.R.T@np.linalg.solve(self.K, [*p,1.]), 'backprojection ray')


@dataclass(frozen=True)
class MirrorPlane:
    normal: np.ndarray
    offset: float
    polygon: np.ndarray | None = None

    @classmethod
    def from_manifest(cls, data):
        try:
            n = _vec(data['normal_world'],3,'mirror normal')
            d = float(data['offset_world'])
        except (TypeError, KeyError, ValueError) as exc:
            raise MirrorGeometryError('mirror requires normal_world and offset_world') from exc
        if not np.isfinite(d) or np.linalg.norm(n)<1e-10:
            raise MirrorGeometryError('invalid mirror plane')
        scale=float(np.linalg.norm(n))
        n,d=n/scale,d/scale
        polygon=None
        if 'polygon_world' in data:
            polygon=np.asarray(data['polygon_world'],float)
            if polygon.ndim!=2 or polygon.shape[1]!=3 or len(polygon)<3 or not np.isfinite(polygon).all():
                raise MirrorGeometryError('polygon_world must be finite Nx3, N>=3')
            if np.max(np.abs(polygon@n+d))>1e-5:
                raise MirrorGeometryError('polygon_world vertices must lie on mirror plane')
            if np.linalg.matrix_rank(polygon[1:]-polygon[0],tol=1e-7)<2:
                raise MirrorGeometryError('mirror polygon must have nonzero area')
        return cls(n,d,polygon)

    def signed_distance(self, p):
        return float(self.normal@_vec(p,3,'point')+self.offset)

    def reflect_point(self, p):
        p=_vec(p,3,'point')
        return p-2*self.signed_distance(p)*self.normal

    def ray_hit(self, center, ray):
        center=_vec(center,3,'center'); ray=unit(ray)
        denom=float(self.normal@ray)
        if abs(denom)<1e-10:
            raise MirrorGeometryError('ray parallel to mirror plane')
        distance=-(self.normal@center+self.offset)/denom
        if distance<=1e-8:
            raise MirrorGeometryError('mirror hit is behind or at camera')
        return center+distance*ray

    def contains(self, point):
        if self.polygon is None:
            return True
        p=_vec(point,3,'mirror hit')
        if abs(self.signed_distance(p))>1e-5:
            return False
        n=self.normal
        temp=np.array([1.,0.,0.]) if abs(n[0])<0.9 else np.array([0.,1.,0.])
        u=unit(np.cross(n,temp));v=np.cross(n,u)
        xy=np.stack([self.polygon@u,self.polygon@v],axis=1).astype('float32')
        coords=(float(p@u),float(p@v))
        return cv2.pointPolygonTest(xy,coords,False)>=0


def reflect_direction(incoming, normal):
    """d_out = d_in - 2(d_in dot n)n, n orientation arbitrary."""
    d=unit(incoming,'incoming'); n=unit(normal,'normal')
    return unit(d-2*np.dot(d,n)*n,'reflected direction')


def refract_direction(incoming, oriented_normal, n_from, n_to):
    """Snell refraction helper, NOT used in mirror detection.

    The normal points into the incident medium, opposed to incoming ray.
    TIR raises TotalInternalReflection.
    """
    v=unit(incoming,'incoming'); n=unit(oriented_normal,'normal')
    ni=float(n_from);nt=float(n_to)
    if not (np.isfinite(ni) and np.isfinite(nt) and ni>0 and nt>0):
        raise MirrorGeometryError('refractive indices must be finite and positive')
    cos_i=-float(np.dot(n,v))
    if cos_i < -1e-8:
        raise MirrorGeometryError('normal must face incoming light')
    cos_i=np.clip(cos_i,0,1)
    ratio=ni/nt
    k=1-ratio**2*(1-cos_i**2)
    if k<-1e-10:
        raise TotalInternalReflection('total internal reflection; transmitted ray absent')
    return unit(ratio*v+(ratio*cos_i-np.sqrt(max(0,k)))*n,'refracted direction')


def expected_reflection(camera: CalibratedCamera, plane: MirrorPlane, object_xyz):
    P=_vec(object_xyz,3,'object point')
    if plane.signed_distance(P)*plane.signed_distance(camera.center)<=1e-8:
        raise MirrorGeometryError('object and camera must be strictly on the same side of mirror')
    virtual=plane.reflect_point(P)
    pred=camera.project(virtual)
    M=plane.ray_hit(camera.center,camera.ray(pred))
    if not plane.contains(M):
        raise MirrorGeometryError('specular reflection falls outside the supplied mirror polygon')
    return {'virtual_xyz_world':virtual,'expected_reflection_xy':pred,'mirror_hit_world':M}


def observed_reflection_residual(camera, plane, object_xyz, reflected_uv):
    """Observed pixel -> mirror ray, then independently check reflection law.

    Reprojection and angle residual are correlated, NOT independent evidence.
    """
    predicted=expected_reflection(camera,plane,object_xyz)
    observed=_vec(reflected_uv,2,'reflected image point')
    M=plane.ray_hit(camera.center,camera.ray(observed))
    if not plane.contains(M):
        raise MirrorGeometryError('observed ray hits outside the mirror polygon')
    incoming=unit(M-_vec(object_xyz,3,'object point'))
    outgoing=unit(camera.center-M)
    expected_out=reflect_direction(incoming,plane.normal)
    angle=float(np.rad2deg(np.arccos(np.clip(expected_out@outgoing,-1,1))))
    # The signed bisector is the surface normal required to explain this
    # incoming/outgoing ray pair. Sign is irrelevant for a geometric plane.
    inferred_n=unit(incoming-outgoing,'ray-implied mirror normal')
    normal_angle=float(np.rad2deg(np.arccos(np.clip(abs(inferred_n@plane.normal),0,1))))
    dist=float(np.linalg.norm(predicted['expected_reflection_xy']-observed))
    return {**predicted, 'observed_mirror_hit_world':M,
            'reflection_law_residual_deg':angle,
            'ray_implied_normal_world':inferred_n,
            'surface_normal_mismatch_deg':normal_angle,
            'reprojection_residual_px':dist}


def analyze_mirror_manifest(data: dict, tolerance_px=3., min_pairs=3):
    if not isinstance(data,dict):
        raise MirrorGeometryError('JSON manifest must be an object')
    cam=CalibratedCamera.from_manifest(data['camera'])
    plane=MirrorPlane.from_manifest(data['mirror_plane'])
    shape=data.get('image_shape_hw')
    if not isinstance(shape,list) or len(shape)!=2 or any(not isinstance(x,int) or x<=0 for x in shape):
        raise MirrorGeometryError('image_shape_hw must be positive integer [height,width]')
    tolerance_px=float(tolerance_px)
    if not np.isfinite(tolerance_px) or tolerance_px<=0:
        raise MirrorGeometryError('tolerance_px must be finite and positive')
    pairs=data.get('correspondences')
    if not isinstance(pairs,list) or not pairs:
        raise MirrorGeometryError('correspondences must be nonempty list')
    ids=set(); items=[]
    for idx,obs in enumerate(pairs):
        if not isinstance(obs,dict) or any(k not in obs for k in ('object_world_xyz','reflection_xy')):
            raise MirrorGeometryError('each correspondence needs object_world_xyz and reflection_xy')
        ident=str(obs.get('id',f'mirror_{idx:03d}'))
        if ident in ids: raise MirrorGeometryError('duplicate correspondence id: '+ident)
        ids.add(ident)
        obj=_vec(obs['object_world_xyz'],3,ident+' object')
        uv=_vec(obs['reflection_xy'],2,ident+' observed reflection')
        confidence=float(obs.get('confidence',1.))
        if not np.isfinite(confidence) or not 0<confidence<=1:
            raise MirrorGeometryError('confidence must be in (0,1]')
        row={'id':ident,'object_xyz_world':obj.tolist(),'observed_reflection_xy':uv.tolist(),
             'confidence':confidence,'status':'INDETERMINATE'}
        if uv[0]<0 or uv[0]>=shape[1] or uv[1]<0 or uv[1]>=shape[0]:
            row['reason']='observed reflection pixel lies outside image bounds'
            items.append(row)
            continue
        try:
            r=observed_reflection_residual(cam,plane,obj,uv)
            row.update({k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in r.items()})
            row['status']='CONSISTENT_UNDER_ASSUMPTIONS' if r['reprojection_residual_px']<=tolerance_px else 'INCONSISTENT_UNDER_ASSUMPTIONS'
        except MirrorGeometryError as exc:
            row['reason']=str(exc)
        items.append(row)
    valid=[p for p in items if p['status']!='INDETERMINATE']
    good=[p for p in valid if p['status']=='CONSISTENT_UNDER_ASSUMPTIONS']
    bad=[p for p in valid if p['status']=='INCONSISTENT_UNDER_ASSUMPTIONS']
    if len(valid)<min_pairs:
        state='INDETERMINATE'
        reason='insufficient physically observable annotated correspondences'
    elif bad and good:
        state='MIXED_EVIDENCE'
        reason='some annotated reflections disagree with the specified calibrated mirror'
    elif bad:
        state='INCONSISTENT_UNDER_ASSUMPTIONS'
        reason='all observable correspondences disagree with the supplied calibrated mirror'
    else:
        state='CONSISTENT_UNDER_ASSUMPTIONS'
        reason='annotated reflections agree within the chosen uncalibrated pixel tolerance'
    residual=[p['reprojection_residual_px'] for p in valid]
    return {
        'module':'P3_R01_PLANAR_MIRROR_GEOMETRY','state':state,'reason':reason,
        'decision':'NO_AI_ORIGIN_CONCLUSION','image_shape_hw':shape,
        'camera':{'K':cam.K.tolist(),'R_world_to_camera':cam.R.tolist(),
                  't_world_to_camera':cam.t.tolist(),'center_world':cam.center.tolist()},
        'mirror_plane':{'unit_normal_world':plane.normal.tolist(),'unit_offset_world':plane.offset,
                        'polygon_world':None if plane.polygon is None else plane.polygon.tolist()},
        'pixel_tolerance_px':tolerance_px,'total_pairs':len(items),'observable_pairs':len(valid),
        'consistent_count':len(good),'inconsistent_count':len(bad),
        'indeterminate_count':len(items)-len(valid),
        'reprojection_rmse_px':float(np.sqrt(np.mean(np.square(residual)))) if residual else None,
        'correspondences':items,
        'assumptions':['calibrated independent K/R/t','externally established planar mirror normal and offset',
          'known independent 3D object points','specular ideal planar mirror and real camera-side object',
          'accurate 2D reflected point annotations','no unmodeled occlusion or lens distortion'],
        'limitations':['residual and reflection-law angle derive from the same correspondences; not independent evidence',
          'physical plausibility is not proof of a real photograph',
          'not an automatic mirror detector or real-photo-validated classifier',
          'polygon containment does not model other occluders',
          'Snell refraction is separate from mirror reflection',
          'pixel tolerance is a test configuration, not an empirically calibrated false-positive threshold'],
    }


def overlay_mirror(image, report):
    h,w=report['image_shape_hw']
    if image is None:
        image=np.full((h,w,3),(40,48,60),np.uint8)
    if image.shape[:2]!=(h,w):raise MirrorGeometryError('image shape differs from image_shape_hw')
    img=image.copy()
    cam=CalibratedCamera.from_manifest(report['camera'])
    plane=MirrorPlane.from_manifest({'normal_world':report['mirror_plane']['unit_normal_world'],
                                    'offset_world':report['mirror_plane']['unit_offset_world'],
                                    **({'polygon_world':report['mirror_plane']['polygon_world']} if report['mirror_plane']['polygon_world'] is not None else {})})
    if plane.polygon is not None:
        try:
            pts=np.asarray([cam.project(v) for v in plane.polygon])
            pts=np.rint(pts).astype(np.int32).reshape(-1,1,2)
            cv2.polylines(img,[pts],True,(180,185,190),1,cv2.LINE_AA)
        except MirrorGeometryError:
            pass
    for row in report['correspondences']:
        obs=np.asarray(row['observed_reflection_xy'])
        q=tuple(np.rint(obs).astype(int))
        status=row['status']
        color=(95,205,85) if status=='CONSISTENT_UNDER_ASSUMPTIONS' else (20,150,255) if status=='INCONSISTENT_UNDER_ASSUMPTIONS' else (155,155,155)
        cv2.circle(img,q,5,color,2,cv2.LINE_AA)
        if 'expected_reflection_xy' in row:
            est=tuple(np.rint(row['expected_reflection_xy']).astype(int))
            cv2.drawMarker(img,est,(255,200,50),cv2.MARKER_CROSS,12,2,cv2.LINE_AA)
            cv2.line(img,q,est,color,1,cv2.LINE_AA)
        try:
            real=tuple(np.rint(cam.project(row['object_xyz_world'])).astype(int))
            cv2.circle(img,real,3,(240,220,180),-1,cv2.LINE_AA)
        except MirrorGeometryError:
            pass
    return img


def run_mirror_manifest(input_path: Path, out: Path, image_path: Path | None=None,
                        tolerance_px=3.):
    data=json.loads(Path(input_path).read_text(encoding='utf-8'))
    result=analyze_mirror_manifest(data,tolerance_px=tolerance_px)
    result['manifest_sha256']=hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    image=None
    if image_path is not None:
        image=cv2.imread(str(image_path),cv2.IMREAD_COLOR)
        if image is None:raise MirrorGeometryError('could not read optional image')
        result['image_sha256']=hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    canvas=overlay_mirror(image,result)
    imgfile=out/'p3_r01_overlay.png'
    if not cv2.imwrite(str(imgfile),canvas):raise MirrorGeometryError('could not save overlay')
    (out/'p3_r01_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result
