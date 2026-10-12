"""P2-S01 known-truth synthetic 3D optics, invalid data and regression tests."""
from __future__ import annotations
import json
import numpy as np
import pytest

from aiforensics.shadow_geometry import (ShadowConfig, ShadowEvidenceError,
                                         fit_projected_light, run_shadow_manifest)
from aiforensics.shadow_synthetic import synthetic_shadow_scene


def test_exact_3d_point_source():
    data,_,true_xy=synthetic_shadow_scene(n=12)
    r=fit_projected_light(data)
    assert r['state']=='MEASURED',r
    assert r['model_class']=='FINITE_PROJECTED_POINT'
    assert r['inlier_count']==12
    assert np.linalg.norm(np.asarray(r['projected_convergence_xy_px'])-true_xy)<1e-6
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_noisy_with_outlier_consensus():
    data,_,truth=synthetic_shadow_scene(n=20,noise_px=.35,outliers=3)
    r=fit_projected_light(data,ShadowConfig(seed=14,bootstrap_trials=30))
    assert r['state']=='MEASURED',r
    assert r['inlier_count']>=15
    assert np.linalg.norm(np.array(r['projected_convergence_xy_px'])-truth)<18
    assert r['outlier_count']>=1
    assert len(r['angular_residual_deg_per_pair'])==20


def test_far_field_parallel_world_rays():
    data,_,_=synthetic_shadow_scene(n=12,directional=True)
    r=fit_projected_light(data)
    assert r['state']=='MEASURED',r
    assert r['inlier_count']==12
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    # 3D parallel rays can converge to a FINITE VP in perspective projection.
    assert r['model_class']=='FINITE_PROJECTED_POINT'


def test_exact_parallel_image_lines_at_infinity():
    rows=[100,200,300,400,500,600]
    data={'image_shape_hw':[720,1280], 'correspondences':[
        {'object_xy':[140.,float(y)],'shadow_xy':[340.,float(y)],'id':str(i)}
        for i,y in enumerate(rows)]}
    r=fit_projected_light(data)
    assert r['state']=='MEASURED',r
    assert r['model_class']=='EFFECTIVELY_AT_INFINITY'
    assert abs(abs(r['image_direction_at_infinity_xy'][0])-1)<1e-6


def test_no_dominant_single_convergence_is_not_ai_verdict():
    # Three different projected light sources, no supported dominant direction.
    configs=[]
    for seed in [13,19,21]:
        d,_,_=synthetic_shadow_scene(n=4,seed=seed)
        configs.extend(d['correspondences'])
    # Better explicit: shifted shadows so no common true projected source.
    for i,c in enumerate(configs):
        c['id']=str(i)
        c['shadow_xy'][0]=max(0.,min(1279.,c['shadow_xy'][0]+(i%4-1.5)*110))
        c['shadow_xy'][1]=max(0.,min(719.,c['shadow_xy'][1]+(i%3-1)*85))
    r=fit_projected_light({'image_shape_hw':[720,1280], 'correspondences':configs},
                          ShadowConfig(seed=1))
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert r['state'] in {'MEASURED','INDETERMINATE'}  # Consensus model, never forensic verdict.


def test_too_few_pairs_rejected():
    data,_,_=synthetic_shadow_scene(n=4)
    data['correspondences']=data['correspondences'][:2]
    with pytest.raises(ShadowEvidenceError,match='at least'):
        fit_projected_light(data)


@pytest.mark.parametrize('mutation',["duplicate", "short", "nan", "outside", "weight", "wrongshape"])
def test_bad_annotations_rejected(mutation):
    data,_,_=synthetic_shadow_scene(n=5)
    pairs=data['correspondences']
    if mutation=='duplicate':pairs[1]['id']=pairs[0]['id']
    elif mutation=='short':pairs[1]['shadow_xy']=pairs[1]['object_xy'][:]
    elif mutation=='nan':pairs[0]['object_xy'][0]=float('nan')
    elif mutation=='outside':pairs[1]['shadow_xy'][0]=-3
    elif mutation=='weight':pairs[1]['confidence']=0
    elif mutation=='wrongshape':data['image_shape_hw']=[720,1280,4]
    with pytest.raises(ShadowEvidenceError):fit_projected_light(data)


def test_manifest_emits_overlay_and_report(tmp_path):
    data,frame,_=synthetic_shadow_scene(n=10)
    import cv2
    source=tmp_path/'scene.png'
    cv2.imwrite(str(source),frame)
    manifest=tmp_path/'pairs.json'
    manifest.write_text(json.dumps(data))
    result=run_shadow_manifest(manifest,tmp_path/'out',source)
    assert result['state']=='MEASURED'
    assert (tmp_path/'out/p2_s01_report.json').exists()
    assert (tmp_path/'out/p2_s01_shadow_overlay.png').exists()
    assert len(result['image_sha256'])==64


def test_manifest_wrong_size_rejected(tmp_path):
    data,frame,_=synthetic_shadow_scene(n=5)
    data['image_shape_hw']=[1000,1200]
    import cv2
    im=tmp_path/'im.png';cv2.imwrite(str(im),frame)
    m=tmp_path/'m.json';m.write_text(json.dumps(data))
    with pytest.raises(ShadowEvidenceError,match='dimensions'):
        run_shadow_manifest(m,tmp_path/'out',im)


def test_trials_reproducible():
    data,_,_=synthetic_shadow_scene(n=15,noise_px=.4,outliers=2)
    x=fit_projected_light(data,ShadowConfig(seed=100,bootstrap_trials=40))
    y=fit_projected_light(data,ShadowConfig(seed=100,bootstrap_trials=40))
    assert x==y


def test_ambiguous_duplicate_collinear_shadow_rays_is_indeterminate():
    data={'image_shape_hw':[720,1280],'correspondences':[
        {'object_xy':[float(x),140.], 'shadow_xy':[float(x+40),140.],'id':str(i)}
        for i,x in enumerate(range(100,300,30))]}
    r=fit_projected_light(data)
    assert r['state']=='INDETERMINATE'


def test_two_competing_physical_lights_cannot_support_single_dominant_model():
    a,_,_=synthetic_shadow_scene(n=7,seed=3)
    b,_,_=synthetic_shadow_scene(n=7,seed=14,light_source_world=[4.5,2.5,6.2])
    pairs=a['correspondences']+b['correspondences']
    for i,pair in enumerate(pairs):pair['id']=str(i)
    r=fit_projected_light({'image_shape_hw':[720,1280],'correspondences':pairs},
       ShadowConfig(seed=7,min_support_fraction=.75,bootstrap_trials=0))
    assert r['state']=='INDETERMINATE',r
    assert r['inlier_count'] <= 9
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_random_correspondences_abstain_not_ai_verdict():
    rng=np.random.default_rng(125)
    data={'image_shape_hw':[720,1280],'correspondences':[]}
    for i in range(18):
        a=rng.uniform([90,90],[1100,600])
        b=rng.uniform([90,90],[1100,600])
        data['correspondences'].append({'id':str(i),'object_xy':a.tolist(),
                                       'shadow_xy':b.tolist()})
    r=fit_projected_light(data,ShadowConfig(seed=33,min_support_fraction=.9,bootstrap_trials=0))
    assert r['state']=='INDETERMINATE',r
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'
