"""Known-truth tests, degeneracies and negative controls for P2-S03."""
import json
from copy import deepcopy
import numpy as np
import cv2
import pytest
from aiforensics.shadow_3d import (Shadow3DError, Shadow3DConfig, analyze_shadow_3d,
                                    reconstruct_shadow_rays,run_shadow3d_manifest)
from aiforensics.shadow_3d_synthetic import synthetic_shadow3d_scene


def _one(**kwargs):
    d,_,truth=synthetic_shadow3d_scene(**kwargs)
    return d,truth


def test_perfect_point_light_3d_position():
    d,truth=_one(noise_px=0)
    r=analyze_shadow_3d(d)
    assert r['state']=='MEASURED',r
    g=r['model_groups'][0]
    assert g['model_class']=='FINITE_POINT_LIGHT',g
    assert np.linalg.norm(np.array(g['source_xyz_world'])-truth['fixture_01']['position'])<1e-7
    assert g['median_line_distance_world']<1e-9
    assert g['rank_eigen_ratio']>0
    assert len(g['inlier_ids'])==16
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_recovered_plane_and_elevated_3d_points():
    data,truth=_one(n=11)
    rows,_=reconstruct_shadow_rays(data)
    for r in rows:
        assert abs(r['Q'][2])<1e-8
        assert abs(r['P'][2]-r['height'])<1e-8
        assert r['u'][2]>0


def test_noisy_with_wrong_correspondences():
    d,_=_one(n=19,noise_px=.3,bad_pairs=3)
    r=analyze_shadow_3d(d)
    assert r['state']=='MEASURED',r
    g=r['model_groups'][0]
    assert g['model_class']=='FINITE_POINT_LIGHT',g
    assert len(g['excluded_ids'])>=3
    assert np.linalg.norm(np.array(g['source_xyz_world'])-[-2.2,3,7.5]) < .25


def test_directional_light_identifies_direction_but_not_distance():
    d,truth=_one(n=17,directional=True,sources=[[.3,-.4,1.0]],noise_px=.1)
    r=analyze_shadow_3d(d)
    assert r['state']=='MEASURED',r
    g=r['model_groups'][0]
    assert g['model_class']=='DIRECTIONAL_OR_DISTANT_LIGHT',g
    assert g['source_xyz_world'] is None
    assert np.linalg.norm(np.asarray(g['source_direction_world'])-truth['fixture_01']['direction'])<.02


def test_two_finite_sources_with_external_family_ids():
    d,_,truth=synthetic_shadow3d_scene(n=13,noise_px=.17,
                  sources=[[-2.2,3,7.5],[3.2,2.0,6.4]])
    r=analyze_shadow_3d(d)
    assert r['state']=='MEASURED',r
    assert r['group_count']==2
    for g in r['model_groups']:
        assert g['model_class']=='FINITE_POINT_LIGHT',g
        assert np.linalg.norm(np.asarray(g['source_xyz_world'])-truth[g['family_id']]['position'])<.3


def test_inconsistent_outlier_groups_abstain():
    d,_=_one(n=12)
    rng=np.random.default_rng(343)
    for item in d['correspondences']:
        item['shadow_xy']=[float(rng.uniform(50,1200)),float(rng.uniform(40,670))]
    r=analyze_shadow_3d(d)
    assert r['state']=='INDETERMINATE',r
    assert r['model_groups'][0]['source_xyz_world'] is None


def test_minimum_support_prevents_one_good_pair():
    d,_=_one(n=16,noise_px=.12,bad_pairs=7)
    r=analyze_shadow_3d(d)
    assert r['state']=='INDETERMINATE'


def test_bad_camera_and_plane():
    d,_=_one()
    cases=[]
    z=deepcopy(d);z['camera']['K'][0][0]=0;cases.append(z)
    z=deepcopy(d);z['camera']['R_world_to_camera'][0][0]=5;cases.append(z)
    z=deepcopy(d);z['ground_plane']['normal_world']=[0,0,0];cases.append(z)
    z=deepcopy(d);z['camera']['t_world_to_camera']=[float('nan'),0,0];cases.append(z)
    for z in cases:
        with pytest.raises(Shadow3DError): analyze_shadow_3d(z)


def test_invalid_heights_confidence_duplicate_ids():
    d,_=_one()
    cases=[]
    z=deepcopy(d);z['correspondences'][0]['height_above_plane']=0;cases.append(z)
    z=deepcopy(d);z['correspondences'][0]['confidence']=1.2;cases.append(z)
    z=deepcopy(d);z['correspondences'][0]['id']=z['correspondences'][1]['id'];cases.append(z)
    z=deepcopy(d);z['correspondences'][0]['object_xy']=[-1,50];cases.append(z)
    for z in cases:
        with pytest.raises(Shadow3DError): analyze_shadow_3d(z)


def test_missing_heights_not_silently_assumed():
    d,_=_one()
    del d['correspondences'][0]['height_above_plane']
    with pytest.raises(Shadow3DError):analyze_shadow_3d(d)


def test_too_few_pairs_abstains():
    d,_=_one()
    d['correspondences']=d['correspondences'][:2]
    r=analyze_shadow_3d(d)
    assert r['state']=='INDETERMINATE'


def test_explicit_groups_but_no_semantic_inference():
    d,_=_one()
    for x in d['correspondences'][:2]:x['family_id']='another'
    r=analyze_shadow_3d(d)
    assert r['state']=='INDETERMINATE'
    assert r['group_count']==2


def test_deterministic_results():
    d,_=_one(noise_px=.2,bad_pairs=2)
    assert analyze_shadow_3d(d)==analyze_shadow_3d(d)


def test_json_and_optional_overlay(tmp_path):
    d,image,_=synthetic_shadow3d_scene(noise_px=.1,bad_pairs=2)
    manifest=tmp_path/'scene.json';manifest.write_text(json.dumps(d))
    frame=tmp_path/'scene.png';cv2.imwrite(str(frame),image)
    report=run_shadow3d_manifest(manifest,tmp_path/'out',frame)
    assert report['state']=='MEASURED'
    assert (tmp_path/'out/p2_s03_overlay.png').is_file()
    assert (tmp_path/'out/p2_s03_report.json').is_file()
    assert len(report['image_sha256'])==64
    with pytest.raises(Shadow3DError):
        bad=tmp_path/'crop.png';cv2.imwrite(str(bad),image[:300]);run_shadow3d_manifest(manifest,tmp_path/'bad',bad)


def test_config_validation():
    for kw in [{'min_pairs':2},{'ransac_trials':0},{'min_support_fraction':1.3},
               {'direction_tolerance_deg':0},{'point_tolerance_world':-1},
               {'min_identifiability_ratio':0}]:
        with pytest.raises(Shadow3DError):Shadow3DConfig(**kw)


def test_tilted_plane_and_translated_world_frame_invariance():
    """Rigid frame changes should rotate and translate the reconstructed source."""
    d,_,truth=synthetic_shadow3d_scene(n=12,noise_px=0)
    origin=np.array([1.7,-3.2,2.4])
    th=np.deg2rad(24.)
    T=np.array([[np.cos(th),0,np.sin(th)],[0,1,0],[-np.sin(th),0,np.cos(th)]])
    original=deepcopy(d)
    R=np.asarray(original['camera']['R_world_to_camera']);t=np.asarray(original['camera']['t_world_to_camera'])
    Rnew=R@T.T
    d['camera']['R_world_to_camera']=Rnew.tolist()
    d['camera']['t_world_to_camera']=(t-Rnew@origin).tolist()
    normal=T@np.array([0.,0.,1.])
    d['ground_plane']['normal_world']=normal.tolist()
    d['ground_plane']['offset_world']=-float(normal@origin)
    r=analyze_shadow_3d(d)
    g=r['model_groups'][0]
    assert r['state']=='MEASURED',g
    assert np.linalg.norm(np.asarray(g['source_xyz_world'])-(T@truth['fixture_01']['position']+origin))<1e-7


def test_rejected_horizon_rays_reduce_support_not_miscounted():
    d,_=_one(n=16)
    for row in d['correspondences'][:12]:
        row['shadow_xy']=[500.,20.]
    r=analyze_shadow_3d(d)
    assert r['state']=='INDETERMINATE'
    assert r['valid_3d_reconstruction_fraction']<.65


def test_distant_finite_light_not_forced_into_precise_local_position():
    d,_=_one(n=15,sources=[[1500.,-1000.,5000.]])
    r=analyze_shadow_3d(d)
    assert r['state'] in ('MEASURED','INDETERMINATE')
    g=r['model_groups'][0]
    assert g['model_class']!='FINITE_POINT_LIGHT'
    assert g['source_xyz_world'] is None


def test_s02_report_bridge_preserves_known_assignment_hypotheses(tmp_path):
    from aiforensics.shadow_3d import attach_s02_families
    d,_,_=synthetic_shadow3d_scene(n=12,bad_pairs=2)
    for row in d['correspondences']:
        row.pop('family_id',None)
    mapping={x['id']:('UNASSIGNED' if i>=10 else 'projected_family_01')
             for i,x in enumerate(d['correspondences'])}
    s02={'module':'P2_S02_MULTIPLE_PROJECTED_SHADOW_CONVERGENCES',
         'state':'MEASURED','image_shape_hw':d['image_shape_hw'],
         'models':[{'model_id':'projected_family_01'}],
         'assignment_by_id':mapping}
    prepared,meta=attach_s02_families(d,s02)
    assert len(prepared['correspondences'])==10
    assert meta['pre_fit_excluded_count']==2
    assert all(x['family_id']=='projected_family_01' for x in prepared['correspondences'])
    assert all('family_id' not in x for x in d['correspondences'])
    assert analyze_shadow_3d(prepared)['state']=='MEASURED'
    s02['image_shape_hw']=[1,2]
    with pytest.raises(Shadow3DError):attach_s02_families(d,s02)
