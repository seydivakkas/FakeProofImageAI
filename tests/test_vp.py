import numpy as np
from aiforensics.vp import VPConfig, fit_vp, find_vps
from aiforensics.synthetic import noisy_vp_case, render_corridor
from aiforensics.imaging import detect_segments


FAST=VPConfig(max_trials=500, bootstrap_trials=0)


def test_noisy_vp_with_outliers():
    seg, mask, ground = noisy_vp_case(seed=12,endpoint_sigma_px=.5)
    fit=fit_vp(seg,(720,1280),FAST)
    assert fit is not None
    assert np.linalg.norm(np.asarray(fit.xy)-ground) < 5
    assert len(fit.inlier_indices) >= 28
    assert fit.residual_rmse_px < 3.0


def test_missing_evidence_returns_none():
    assert fit_vp(np.empty((0,4)),(720,1280),FAST) is None
    parallels=np.array([[0,y,300,y] for y in [10,40,70,100,130,160,190]])
    assert fit_vp(parallels,(720,1280),FAST) is None


def test_one_direction_not_claimed_ai_origin():
    seg, _, _=noisy_vp_case(seed=3)
    fits=find_vps(seg,(720,1280),max_models=2,config=FAST)
    assert fits
    assert fits[0].finite_model_only
    assert all(hasattr(f,"residual_rmse_px") for f in fits)


def test_rendered_corridor_detects_geometric_structure():
    image,truth=render_corridor(width=960,height=540)
    seg=detect_segments(image,min_length_px=30)
    assert len(seg)>10
    fits=find_vps(seg,image.shape[:2],max_models=3,config=FAST)
    assert fits
    assert any(np.linalg.norm(np.asarray(f.xy)-np.asarray(truth))<12 for f in fits)


def test_two_distinct_directions_are_not_a_fake_flag():
    a, _, _ = noisy_vp_case(vp=(320,240), inlier_count=36,
                            outlier_count=0, seed=51)
    b, _, _ = noisy_vp_case(vp=(960,450), inlier_count=36,
                            outlier_count=0, seed=52)
    all_segments=np.concatenate([a,b])
    fits=find_vps(all_segments,(720,1280),max_models=3,config=FAST)
    assert len(fits)>=2
    assert any(np.linalg.norm(np.asarray(f.xy) - [320,240]) < 8 for f in fits)
    assert any(np.linalg.norm(np.asarray(f.xy) - [960,450]) < 8 for f in fits)
