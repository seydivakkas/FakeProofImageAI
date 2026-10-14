"""P9-I02: native-pixel annotation geometry and locally auditable persistence.

Interactive points are user-provided observations, not verified calibration,
world-space distance, image provenance, or an AI-origin verdict.
"""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import tempfile

SCHEMA = 'fakeproof.annotations.v1'
KINDS = frozenset({'point', 'line', 'polyline', 'polygon', 'rectangle'})
FAMILIES = frozenset({'X', 'Y', 'Z'})
MAX_MARKS = 20000
MAX_VERTICES = 10000
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024

class AnnotationError(ValueError):
    pass


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _xy(point, width, height):
    if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(map(_finite, point)):
        raise AnnotationError('Noktalar sonlu (x,y) sayıları olmalıdır')
    x, y = map(float, point)
    if not 0 <= x < width or not 0 <= y < height:
        raise AnnotationError('Nokta özgün görüntü koordinatlarının dışında')
    return [x, y]


def _segment_length(a, b):
    return math.hypot(b[0]-a[0], b[1]-a[1])


def _validate_mark(mark, width, height):
    if not isinstance(mark, dict):
        raise AnnotationError('İşaretleme nesne olmalıdır')
    if set(mark) != {'id', 'kind', 'points', 'family', 'label'}:
        raise AnnotationError('İşaretleme alanları eksik veya fazla')
    if not isinstance(mark['id'], int) or isinstance(mark['id'], bool) or mark['id'] < 1:
        raise AnnotationError('Geçersiz işaretleme ID')
    kind = mark['kind']
    if kind not in KINDS:
        raise AnnotationError('Bilinmeyen çizim türü')
    pts = mark['points']
    if not isinstance(pts, list) or not pts or len(pts) > MAX_VERTICES:
        raise AnnotationError('Geçersiz nokta listesi')
    lengths = {'point':(1,1), 'line':(2,2), 'polyline':(2,MAX_VERTICES),
               'polygon':(3,MAX_VERTICES), 'rectangle':(2,2)}
    lower, upper = lengths[kind]
    if not lower <= len(pts) <= upper:
        raise AnnotationError('Çizim türüne göre yanlış nokta sayısı')
    points = [_xy(p,width,height) for p in pts]
    if kind in ('line','rectangle') and _segment_length(*points) < 1e-9:
        raise AnnotationError('Sıfır boyutlu çizim')
    if kind in ('polyline','polygon') and any(_segment_length(a,b) < 1e-9
                         for a,b in zip(points,points[1:])):
        raise AnnotationError('Yinelenen komşu köşeler')
    if kind == 'polygon':
        if abs(polygon_signed_area(points)) < 1e-9:
            raise AnnotationError('Sıfır alanlı çokgen')
        if _has_intersections(points):
            raise AnnotationError('Öz-kesişimli çokgen desteklenmez')
    family = mark['family']
    if family is not None and (kind != 'line' or family not in FAMILIES):
        raise AnnotationError('X/Y/Z yalnız doğrusal ve elle etiketli çizgiler için')
    if not isinstance(mark['label'], str) or len(mark['label']) > 256:
        raise AnnotationError('Geçersiz etiket')
    return dict(id=mark['id'],kind=kind,points=points,family=family,label=mark['label'])


def polygon_signed_area(points):
    return .5 * sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))


def _has_intersections(points):
    def orient(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def onsegment(a,b,c):
        return (min(a[0],b[0])<=c[0]<=max(a[0],b[0]) and
                min(a[1],b[1])<=c[1]<=max(a[1],b[1]))
    def overlap(a,b,c,d):
        o1,o2,o3,o4=(orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b))
        if (o1*o2<0 and o3*o4<0): return True
        return any(abs(o)<1e-12 and onsegment(*x) for o,x in (
            (o1,(a,b,c)),(o2,(a,b,d)),(o3,(c,d,a)),(o4,(c,d,b))))
    edges=list(zip(points,points[1:]+points[:1]))
    n=len(edges)
    return any(overlap(*edges[i],*edges[j]) for i in range(n)
               for j in range(i+1,n) if abs(i-j)>1 and {i,j}!={0,n-1})


class AnnotationDocument:
    def __init__(self, width, height, image_sha256, marks=None):
        if type(width) is not int or type(height) is not int or not (1<=width<=200000 and 1<=height<=200000):
            raise AnnotationError('Pozitif görüntü boyutu (piksel) gerekli')
        if not isinstance(image_sha256,str) or len(image_sha256)!=64 or any(c not in '0123456789abcdef' for c in image_sha256):
            raise AnnotationError('SHA-256 küçük harfli hexadecimal olmalı')
        self.width,self.height,self.image_sha256=width,height,image_sha256
        self.marks=[]
        self._history=[]
        self._redo=[]
        if marks:
            self._assign(marks)

    def _assign(self,marks):
        if not isinstance(marks,list) or len(marks)>MAX_MARKS:
            raise AnnotationError('Çok fazla işaretleme')
        validated=[_validate_mark(m,self.width,self.height) for m in marks]
        ids=[m['id'] for m in validated]
        if len(ids)!=len(set(ids)):
            raise AnnotationError('Yinelenen ID')
        self.marks=validated

    def _commit(self):
        self._history.append(copy.deepcopy(self.marks))
        if len(self._history)>100:
            self._history.pop(0)
        self._redo.clear()

    def add(self,kind,points,*,family=None,label=''):
        self._commit()
        mark=dict(id=max((m['id'] for m in self.marks),default=0)+1,
                  kind=kind,points=[list(x) for x in points],family=family,label=label)
        try:
            self._assign(self.marks+[mark])
        except Exception:
            self.marks=self._history.pop()
            raise
        return mark['id']

    def replace(self, mark_id, *, points=None, family=Ellipsis, label=None, record_history=True):
        mark=next((m for m in self.marks if m['id']==mark_id),None)
        if mark is None: raise AnnotationError('Seçim bulunamadı')
        replacement=copy.deepcopy(mark)
        if points is not None: replacement['points']=[list(x) for x in points]
        if family is not Ellipsis: replacement['family']=family
        if label is not None: replacement['label']=label
        new=[replacement if m['id']==mark_id else m for m in self.marks]
        validated=[_validate_mark(m,self.width,self.height) for m in new]
        if record_history:self._commit()
        self.marks=validated

    def checkpoint(self, previous_marks):
        """Commit a completed interactive drag as ONE undo step."""
        if previous_marks != self.marks:
            self._history.append(copy.deepcopy(previous_marks))
            if len(self._history)>100:self._history.pop(0)
            self._redo.clear()

    def delete(self,mark_id):
        if not any(m['id']==mark_id for m in self.marks):return False
        self._commit()
        self.marks=[m for m in self.marks if m['id']!=mark_id]
        return True

    def undo(self):
        if not self._history:return False
        self._redo.append(copy.deepcopy(self.marks))
        self.marks=self._history.pop()
        return True

    def redo(self):
        if not self._redo:return False
        self._history.append(copy.deepcopy(self.marks))
        self.marks=self._redo.pop()
        return True

    def to_dict(self):
        return {'schema_version':SCHEMA,'coordinate_space':'original_image_pixels',
                'image_sha256':self.image_sha256,
                'image_size_wh':[self.width,self.height],
                'marks':copy.deepcopy(self.marks),
                'source_type':'user_annotation_unverified',
                'metric_scale_verified':False,
                'decision':'NO_AI_ORIGIN_CONCLUSION'}

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict) or data.get('schema_version')!=SCHEMA or set(data)!={
            'schema_version','coordinate_space','image_sha256','image_size_wh',
            'marks','source_type','metric_scale_verified','decision'}:
            raise AnnotationError('Anotasyon şeması geçersiz')
        if (data['coordinate_space']!='original_image_pixels' or
                data['source_type']!='user_annotation_unverified' or
                data['metric_scale_verified'] is not False or
                data['decision']!='NO_AI_ORIGIN_CONCLUSION'):
            raise AnnotationError('Doğrulama durumları değiştirilemez')
        wh=data['image_size_wh']
        if not isinstance(wh,list) or len(wh)!=2:
            raise AnnotationError('Görüntü boyutları eksik')
        return cls(*wh,data['image_sha256'],data['marks'])

    def save(self,path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.annotations-',suffix='.tmp',dir=path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump(self.to_dict(),f,indent=2,ensure_ascii=False,allow_nan=False)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return path

    @classmethod
    def load(cls,path,*,image_sha256=None,image_size_wh=None):
        path=Path(path)
        if path.stat().st_size>MAX_DOCUMENT_BYTES:raise AnnotationError('Anotasyon dosyası çok büyük')
        doc=cls.from_dict(json.loads(path.read_text(encoding='utf-8')))
        if image_sha256 is not None and doc.image_sha256!=image_sha256:
            raise AnnotationError('Görüntü SHA-256 eşleşmiyor')
        if image_size_wh is not None and (doc.width,doc.height)!=tuple(image_size_wh):
            raise AnnotationError('Görüntü boyutları eşleşmiyor')
        return doc

    def inspect(self,mark_id):
        mark=next((m for m in self.marks if m['id']==mark_id),None)
        if mark is None:raise AnnotationError('İşaretleme bulunamadı')
        pts=mark['points']
        length=sum(_segment_length(a,b) for a,b in zip(pts,pts[1:]))
        if mark['kind']=='rectangle':
            length=2*(abs(pts[1][0]-pts[0][0])+abs(pts[1][1]-pts[0][1]))
        area=(abs(polygon_signed_area(pts)) if mark['kind']=='polygon' else
              abs((pts[1][0]-pts[0][0])*(pts[1][1]-pts[0][1]))
              if mark['kind']=='rectangle' else None)
        return {'id':mark_id,'kind':mark['kind'],'length_px':length,
                'area_px2':area,'physical_unit_available':False,
                'measurement_status':'PIXEL_ONLY_NOT_METRIC'}

    def g02_draft(self):
        """Safe G02-shaped draft; labels do not independently prove orthogonality."""
        groups={k:[] for k in ('X','Y','Z')}
        for mark in self.marks:
            if mark['kind']=='line' and mark['family'] in groups:
                a,b=mark['points']
                groups[mark['family']].append([*a,*b])
        if any(len(v)<2 for v in groups.values()):
            raise AnnotationError('G02 taslağı için X/Y/Z ailelerinde en az ikişer çizgi gerekli')
        return {'image_shape_hw':[self.height,self.width],
                'orthogonal_groups':[groups[k] for k in ('X','Y','Z')],
                'annotation_source_sha256':self.image_sha256,
                'provenance_status':'USER_LABELED_NOT_INDEPENDENTLY_VERIFIED',
                'warning':'X/Y/Z atanması ortogonal gerçek dünya doğrultularını kanıtlamaz. '
                          'Bu taslak bağımsız kalibrasyon ölçümü ve doğrulamasının yerine geçmez.'}


class Viewport:
    """Invertible native-pixel -> canvas-pixel affine mapping."""
    def __init__(self,scale=1.,offset_x=0.,offset_y=0.):
        self.scale=float(scale)
        self.offset_x=float(offset_x)
        self.offset_y=float(offset_y)
        if not .01<=self.scale<=32:raise AnnotationError('Geçersiz zoom')

    def to_canvas(self,p):
        return (p[0]*self.scale+self.offset_x,p[1]*self.scale+self.offset_y)

    def from_canvas(self,p):
        return ((p[0]-self.offset_x)/self.scale,(p[1]-self.offset_y)/self.scale)

    def zoom_at(self,factor,canvas_xy):
        if not _finite(factor) or factor<=0:raise AnnotationError('Geçersiz zoom çarpanı')
        prev=self.from_canvas(canvas_xy)
        self.scale=min(8.,max(.025,self.scale*factor))
        self.offset_x=canvas_xy[0]-prev[0]*self.scale
        self.offset_y=canvas_xy[1]-prev[1]*self.scale

    def pan(self,dx,dy):
        if not _finite(dx) or not _finite(dy):raise AnnotationError('Kaydırma sonlu olmalı')
        self.offset_x+=dx;self.offset_y+=dy