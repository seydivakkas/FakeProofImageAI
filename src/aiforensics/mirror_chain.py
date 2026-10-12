"""P3-R03: ordered, calibrated, *ideal specular planar* multi-mirror paths.

Mirror order is OBJECT -> CAMERA. Tracing an observed pixel reverses this order.
Finite opaque mirror polygons are required; automatic mirror/correspondence discovery
and arbitrary scene occluders are outside scope. This is NOT an AI detector.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from .mirror_geometry import (CalibratedCamera, MirrorPlane, MirrorGeometryError,
                              _vec, unit, reflect_direction)


class MirrorChainError(MirrorGeometryError):
    """Invalid input or geometrically inaccessible ordered reflection path."""


def _finite_polygon(vertices, normal):
    """Guard physically meaningful bounded *convex* polygon, without hidden concavity."""
    p = np.asarray(vertices, dtype=float)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 3:
        raise MirrorChainError('mirror polygon must be a finite 3D convex polygon')
    if np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[1])) < 1e-8:
        raise MirrorChainError('mirror polygon has degenerate consecutive vertices')
    signs=[]
    for i in range(len(p)):
        a,b,c=p[i],p[(i+1)%len(p)],p[(i+2)%len(p)]
        s=float(np.dot(np.cross(b-a,c-b),normal))
        if abs(s)<1e-9:continue
        signs.append(np.sign(s))
    if not signs or min(signs)<0<max(signs):
        raise MirrorChainError('mirror polygon must be convex and ordered around its boundary')
    return p


def parse_mirrors(data):
    mirrors=data.get('mirrors')
    if not isinstance(mirrors,list) or not 2<=len(mirrors)<=8:
        raise MirrorChainError('mirrors must list 2 to 8 finite planar mirrors')
    out={}
    for raw in mirrors:
        if not isinstance(raw,dict) or not isinstance(raw.get('id'),str) or not raw['id'].strip():
            raise MirrorChainError('each mirror requires a nonempty string id')
        mid=raw['id']
        if mid in out:raise MirrorChainError('duplicate mirror id: '+mid)
        if 'polygon_world' not in raw:
            raise MirrorChainError('finite polygon_world required for each mirror; infinite planes cannot verify paths')
        if raw.get('reflective_side','both') not in ('positive','negative','both'):
            raise MirrorChainError('reflective_side must be positive, negative or both')
        plane=MirrorPlane.from_manifest(raw)
        _finite_polygon(plane.polygon,plane.normal)
        out[mid]=plane
    return out


def _hit_distance(origin, direction, plane):
    d=float(plane.normal@direction)
    if abs(d)<1e-10:return None
    t=-plane.signed_distance(origin)/d
    if t<=1e-7:return None
    return float(t)


def _unintended_mirror_hit(start, direction, length, mirrors, intended_id=None):
    """First obstruction by any other supplied opaque mirror polygon on segment.

    This does not model walls, people, furniture, edge thickness or transparent glass.
    """
    for mid,m in mirrors.items():
        if mid==intended_id:continue
        dist=_hit_distance(start,direction,m)
        if dist is None or dist >= length-1e-6:continue
        if m.contains(start+dist*direction):return mid
    return None


def _ids(order, mirrors):
    if not isinstance(order,list) or not 2<=len(order)<=4:
        raise MirrorChainError('order must contain 2 to 4 mirror ids (object to camera)')
    if any(not isinstance(k,str) or k not in mirrors for k in order):
        raise MirrorChainError('order references unknown mirror ids')
    if len(set(order)) != len(order):
        raise MirrorChainError('repeating the same mirror in an order is currently unsupported')
    return order


def virtual_chain(mirrors, order, object_xyz):
    """Successive images: V_i = reflection_Mi(V_(i-1))."""
    p=_vec(object_xyz,3,'object_xyz')
    chain=[p]
    for mid in _ids(order,mirrors):
        p=mirrors[mid].reflect_point(p)
        chain.append(p)
    return chain


def trace_pixel(camera, mirrors, order, xy, object_xyz=None, reflective_sides=None):
    """Trace from camera via mirrors in REVERSE order, applying reflection law.

    Report physical camera->hit->...->object path and independent 3D closest-ray
    residual relative to externally supplied object position. The residual is
    geometrically correlated with image reprojection, not an independent vote.
    """
    order=_ids(order,mirrors)
    C=camera.center
    direction=camera.ray(xy)
    origin=C.copy()
    hits=[]
    segments=[]
    for mid in reversed(order):
        plane=mirrors[mid]
        length=_hit_distance(origin,direction,plane)
        if length is None:
            raise MirrorChainError('ordered ray does not intersect mirror '+mid+' in forward direction')
        hit=origin+length*direction
        side=(reflective_sides or {}).get(mid,'both')
        if (side=='positive' and plane.signed_distance(origin)<=1e-7 or
            side=='negative' and plane.signed_distance(origin)>=-1e-7):
            raise MirrorChainError('ray reaches non-reflective side of mirror '+mid)
        if not plane.contains(hit):
            raise MirrorChainError('ordered ray hits outside finite polygon: '+mid)
        blocked=_unintended_mirror_hit(origin,direction,length,mirrors,intended_id=mid)
        if blocked is not None:
            raise MirrorChainError('unintended earlier mirror obstruction: '+blocked)
        segments.append({'from_world':origin.tolist(),'to_world':hit.tolist(),
                         'length_world':length,'mirror_id':mid})
        hits.append({'mirror_id':mid,'hit_xyz_world':hit.tolist(),
                     'incident_direction_world':direction.tolist()})
        direction=reflect_direction(direction,plane.normal)
        hits[-1]['outgoing_direction_world']=direction.tolist()
        origin=hit
    result={'ray_hits_camera_to_object':hits,'segments':segments,
            'outgoing_to_object_direction_world':direction.tolist()}
    if object_xyz is not None:
        P=_vec(object_xyz,3,'object_xyz')
        along=float(np.dot(P-origin,direction))
        if along<=1e-7:
            raise MirrorChainError('object lies behind last reflected ray')
        blocked=_unintended_mirror_hit(origin,direction,along,mirrors)
        if blocked is not None:
            raise MirrorChainError('object path is blocked by supplied opaque mirror: '+blocked)
        miss=float(np.linalg.norm(np.cross(P-origin,direction)))
        angle=float(np.degrees(np.arctan2(miss,along)))
        result.update(object_ray_miss_world=miss,
                      object_ray_angle_deg=angle,
                      object_ray_along_world=along,
                      path_world=[C.tolist()]+[h['hit_xyz_world'] for h in hits]+[P.tolist()])
    return result


def predict_mirror_chain(camera, mirrors, order, object_xyz, reflective_sides=None):
    chain=virtual_chain(mirrors,order,object_xyz)
    uv=camera.project(chain[-1])
    trace=trace_pixel(camera,mirrors,order,uv,object_xyz,reflective_sides)
    # Geometric self-check catches degenerate or impossible virtual constructions.
    norm=float(np.linalg.norm(chain[0]-camera.center))
    if trace['object_ray_miss_world']>1e-6*max(norm,1.):
        raise MirrorChainError('virtual image does not yield a physically realizable ordered ray')
    return {'expected_reflection_xy':uv.tolist(),
            'virtual_image_chain_world':[p.tolist() for p in chain],
            **trace}


def evaluate_multi_mirror(data, tolerance_px=3., min_pairs=3):
    if not isinstance(data,dict):raise MirrorChainError('manifest must be a JSON object')
    try:
        camera=CalibratedCamera.from_manifest(data['camera'])
    except (KeyError,TypeError,ValueError) as e:
        raise MirrorChainError('invalid calibrated camera: '+str(e)) from e
    mirrors=parse_mirrors(data)
    sides={m['id']:m.get('reflective_side','both') for m in data['mirrors']}
    shape=data.get('image_shape_hw')
    if not (isinstance(shape,list) and len(shape)==2 and all(type(n)==int and n>0 for n in shape)):
        raise MirrorChainError('image_shape_hw must be [height,width] positive integers')
    if not np.isfinite(tolerance_px) or tolerance_px<=0:
        raise MirrorChainError('tolerance_px must be positive and finite')
    if min_pairs<1:raise MirrorChainError('min_pairs must be >=1')
    entries=data.get('correspondences')
    if not isinstance(entries,list) or not entries:raise MirrorChainError('correspondences must be nonempty')
    common_order=data.get('reflection_order_object_to_camera')
    if common_order is not None:_ids(common_order,mirrors)
    seen=set();rows=[]
    for i,entry in enumerate(entries):
        if not isinstance(entry,dict):raise MirrorChainError('each correspondence must be object')
        ident=entry.get('id',f'chain_{i:03d}')
        if not isinstance(ident,str) or not ident.strip() or ident in seen:
            raise MirrorChainError('duplicate or invalid correspondence id')
        seen.add(ident)
        if 'object_world_xyz' not in entry or 'reflection_xy' not in entry:
            raise MirrorChainError('each correspondence requires object_world_xyz/reflection_xy')
        P=_vec(entry['object_world_xyz'],3,'object_world_xyz')
        observed=_vec(entry['reflection_xy'],2,'reflection_xy')
        order=entry.get('reflection_order_object_to_camera',common_order)
        _ids(order,mirrors)
        conf=float(entry.get('confidence',1.))
        if not (np.isfinite(conf) and 0<conf<=1):
            raise MirrorChainError('confidence must be in (0,1]')
        row={'id':ident,'object_xyz_world':P.tolist(),
             'observed_reflection_xy':observed.tolist(),
             'reflection_order_object_to_camera':order,'confidence':conf,
             'status':'INDETERMINATE'}
        try:
            pred=predict_mirror_chain(camera,mirrors,order,P,sides)
            row['expected_reflection_xy']=pred['expected_reflection_xy']
            row['virtual_image_chain_world']=pred['virtual_image_chain_world']
            if not (0<=observed[0]<shape[1] and 0<=observed[1]<shape[0]):
                raise MirrorChainError('observed pixel outside image')
            if not (0<=pred['expected_reflection_xy'][0]<shape[1] and
                    0<=pred['expected_reflection_xy'][1]<shape[0]):
                raise MirrorChainError('predicted pixel outside image')
            err=float(np.linalg.norm(observed-np.asarray(pred['expected_reflection_xy'])))
            row['reprojection_residual_px']=err
            try:
                traced=trace_pixel(camera,mirrors,order,observed,P,sides)
                row.update(traced)
                row['status']=('CONSISTENT_UNDER_ASSUMPTIONS' if err<=tolerance_px
                               else 'INCONSISTENT_UNDER_ASSUMPTIONS')
            except MirrorGeometryError as exc:
                # Known valid predicted ray + on-image annotated observed point,
                # but no physically reachable *observed* path under this exact
                # ordered finite-mirror hypothesis => model-relative contradiction.
                row['physical_trace_rejection_reason']=str(exc)
                row['status']='INCONSISTENT_UNDER_ASSUMPTIONS'
        except MirrorGeometryError as exc:
            # No valid model prediction or no measurable pixel; insufficient
            # physically meaningful support for an inconsistency statement.
            row['reason']=str(exc)
        rows.append(row)
    valid=[r for r in rows if r['status']!='INDETERMINATE']
    good=[r for r in valid if r['status']=='CONSISTENT_UNDER_ASSUMPTIONS']
    bad=[r for r in valid if r['status']=='INCONSISTENT_UNDER_ASSUMPTIONS']
    distinct_objects=(len(np.unique(np.round(np.asarray([r['object_xyz_world'] for r in valid]),6),axis=0))
                      if valid else 0)
    if len(valid)<min_pairs or distinct_objects<min_pairs:
        state='INDETERMINATE';reason='too few independent physically observable object correspondences'
    elif good and bad:
        state='MIXED_EVIDENCE';reason='some observable reflections deviate from the specified model'
    elif bad:
        state='INCONSISTENT_UNDER_ASSUMPTIONS';reason='observable annotations deviate from assumed geometry'
    else:
        state='CONSISTENT_UNDER_ASSUMPTIONS';reason='observable annotations are within configured tolerance'
    error=[r['reprojection_residual_px'] for r in valid]
    return {'module':'P3_R03_MULTI_MIRROR_RAY_CHAIN','state':state,'reason':reason,
            'decision':'NO_AI_ORIGIN_CONCLUSION','image_shape_hw':shape,
            'camera':{'K':camera.K.tolist(),'R_world_to_camera':camera.R.tolist(),
                      't_world_to_camera':camera.t.tolist(),'center_world':camera.center.tolist()},
            'mirrors':[{'id':mid,'normal_world':m.normal.tolist(),
                        'offset_world':m.offset,'polygon_world':m.polygon.tolist(),
                        'reflective_side':sides[mid]}
                       for mid,m in mirrors.items()],
            'tolerance_px':float(tolerance_px),'total_pairs':len(rows),
            'observable_pairs':len(valid),'independent_object_count':distinct_objects,'consistent_count':len(good),
            'inconsistent_count':len(bad),'indeterminate_count':len(rows)-len(valid),
            'reprojection_rmse_px':float(np.sqrt(np.mean(np.square(error)))) if error else None,
            'correspondences':rows,
            'assumptions':['independently established calibrated K/R/t','known 3D object locations and correspondences',
                           'finite opaque convex planar mirrors and supplied ordered bounce path',
                           'ideal specular reflection; all geometry shares the same metric coordinates',
                           'mirror reflective_side if provided describes the allowed face; coatings and optical throughput are not modeled'],
            'limitations':['pixel and 3D ray miss residuals are correlated, not independent physical proofs',
                           'unmodeled opaque objects and mirror thickness may occlude a path',
                           'no automatic bounce-order estimation or mirror detection',
                           'not validated on independent real images or for AI-origin detection',
                           'configured pixel tolerance is not a calibrated statistical false-positive threshold']}


def overlay_mirror_chain(image,report):
    h,w=report['image_shape_hw']
    if image is None:image=np.full((h,w,3),(40,48,60),dtype=np.uint8)
    if image.shape[:2]!=(h,w):raise MirrorChainError('image dimensions differ from manifest')
    out=image.copy()
    for row in report['correspondences']:
        uv=np.rint(row['observed_reflection_xy']).astype(int)
        c=((95,205,85) if row['status']=='CONSISTENT_UNDER_ASSUMPTIONS' else
           (30,150,255) if row['status']=='INCONSISTENT_UNDER_ASSUMPTIONS' else (180,180,180))
        cv2.circle(out,tuple(uv),5,c,2,cv2.LINE_AA)
        if 'expected_reflection_xy' in row:
            ex=np.rint(row['expected_reflection_xy']).astype(int)
            cv2.drawMarker(out,tuple(ex),(255,190,60),cv2.MARKER_CROSS,12,2,cv2.LINE_AA)
            cv2.line(out,tuple(uv),tuple(ex),c,1,cv2.LINE_AA)
    cv2.putText(out,'CONTROLLED / CALIBRATED MIRROR CHAIN - NOT AI ORIGIN PROOF',
                (15,h-20),cv2.FONT_HERSHEY_SIMPLEX,.5,(230,225,225),1,cv2.LINE_AA)
    return out


def run_multi_mirror_manifest(input_path,out,image_path=None,tolerance_px=3.,min_pairs=3):
    input_path=Path(input_path);out=Path(out)
    raw=input_path.read_bytes()
    report=evaluate_multi_mirror(json.loads(raw.decode('utf-8')),tolerance_px,min_pairs)
    report['manifest_sha256']=hashlib.sha256(raw).hexdigest()
    image=None
    if image_path is not None:
        image_path=Path(image_path)
        image=cv2.imread(str(image_path),cv2.IMREAD_COLOR)
        if image is None:raise MirrorChainError('image could not be read')
        report['image_sha256']=hashlib.sha256(image_path.read_bytes()).hexdigest()
    over=overlay_mirror_chain(image,report)
    out.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(out/'p3_r03_overlay.png'),over):
        raise MirrorChainError('overlay image could not be written')
    (out/'p3_r03_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
