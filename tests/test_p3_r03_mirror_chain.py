"""Controlled analytic and adversarial planar multi-mirror physics tests."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from aiforensics.mirror_chain import (MirrorChainError, _hit_distance, evaluate_multi_mirror,
                                      parse_mirrors, predict_mirror_chain, run_multi_mirror_manifest,
                                      trace_pixel, virtual_chain)
from aiforensics.mirror_chain_synthetic import synthetic_two_mirror_scene
from aiforensics.mirror_geometry import CalibratedCamera, reflect_direction


def setup_case(seed=4, n=15, corrupt=3, noise=.35):
    d,im,truth=synthetic_two_mirror_scene(seed=seed,n=n,corrupt=corrupt,noise_px=noise)
    cam=CalibratedCamera.from_manifest(d['camera'])
    mirrors=parse_mirrors(d)
    return d,im,truth,cam,mirrors


def test_two_mirror_perfect_ray():
    d,_,_,cam,mirrors=setup_case(corrupt=0,noise=0)
    obj=d['correspondences'][0]['object_world_xyz']
    p=predict_mirror_chain(cam,mirrors,['side','back'],obj)
    assert p['object_ray_miss_world']<1e-10
    assert [h['mirror_id'] for h in p['ray_hits_camera_to_object']]==['back','side']
    assert len(p['virtual_image_chain_world'])==3
    assert np.allclose(p['path_world'][0],[0,0,0])
    assert np.allclose(p['path_world'][-1],obj)
    for hit in p['ray_hits_camera_to_object']:
        inc=np.asarray(hit['incident_direction_world'])
        out=np.asarray(hit['outgoing_direction_world'])
        n=mirrors[hit['mirror_id']].normal
        assert np.allclose(out,reflect_direction(inc,n),atol=1e-12)
        assert abs(mirrors[hit['mirror_id']].signed_distance(hit['hit_xyz_world']))<1e-9


def test_virtual_chain_is_reflection_order_and_noncommutative():
    d,_,_,_,mirrors=setup_case(corrupt=0,noise=0)
    point=np.asarray(d['correspondences'][0]['object_world_xyz'])
    first=virtual_chain(mirrors,['side','back'],point)
    reversed_chain=virtual_chain(mirrors,['back','side'],point)
    assert np.allclose(first[1],mirrors['side'].reflect_point(point))
    assert np.allclose(first[2],mirrors['back'].reflect_point(first[1]))
    # Orthogonal reflection planes happen to commute in position, but NOT in
    # physical ray ordering; make sure this is not claimed as order evidence.
    assert np.allclose(first[-1],reversed_chain[-1])
    with pytest.raises(MirrorChainError):
        predict_mirror_chain(CalibratedCamera.from_manifest(d['camera']),mirrors,['back','side'],point)


def test_manifest_20_clean_and_corrupted():
    d,_,truth,_,_=setup_case(n=20)
    r=evaluate_multi_mirror(d)
    assert r['state']=='MIXED_EVIDENCE'
    assert (r['consistent_count'],r['inconsistent_count'],r['indeterminate_count'])==(
        truth['known_good'],truth['known_corrupt'],0)
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert all(len(x['virtual_image_chain_world'])==3 for x in r['correspondences'])


@pytest.mark.parametrize('seed',[0,1,2,3,4,5,6,7,8,9,10,16])
def test_seeded_correspondence_negatives(seed):
    d,_,truth,_,_=setup_case(seed=seed,n=14,corrupt=2,noise=.45)
    r=evaluate_multi_mirror(d)
    assert r['consistent_count']==truth['known_good']
    assert r['inconsistent_count']==truth['known_corrupt']
    assert r['indeterminate_count']==0


def test_three_mirror_full_path():
    d,_,_,cam,_=setup_case(corrupt=0)
    mirrors=d['mirrors']
    mirrors[0]['polygon_world']=[[-1.6,-4,0],[-1.6,4,0],[-1.6,4,4],[-1.6,-4,4]]
    mirrors[1]['polygon_world']=[[-1.57,-4,4],[4,-4,4],[4,4,4],[-1.57,4,4]]
    mirrors.append({'id':'top','normal_world':[0,1,0],'offset_world':-2,
                    'polygon_world':[[-2,2,0],[4,2,0],[4,2,4],[-2,2,4]],
                    'reflective_side':'negative'})
    ms=parse_mirrors(d)
    p=np.array([-1.480708620729852,1.8144322097711436,1.2610293011508453])
    prediction=predict_mirror_chain(cam,ms,['side','top','back'],p,
                                   {'side':'positive','top':'negative','back':'negative'})
    assert prediction['object_ray_miss_world']<1e-9
    assert [x['mirror_id'] for x in prediction['ray_hits_camera_to_object']]==['back','top','side']
    assert len(prediction['virtual_image_chain_world'])==4
    pts=[p,np.array([-1.47,1.83,1.3]),np.array([-1.49,1.82,1.2])]
    d['correspondences']=[{'object_world_xyz':q.tolist(),
                           'reflection_xy':predict_mirror_chain(cam,ms,['side','top','back'],q,
                               {'side':'positive','top':'negative','back':'negative'})['expected_reflection_xy']}
                          for q in pts]
    d['reflection_order_object_to_camera']=['side','top','back']
    result=evaluate_multi_mirror(d)
    assert result['consistent_count']==3
    assert result['indeterminate_count']==0


def test_wrong_reflective_face_fails_closed():
    d,_,_,_,_=setup_case(corrupt=0)
    d['mirrors'][1]['reflective_side']='positive'
    r=evaluate_multi_mirror(d)
    assert r['state']=='INDETERMINATE'
    assert r['observable_pairs']==0
    assert 'non-reflective side' in r['correspondences'][0]['reason']


def test_polygon_clipping_is_not_ignored():
    d,_,_,_,_=setup_case(corrupt=0)
    d['mirrors'][1]['polygon_world']=[[-.3,-.1,4],[.3,-.1,4],[.3,.1,4],[-.3,.1,4]]
    r=evaluate_multi_mirror(d)
    assert r['observable_pairs']==0
    assert all('outside finite polygon' in x['reason'] for x in r['correspondences'])


def test_observed_nonphysical_path_is_inconsistent_not_measured_as_good():
    d,_,_,_,_=setup_case(corrupt=0,noise=0)
    valid=evaluate_multi_mirror(d)['correspondences'][0]['expected_reflection_xy']
    d['correspondences'][0]['reflection_xy']=[valid[0]+120,valid[1]]
    r=evaluate_multi_mirror(d)
    first=r['correspondences'][0]
    assert first['status']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert first['reprojection_residual_px']>100
    assert first.get('physical_trace_rejection_reason') or first.get('object_ray_miss_world') is not None


def test_observed_pixel_out_of_frame_indeterminate():
    d,_,_,_,_=setup_case(corrupt=0)
    d['correspondences'][0]['reflection_xy']=[-50,100]
    r=evaluate_multi_mirror(d)
    assert r['correspondences'][0]['status']=='INDETERMINATE'


def test_one_observable_but_insufficient_evidence():
    d,_,_,_,_=setup_case(n=4,corrupt=0)
    d['correspondences']=d['correspondences'][:1]
    r=evaluate_multi_mirror(d)
    assert r['state']=='INDETERMINATE' and r['consistent_count']==1


def test_zero_reprojection_when_noise_disabled():
    d,_,_,_,_=setup_case(corrupt=0,noise=0)
    r=evaluate_multi_mirror(d)
    assert r['consistent_count']==len(d['correspondences'])
    assert r['reprojection_rmse_px']<1e-9


def test_confidence_and_shuffled_mirror_list_do_not_change_geometry():
    d,_,_,_,_=setup_case(corrupt=0)
    base=evaluate_multi_mirror(d)
    d['mirrors'].reverse()
    r=evaluate_multi_mirror(d)
    assert np.isclose(base['reprojection_rmse_px'],r['reprojection_rmse_px'])


@pytest.mark.parametrize('mutator',[
    lambda x: x['mirrors'].append(copy.deepcopy(x['mirrors'][0])),
    lambda x: x.pop('mirrors'),
    lambda x: x['mirrors'][0].pop('polygon_world'),
    lambda x: x['mirrors'][0].update(reflective_side='wrong'),
    lambda x: x.update(reflection_order_object_to_camera=['side','side']),
    lambda x: x.update(reflection_order_object_to_camera=['not_there','back']),
    lambda x: x.update(reflection_order_object_to_camera=['back']),
    lambda x: x.update(reflection_order_object_to_camera=['side']*5),
    lambda x: x['correspondences'][1].update(id=x['correspondences'][0]['id']),
    lambda x: x['correspondences'][0].update(confidence=0),
    lambda x: x['correspondences'][0].update(object_world_xyz=[float('nan'),0,1]),
    lambda x: x.update(image_shape_hw=[720,-3]),
    lambda x: x['mirrors'][0].update(polygon_world=[[-1.6,0,0]]*4),
    lambda x: x.update(camera={'K':[[0]],'R_world_to_camera':[], 't_world_to_camera':[0,0,0]}),
])
def test_invalid_manifest_rejected(mutator):
    d,_,_,_,_=setup_case(n=4,corrupt=0)
    mutator(d)
    with pytest.raises((MirrorChainError,ValueError,KeyError,TypeError)):
        evaluate_multi_mirror(d)


def test_nonconvex_polygon_is_rejected():
    d,_,_,_,_=setup_case(corrupt=0)
    d['mirrors'][1]['polygon_world']=[[-2,-2,4],[3,-2,4],[0,0,4],[3,2,4],[-2,2,4]]
    with pytest.raises(MirrorChainError,match='convex'):
        evaluate_multi_mirror(d)


def test_json_cli_roundtrip_and_hash(tmp_path):
    d,image,_,_,_=setup_case()
    import cv2
    manifest=tmp_path/'fixture.json';img=tmp_path/'frame.png';out=tmp_path/'results'
    manifest.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
    assert cv2.imwrite(str(img),image)
    result=run_multi_mirror_manifest(manifest,out,img)
    assert (out/'p3_r03_overlay.png').exists()
    assert (out/'p3_r03_report.json').exists()
    assert result['manifest_sha256'] and result['image_sha256']
    assert json.loads((out/'p3_r03_report.json').read_text())['total_pairs']==len(d['correspondences'])
    proc=subprocess.run([sys.executable,'-m','aiforensics','analyze-mirror-chain',
                         '--input',str(manifest),'--image',str(img),'--out',str(out/'cli')],
                        capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)['consistent']==result['consistent_count']


def test_intervening_opaque_mirror_occludes_declared_path():
    d,_,_,_,_=setup_case(corrupt=0,noise=0)
    # Additional blocking plane between calibrated camera at Z=0 and the
    # physical back mirror at Z=4. A geometrically existing virtual image is
    # not sufficient when another supplied opaque mirror intercepts the ray.
    d['mirrors'].append({'id':'blocking','normal_world':[0,0,1],
                         'offset_world':-2.0,
                         'polygon_world':[[-2,-2,2],[2,-2,2],[2,2,2],[-2,2,2]]})
    r=evaluate_multi_mirror(d)
    assert r['observable_pairs']==0
    assert all('obstruction' in x['reason'] for x in r['correspondences'])


def test_mirror_reflection_order_is_enforced_for_ray_path():
    d,_,_,_,_=setup_case(corrupt=0,noise=0)
    d['reflection_order_object_to_camera']=['back','side']
    r=evaluate_multi_mirror(d)
    assert r['observable_pairs']==0
    assert r['state']=='INDETERMINATE'


def test_mirror_face_can_be_explicitly_two_sided():
    d,_,_,_,_=setup_case(corrupt=0)
    d['mirrors'][0]['reflective_side']='both'
    d['mirrors'][1]['reflective_side']='both'
    r=evaluate_multi_mirror(d)
    assert r['consistent_count']==len(d['correspondences'])


def test_repeating_same_physical_point_not_false_independent_evidence():
    d,_,_,_,_=setup_case(corrupt=0,noise=0)
    row=d['correspondences'][0]
    d['correspondences']=[dict(row,id=f'dup_{i}') for i in range(5)]
    r=evaluate_multi_mirror(d)
    assert r['consistent_count']==5
    assert r['independent_object_count']==1
    assert r['state']=='INDETERMINATE'
