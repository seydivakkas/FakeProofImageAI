import numpy as np
import pytest
from aiforensics.homography import validate_planar_homography,HomographyError


def case():
    world=np.array([(x,y) for y in [0.,1.,2.] for x in [0.,1.,2.,3.]],float)
    H=np.array([[150.,12.,120.],[8.,110.,65.],[.03,.05,1.]])
    h=np.column_stack([world,np.ones(len(world))])@H.T
    image=h[:,:2]/h[:,2:]
    train=[0,1,3,4,5,7,8,9]
    return world,image,train


def test_exact_holdout():
    world,img,tr=case()
    r=validate_planar_homography(world,img,tr)
    assert r['state']=='MEASURED',r
    assert r['holdout_reprojection_rmse_px']<.01
    assert len(r['holdout_indices'])==4


def test_independent_holdout_anomaly():
    w,im,tr=case(); im[10]+=np.array([30,15])
    r=validate_planar_homography(w,im,tr)
    assert r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS'
    assert r['holdout_reprojection_rmse_px']>10


def test_noise_small():
    w,im,tr=case()
    im+=np.random.default_rng(25).normal(0,.1,im.shape)
    r=validate_planar_homography(w,im,tr)
    assert r['state']=='MEASURED',r
    assert r['holdout_reprojection_rmse_px']<2


def test_collinear_training_returns_indeterminate():
    w,im,tr=case();tr=[0,1,2,3]
    r=validate_planar_homography(w,im,tr)
    assert r['state']=='INDETERMINATE'


def test_invalid_indices_or_duplicate_correspondence():
    w,im,tr=case()
    with pytest.raises(HomographyError):validate_planar_homography(w,im,[0,1,1,2,3])
    w[2]=w[1]
    with pytest.raises(HomographyError):validate_planar_homography(w,im,tr)
