import numpy as np
import cv2
from aiforensics.auto_patterns import detect_repeated_candidates,PatternConfig


def test_synthetic_repeated_marks_with_independent_segments():
    im=np.zeros((600,800,3),np.uint8)
    supports=[[400,35,400,555],[180,40,180,560]]
    crossbars=[[80,y,710,y] for y in [90,150,205,260,321,390,475]]
    seg=np.asarray(supports+crossbars,float)
    found=detect_repeated_candidates(im,PatternConfig(min_support_length_px=150,min_marks=5),seg)
    assert found and len(found[0]['points_xy'])>=5
    assert found[0]['evidence_state']=='CANDIDATE_ONLY_UNVERIFIED_WORLD_SPACING'
    assert found[0]['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert found[0]['hypothetical_lattice_fit']['holdout_rmse_px']>=0


def test_no_repetitions_no_candidate():
    im=np.zeros((300,400,3),np.uint8)
    seg=np.array([[20,30,300,30],[20,80,300,80],[20,120,300,120]],float)
    assert detect_repeated_candidates(im,PatternConfig(min_marks=5),seg)==[]


def test_detected_drawing_candidates():
    im=np.zeros((640,880,3),np.uint8)
    for x in [180,440,700]:cv2.line(im,(x,30),(x,600),(245,245,245),2)
    for y in [100,170,240,310,380,450,520]:cv2.line(im,(80,y),(780,y),(245,245,245),2)
    result=detect_repeated_candidates(im,PatternConfig(min_marks=5,min_support_length_px=150))
    assert len(result)>=1
    assert max(x['count'] for x in result)>=5


def test_invalid_segments():
    im=np.zeros((10,10,3),np.uint8)
    import pytest
    with pytest.raises(ValueError):detect_repeated_candidates(im,segments=np.ones((2,3)))
