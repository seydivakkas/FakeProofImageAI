"""P9-I04 synthetic review, provenance and manifest/security regression tests."""
import copy
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from aiforensics.annotation_model import AnnotationDocument
from aiforensics.review_workspace import (
    ReviewError, _within, annotation_layers, bind_finding_to_image,
    dependency_graph, image_overlays, linked_images, list_images,
    read_bindings, read_report, register_overlay, report_catalog,
)


@pytest.fixture
def env(tmp_path):
    from PIL import Image
    root = tmp_path / 'project'
    (root/'images').mkdir(parents=True)
    (root/'runs'/'0001_P8_E03').mkdir(parents=True)
    path = root/'images'/'original.png'
    Image.new('RGB', (120,80), (10,20,30)).save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source_zip = Path('/mnt/data/FakeProofImageAI_P8_E03_Demo_Reports_v0.28.0.zip')
    # The fixture also works after export outside the agent container.
    if source_zip.is_file():
        with zipfile.ZipFile(source_zip) as z:
            report=json.loads(z.read('outputs/p8_e03/p8_e03_explainable_report.json'))
    else:
        report={
            'schema_version':'p8.e03.v1', 'decision':'NO_AI_ORIGIN_CONCLUSION',
            'findings':[{'record_id':'P1-G01/a','module_id':'P1-G01',
                         'single_test':{'state':'INDETERMINATE'},
                         'dependency':{'component_id':'dependency_001'}}],
            'dependency_groups':[{'component_id':'dependency_001',
                                  'members':['P1-G01/a'], 'explicit_edges':[],
                                  'shared_evidence':{'shared_references':[]}}]
        }
    (root/'runs'/'0001_P8_E03'/'p8_e03_explainable_report.json').write_text(
        json.dumps(report,ensure_ascii=False),encoding='utf-8')
    class Project:
        def __init__(self):
            self.root = root
            self.data={'images':[{'name':'original.png','file':'original.png','sha256':digest}],
                       'runs':[{'run_id':'0001_P8_E03'}]}
    return Project(), digest, path, report


def test_images_inventory(env):
    p,d,_,_=env
    assert list_images(p)[0]['sha256']==d
    assert list_images(p)[0]['camera_origin_verified'] is False


def test_image_integrity_fails_closed(env):
    p,d,path,_=env
    path.write_bytes(b'broken')
    with pytest.raises(ReviewError,match='SHA-256'):
        annotation_layers(p,d)


def test_annotation_matches_only_exact_hash(env):
    p,d,_,_=env
    (p.root/'annotations').mkdir()
    doc=AnnotationDocument(120,80,d)
    doc.add('line',[(1,1),(50,50)],family='X')
    doc.save(p.root/'annotations'/'a.json')
    layers=annotation_layers(p,d)
    assert layers[0]['count']==1
    assert layers[0]['marks'][0]['family']=='X'


def test_foreign_annotation_omitted(env):
    p,d,_,_=env
    (p.root/'annotations').mkdir()
    AnnotationDocument(120,80,'0'*64).save(p.root/'annotations'/'foreign.json')
    assert annotation_layers(p,d)==[]


def test_report_catalog_loads_real_only(env):
    p,_,_,r=env
    assert len(report_catalog(p))==1
    assert read_report(p,report_catalog(p)[0]['id'])['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_report_rejects_bad_origin_claim(env):
    p,_,_,r=env
    (p.root/'runs'/'0001_P8_E03'/'p8_e03_explainable_report.json').write_text(
        json.dumps(dict(r,decision='AI_GENERATED')))
    assert report_catalog(p)==[]


def test_report_rejects_bad_schema(env):
    p,_,_,r=env
    (p.root/'runs'/'0001_P8_E03'/'p8_e03_explainable_report.json').write_text(
        json.dumps(dict(r,schema_version='fake')))
    assert report_catalog(p)==[]


def test_explicit_binding_is_unverified_and_idempotent(env):
    p,d,_,r=env
    rid=report_catalog(p)[0]['id']; record=r['findings'][0]['record_id']
    item=bind_finding_to_image(p,rid,record,d)
    assert item['link_type']=='user_asserted_not_verified'
    bind_finding_to_image(p,rid,record,d)
    assert len(read_bindings(p))==1
    assert linked_images(p,rid,record)[0]['provenance']=='user_asserted_not_verified'


def test_binding_unknown_record_fails(env):
    p,d,_,r=env
    with pytest.raises(ReviewError):
        bind_finding_to_image(p,report_catalog(p)[0]['id'],'nonexistent',d)
    assert not (p.root/'review_links.json').exists()


def test_binding_unknown_image_fails(env):
    p,d,_,r=env
    with pytest.raises(ReviewError):
        bind_finding_to_image(p,report_catalog(p)[0]['id'],r['findings'][0]['record_id'],'f'*64)


def test_stale_binding_disappears(env):
    p,d,path,r=env
    rid=report_catalog(p)[0]['id'];record=r['findings'][0]['record_id']
    bind_finding_to_image(p,rid,record,d)
    path.write_bytes(b'broken')
    assert linked_images(p,rid,record)==[]


def test_link_contract_tampered_rejected(env):
    p,_,_,_=env
    (p.root/'review_links.json').write_text('{"schema_version":"bad","links":[]}')
    with pytest.raises(ReviewError):read_bindings(p)


def test_dependency_graph_has_no_invented_edges(env):
    _,_,_,report=env
    output=dependency_graph(report)
    assert len(output['nodes'])==len(report['findings'])
    assert all(x['kind'] in ('explicit_declared','shared_lineage') for x in output['edges'])
    assert output['note']


def test_dependency_rejects_unknown_member(env):
    _,_,_,report=env
    report=copy.deepcopy(report)
    report['dependency_groups'][0]['members'].append('not-in-report')
    with pytest.raises(ReviewError):dependency_graph(report)


def test_no_path_traversal(tmp_path):
    p=tmp_path/'root';p.mkdir()
    with pytest.raises(ReviewError):_within(p,p/'../outside')


def test_png_overlay_geometry_and_hash(env,tmp_path):
    from PIL import Image
    p,d,_,_=env
    overlay=tmp_path/'overlay.png'
    Image.new('RGBA',(120,80),(255,0,0,100)).save(overlay)
    reg=register_overlay(p,d,overlay)
    assert reg['verification']=='user_asserted_unverified'
    assert image_overlays(p,d)[0]['digest']==reg['file_sha256']
    register_overlay(p,d,overlay)
    assert len(image_overlays(p,d))==1


def test_png_overlay_wrong_dimensions_fail(env,tmp_path):
    from PIL import Image
    p,d,_,_=env
    overlay=tmp_path/'overlay.png'
    Image.new('RGBA',(20,20)).save(overlay)
    with pytest.raises(ReviewError):register_overlay(p,d,overlay)


def test_png_overlay_mutation_hidden(env,tmp_path):
    from PIL import Image
    p,d,_,_=env
    overlay=tmp_path/'overlay.png'
    Image.new('RGBA',(120,80)).save(overlay)
    reg=register_overlay(p,d,overlay)
    (p.root/'review_overlays'/reg['file']).write_bytes(b'corrupt')
    assert image_overlays(p,d)==[]


def test_cli_free_ui_import():
    from aiforensics.review_ui import ReviewWindow
    assert hasattr(ReviewWindow,'_draw_graph')
    assert hasattr(ReviewWindow,'_show_finding')
