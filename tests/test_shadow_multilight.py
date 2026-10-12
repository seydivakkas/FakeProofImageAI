"""P2-S02: strict known 3D ray geometry + noisy/outlier/ambiguous regression."""
from __future__ import annotations
import json
import numpy as np
import cv2
import pytest

from aiforensics.shadow_multilight import (MultiLightConfig, fit_multiple_projected_lights,
                                          run_multilight_manifest, ShadowEvidenceError)
from aiforensics.shadow_multi_synthetic import synthetic_multilight_scene


def _fixture(per_light=10, seed=30, noise=.2, bad=3, light_sources=None):
    return synthetic_multilight_scene(per_light=per_light, seed=seed, noise_px=noise,
                                      bad_pairs=bad, light_sources=light_sources)


def _match_estimated_models(result, truth, max_error):
    point_truth=list(truth['points_px'].values())
    estimates=[m['projected_convergence_xy_px'] for m in result['models']]
    assert len(estimates)==len(point_truth), result
    assert all(p is not None for p in estimates)
    d=np.linalg.norm(np.asarray(estimates)[:,None,:]-np.asarray(point_truth)[None,:,:],axis=2)
    for row in d:
        assert row.min()<max_error, d
    assert len({int(np.argmin(row)) for row in d})==len(point_truth)


def test_two_lights_exact_3d_projection_and_mismatches():
    data,_,truth=_fixture(noise=0,bad=3)
    r=fit_multiple_projected_lights(data,MultiLightConfig(bootstrap_trials=0))
    assert r['state']=='MEASURED',r
    assert r['model_count']==2
    _match_estimated_models(r,truth,1e-6)
    assert set(r['unassigned_ids'])=={'wrong_00','wrong_01','wrong_02'}
    assert all(m['inlier_count']==10 for m in r['models'])
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert r['real_validation']=='DEFERRED'


def test_noisy_known_3d_scene_with_wrong_pairs():
    data,_,truth=_fixture(per_light=12,noise=.4,bad=4)
    r=fit_multiple_projected_lights(data,MultiLightConfig(seed=7,bootstrap_trials=20))
    assert r['state']=='MEASURED',r
    _match_estimated_models(r,truth,12.0)
    for m in r['models']:
        assert m['inlier_count'] >= 10
        assert m['median_angular_residual_deg'] < 1.0
        assert m['bootstrap_dispersion_xy_px_exploratory'] is not None
    assert len(r['unassigned_ids']) >= 3


def test_single_source_not_inventing_multiple():
    data,_,truth=_fixture(per_light=13,noise=.18,bad=3,light_sources=[[-2.2,3,7.5]])
    r=fit_multiple_projected_lights(data)
    assert r['state']=='MEASURED'
    assert r['model_count']==1
    _match_estimated_models(r,truth,4)


def test_max_models_cap_and_exclusivity():
    data,_,_=_fixture(per_light=11,noise=.3,bad=2)
    r=fit_multiple_projected_lights(data,MultiLightConfig(max_models=1,bootstrap_trials=0))
    assert r['model_count']==1
    assert r['state']=='INDETERMINATE'  # <55% of this 2-source fixture is explained
    a=[x for m in r['models'] for x in m['member_ids']]
    assert len(a)==len(set(a))


def test_far_field_parallel_world_rays_supported_as_projection_not_point_light():
    from aiforensics.shadow_synthetic import synthetic_shadow_scene
    d,_,_=synthetic_shadow_scene(n=12,directional=True,noise_px=.08)
    r=fit_multiple_projected_lights(d)
    assert r['state']=='MEASURED'
    assert r['model_count']==1
    assert r['models'][0]['inlier_count']==12
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_random_wrong_matches_abstain():
    rng=np.random.default_rng(125)
    rows=[]
    for k in range(22):
        a=rng.uniform([100,120],[1000,430]); b=rng.uniform([100,150],[1000,620])
        rows.append({'id':str(k),'object_xy':a.tolist(),'shadow_xy':b.tolist()})
    data={'image_shape_hw':[720,1280],'correspondences':rows}
    r=fit_multiple_projected_lights(data,MultiLightConfig(seed=21,bootstrap_trials=0))
    assert r['state']=='INDETERMINATE'
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_degenerate_collinear_rays_no_fake_light():
    data={'image_shape_hw':[720,1280],'correspondences':[
        {'id':str(i),'object_xy':[100+20*i,140.],'shadow_xy':[160+20*i,140.]}
        for i in range(14)]}
    r=fit_multiple_projected_lights(data,MultiLightConfig(bootstrap_trials=0))
    assert r['state']=='INDETERMINATE'
    assert r['model_count']==0


def test_deterministic_across_same_seed():
    data,_,_=_fixture(per_light=8,noise=.48,bad=3)
    config=MultiLightConfig(seed=302,bootstrap_trials=12)
    assert fit_multiple_projected_lights(data,config)==fit_multiple_projected_lights(data,config)


def test_nearby_sources_do_not_force_two_distinct_models():
    src=[[-2.2,3,7.5],[-2.19,3.0,7.5]]
    data,_,_=_fixture(per_light=10,noise=.25,bad=0,light_sources=src)
    r=fit_multiple_projected_lights(data,MultiLightConfig(bootstrap_trials=0))
    assert r['model_count'] <= 1
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_invalid_configuration_and_invalid_input():
    for kw in [{'max_models':0},{'min_model_support_fraction':0},
               {'min_total_support_fraction':3},{'ambiguity_margin_deg':2.3},
               {'min_pairs_per_model':2}, {'ransac_trials':0}]:
        with pytest.raises(ShadowEvidenceError):MultiLightConfig(**kw)
    data,_,_=_fixture()
    data['correspondences'][1]['id']=data['correspondences'][0]['id']
    with pytest.raises(ShadowEvidenceError,match='unique'):
        fit_multiple_projected_lights(data)


def test_three_sources_when_geometry_separable():
    src=[[-2.2,3,7.5],[4.5,2.5,6.2],[-4.5,4.3,7.4]]
    data,_,truth=_fixture(per_light=12,seed=54,noise=.15,bad=1,light_sources=src)
    r=fit_multiple_projected_lights(data,MultiLightConfig(bootstrap_trials=0,seed=17))
    assert r['state']=='MEASURED',r
    assert r['model_count']==3,r
    _match_estimated_models(r,truth,12)


def test_json_cli_manifest_image_overlay(tmp_path):
    data,frame,_=_fixture(per_light=8,noise=.15,bad=2)
    manifest=tmp_path/'pairs.json';manifest.write_text(json.dumps(data))
    image=tmp_path/'frame.png';cv2.imwrite(str(image),frame)
    report=run_multilight_manifest(manifest,tmp_path/'output',image)
    assert report['state']=='MEASURED'
    assert (tmp_path/'output/p2_s02_overlay.png').is_file()
    result=json.loads((tmp_path/'output/p2_s02_report.json').read_text())
    assert result['model_count']==2
    assert len(result['image_sha256'])==64


def test_wrong_size_overlay_rejected(tmp_path):
    data,frame,_=_fixture(bad=0)
    p=tmp_path/'pairs.json';p.write_text(json.dumps(data))
    path=tmp_path/'wrong.png';cv2.imwrite(str(path),frame[:400])
    with pytest.raises(ShadowEvidenceError,match='dimensions'):
        run_multilight_manifest(p,tmp_path/'out',path)
