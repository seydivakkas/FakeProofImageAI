"""Photographic image content tests; these are not independent field calibration."""
import pytest
import cv2
import numpy as np

scikit = pytest.importorskip('skimage',reason='Install .[benchmark] for real-pixel tests')
from skimage import data
from aiforensics.region_patterns import PlaneRegion,analyze_regions
from aiforensics.g04_pair import match_photo_pair


def test_brick_photo_patterns_and_no_semantic_overclaim():
    brick=cv2.cvtColor(data.brick(),cv2.COLOR_GRAY2BGR)
    r=analyze_regions(brick,[PlaneRegion('wall_like',((2,2),(509,2),(509,509),(2,509)),
                                                 'wall','unverified_candidate')])
    region=r['regions'][0]
    assert region['rectangular_candidates']>10
    assert region['plane_label']=='unknown' # no independent semantic GT
    assert region['physical_spacing_evidence']=='NOT_MEASURED'


def test_rocket_real_photographic_pixels_controlled_warp():
    im=cv2.cvtColor(data.rocket(),cv2.COLOR_RGB2BGR)
    h,w=im.shape[:2]
    src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    dst=np.float32([[14,15],[w-22,5],[w-5,h-23],[18,h-9]])
    H=cv2.getPerspectiveTransform(src,dst)
    other=cv2.warpPerspective(im,H,(w,h))
    r=match_photo_pair(im,other)
    assert r['status'].startswith('DESCRIPTIVE_')
    assert r['holdout_match_diagnostics']['median_error_all_px']<1
    assert r['holdout_match_diagnostics']['inlier_fraction_at_3px']>.80
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_real_stereo_pair_is_descriptive_not_a_physical_verdict():
    a,b,_=data.stereo_motorcycle()
    pair=match_photo_pair(cv2.cvtColor(a,cv2.COLOR_RGB2BGR),
                          cv2.cvtColor(b,cv2.COLOR_RGB2BGR))
    assert pair['status'].startswith('DESCRIPTIVE_')
    assert pair['holdout_count']>20
    assert pair['physical_consistency_verdict']=='NOT_ASSESSED_WITH_INDEPENDENT_PLANE_MATCHES'
