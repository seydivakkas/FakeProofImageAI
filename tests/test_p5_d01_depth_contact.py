"""P5-D01 synthetic geometry with independent proofs; no real-photo accuracy."""
import copy
import json
import numpy as np
import pytest
from aiforensics.depth_contact import (DepthContactError, DepthContactConfig,
    PinholeCamera, SupportPlane, evaluate_contact, run_depth_contact_manifest)
from aiforensics.depth_contact_synthetic import synthetic_depth_contact_fixture, render_depth_contact_overlay


@pytest.fixture
def case():
    return synthetic_depth_contact_fixture(seed=123)


def test_controlled_positive_negative_unknown(case):
    manifest,truth=case
    result=evaluate_contact(manifest)
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert {r['id']:r['state'] for r in result['observations']}==truth


def test_ray_plane_intersection_is_never_contact_proof(case):
    data,_=case
    data['observations']=[data['observations'][-2]]
    r=evaluate_contact(data)['observations'][0]
    assert r['inside_support_polygon']
    assert r['state']=='INDETERMINATE'
    assert r['ray_plane_point_world_xyz'] is not None


def test_outside_polygon_without_anchor_abstains(case):
    data,_=case
    data['observations']=[data['observations'][-3]]
    r=evaluate_contact(data)['observations'][0]
    assert not r['inside_support_polygon']
    assert r['state']=='INDETERMINATE'


def test_3d_anchor_out_of_plane_is_inconsistent(case):
    data,_=case
    data['observations']=[data['observations'][5]]
    r=evaluate_contact(data)['observations'][0]
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert r['independent_anchor_plane_signed_distance_world']==pytest.approx(.55)


def test_wrong_top_holdout_inconsistent(case):
    data,_=case
    data['observations']=[data['observations'][4]]
    r=evaluate_contact(data)['observations'][0]
    assert r['upright_top_reprojection_error_px']>15
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_without_independent_height_evidence_abstains(case):
    data,_=case
    data['observations']=[data['observations'][0]]
    x=data['observations'][0]
    del x['independent_base_world_xyz']
    del x['base_world_provenance']
    x['height_provenance']='inferred_from_same_image'
    r=evaluate_contact(data)['observations'][0]
    assert r['state']=='INDETERMINATE'
    assert 'upright_top_reprojection_error_px' not in r


def test_bad_metric_anchor_without_provenance_not_considered(case):
    data,_=case
    data['observations']=[data['observations'][5]]
    data['observations'][0]['base_world_provenance']='image_assumed_ground'
    r=evaluate_contact(data)['observations'][0]
    assert r['state']=='INDETERMINATE'


def test_height_not_upright_abstains(case):
    data,_=case
    data['observations']=[data['observations'][0]]
    x=data['observations'][0]
    x.pop('independent_base_world_xyz')
    x['upright_gravity_aligned']=False
    assert evaluate_contact(data)['state']=='INDETERMINATE'


def test_camera_round_trip(case):
    d,_=case
    c=PinholeCamera(d['camera'],d['image_shape_hw'])
    p=np.array([.5,2.,1.])
    xy=c.project(p)
    ray=c.ray(xy)
    assert np.linalg.norm(np.cross(p-c.C,ray))<1e-8


def test_distortion_round_trip(case):
    d,_=case
    d['camera']['distortion_coefficients_k1_k2_p1_p2_k3']=[-.06,.01,.001,-.0008,0.]
    c=PinholeCamera(d['camera'],d['image_shape_hw'])
    p=np.array([.5,2.,1.])
    ray=c.ray(c.project(p))
    assert np.linalg.norm(np.cross(p-c.C,ray))<1e-5


def test_cameras_wrong_matrix_refused(case):
    d,_=case
    d['camera']['R_world_to_camera']=[[1,0,0],[0,1,0],[0,0,-1]]
    with pytest.raises(DepthContactError,match='proper orthogonal'):
        evaluate_contact(d)


@pytest.mark.parametrize('bad', [
    [[0.,0.,0.],[1.,0.,0.],[1.,1.,0.]],
    [[0,0,0],[3,0,0],[1,1,.2],[0,2,0]],
    [[0,0,0],[3,3,0],[3,0,0],[0,3,0]],
])
def test_bad_support_polygon(case,bad):
    d,_=case
    d['support_surfaces'][0]['polygon_world_xyz']=bad
    if bad == [[0.,0.,0.],[1.,0.,0.],[1.,1.,0.]]:
        # A valid triangle is a supported finite convex polygon.
        assert evaluate_contact(d)['module']=='P5_D01_DEPTH_CONTACT_SUPPORT'
    else:
        with pytest.raises(DepthContactError):evaluate_contact(d)


def test_parallel_ground_ray_abstention(case):
    d,_=case
    c=PinholeCamera(d['camera'],d['image_shape_hw'])
    # exact horizon point in pinhole image, using direction along world x-axis
    vec=np.array([1.,0.,0.]);p=d['camera']['K']
    k=np.array(p);uvz=k@c.R@vec
    uv=uvz[:2]/uvz[2] if abs(uvz[2])>1e-8 else None
    if uv is not None and 0 <= uv[0] < 1280 and 0 <= uv[1] < 720:
        d['observations']=[{'id':'horizon','support_id':'floor','base_pixel_xy':uv.tolist()}]
        assert evaluate_contact(d)['state']=='INDETERMINATE'
    else:
        plane=SupportPlane(d['support_surfaces'][0])
        world_ray=np.array([1.,0.,0.]); assert abs(plane.n@world_ray)<1e-9


def test_static_com_outside_support(case):
    d,_=case
    d['observations']=[d['observations'][-1]]
    r=evaluate_contact(d)['observations'][0]
    assert not r['gravity_static_support_possible']
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_static_com_inside_support(case):
    d,_=case
    d['observations']=[d['observations'][-1]]
    d['observations'][0]['center_of_mass_world_xyz']=[1,3,1.5]
    assert evaluate_contact(d)['state']=='CONSISTENT'


def test_independent_anchor_reprojection_failure(case):
    d,_=case
    d['observations']=[d['observations'][0]]
    d['observations'][0].pop('top_pixel_xy')
    d['observations'][0].pop('known_height_world')
    d['observations'][0]['base_pixel_xy'][0]+=20
    r=evaluate_contact(d)['observations'][0]
    assert any('reprojection' in x for x in r['inconsistency_reasons'])


def test_not_measure_off_image(case):
    d,_=case
    d['observations'][0]['base_pixel_xy']=[-1.,400.]
    with pytest.raises(DepthContactError,match='outside image'):
        evaluate_contact(d)


def test_optional_distortion_bad_is_rejected(case):
    d,_=case
    d['camera']['distortion_coefficients_k1_k2_p1_p2_k3']=[0,0,0]
    with pytest.raises(DepthContactError):evaluate_contact(d)


def test_duplicate_ids_rejected(case):
    d,_=case
    d['observations'][1]['id']=d['observations'][0]['id']
    with pytest.raises(DepthContactError):evaluate_contact(d)


def test_file_api_and_overlay(case,tmp_path):
    d,truth=case
    p=tmp_path/'fixture.json'
    p.write_text(json.dumps(d),encoding='utf8')
    r=run_depth_contact_manifest(p,tmp_path/'out')
    assert r['input_sha256']
    assert (tmp_path/'out/p5_d01_report.json').exists()
    img=render_depth_contact_overlay(d,r)
    assert img.shape==(720,1280,3)


def test_geometric_truth_not_ai_origin(case):
    d,_=case
    r=evaluate_contact(d)
    assert 'AI_ORIGIN' in r['decision']
    assert all('AI' not in x['state'] for x in r['observations'])


def test_bad_config():
    with pytest.raises(DepthContactError):DepthContactConfig(pixel_tolerance=0)


def test_conditional_depth_uncertainty_reported(case):
    data,_=case
    data['observations']=[data['observations'][0]]
    r=evaluate_contact(data)['observations'][0]
    assert np.all(np.asarray(r['conditional_ground_xyz_std_world']) >= 0)
    assert r['conditional_range_sigma_world']>0
    assert np.min(np.linalg.eigvalsh(np.array(r['conditional_ground_covariance_world2']))) >= -1e-12


def test_larger_base_pixel_noise_larger_uncertainty(case):
    data,_=case
    data['observations']=[data['observations'][0]]
    s=evaluate_contact(data)['observations'][0]['conditional_range_sigma_world']
    data['observations'][0]['base_pixel_sigma_px'] *= 2
    assert evaluate_contact(data)['observations'][0]['conditional_range_sigma_world']==pytest.approx(s*2, rel=1e-5)


def test_tilted_plane_contact_and_vertical_height(case):
    data,_=case
    plane=data['support_surfaces'][0]
    slope=0.125
    plane['normal_world']=[0.,-slope,1.]
    plane['polygon_world_xyz']=[[-3.,0.,0.],[3.,0.,0.],[3.,6.,6*slope],[-3.,6.,6*slope]]
    from aiforensics.depth_contact import PinholeCamera
    c=PinholeCamera(data['camera'],data['image_shape_hw'])
    base=np.array([1.,2.,2*slope]);top=base+np.array([0.,0.,1.7])
    data['observations']=[{'id':'inclined','support_id':'floor',
        'base_pixel_xy':c.project(base).tolist(),'top_pixel_xy':c.project(top).tolist(),
        'known_height_world':1.7,'height_provenance':'independent_metric',
        'upright_gravity_aligned':True,'independent_base_world_xyz':base.tolist(),
        'base_world_provenance':'independent_metric'}]
    r=evaluate_contact(data)['observations'][0]
    assert r['state']=='CONSISTENT'
    assert np.allclose(r['ray_plane_point_world_xyz'],base,atol=1e-9)


def test_normal_reversed_com_abstains(case):
    data,_=case
    data['observations']=[data['observations'][-1]]
    data['support_surfaces'][0]['normal_world']=[0,0,-1]
    data['observations'][0]['center_of_mass_world_xyz']=[1,3,1.5]
    r=evaluate_contact(data)['observations'][0]
    assert r['state']=='INDETERMINATE'


def test_image_overlay_background(case):
    data,_=case
    r=evaluate_contact(data)
    img=np.full((720,1280,3),80,dtype=np.uint8)
    v=render_depth_contact_overlay(data,r,background=img)
    assert v.shape==img.shape
    with pytest.raises(ValueError):render_depth_contact_overlay(data,r,background=np.zeros((2,2,3),np.uint8))


def test_noisy_borderline_top_abstains_not_false_violation(case):
    data,_=case
    data['observations']=[data['observations'][0]]
    row=data['observations'][0]
    row['base_pixel_sigma_px']=1.1
    row['top_pixel_sigma_px']=1.1
    row['top_pixel_xy'][0]+=4.2
    report=evaluate_contact(data)['observations'][0]
    assert report['state']=='INDETERMINATE'
    assert report['measurement_ambiguities']


def test_large_wrong_top_even_noisy_is_inconsistent(case):
    data,_=case
    data['observations']=[data['observations'][0]]
    row=data['observations'][0]
    row['base_pixel_sigma_px']=1.1
    row['top_pixel_sigma_px']=1.1
    row['top_pixel_xy'][0]+=55.
    assert evaluate_contact(data)['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
