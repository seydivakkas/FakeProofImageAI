"""G03b: annotated plane regions and *candidate* repeated rectangular elements.

Separating floor and facade is not uniquely identifiable from projective lines
alone. Only an independent, explicitly supplied annotation can give a semantic
class here. Unannotated polygons and estimated repeats ABSTAIN from semantic
and equal-world-spacing conclusions.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from .auto_patterns import PatternConfig, detect_repeated_candidates
from .imaging import load_bgr, write_image

_ALLOWED = {'floor', 'facade', 'wall', 'unknown'}

@dataclass(frozen=True)
class PlaneRegion:
    region_id: str
    polygon_xy: tuple[tuple[float,float], ...]
    plane_class: str = 'unknown'
    annotation_source: str = 'unverified_candidate'

    @classmethod
    def from_mapping(cls, raw:dict):
        return cls(str(raw['region_id']),tuple(map(tuple,raw['polygon_xy'])),
                   raw.get('plane_class','unknown'),raw.get('annotation_source','unverified_candidate'))


def validated_mask(shape:tuple[int,int], region:PlaneRegion)->np.ndarray:
    h,w=shape[:2]
    if not region.region_id or region.plane_class not in _ALLOWED:
        raise ValueError('Missing region_id or invalid plane_class')
    pts=np.asarray(region.polygon_xy,dtype=float)
    if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<3 or not np.isfinite(pts).all():
        raise ValueError('Region polygon must have >=3 finite 2D vertices')
    if np.any(pts[:,0]<0) or np.any(pts[:,0]>=w) or np.any(pts[:,1]<0) or np.any(pts[:,1]>=h):
        raise ValueError('Region polygon must lie within image bounds')
    if abs(cv2.contourArea(np.asarray(pts,dtype=np.float32)))<100:
        raise ValueError('Region polygon area too small')
    # Require a simple polygon: crossing nonadjacent edges are not allowed.
    n=len(pts)
    def intersects(a,b,c,d):
        def turn(x,y,z):
            a=y-x;b=z-x
            return float(a[0]*b[1]-a[1]*b[0])
        u,v,t,z = turn(a,b,c),turn(a,b,d),turn(c,d,a),turn(c,d,b)
        return u*v < -1e-8 and t*z < -1e-8
    for i in range(n):
        for j in range(i+1,n):
            if (i-j)%n in (1,n-1,0):continue
            if intersects(pts[i],pts[(i+1)%n],pts[j],pts[(j+1)%n]):
                raise ValueError('Self-crossing region polygon')
    mask=np.zeros((h,w),dtype=np.uint8)
    cv2.fillPoly(mask,[np.round(pts).astype(np.int32)],255)
    return mask


def _iou_box(a,b)->float:
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[0]+a[2],b[0]+b[2]);y2=min(a[1]+a[3],b[1]+b[3]);
    inter=max(0,x2-x1)*max(0,y2-y1)
    return inter/(a[2]*a[3]+b[2]*b[3]-inter+1e-9)


def _rectangular_candidates(img:np.ndarray, mask:np.ndarray, min_area:int=220)->list[dict]:
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    edge=cv2.Canny(gray,45,130)
    edge=cv2.morphologyEx(edge,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(edge,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        perimeter=cv2.arcLength(contour,True)
        if perimeter<45:continue
        quad=cv2.approxPolyDP(contour,.03*perimeter,True)
        area=cv2.contourArea(quad)
        if len(quad)!=4 or not cv2.isContourConvex(quad) or not min_area<=area<=img.shape[0]*img.shape[1]*.17:continue
        x,y,w,h=cv2.boundingRect(quad)
        if w<9 or h<9 or w*h>img.shape[0]*img.shape[1]*.2:continue
        q=quad.reshape(-1,2)
        if any(mask[min(mask.shape[0]-1,max(0,int(p[1]))),min(mask.shape[1]-1,max(0,int(p[0])))]==0 for p in q):continue
        fill=area/(w*h)
        if fill<.50:continue
        if any(_iou_box((x,y,w,h),p['box_xywh'])>.68 for p in boxes):continue
        patch=cv2.resize(gray[y:y+h,x:x+w],(24,24),interpolation=cv2.INTER_AREA)
        patch=patch.astype(np.float32)
        patch=(patch-patch.mean())/(patch.std()+3.)
        boxes.append({'box_xywh':(int(x),int(y),int(w),int(h)),
                      'aspect':float(w/h),'quad_xy':q.tolist(),'patch':patch})
    return boxes


def _repeated_groups(boxes:list[dict], min_group:int=3)->list[dict]:
    """Connected components of pairwise shape+appearance compatibility.

    Comparisons are deliberately strict 2D appearance hypotheses, not
    physical equivalence; perspective scale and shading often reduce recall.
    """
    n=len(boxes)
    neighbors=[set() for _ in range(n)]
    for i in range(n):
        for j in range(i+1,n):
            a,b=boxes[i],boxes[j]
            area_a=a['box_xywh'][2]*a['box_xywh'][3]
            area_b=b['box_xywh'][2]*b['box_xywh'][3]
            if max(area_a,area_b)/min(area_a,area_b)>2.1:continue
            if max(a['aspect'],b['aspect'])/min(a['aspect'],b['aspect'])>1.45:continue
            corr=float(np.mean(a['patch']*b['patch']))
            # normalized spatial similarity: textured designs may differ
            if corr<.18:continue
            neighbors[i].add(j);neighbors[j].add(i)
    seen=set();results=[]
    for i in range(n):
        if i in seen:continue
        group={i};stack=[i];seen.add(i)
        while stack:
            for j in neighbors[stack.pop()]:
                if j not in seen:seen.add(j);group.add(j);stack.append(j)
        if len(group)>=min_group:
            inds=sorted(group)
            boxes_group=[boxes[k]['box_xywh'] for k in inds]
            results.append({'count':len(inds),'boxes_xywh':boxes_group,
                'status':'APPEARANCE_MATCH_CANDIDATES_ONLY',
                'world_equal_spacing':'UNVERIFIED',
                'semantic_element_type':'UNVERIFIED'})
    results.sort(key=lambda a:-a['count'])
    return results


def analyze_regions(image:np.ndarray, regions:list[PlaneRegion],
                    *,min_group:int=3, max_line_groups:int=5)->dict:
    if image.ndim!=3 or image.shape[2]!=3:raise ValueError('Expected BGR image')
    results=[]
    for region in regions:
        mask=validated_mask(image.shape[:2],region)
        # Mask out segments whose complete endpoints lie outside polygon.
        rects=_rectangular_candidates(image,mask)
        groups=_repeated_groups(rects,min_group)
        # Segments on a masked image may be artificially created at mask edge.
        # Use full image detector, then filter endpoints to inside the region.
        from .imaging import detect_segments
        segs=np.vstack([detect_segments(image,min_length_px=22,method=m) for m in ('lsd','hough')])
        ends=np.rint(segs.reshape(-1,2,2)).astype(int)
        ends[:,:,0]=np.clip(ends[:,:,0],0,image.shape[1]-1)
        ends[:,:,1]=np.clip(ends[:,:,1],0,image.shape[0]-1)
        keep=np.all(mask[ends[:,:,1],ends[:,:,0]]>0,axis=1)
        segs=segs[keep]
        lines=detect_repeated_candidates(image,PatternConfig(min_marks=4,max_candidates=max_line_groups),
                                         segs) if len(segs) else []
        # Guard candidate points against leaving the polygon on concave regions.
        lines=[v for v in lines if all(mask[min(image.shape[0]-1,max(0,round(p[1]))),min(image.shape[1]-1,max(0,round(p[0])))]>0
                     for p in v['points_xy'])]
        annotation_verified=region.annotation_source in {'human_verified','independent_dataset_annotation'}
        semantic=region.plane_class if annotation_verified else 'unknown'
        results.append({'region_id':region.region_id,
           'plane_label':semantic,
           'label_state':'DECLARED_EXTERNALLY_ANNOTATED' if annotation_verified else 'UNVERIFIED',
           'annotation_source':region.annotation_source,
           'region_polygon_xy':[list(p) for p in region.polygon_xy],
           'rectangular_candidates':len(rects),'appearance_repeat_groups':groups,
           'line_intersection_candidates':lines,
           'physical_spacing_evidence':'NOT_MEASURED',
           'limits':['Plane geometry alone cannot distinguish floor from facade uniquely.',
                     'Appearance matching gives candidate repeated elements, not validated object identity.',
                     'No known physical spacing or homography ground truth was supplied.']})
    return {'module':'G03B_PLANE_AWARE_REPETITION','state':'CANDIDATE_ONLY',
            'region_count':len(results),'regions':results,
            'decision':'NO_AI_ORIGIN_CONCLUSION'}


def run_region_manifest(path:Path,out:Path)->dict:
    raw=json.loads(path.read_text(encoding='utf-8'))
    image_path=(path.parent/str(raw['image'])).resolve()
    if not image_path.is_relative_to(path.parent.resolve()):raise ValueError('Image cannot escape manifest directory')
    img=load_bgr(image_path)
    regions=[PlaneRegion.from_mapping(x) for x in raw['regions']]
    if not regions:raise ValueError('At least one region required')
    report=analyze_regions(img,regions)
    report['image_sha256']=hashlib.sha256(image_path.read_bytes()).hexdigest()
    overlay=img.copy()
    for region in report['regions']:
        poly=np.rint(region['region_polygon_xy']).astype(int)
        cv2.polylines(overlay,[poly],True,(0,225,255),2,cv2.LINE_AA)
        cv2.putText(overlay,region['region_id']+':'+region['plane_label'],tuple(poly[0]),
                    cv2.FONT_HERSHEY_SIMPLEX,.55,(0,220,255),2,cv2.LINE_AA)
        for g in region['appearance_repeat_groups']:
            for x,y,w,h in g['boxes_xywh']:
                cv2.rectangle(overlay,(x,y),(x+w,y+h),(70,240,70),1,cv2.LINE_AA)
        for x in region['line_intersection_candidates']:
            for p in x['points_xy']:
                cv2.circle(overlay,tuple(np.rint(p).astype(int)),3,(255,130,60),-1)
    out.mkdir(parents=True,exist_ok=True)
    report['overlay']='g03b_plane_patterns.png'
    write_image(out/'g03b_plane_patterns.png',overlay)
    (out/'g03b_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return report
