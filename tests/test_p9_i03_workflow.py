"""P9-I03: synthetic form, dependency and guarded execution regression tests."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aiforensics.workflow_planner import (
    FORM_CATALOG, WorkflowError, ModuleForm, build_execution_plan,
    execute_plan, field_path_label, list_form_fields, load_form_data,
    load_synthetic_example, save_form_data, structural_checks,
    update_form_field,
)
from aiforensics.desktop_core import COMMANDS


def _manifest(mid,tmp_path):
    if mid=='P8-E02' or mid=='P8-E03':
        # P8 test input is a harmless structural example. Real E01/E02 will
        # independently assess all assumptions and data lineage.
        a={'schema_version':'p8.e01.v1','dataset_scope':'real_unverified',
           'records':[{'module_id':'P1-G01','observation_id':'test'}],
           'fusion':{'plan_pre_registered':False}}
        path=tmp_path/(mid+'.json');path.write_text(json.dumps(a),encoding='utf-8')
        return path,a
    return load_synthetic_example(mid,destination=tmp_path/mid)


def test_registry_matches_real_cli_allowlist():
    assert len(FORM_CATALOG)==27
    assert set(FORM_CATALOG)==set(COMMANDS)
    assert sum(s.input_kind=='image' for s in FORM_CATALOG.values())==1
    assert FORM_CATALOG['P5-D01'].command=='analyze-depth-contact'
    assert FORM_CATALOG['P8-E03'].command=='explain-evidence'


@pytest.mark.parametrize('mid', [m for m in FORM_CATALOG if m!='P1-G01'])
def test_every_json_module_has_structural_template(mid,tmp_path):
    path,data=_manifest(mid,tmp_path)
    assert not structural_checks(mid,data)
    assert load_form_data(mid,path)==data


def test_annotated_camera_not_invented(tmp_path):
    path,doc=_manifest('P5-D01',tmp_path)
    del doc['camera']
    assert any('camera' in x for x in structural_checks('P5-D01',doc))
    with pytest.raises(WorkflowError):save_form_data('P5-D01',doc,tmp_path/'bad.json')


def test_render_scalar_and_container_field_paths(tmp_path):
    _,data=_manifest('P6-M01',tmp_path)
    fields=list_form_fields(data)
    assert any(row['kind']=='array' for row in fields)
    assert any(row['kind']=='object' or row['kind']=='boolean' or row['kind']=='number' for row in fields)
    assert field_path_label(('samples',0,'name'))=='samples.[0].name'


def test_typed_field_roundtrip_and_transaction():
    original={'nested':{'gain':2.3,'enabled':True,'name':'sample'},'list':[1,2]}
    out=update_form_field(original,('nested','gain'),'2.75')
    assert out['nested']['gain']==2.75
    assert original['nested']['gain']==2.3
    assert update_form_field(out,('nested','enabled'),'false')['nested']['enabled'] is False
    assert update_form_field(out,('nested','name'),'ışık') ['nested']['name']=='ışık'
    assert update_form_field(out,('list',1),'5')['list']==[1,5]
    assert update_form_field(out,('list',),'[5, 6]')['list']==[5,6]


@pytest.mark.parametrize('value',["true",'"5"','[]','null'])
def test_type_mismatch_blocks(value):
    with pytest.raises(WorkflowError):update_form_field({'x':7},('x',),value)


def test_invalid_json_is_blocked():
    with pytest.raises(WorkflowError):update_form_field({'x':[1,2]},('x',),'[1, NaN]')


def test_bad_path_blocked():
    with pytest.raises(WorkflowError):update_form_field({'x':1},('nonexistent',),'2')


def test_document_save_validate_and_utf8(tmp_path):
    data={'schema_version':'p8.e01.v1','records':[{'module_id':'P1-G01','note':'gölge'}]}
    out=save_form_data('P8-E01',data,tmp_path/'test.json')
    assert out.is_file() and 'gölge' in out.read_text(encoding='utf-8')
    assert load_form_data('P8-E01',out)==data


def test_reject_nonfinite_json(tmp_path):
    p=tmp_path/'malformed.json';p.write_text('{"a":NaN}',encoding='utf-8')
    with pytest.raises(WorkflowError):load_form_data('P6-M01',p)


def test_structural_preflight_blocks_missing_nested_calibration(tmp_path):
    p=tmp_path/'bad.json';p.write_text('{}')
    plan=build_execution_plan(['P5-D02'],{'P5-D02':str(p)})
    assert plan['blocked_count']==1
    assert 'camera' in str(plan['steps'][0]['reasons'])


def test_no_implicit_manifest_transfer_between_modules(tmp_path):
    a=tmp_path/'frame.jpg';a.write_bytes(b'not a valid image but extension and hash fine')
    plan=build_execution_plan(['P1-G01','P5-D01'],{'P1-G01':str(a)})
    assert plan['ready_count']==1
    assert plan['blocked_count']==1
    assert plan['steps'][1]['input_path'] is None
    assert plan['automatic_upstream_data_reuse'] is False


def test_selected_dependency_order_is_deterministic(tmp_path):
    source=tmp_path/'e.json';source.write_text('{"schema_version":"p8.e01.v1","records":[{}],"fusion":{}}')
    p=build_execution_plan(['P8-E03','P8-E01','P8-E02'],
         {m:str(source) for m in ['P8-E03','P8-E01','P8-E02']})
    assert [x['module_id'] for x in p['steps']]==['P8-E01','P8-E02','P8-E03']
    assert all(x['state']=='READY' for x in p['steps'])


def test_independent_physics_modules_do_not_force_g01(tmp_path):
    path,_=_manifest('P5-D01',tmp_path)
    plan=build_execution_plan(['P5-D01'],{'P5-D01':str(path)})
    assert plan['ready_count']==1
    assert plan['steps'][0]['previous_selected']==[]


def test_custom_cycle_is_rejected():
    with pytest.raises(WorkflowError):build_execution_plan(['P8-E01','P8-E02'],{},
      preferred={'P8-E01':('P8-E02',),'P8-E02':('P8-E01',)})


def test_duplicate_and_unknown_mod_rejected():
    with pytest.raises(WorkflowError):build_execution_plan(['P1-G01','P1-G01'],{})
    with pytest.raises(WorkflowError):build_execution_plan(['P0-XXX'],{})


class FakeProject:
    def __init__(self):self.called=[]
    def run(self,mid,path):
        self.called.append(mid)
        return {'state':'SUCCEEDED','run_id':'0001_'+mid},Path('/tmp/results')


def test_execute_plan_keeps_cli_order(tmp_path):
    a=tmp_path/'a.png';a.write_bytes(b'pixels')
    manifest, _=_manifest('P5-D01',tmp_path)
    plan=build_execution_plan(['P5-D01','P1-G01'],{'P1-G01':str(a),'P5-D01':str(manifest)})
    project=FakeProject()
    result=execute_plan(project,plan)
    assert project.called==['P5-D01','P1-G01']
    assert len(result['events'])==2
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_modified_file_sha_protected(tmp_path):
    a=tmp_path/'a.png';a.write_bytes(b'first')
    plan=build_execution_plan(['P1-G01'],{'P1-G01':str(a)})
    a.write_bytes(b'CHANGED')
    project=FakeProject();result=execute_plan(project,plan)
    assert result['events'][0]['state']=='INPUT_CHANGED'
    assert project.called==[]


def test_ready_after_failed_dependency_is_blocked(tmp_path):
    p,_=_manifest('P8-E02',tmp_path)
    p1,_=_manifest('P8-E01',tmp_path)
    plan=build_execution_plan(['P8-E02','P8-E01'],{'P8-E01':str(p1),'P8-E02':str(p)})
    class BadProject:
        def __init__(self):self.called=[]
        def run(self,mid,path):
            self.called.append(mid)
            return {'state':'FAILED','run_id':'1'},Path('/tmp')
    pr=BadProject();out=execute_plan(pr,plan,halt_on_failure=False)
    assert pr.called==['P8-E01']
    assert out['events'][1]['state']=='BLOCKED_DEPENDENCY'


def test_stop_before_start():
    plan=build_execution_plan(['P1-G01'],{})
    out=execute_plan(FakeProject(),plan,stop_requested=lambda:True)
    assert out['events'][0]['state']=='CANCELLED_BEFORE_START'


def test_p7_sensor_npz_missing_rejected(tmp_path):
    path,data=_manifest('P7-S02',tmp_path)
    assert build_execution_plan(['P7-S02'],{'P7-S02':str(path)})['ready_count']==1
    (path.parent/'reference.npz').unlink()
    p=build_execution_plan(['P7-S02'],{'P7-S02':str(path)})
    assert p['blocked_count']==1


def test_synthetic_example_never_overwritten(tmp_path):
    path,_=_manifest('P5-D02',tmp_path)
    with pytest.raises(WorkflowError):load_synthetic_example('P5-D02',destination=tmp_path/'P5-D02')


def test_plan_state_never_ai_verdict(tmp_path):
    path,doc=_manifest('P6-M02',tmp_path)
    result=build_execution_plan(['P6-M02'],{'P6-M02':str(path)})
    assert result['scientific_validation']=='NOT_PERFORMED'
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'
