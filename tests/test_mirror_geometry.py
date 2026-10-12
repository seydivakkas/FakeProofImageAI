import json
import numpy as np
import pytest

from aiforensics.mirror_geometry import (
    CalibratedCamera, MirrorPlane, MirrorGeometryError, TotalInternalReflection,
    reflect_direction, refract_direction, expected_reflection,
    observed_reflection_residual, analyze_mirror_manifest, run_mirror_manifest
)
from aiforensics.mirror_synthetic import synthetic_mirror_scene


def fixture(**kwargs):
    manifest,frame,truth=synthetic_mirror_scene(**kwargs)
    cam=CalibratedCamera.from_manifest(manifest['camera'])
    plane=MirrorPlane.from_manifest(manifest['mirror_plane'])
    return manifest,frame,truth,cam,plane


def test_reflection_of_ray_obeys_equal_angles():
    d=np.array([.6, .8,0.]);n=[0,1,0]
    out=reflect_direction(d,n)
    assert np.allclose(out,[.6,-.8,0.])
    assert np.isclose(np.linalg.norm(out),1)


def test_refraction_snell_air_water_and_tir():
    inc=np.array([np.sin(np.deg2rad(30)),-np.cos(np.deg2rad(30)),0])
    refracted=refract_direction(inc,[0,1,0],1.,1.5)
    angle=np.arccos(-refracted[1])
    assert np.isclose(1.0*np.sin(np.deg2rad(30)),1.5*np.sin(angle),atol=1e-10)
    with pytest.raises(TotalInternalReflection):
        refract_direction([np.sin(np.deg2rad(60)),-np.cos(np.deg2rad(60)),0],[0,1,0],1.5,1)


def test_refract_invalid_orientation_and_indices():
    with pytest.raises(MirrorGeometryError,match='normal must face'):
        refract_direction([0,-1,0],[0,-1,0],1,1.5)
    with pytest.raises(MirrorGeometryError,match='indices'):
        refract_direction([0,-1,0],[0,1,0],0,1.5)


def test_reflect_point_and_involution_nonunit_plane():
    p=MirrorPlane.from_manifest({'normal_world':[0,3,0],'offset_world':-6})  # y=2
    a=np.array([1.,0.,3.]);v=p.reflect_point(a)
    assert np.allclose(v,[1,4,3])
    assert np.allclose(p.reflect_point(v),a)


def test_mirror_optical_geometry_matches_expected_pixel():
    manifest,_,_,cam,plane=fixture(noise_px=0,corrupt=0)
    for obs in manifest['correspondences']:
        result=observed_reflection_residual(cam,plane,obs['object_world_xyz'],obs['reflection_xy'])
        assert result['reprojection_residual_px']<1e-8
        assert result['reflection_law_residual_deg']<1e-5
        assert result['surface_normal_mismatch_deg']<1e-5
        assert abs(plane.signed_distance(result['mirror_hit_world']))<1e-9


def test_mirror_geometry_independent_camera_and_virtual_point():
    _,_,_,cam,plane=fixture(noise_px=0,corrupt=0)
    P=np.array([1.0,-2.0,1.5])
    virtual=plane.reflect_point(P)
    result=expected_reflection(cam,plane,P)
    assert np.allclose(result['virtual_xyz_world'],virtual)
    hit=result['mirror_hit_world']
    assert np.linalg.norm(np.cross(hit-cam.center,virtual-cam.center))<1e-7
    assert abs(plane.signed_distance(hit))<1e-8


def test_perfect_scene_consistent():
    manifest,_,_,_,_=fixture(n=12,noise_px=0,corrupt=0)
    report=analyze_mirror_manifest(manifest)
    assert report['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert report['consistent_count']==12
    assert report['reprojection_rmse_px']<1e-8
    assert report['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_corrupted_matches_flagged_without_ai_verdict():
    manifest,_,truth,_,_=fixture(n=14,noise_px=.35,corrupt=3)
    report=analyze_mirror_manifest(manifest,tolerance_px=3)
    assert report['state']=='MIXED_EVIDENCE'
    assert report['consistent_count']==truth['known_good']
    assert report['inconsistent_count']==truth['known_corrupted']
    assert report['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_wrong_plane_generates_mismatch_or_not_observable():
    manifest,_,_,_,_=fixture(n=12,noise_px=0,corrupt=0)
    manifest['mirror_plane'].pop('polygon_world')  # no stale polygon for newly proposed plane
    manifest['mirror_plane']['normal_world']=[-.12,-1.,0.]
    report=analyze_mirror_manifest(manifest)
    assert report['state']!='CONSISTENT_UNDER_ASSUMPTIONS'


def test_wrong_camera_rotation_generates_mismatch():
    m,_,_,_,_=fixture(noise_px=0,corrupt=0)
    R=np.asarray(m['camera']['R_world_to_camera'])
    turn=np.array([[np.cos(.06),-np.sin(.06),0],[np.sin(.06),np.cos(.06),0],[0,0,1]])
    m['camera']['R_world_to_camera']=(turn@R).tolist()
    rep=analyze_mirror_manifest(m)
    assert rep['inconsistent_count']>=8


def test_mirror_polygon_gates_outside_hit():
    m,_,_,cam,plane=fixture(noise_px=0,corrupt=0)
    obs=m['correspondences'][0]
    pred=expected_reflection(cam,plane,obs['object_world_xyz'])
    hit=pred['mirror_hit_world']
    m['mirror_plane']['polygon_world']=[(hit+[-.005,0,-.005]).tolist(),(hit+[.005,0,-.005]).tolist(),
                                         (hit+[.005,0,.005]).tolist(),(hit+[-.005,0,.005]).tolist()]
    report=analyze_mirror_manifest(m)
    assert report['indeterminate_count']>=10
    assert report['state']=='INDETERMINATE'


def test_observed_pixel_outside_mirror_is_not_accepted():
    m,_,_,cam,plane=fixture(noise_px=0,corrupt=0)
    m['correspondences'][0]['reflection_xy']=[-100000.,30000.]
    rep=analyze_mirror_manifest(m)
    assert rep['correspondences'][0]['status']=='INDETERMINATE'


def test_camera_rotation_must_be_proper():
    m,_,_,_,_=fixture()
    m['camera']['R_world_to_camera']=[[-1,0,0],[0,1,0],[0,0,1]]
    with pytest.raises(MirrorGeometryError,match='rotation'):
        analyze_mirror_manifest(m)


def test_invalid_K_rejected():
    m,_,_,_,_=fixture()
    m['camera']['K'][0][0]=0
    with pytest.raises(MirrorGeometryError,match='K must'):
        analyze_mirror_manifest(m)


def test_camera_on_mirror_plane_cannot_observe_virtual_reflection():
    m,_,_,_,_=fixture()
    # place camera center exactly on mirror plane, retaining R
    R=np.asarray(m['camera']['R_world_to_camera']); center=np.array([0.,0.,1.75])
    m['camera']['t_world_to_camera']=(-R@center).tolist()
    report=analyze_mirror_manifest(m)
    assert report['state']=='INDETERMINATE'


def test_bad_identifiers_are_rejected():
    m,_,_,_,_=fixture()
    m['correspondences'][1]['id']=m['correspondences'][0]['id']
    with pytest.raises(MirrorGeometryError,match='duplicate'):
        analyze_mirror_manifest(m)


def test_reject_extraneous_nan_and_negative_tolerance():
    m,_,_,_,_=fixture()
    with pytest.raises(MirrorGeometryError,match='tolerance'):
        analyze_mirror_manifest(m,tolerance_px=-1)
    m['correspondences'][0]['object_world_xyz'][0]=float('nan')
    with pytest.raises(MirrorGeometryError,match='finite'):
        analyze_mirror_manifest(m)


def test_json_and_overlay_roundtrip(tmp_path):
    m,frame,_,_,_=fixture(n=12,noise_px=.15,corrupt=2)
    path=tmp_path/'manifest.json';path.write_text(json.dumps(m),encoding='utf-8')
    import cv2
    imp=tmp_path/'mirror.png';cv2.imwrite(str(imp),frame)
    result=run_mirror_manifest(path,tmp_path/'out',imp)
    assert result['state']=='MIXED_EVIDENCE'
    assert (tmp_path/'out'/'p3_r01_overlay.png').is_file()
    saved=json.loads((tmp_path/'out'/'p3_r01_report.json').read_text())
    assert saved['manifest_sha256']==result['manifest_sha256']
    assert saved['image_sha256']==result['image_sha256']


def test_image_shape_mismatch_rejected(tmp_path):
    m,frame,_,_,_=fixture()
    import cv2
    path=tmp_path/'data.json';path.write_text(json.dumps(m))
    image=tmp_path/'wrong.png';cv2.imwrite(str(image),frame[:200,:200])
    with pytest.raises(MirrorGeometryError,match='image shape'):
        run_mirror_manifest(path,tmp_path/'out',image)
