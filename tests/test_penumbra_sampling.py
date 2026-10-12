"""Confirmed radiometric image scan contract, no unverified gamma assumptions."""
import json
import numpy as np
import pytest
from aiforensics.penumbra import PenumbraError,edge_irradiance,analyze_penumbra_manifest
from aiforensics.penumbra_sampling import extract_edge_profiles_from_array, run_sample_transects


def _scene():
    h,w=210,360
    X=np.arange(w,dtype=float)-w/2
    scene=np.stack([edge_irradiance(X,5.,3.4+i*.3,.13,.89,'right') for i in range(h)])
    transects=[]
    for i,row in enumerate((20,72,140,195)):
        transects.append({'id':f'transect_{i}','start_xy':[80,row],
            'end_xy':[285,row],'sample_count':250,'source_shape':'UNIFORM_DISK',
            'light_side':'right'})
    return scene,{'schema':'P2_S05_TRANSECTS_V1','radiometric_space':'LINEAR_RELATIVE_IRRADIANCE',
                  'declared_common_source':False,'transects':transects}


def test_extract_correct_linear_profiles():
    scene,manifest=_scene()
    result=extract_edge_profiles_from_array(scene,manifest)
    assert len(result['edges'])==4
    fit=analyze_penumbra_manifest(result)
    assert fit['profiles_measured']==4
    assert fit['state']=='INDETERMINATE' # no metric height/scale
    assert all(x['angular_diameter_deg'] is None for x in fit['evidence'])


def test_npy_file_pipeline(tmp_path):
    scene,manifest=_scene()
    np.save(tmp_path/'scene.npy',scene)
    (tmp_path/'transects.json').write_text(json.dumps(manifest))
    extracted=run_sample_transects(tmp_path/'scene.npy',tmp_path/'transects.json',tmp_path/'extracted.json')
    assert len(extracted['linear_image_sha256'])==64
    assert (tmp_path/'extracted.json').is_file()


def test_image_gamma_contract_and_bounds():
    scene,manifest=_scene()
    manifest['radiometric_space']='SRGB_UNKNOWN'
    with pytest.raises(PenumbraError):extract_edge_profiles_from_array(scene,manifest)
    scene,manifest=_scene()
    manifest['transects'][0]['end_xy']=[800,100]
    with pytest.raises(PenumbraError):extract_edge_profiles_from_array(scene,manifest)


def test_rgb_linear_luminance():
    scene,manifest=_scene()
    rgb=np.repeat(scene[:,:,None],3,axis=2)
    out=extract_edge_profiles_from_array(rgb,manifest)
    assert np.allclose(out['edges'][0]['linear_irradiance'],
                       extract_edge_profiles_from_array(scene,manifest)['edges'][0]['linear_irradiance'])


def test_reject_nonfinite_pixels():
    scene,manifest=_scene();scene[0,0]=np.nan
    with pytest.raises(PenumbraError):extract_edge_profiles_from_array(scene,manifest)
