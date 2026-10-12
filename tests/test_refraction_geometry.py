"""P3-R02 synthetic physics, negative controls and integration tests."""
import copy
import json
import subprocess
import sys

import numpy as np
import pytest

from aiforensics.mirror_geometry import (CalibratedCamera, TotalInternalReflection,
                                         refract_direction)
from aiforensics.refraction_geometry import (
    RefractiveInterface, RefractionGeometryError, solve_planar_refraction,
    trace_observed_ray, analyze_refraction_manifest, run_refraction_manifest,
    overlay_refraction)
from aiforensics.refraction_synthetic import synthetic_refraction_scene


def scene(model='single_interface', **kw):
    data,image,truth=synthetic_refraction_scene(model=model,n=13,corrupt=2,noise_px=0.,**kw)
    return data,image,truth


def compute(data, j=0):
    return solve_planar_refraction(CalibratedCamera.from_manifest(data['camera']),
             RefractiveInterface.from_manifest(data['interface']),
             data['correspondences'][j]['object_world_xyz'])


@pytest.mark.parametrize('model', ['single_interface','parallel_slab'])
def test_model_zero_residual_perfect_points(model):
    data,_,_=scene(model)
    report=analyze_refraction_manifest(data,tolerance_px=1.)
    assert report['consistent_count']==11
    assert report['inconsistent_count']==2
    assert report['indeterminate_count']==0
    assert report['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert max(r['reprojection_residual_px'] for r in report['correspondences'][:11])<1e-8


@pytest.mark.parametrize('model', ['single_interface','parallel_slab'])
def test_identical_all_media_has_no_image_shift(model):
    data,_,_=scene(model,n_camera=1.,n_layer=1.,n_beyond=1.)
    for j in range(11):
        x=compute(data,j)
        assert x['pixel_shift_norm_px']<1e-9
        assert x['snell_residual']<1e-12


def test_water_single_interface_causes_nonzero_angular_shift():
    data,_,_=scene()
    assert max(compute(data,j)['pixel_shift_norm_px'] for j in range(11))>5.


def test_parallel_glass_outgoing_ray_parallel_incoming():
    data,_,_=scene('parallel_slab',n_camera=1.,n_layer=1.5,n_beyond=1.)
    for j in range(11):
        x=compute(data,j)
        C,A,B,P=[np.asarray(t) for t in x['ray_points_world']]
        d1=(A-C)/np.linalg.norm(A-C)
        d3=(P-B)/np.linalg.norm(P-B)
        assert np.linalg.norm(d1-d3)<1e-10
        assert x['snell_residual']<1e-12
    assert max(compute(data,j)['pixel_shift_norm_px'] for j in range(11))>0.1


def test_normal_incidence_no_shift():
    data,_,_=scene()
    data['correspondences'][0]['object_world_xyz']=[0,0,7]
    x=compute(data)
    assert np.linalg.norm(x['pixel_shift_xy'])<1e-10


def test_snell_angle_law_nonzero_angle():
    data,_,_=scene('single_interface')
    x=max((compute(data,j) for j in range(11)),key=lambda x:x['interface_incidence_angles_deg'][0])
    a,b=np.deg2rad(x['interface_incidence_angles_deg'])
    assert abs(1.*np.sin(a)-1.333*np.sin(b))<1e-12
    assert a>b


def test_tir_ray_from_glass_to_air():
    ray=np.array([np.sqrt(3)/2,0.,.5])
    with pytest.raises(TotalInternalReflection):
        refract_direction(ray,[0.,0.,-1.],1.5,1.)


def test_critical_angle_boundary_and_subcritical():
    theta=np.arcsin(1/1.5)
    sub=np.sin(theta-.05); ray=np.array([sub,0.,np.sqrt(1-sub*sub)])
    assert np.isfinite(refract_direction(ray,[0,0,-1],1.5,1.)).all()
    supertheta=theta+.04
    with pytest.raises(TotalInternalReflection):
        refract_direction([np.sin(supertheta),0,np.cos(supertheta)],[0,0,-1],1.5,1.)


@pytest.mark.parametrize('model', ['single_interface','parallel_slab'])
def test_trace_exact_expected_ray_returns_known_3d_point(model):
    data,_,_=scene(model)
    camera=CalibratedCamera.from_manifest(data['camera'])
    interface=RefractiveInterface.from_manifest(data['interface'])
    for i in range(11):
        P=data['correspondences'][i]['object_world_xyz']
        x=solve_planar_refraction(camera,interface,P)
        trace=trace_observed_ray(camera,interface,x['expected_xy'],P)
        assert trace['traced_world_error']<1e-9


def test_apparent_position_shift_differs_from_zero():
    data,_,_=scene()
    camera=CalibratedCamera.from_manifest(data['camera'])
    interface=RefractiveInterface.from_manifest(data['interface'])
    x=max((compute(data,j) for j in range(11)),key=lambda x:x['pixel_shift_norm_px'])
    P=data['correspondences'][np.argmax([compute(data,j)['pixel_shift_norm_px'] for j in range(11)])]['object_world_xyz']
    trace=trace_observed_ray(camera,interface,x['expected_xy'],P)
    assert trace['apparent_position_shift_world']>.02


def test_index_order_covers_dense_camera_medium():
    data,_,_=scene(n_camera=1.52,n_layer=1.)
    x=compute(data)
    assert x['snell_residual']<1e-12


@pytest.mark.parametrize('key, value', [
    ('normal_toward_camera_world',[0,0,0]),
    ('normal_toward_camera_world',[0,0,1]),
    ('point_world',[1,2]),
    ('n_layer',0),('n_layer',-1.0),('n_layer',float('nan')),
    ('model','unknown')])
def test_bad_interface_data_fail_closed(key,value):
    data,_,_=scene()
    data['interface'][key]=value
    with pytest.raises((RefractionGeometryError,ValueError)):
        analyze_refraction_manifest(data)


@pytest.mark.parametrize('thickness', [0,-1,float('nan')])
def test_slab_bad_thickness(thickness):
    data,_,_=scene('parallel_slab')
    data['interface']['thickness_world']=thickness
    with pytest.raises(RefractionGeometryError):
        analyze_refraction_manifest(data)


def test_slab_requires_index_beyond():
    data,_,_=scene('parallel_slab')
    data['interface'].pop('n_beyond')
    with pytest.raises(RefractionGeometryError):analyze_refraction_manifest(data)


def test_object_in_wrong_medium_is_indeterminate_not_inconsistent():
    data,_,_=scene()
    data['correspondences'][0]['object_world_xyz']=[.2,.1,1.]
    report=analyze_refraction_manifest(data)
    assert report['correspondences'][0]['state']=='INDETERMINATE'


def test_observation_outside_sensor_indeterminate():
    data,_,_=scene()
    data['correspondences'][1]['observed_xy']=[-3,50]
    report=analyze_refraction_manifest(data)
    assert report['correspondences'][1]['state']=='INDETERMINATE'


def test_inconsistent_observation_explicit():
    data,_,_=scene()
    data['correspondences'][3]['observed_xy'][0]+=40
    out=analyze_refraction_manifest(data)
    assert out['correspondences'][3]['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'


def test_all_points_unobservable_no_false_pass():
    data,_,_=scene()
    for x in data['correspondences']:x['object_world_xyz']=[0,0,1]
    report=analyze_refraction_manifest(data)
    assert report['state']=='INDETERMINATE'
    assert report['consistent_count']==0
    assert report['indeterminate_count']==13


def test_aperture_miss_is_indeterminate():
    data,_,_=scene()
    data['interface']['polygon_world']=[[-.1,-.1,3], [.1,-.1,3], [.1,.1,3],[-.1,.1,3]]
    report=analyze_refraction_manifest(data)
    assert report['indeterminate_count']>0


def test_slab_rear_aperture_miss():
    data,_,_=scene('parallel_slab')
    data['interface']['polygon_world']=[[-.12,-.12,3],[.12,-.12,3],[.12,.12,3],[-.12,.12,3]]
    assert analyze_refraction_manifest(data)['indeterminate_count']>0


def test_polygon_vertices_nonplanar_rejected():
    data,_,_=scene()
    data['interface']['polygon_world']=[[0,0,3],[1,0,3],[1,1,2],[0,1,3]]
    with pytest.raises(ValueError):analyze_refraction_manifest(data)


def test_manifest_duplicate_id_rejected():
    data,_,_=scene()
    data['correspondences'][1]['id']=data['correspondences'][0]['id']
    with pytest.raises(RefractionGeometryError):analyze_refraction_manifest(data)


def test_nonorthogonal_camera_rejected():
    data,_,_=scene()
    data['camera']['R_world_to_camera'][0][0]=1.4
    with pytest.raises(RefractionGeometryError):analyze_refraction_manifest(data)


def test_image_shape_invalid_rejected():
    data,_,_=scene();data['image_shape_hw']=[0,500]
    with pytest.raises(RefractionGeometryError):analyze_refraction_manifest(data)


def test_confidence_zero_rejected():
    data,_,_=scene();data['correspondences'][2]['confidence']=0.
    with pytest.raises(RefractionGeometryError):analyze_refraction_manifest(data)


def test_min_observable_count():
    data,_,_=scene()
    out=analyze_refraction_manifest(data,min_pairs=14)
    assert out['state']=='INDETERMINATE'


def test_overlay_and_report_files(tmp_path):
    data,image,truth=scene()
    f=tmp_path/'manifest.json';f.write_text(json.dumps(data))
    from cv2 import imwrite
    source=tmp_path/'image.png';imwrite(str(source),image)
    report=run_refraction_manifest(f,tmp_path/'out',source)
    assert report['consistent_count']==truth['known_good']
    assert (tmp_path/'out'/'p3_r02_report.json').is_file()
    assert (tmp_path/'out'/'p3_r02_overlay.png').is_file()
    assert overlay_refraction(image,report).shape==image.shape


def test_cli_demo_and_analysis(tmp_path):
    demo=tmp_path/'demo'
    p=subprocess.run([sys.executable,'-m','aiforensics','demo-refraction','--out',str(demo)],
                     capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert (demo/'p3_r02_fixture.json').is_file()
    analysis=tmp_path/'analysis'
    p=subprocess.run([sys.executable,'-m','aiforensics','analyze-refraction',
                      '--input',str(demo/'p3_r02_fixture.json'),
                      '--image',str(demo/'p3_r02_fixture.png'),
                      '--out',str(analysis)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    result=json.loads((analysis/'p3_r02_report.json').read_text())
    assert result['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert result['consistent_count']==15
    assert result['inconsistent_count']==3


def test_coordinate_rotation_invariance():
    # Rotating all world geometry together does not alter the camera pixels.
    data,_,_=scene()
    baseline=compute(data,0)['expected_xy']
    a=np.deg2rad(23.);b=np.deg2rad(-18.)
    Z=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1.]])
    Y=np.array([[np.cos(b),0,np.sin(b)],[0,1,0],[-np.sin(b),0,np.cos(b)]])
    W=Z@Y
    data['camera']['R_world_to_camera']=W.T.tolist()
    data['interface']['point_world']=(W@np.array([0,0,3.])).tolist()
    data['interface']['normal_toward_camera_world']=(W@np.array([0,0,-1.])).tolist()
    for r in data['correspondences']:
        r['object_world_xyz']=(W@np.asarray(r['object_world_xyz'])).tolist()
    adjusted=compute(data,0)['expected_xy']
    assert np.allclose(adjusted,baseline,atol=1e-9)


def test_tir_in_full_ray_trace_produces_no_transmitted_point():
    data,_,_=scene(n_camera=1.5,n_layer=1.)
    cam=CalibratedCamera.from_manifest(data['camera'])
    face=RefractiveInterface.from_manifest(data['interface'])
    with pytest.raises(TotalInternalReflection):
        trace_observed_ray(cam,face,[2000,360],[0,0,7])


def test_benchmark_reproducible_small(tmp_path):
    from scripts.p3_refraction_benchmark import run
    p=tmp_path/'sample.json'
    x=run(6,p);y=run(6,p)
    assert x==y
    assert x['exact_assignment_trials']==6
    assert x['report_class']=='SYNTHETIC_CONTROLLED_ONLY'


def test_slab_stress_nonmatching_exit_index():
    data,_,_=scene('parallel_slab',n_camera=1.,n_layer=1.5,n_beyond=1.333)
    x=compute(data)
    assert len(x['interface_incidence_angles_deg'])==3
    assert x['snell_residual']<1e-12


def test_index_estimation_from_disjoint_training_points():
    from aiforensics.refraction_index import estimate_index_manifest
    data,_,_=synthetic_refraction_scene(model='single_interface',n=24,corrupt=3,noise_px=.2,seed=15)
    data['interface'].pop('n_layer')
    report=estimate_index_manifest(data,tolerance_px=3.)
    assert abs(report['estimated_n_layer']-1.333)<.015
    assert report['train_count']==12
    assert report['holdout_count']==12
    assert report['holdout_validation']['consistent_count']==9
    assert report['holdout_validation']['inconsistent_count']==3


def test_index_no_bogus_certification_without_explicit_holdout():
    from aiforensics.refraction_index import estimate_index_manifest
    data,_,_=scene()
    data.pop('index_fit')
    with pytest.raises(RefractionGeometryError):
        estimate_index_manifest(data)


def test_index_disjoint_id_required():
    from aiforensics.refraction_index import estimate_index_manifest
    data,_,_=scene()
    data['index_fit']['holdout_ids'][0]=data['index_fit']['train_ids'][0]
    with pytest.raises(RefractionGeometryError):estimate_index_manifest(data)


def test_index_nonidentifiable_near_normal():
    from aiforensics.refraction_index import pointwise_index
    data,_,_=scene()
    cam=CalibratedCamera.from_manifest(data['camera'])
    face=RefractiveInterface.from_manifest(data['interface'])
    with pytest.raises(RefractionGeometryError):
        pointwise_index(cam,face,[0,0,7],[640,360])


def test_index_slab_is_not_fit_with_single_boundary_equations():
    from aiforensics.refraction_index import estimate_index_manifest
    data,_,_=scene('parallel_slab')
    with pytest.raises(RefractionGeometryError):estimate_index_manifest(data)


def test_cli_estimate_index(tmp_path):
    demo=tmp_path/'water';demo.mkdir()
    data,_,_=synthetic_refraction_scene(n=24,corrupt=2,noise_px=.18,seed=19)
    data['interface'].pop('n_layer')
    path=demo/'manifest.json';path.write_text(json.dumps(data))
    p=subprocess.run([sys.executable,'-m','aiforensics','estimate-refraction-index',
                      '--input',str(path),'--out',str(tmp_path/'fit')],
                     capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    report=json.loads((tmp_path/'fit'/'p3_r02_index_report.json').read_text())
    assert abs(report['estimated_n_layer']-1.333)<.02
    assert report['holdout_count']==12
