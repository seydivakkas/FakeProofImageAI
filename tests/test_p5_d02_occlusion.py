"""P5-D02 controlled multipane geometry and negative evidence regressions."""
import copy
import json
import numpy as np
import pytest

from aiforensics.depth_contact import PinholeCamera
from aiforensics.depth_contact_synthetic import synthetic_depth_contact_fixture
from aiforensics.depth_occlusion import (
    OcclusionGeometryError, OcclusionConfig, evaluate_occlusion, run_occlusion_manifest)
from aiforensics.depth_occlusion_synthetic import synthetic_occlusion_fixture, render_occlusion_overlay


@pytest.fixture
def fixture():
    return synthetic_occlusion_fixture()


def get(report, name):
    return next(r for r in report['observations'] if r['id'] == name)


def test_synthetic_expected(fixture):
    data, truth = fixture
    result = evaluate_occlusion(data)
    assert {r['id']:r['state'] for r in result['observations']} == truth
    assert result['counts'] == {'CONSISTENT':3,'INCONSISTENT_UNDER_ASSUMPTIONS':2,'INDETERMINATE':2}
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_occluder_in_front(fixture):
    data,_=fixture
    r=get(evaluate_occlusion(data),'far_claimed_visible')
    assert [x['surface_id'] for x in r['ray_intersections']] == ['near_panel','far_facade']
    assert r['ray_intersections'][0]['ray_depth_world'] < r['ray_intersections'][1]['ray_depth_world']
    assert r['predicted_front_opaque_surface_id']=='near_panel'


def test_non_overlap_preserves_far_visibility(fixture):
    data,_=fixture
    r=get(evaluate_occlusion(data),'far_unblocked')
    assert r['predicted_front_opaque_surface_id']=='far_facade'


def test_untrusted_mask_never_passes(fixture):
    data,_=fixture
    data['visibility_probes'][0]['visibility_provenance']='same_3d_renderer'
    r=get(evaluate_occlusion(data),'near_visible')
    assert r['state']=='INDETERMINATE'


def test_untrusted_surface_never_passes(fixture):
    data,_=fixture
    data['surfaces'][0]['geometry_provenance']='inferred_from_image'
    r=get(evaluate_occlusion(data),'near_visible')
    assert r['state']=='INDETERMINATE'


def test_missing_front_annotation_abstains(fixture):
    data,_=fixture
    data['visibility_probes'][0].pop('observed_front_surface_id')
    assert get(evaluate_occlusion(data),'near_visible')['state']=='INDETERMINATE'


def test_known_transparent_front_not_occluder(fixture):
    data,_=fixture
    data['surfaces'][0]['opaque']=False
    # Known transparent layer does not block an opaque far panel.
    assert get(evaluate_occlusion(data),'far_claimed_visible')['state']=='CONSISTENT'


def test_single_sided_backface_rejected(fixture):
    data,_=fixture
    data['surfaces'][0]['double_sided']=False
    # Normal +Y looks away from camera at y=-8, thus no front hit.
    assert get(evaluate_occlusion(data),'far_claimed_visible')['state']=='CONSISTENT'


def test_surface_order_tie_abstains(fixture):
    data,_=fixture
    data['surfaces'][1]['offset_world']=-2.01
    data['surfaces'][1]['polygon_world_xyz']=[[-2.3,2.01,0.],[2.3,2.01,0.],[2.3,2.01,3.6],[-2.3,2.01,3.6]]
    assert get(evaluate_occlusion(data),'near_visible')['state']=='INDETERMINATE'


def test_boundary_noise_abstention(fixture):
    data,_=fixture
    cam=PinholeCamera(data['camera'],data['image_shape_hw'])
    # At x=1.15 on far wall, projected near x=.958: within near edge.
    uv=cam.project([1.15,4.,1.5])
    data['visibility_probes']=[{'id':'edge','pixel_xy':uv.tolist(),'pixel_sigma_px':7,
             'observed_front_surface_id':'near_panel','visibility_provenance':'independent_annotation'}]
    data['metric_anchors']=[]
    r=evaluate_occlusion(data)['observations'][0]
    assert r['state']=='INDETERMINATE'
    assert r['stable_under_pixel_noise'] is False


def test_no_intersection_incomplete_scene_abstains(fixture):
    data,_=fixture
    cam=PinholeCamera(data['camera'],data['image_shape_hw'])
    uv=cam.project([3.5,4.,1.5])
    data['visibility_probes']=[{'id':'outside','pixel_xy':uv.tolist(),
             'observed_front_surface_id':'near_panel','visibility_provenance':'independent_annotation'}]
    data['metric_anchors']=[]
    assert evaluate_occlusion(data)['state']=='INDETERMINATE'


def test_complete_scene_missing_annotation_model_inconsistent(fixture):
    data,_=fixture
    cam=PinholeCamera(data['camera'],data['image_shape_hw'])
    uv=cam.project([3.5,4.,1.5])
    data['declared_scene_complete']=True
    data['visibility_probes']=[{'id':'outside','pixel_xy':uv.tolist(),
             'observed_front_surface_id':'near_panel','visibility_provenance':'independent_annotation'}]
    data['metric_anchors']=[]
    assert evaluate_occlusion(data)['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_visible_anchor_occluded(fixture):
    data,_=fixture
    r=get(evaluate_occlusion(data),'hidden_far_anchor')
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert 'opaque' in str(r['inconsistency_reasons'])


def test_3d_anchor_not_in_surface(fixture):
    data,_=fixture
    data['metric_anchors'][0]['independent_world_xyz'][1]+=0.20
    assert get(evaluate_occlusion(data),'visible_near_anchor')['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_3d_anchor_pixel_mismatch(fixture):
    data,_=fixture
    data['metric_anchors'][0]['pixel_xy'][0]+=22
    assert get(evaluate_occlusion(data),'visible_near_anchor')['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_anchor_uncertain_pixel(fixture):
    data,_=fixture
    data['metric_anchors'][0]['pixel_xy'][0]+=4
    data['metric_anchors'][0]['pixel_sigma_px']=2
    data['metric_anchors'][0].pop('claimed_visible')
    assert get(evaluate_occlusion(data),'visible_near_anchor')['state']=='INDETERMINATE'


def test_anchor_visibility_from_same_image_not_evidence(fixture):
    data,_=fixture
    data['metric_anchors'][0]['visibility_provenance']='inferred'
    assert get(evaluate_occlusion(data),'visible_near_anchor')['state']=='INDETERMINATE'


def test_no_claimed_visible_anchor_still_checks_metric_geometry(fixture):
    data,_=fixture
    data['metric_anchors'][0].pop('claimed_visible')
    assert get(evaluate_occlusion(data),'visible_near_anchor')['state']=='CONSISTENT'


def test_camera_distortion_integration(fixture):
    data,_=fixture
    data['camera']['distortion_coefficients_k1_k2_p1_p2_k3']=[-.04,.008,.0002,-.0003,0]
    cam=PinholeCamera(data['camera'],data['image_shape_hw'])
    data['visibility_probes'][0]['pixel_xy']=cam.project([.1,4.,1.4]).tolist()
    data['visibility_probes'][1]['pixel_xy']=cam.project([.1,4.,1.4]).tolist()
    data['visibility_probes'][2]['pixel_xy']=cam.project([1.6,4.,1.3]).tolist()
    data['visibility_probes']=data['visibility_probes'][:3]
    data['metric_anchors']=[]
    assert {r['id']:r['state'] for r in evaluate_occlusion(data)['observations']}=={
          'near_visible':'CONSISTENT','far_claimed_visible':'INCONSISTENT_UNDER_ASSUMPTIONS',
          'far_unblocked':'CONSISTENT'}


def test_d01_integration(fixture):
    data,_=fixture
    original,_=synthetic_depth_contact_fixture()
    data['gravity_world']=original['gravity_world']
    data['support_surfaces']=original['support_surfaces']
    data['d01_observations']=original['observations'][:1]
    result=evaluate_occlusion(data)
    assert result['p5_d01_integration']['counts']['CONSISTENT']==1
    assert result['counts']['CONSISTENT']==3


@pytest.mark.parametrize('field,value',[
   ('visibility_probes','bad'),('metric_anchors','bad'),('surfaces',[]),
])
def test_invalid_scene_shape(fixture,field,value):
    data,_=fixture
    data[field]=value
    with pytest.raises(OcclusionGeometryError):evaluate_occlusion(data)


@pytest.mark.parametrize('sigma',[-1,21,'bad',float('nan')])
def test_bad_uncertainty(fixture,sigma):
    data,_=fixture
    data['visibility_probes'][0]['pixel_sigma_px']=sigma
    with pytest.raises(OcclusionGeometryError):evaluate_occlusion(data)


def test_duplicate_ids(fixture):
    data,_=fixture
    data['metric_anchors'][0]['id']=data['visibility_probes'][0]['id']
    with pytest.raises(OcclusionGeometryError):evaluate_occlusion(data)


def test_invalid_convex_poly(fixture):
    data,_=fixture
    data['surfaces'][0]['polygon_world_xyz'][0][1]=1.4
    with pytest.raises(OcclusionGeometryError):evaluate_occlusion(data)


def test_missing_provenance_abstains(fixture):
    data,_=fixture
    data['surfaces'][0].pop('geometry_provenance')
    assert get(evaluate_occlusion(data),'near_visible')['state']=='INDETERMINATE'


def test_evaluation_deterministic(fixture):
    data,_=fixture
    assert evaluate_occlusion(data)==evaluate_occlusion(data)


def test_files_cli_overlay(fixture,tmp_path):
    data,truth=fixture
    path=tmp_path/'fixture.json'
    path.write_text(json.dumps(data),encoding='utf-8')
    report=run_occlusion_manifest(path,tmp_path/'out')
    assert report['input_sha256']
    assert (tmp_path/'out'/'p5_d02_report.json').exists()
    overlay=render_occlusion_overlay(data,report)
    assert overlay.shape==(720,1280,3)
    assert overlay.dtype==np.uint8


def test_empty_annotations_not_supported(fixture):
    data,_=fixture
    data['visibility_probes']=[]
    data['metric_anchors']=[]
    with pytest.raises(OcclusionGeometryError):evaluate_occlusion(data)


def test_bad_positive_config():
    with pytest.raises(OcclusionGeometryError):OcclusionConfig(pixel_tolerance=-1)


def test_nonfinite_anchor_rejected(fixture):
    data,_=fixture
    data['metric_anchors'][0]['independent_world_xyz'][0]=float('nan')
    with pytest.raises(OcclusionGeometryError):evaluate_occlusion(data)


def test_unknown_surface_id_not_asserted(fixture):
    data,_=fixture
    data['visibility_probes'][0]['observed_front_surface_id']='unknown_occluder'
    assert get(evaluate_occlusion(data),'near_visible')['state']=='INDETERMINATE'


def test_subpixel_edge_guard_without_reported_sigma(fixture):
    data,_=fixture
    cam=PinholeCamera(data['camera'],data['image_shape_hw'])
    # The ray through x=1.20 at y=4 crosses x=1.0 on the near plane.
    xy=cam.project([1.2,4.,1.7])
    data['visibility_probes']=[{'id':'exact_boundary','pixel_xy':xy.tolist(),
             'observed_front_surface_id':'near_panel','visibility_provenance':'independent_annotation'}]
    data['metric_anchors']=[]
    r=evaluate_occlusion(data)['observations'][0]
    assert r['state']=='INDETERMINATE'


def test_benchmark_repeatability(tmp_path):
    from scripts.p5_occlusion_benchmark import main
    x=main(['--trials','4','--out',str(tmp_path/'benchmark1.json')])
    y=main(['--trials','4','--out',str(tmp_path/'benchmark2.json')])
    assert x==y
    assert x['observations']==28
    assert x['real_photo_accuracy']=='NOT_MEASURED'


def test_cli_commands(tmp_path):
    from aiforensics.cli import main
    out=tmp_path/'demo'
    main(['demo-occlusion','--out',str(out)])
    assert (out/'p5_d02_report.json').is_file()
    reportdir=tmp_path/'analysis'
    main(['analyze-occlusion','--input',str(out/'p5_d02_fixture.json'), '--out',str(reportdir)])
    assert (reportdir/'p5_d02_report.json').is_file()
