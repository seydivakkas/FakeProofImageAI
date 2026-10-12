import sys
from pathlib import Path
import json
import numpy as np
import cv2
from scipy.io import savemat
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_york_manifest import prepare
from aiforensics.real_validation import RealValidationError


def test_independent_york_manifest_contract(tmp_path):
    im=tmp_path/'photo.jpg';cv2.imwrite(str(im),np.zeros((80,120,3),np.uint8))
    params=tmp_path/'cameraParameters.mat'
    savemat(params,{'focal':np.array([[9.]]),'pixelSize':np.array([[.01]]),'pp':np.array([[60.,40.]])})
    labels=tmp_path/'labels.json'; labels.write_text(json.dumps({'group_label_provenance':'human_independently_annotated',
        'orthogonal_groups':[[[5+j,10,5+j,60] for j in range(i*10,i*10+10)] for i in range(3)]}))
    manifest=prepare(im,params,labels)
    assert manifest['known_intrinsics_K'][0][0]==900
    assert all(len(a)>=3 for a in manifest['holdout_orthogonal_groups'])
    assert im.with_suffix('.g02_manifest.json').is_file()
    assert manifest['capture_type']=='real_camera'
    # These labels are numerically invalid Manhattan geometry, so the resulting
    # manifest is an input CONTRACT test, never a real calibration acceptance.


def test_ground_truth_derived_annotations_rejected(tmp_path):
    im=tmp_path/'photo.jpg';cv2.imwrite(str(im),np.zeros((80,120,3),np.uint8))
    params=tmp_path/'camera.mat';savemat(params,{'focal':[[9.]],'pixelSize':[[.01]],'pp':[[60.,40.]]})
    labels=tmp_path/'labels.json';labels.write_text(json.dumps({'group_label_provenance':'K_derived_automatic',
        'orthogonal_groups':[[[1,2,3,4]]*10]*3}))
    with pytest.raises(RealValidationError,match='leak'):
        prepare(im,params,labels)
