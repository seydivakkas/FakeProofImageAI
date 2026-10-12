"""Physics-first P2-S04 analytic, robustness, degen and negative-control tests."""
import json
import numpy as np
import cv2
import pytest
from copy import deepcopy
from aiforensics.solar_geometry import (
    solar_position_noaa, sun_direction_from_angles, angles_from_sun_direction,
    cast_shadow_to_plane, analyze_solar_geometry, SolarGeometryError,SolarConfig,run_solar_manifest)
from aiforensics.solar_synthetic import synthetic_solar_scene


def test_direction_cardinal_and_wraparound():
    cases=[(0,0,[0,1,0]),(90,0,[1,0,0]),(180,0,[0,-1,0]),(270,0,[-1,0,0]),(0,90,[0,0,1])]
    for az,el,expect in cases:
        v=sun_direction_from_angles(az,el)
        assert np.allclose(v,expect,atol=1e-10)
        a,e=angles_from_sun_direction(v)
        assert abs(e-el)<1e-8
        if el!=90:assert abs(a-az)<1e-8
        else:assert a is None


def test_shadow_length_horizontal_ground_formula():
    H=1.75;el=35.;v=sun_direction_from_angles(100,el)
    P=np.array([0.,0.,H]);q=cast_shadow_to_plane(P,v,[0.,0.,1.],0)
    assert abs(q[2])<1e-12
    assert abs(np.linalg.norm(q[:2])-H/np.tan(np.deg2rad(el)))<1e-10
    assert np.dot(q[:2],v[:2])<0


def test_sloped_plane_geometric_intersection():
    a,b=.12,-.08
    n=np.array([-a,-b,1.]);n/=np.linalg.norm(n)
    p=np.array([1.,1.,a+b+1.1]);sun=sun_direction_from_angles(135,44)
    q=cast_shadow_to_plane(p,sun,n,0)
    assert abs(n@q)<1e-10
    assert np.linalg.norm(np.cross(p-q,sun))<1e-10


def test_noaa_equinox_equator_noon_close_to_zenith():
    # Independent physical sanity: equinox at equator close to overhead at UTC solar noon.
    p=solar_position_noaa(0,0,'2025-03-20T12:00:00Z')
    assert p['sun_above_geometric_horizon']
    assert p['elevation_deg']>87
    assert np.isfinite(p['direction_enu']).all()


def test_noaa_symmetry_east_morning_west_afternoon():
    morning=solar_position_noaa(0,0,'2025-03-20T09:00:00Z')
    after=solar_position_noaa(0,0,'2025-03-20T15:00:00Z')
    assert 60<morning['azimuth_deg_clockwise_from_true_north']<120
    assert 240<after['azimuth_deg_clockwise_from_true_north']<300
    assert morning['elevation_deg']>0 and after['elevation_deg']>0


def test_noaa_night_below_horizon():
    r=solar_position_noaa(0,0,'2025-03-20T00:00:00Z')
    assert r['elevation_deg']<0


def test_noaa_invalid_times_and_locations():
    for stamp in ['2025-06-21T12:00:00','2025-06-21T15:00:00+03:00','invalid']:
        with pytest.raises(SolarGeometryError):solar_position_noaa(41,29,stamp)
    for lat,lon in [(91,0),(0,181),(float('nan'),0)]:
        with pytest.raises(SolarGeometryError):solar_position_noaa(lat,lon,'2025-06-21T12:00:00Z')


def test_noise_free_known_sun_position():
    d,_,truth=synthetic_solar_scene(n=15)
    r=analyze_solar_geometry(d)
    assert r['state']=='MEASURED',r
    assert r['direction_fit']['inlier_count']==15
    assert abs(r['measured_sun_elevation_deg']-truth['sun_elevation_deg'])<1e-7
    assert abs(r['measured_sun_azimuth_deg']-truth['sun_azimuth_deg'])<1e-7
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_azimuth_shadow_direction_opposite():
    d,_,_=synthetic_solar_scene(n=12,azimuth_deg=356,elevation_deg=38)
    r=analyze_solar_geometry(d)
    assert r['state']=='MEASURED'
    assert abs(r['shadow_azimuth_deg']-176)<1e-6


def test_noisy_and_wrong_matches_excluded():
    d,_,truth=synthetic_solar_scene(n=22,noise_px=.2,wrong_pairs=4)
    r=analyze_solar_geometry(d)
    assert r['state']=='MEASURED',r.get('reason')
    assert abs(r['measured_sun_elevation_deg']-truth['sun_elevation_deg'])<2.
    assert abs(r['measured_sun_azimuth_deg']-truth['sun_azimuth_deg'])<2.
    assert r['direction_fit']['inlier_count']>=18
    assert len(r['direction_fit']['excluded_ids'])>=4


def test_sloped_ground_valid_not_naive_ratio():
    d,_,truth=synthetic_solar_scene(n=18,slope_x=.12,slope_y=-.07)
    r=analyze_solar_geometry(d)
    assert r['state']=='MEASURED'
    assert abs(r['measured_sun_elevation_deg']-truth['sun_elevation_deg'])<1e-7


def test_claim_matches_generated_sun():
    claim={'latitude_deg':41.0,'longitude_deg':29.0,'timestamp_utc':'2025-06-21T09:00:00Z'}
    d,_,_=synthetic_solar_scene(solar_claim=claim)
    r=analyze_solar_geometry(d)
    assert r['ephemeris_comparison']['state']=='CONSISTENT_UNDER_ASSUMPTIONS'
    assert r['ephemeris_comparison']['direction_angle_difference_deg']<1e-6


def test_claim_mismatch_produces_inconsistency_not_fake_verdict():
    d,_,_=synthetic_solar_scene()
    d['solar_claim']={'latitude_deg':41.0,'longitude_deg':29.0,'timestamp_utc':'2025-06-21T09:00:00Z'}
    r=analyze_solar_geometry(d)
    assert r['ephemeris_comparison']['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_night_claim_abstains():
    d,_,_=synthetic_solar_scene()
    d['solar_claim']={'latitude_deg':0.0,'longitude_deg':0.0,'timestamp_utc':'2025-03-20T00:00:00Z'}
    r=analyze_solar_geometry(d)
    assert r['ephemeris_comparison']['state']=='INDETERMINATE'


def test_bad_tip_annotation_rejected_not_physical_inconsistency():
    d,_,_=synthetic_solar_scene()
    d['correspondences'][0]['tip_xy'][0]+=70
    r=analyze_solar_geometry(d)
    assert any(x['id']=='sun_pair_000' for x in r['rejected_pairs'])
    assert r['state']=='MEASURED'


def test_missing_frame_units_and_height_fail_closed():
    for key in ('world_frame','world_units'):
        d,_,_=synthetic_solar_scene()
        del d[key]
        with pytest.raises(SolarGeometryError):analyze_solar_geometry(d)
    d,_,_=synthetic_solar_scene()
    d['correspondences'][0]['object_height_m']=-1
    with pytest.raises(SolarGeometryError):analyze_solar_geometry(d)


def test_wrong_camera_pose_causes_tip_reprojection_rejection():
    d,_,_=synthetic_solar_scene()
    # Inject incorrect rotation while keeping R a proper 3D rotation.
    theta=np.deg2rad(30.)
    rot=np.array([[1.,0.,0.],[0.,np.cos(theta),-np.sin(theta)],[0.,np.sin(theta),np.cos(theta)]])
    d['camera']['R_world_to_camera']=(rot@np.array(d['camera']['R_world_to_camera'])).tolist()
    r=analyze_solar_geometry(d)
    assert r['state']=='INDETERMINATE'
    assert len(r['rejected_pairs'])>0


def test_few_correspondences_abstain():
    d,_,_=synthetic_solar_scene()
    d['correspondences']=d['correspondences'][:2]
    r=analyze_solar_geometry(d)
    assert r['state']=='INDETERMINATE'


def test_mixed_two_lights_abstain_if_neither_supports_threshold():
    d,_,_=synthetic_solar_scene(n=20)
    different,_,_=synthetic_solar_scene(n=20,azimuth_deg=260,elevation_deg=55,seed=47)
    d['correspondences']=d['correspondences'][:10]+different['correspondences'][:10]
    for i,x in enumerate(d['correspondences']): x['id']=f'mixed_{i}'
    r=analyze_solar_geometry(d)
    assert r['state']=='INDETERMINATE'


def test_repeatable_results():
    d,_,_=synthetic_solar_scene(noise_px=.15,wrong_pairs=2)
    assert analyze_solar_geometry(d)==analyze_solar_geometry(d)


def test_cli_file_and_image_overlay(tmp_path):
    d,img,_=synthetic_solar_scene(n=14,noise_px=.1)
    file=tmp_path/'s.json';file.write_text(json.dumps(d))
    image=tmp_path/'s.png';cv2.imwrite(str(image),img)
    r=run_solar_manifest(file,tmp_path/'out',image)
    assert r['state']=='MEASURED'
    assert (tmp_path/'out/p2_s04_report.json').is_file()
    assert (tmp_path/'out/p2_s04_overlay.png').is_file()
    assert len(r['input_sha256'])==64
    with pytest.raises(SolarGeometryError):
        wrong=tmp_path/'wrong.png';cv2.imwrite(str(wrong),img[:100]);run_solar_manifest(file,tmp_path/'wrongout',wrong)


def test_invalid_config():
    for args in [{'min_pairs':2},{'direction_tolerance_deg':0},{'min_support_fraction':1.3},
                 {'ransac_trials':0},{'tip_reprojection_tolerance_px':-1}]:
        with pytest.raises(SolarGeometryError):SolarConfig(**args)


def test_no_ephemeris_without_claim():
    d,_,_=synthetic_solar_scene()
    r=analyze_solar_geometry(d)
    assert r['ephemeris_comparison']['state']=='NOT_REQUESTED'


def test_nonhorizontal_horizon_does_not_mean_sun_inconsistent():
    d,_,_=synthetic_solar_scene(slope_x=.2,slope_y=.12)
    r=analyze_solar_geometry(d)
    assert r['state']=='MEASURED'
