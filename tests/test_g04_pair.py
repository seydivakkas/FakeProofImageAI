import numpy as np
import cv2
from aiforensics.g04_pair import match_photo_pair


def test_photographic_pixel_like_warp_with_feature_outliers_abstains():
    rng=np.random.default_rng(77)
    img=np.zeros((370,570,3),dtype=np.uint8)
    for i in range(140):
        x=int(rng.integers(20,540));y=int(rng.integers(20,330))
        cv2.circle(img,(x,y),int(rng.integers(2,8)),
                   tuple(int(v) for v in rng.integers(70,255,3)),-1)
    a=np.float32([[0,0],[569,0],[569,369],[0,369]])
    b=np.float32([[10,12],[550,8],[560,356],[15,362]])
    warp=cv2.getPerspectiveTransform(a,b)
    other=cv2.warpPerspective(img,warp,(570,370))
    r=match_photo_pair(img,other)
    assert r['status'].startswith('DESCRIPTIVE_PAIR_MATCHES')
    assert r['physical_consistency_verdict']=='NOT_ASSESSED_WITH_INDEPENDENT_PLANE_MATCHES'
    assert r['holdout_match_diagnostics']['median_error_all_px']<2.
    assert r['decision']=='NO_AI_ORIGIN_CONCLUSION'


def test_blank_pair_returns_indeterminate():
    a=np.zeros((200,300,3),np.uint8)
    assert match_photo_pair(a,a)['status']=='INDETERMINATE'
