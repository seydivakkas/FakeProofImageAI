"""P9-I02 synthetic/editor-contract tests. Never equivalent to camera validation."""
import copy
import json
import math
from pathlib import Path
import pytest

from aiforensics.annotation_model import (
    AnnotationDocument, AnnotationError, Viewport, SCHEMA)
from aiforensics.annotation_editor import hit_test

H='ab'*32


def doc():return AnnotationDocument(320,240,H)


def test_native_pixel_roundtrip(tmp_path):
    d=doc()
    d.add('line',[(10,20),(100,50)],family='X')
    saved=d.save(tmp_path/'marks.json')
    loaded=AnnotationDocument.load(saved,image_sha256=H,image_size_wh=(320,240))
    assert loaded.to_dict()==d.to_dict()
    assert loaded.to_dict()['source_type']=='user_annotation_unverified'
    assert loaded.to_dict()['metric_scale_verified'] is False


def test_undo_and_redo():
    d=doc();mark=d.add('point',[(30,40)])
    d.replace(mark,points=[(60,70)])
    assert d.undo() and d.marks[0]['points']==[[30.,40.]]
    assert d.redo() and d.marks[0]['points']==[[60.,70.]]
    assert d.delete(mark)
    assert d.undo()


def test_one_drag_one_undo():
    d=doc();k=d.add('line',[(5,10),(100,10)])
    before=copy.deepcopy(d.marks)
    for x in range(9,20):d.replace(k,points=[[x,10],[100,10]],record_history=False)
    d.checkpoint(before)
    assert d.undo() and d.marks[0]['points'][0]==[5,10]


def test_polyline_measurement():
    d=doc();k=d.add('polyline',[[0,0],[3,4],[3,8]])
    assert d.inspect(k)['length_px']==pytest.approx(9)
    assert d.inspect(k)['physical_unit_available'] is False


def test_rect_area_and_perimeter():
    d=doc();k=d.add('rectangle',[[9,7],[2,3]])
    assert d.inspect(k)['area_px2']==28
    assert d.inspect(k)['length_px']==22


def test_polygon_area():
    d=doc();k=d.add('polygon',[[0,0],[4,0],[4,3],[0,3]])
    assert d.inspect(k)['area_px2']==12


def test_polygon_crossing_rejected():
    with pytest.raises(AnnotationError):doc().add('polygon',[[1,1],[9,9],[1,9],[9,1]])


@pytest.mark.parametrize('kind,points',[
    ('point',[[500,1]]),('line',[[1,1],[1,1]]),('polygon',[[1,1],[2,2],[3,3]]),
    ('line',[[1,1]]),('polyline',[[1,1],[1,1]]),('point',[[math.nan,1]]),
    ('rectangle',[[0,0],[300,500]]),('polygon',[[3,1],[1,1]]),
])
def test_invalid_geometry_rejected(kind,points):
    with pytest.raises(AnnotationError):doc().add(kind,points)


def test_family_only_lines():
    with pytest.raises(AnnotationError):doc().add('point',[[1,1]],family='X')
    with pytest.raises(AnnotationError):doc().add('line',[[1,1],[5,5]],family='W')


def test_g02_draft_three_groups():
    d=doc()
    for fam,i in zip('XYZ',range(3)):
        d.add('line',[[0,30+i*35],[260,50+i*35]],family=fam)
        d.add('line',[[5,40+i*35],[240,60+i*35]],family=fam)
    m=d.g02_draft()
    assert m['image_shape_hw']==[240,320]
    assert len(m['orthogonal_groups'])==3
    assert all(len(g)==2 and len(g[0])==4 for g in m['orthogonal_groups'])
    assert m['provenance_status']=='USER_LABELED_NOT_INDEPENDENTLY_VERIFIED'


def test_g02_requires_three_families():
    d=doc();d.add('line',[[2,2],[20,20]],family='X')
    with pytest.raises(AnnotationError):d.g02_draft()


def test_replace_failure_is_atomic():
    d=doc();i=d.add('point',[(1,1)])
    with pytest.raises(AnnotationError):d.replace(i,points=[(-10,10)])
    assert d.marks[0]['points']==[[1.,1.]]


def test_hash_lock_prevents_wrong_image(tmp_path):
    saved=doc().save(tmp_path/'annotations.json')
    with pytest.raises(AnnotationError):AnnotationDocument.load(saved,image_sha256='cd'*32)
    with pytest.raises(AnnotationError):AnnotationDocument.load(saved,image_size_wh=[640,480])


def test_forged_validation_flag_rejected():
    item=doc().to_dict();item['metric_scale_verified']=True
    with pytest.raises(AnnotationError):AnnotationDocument.from_dict(item)


def test_duplicate_ids_rejected():
    d=doc();d.add('point',[[5,5]])
    data=d.to_dict();data['marks'].append(copy.deepcopy(data['marks'][0]))
    with pytest.raises(AnnotationError):AnnotationDocument.from_dict(data)


def test_zoom_center_is_stationary():
    v=Viewport(.75,20,30);pixel=[10.5,22.75]
    screen=v.to_canvas(pixel)
    v.zoom_at(1.3,screen)
    assert v.to_canvas(pixel)==pytest.approx(screen)
    assert v.from_canvas(screen)==pytest.approx(pixel)


def test_pan_inverse():
    v=Viewport(1.2,10,20);v.pan(-24,36)
    p=[40.5,88.]
    assert v.from_canvas(v.to_canvas(p))==pytest.approx(p)


def test_invalid_zoom():
    v=Viewport()
    with pytest.raises(AnnotationError):v.zoom_at(0,(10,20))


def test_hit_test_endpoints_and_segment():
    d=doc();i=d.add('line',[[10,10],[200,10]])
    assert hit_test(d.marks,(10,10),2)==(i,0)
    assert hit_test(d.marks,(60,12),3)==(i,None)
    assert hit_test(d.marks,(60,30),3)==(None,None)


def test_hit_test_polygon_edges():
    d=doc();i=d.add('polygon',[[10,10],[90,10],[90,90],[10,90]])
    assert hit_test(d.marks,(10,50),3)==(i,None)


def test_json_is_strict(tmp_path):
    d=doc().to_dict();d['unexpected']='noise'
    with pytest.raises(AnnotationError):AnnotationDocument.from_dict(d)


def test_pixel_coords_not_scaled_on_save(tmp_path):
    d=doc();k=d.add('point',[(123.5,75.25)])
    v=Viewport(2.5,20,30)
    _=v.to_canvas(d.marks[0]['points'][0])
    saved=d.save(tmp_path/'d.json')
    assert json.loads(saved.read_text())['marks'][0]['points']==[[123.5,75.25]]


def test_label_is_preserved():
    d=doc();k=d.add('point',[[12,34]],label='Temas A')
    assert d.marks[0]['label']=='Temas A'
    d.replace(k,label='Temas B')
    assert d.marks[0]['label']=='Temas B'