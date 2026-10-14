"""P9-I05 regression: no false calibration or AI-origin verdicts."""
from types import SimpleNamespace
import pytest
from aiforensics.journey_core import available_projects, journey_snapshot
from aiforensics.annotation_model import AnnotationDocument
from aiforensics.journey_ui import stage_caption

def project(tmp_path):
    root=tmp_path/'Demo';(root/'manifests').mkdir(parents=True)
    return SimpleNamespace(name='Demo',root=root,
        data={'images':[],'runs':[],'calibration':None})

def test_empty_workspaces(tmp_path):
    assert available_projects(tmp_path/'none')==[]
    snap=journey_snapshot(project(tmp_path))
    assert snap['recommended_step']=='image'
    assert snap['decision']=='NO_AI_ORIGIN_CONCLUSION'

def test_project_listing_filters_names(tmp_path):
    for name in ('Bravo','Alfa','..invalid'):
        path=tmp_path/name;path.mkdir();(path/'project.json').write_text('{}')
    assert available_projects(tmp_path)==['Alfa','Bravo']

def test_image_not_automatic_calibration(tmp_path):
    p=project(tmp_path);p.data['images']=[{'sha256':'a'*64}]
    steps=journey_snapshot(p)['steps']
    assert steps[0].state=='RECORDED'
    assert steps[1].state=='ACTION_REQUIRED'
    assert steps[2].state=='ACTION_REQUIRED'

def test_annotation_draft_only(tmp_path):
    p=project(tmp_path);digest='a'*64
    p.data['images']=[{'sha256':digest}]
    doc=AnnotationDocument(20,20,digest)
    doc.add('point',[(2,3)])
    doc.save(p.root/'manifests'/('annotations_'+digest+'.json'))
    snap=journey_snapshot(p)
    assert snap['annotation_draft_count']==1
    assert snap['steps'][1].state=='DRAFT'
    assert 'bağımsız doğrulama yok' in snap['steps'][1].detail

def test_wrong_digest_annotation_ignored(tmp_path):
    p=project(tmp_path);digest='a'*64
    p.data['images']=[{'sha256':digest}]
    doc=AnnotationDocument(20,20,'b'*64);doc.add('point',[(2,3)])
    doc.save(p.root/'manifests'/('annotations_'+digest+'.json'))
    assert journey_snapshot(p)['annotation_draft_count']==0

def test_failure_not_success(tmp_path):
    p=project(tmp_path)
    p.data['runs']=[{'module_id':'P1-G01','state':'FAILED'}]
    snap=journey_snapshot(p)
    assert snap['steps'][2].state=='ATTEMPTED'
    assert snap['physics_success_count']==0
    assert snap['failed_run_count']==1

def test_evidence_and_report_are_not_authenticity(tmp_path):
    p=project(tmp_path);p.data['runs']=[
        {'module_id':'P1-G01','state':'SUCCEEDED'},
        {'module_id':'P8-E01','state':'SUCCEEDED'},
        {'module_id':'P8-E03','state':'FAILED'}]
    snap=journey_snapshot(p)
    assert snap['steps'][2].state=='RECORDED'
    assert snap['steps'][3].state=='RECORDED'
    assert snap['steps'][4].state=='READY_TO_SELECT'
    assert snap['decision']=='NO_AI_ORIGIN_CONCLUSION'

def test_neutral_stage_labels():
    from aiforensics.journey_core import JourneyStep
    assert stage_caption(JourneyStep('x','a','b','DRAFT',''))=='Taslak'
    assert stage_caption(JourneyStep('x','a','b','ATTEMPTED',''))=='Denendi'
    assert stage_caption(JourneyStep('x','a','b','UNKNOWN',''))=='İncelenecek'
