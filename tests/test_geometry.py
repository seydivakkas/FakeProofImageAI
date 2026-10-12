import numpy as np
import pytest
from aiforensics.geometry import (segments_to_lines, intersect_lines,
                                  point_line_residuals, cross_ratio, project_points)


def test_intersection_and_residual():
    seg = np.array([[0,0,10,10],[0,10,10,0]])
    l=segments_to_lines(seg)
    vp=intersect_lines(*l)
    assert np.allclose(vp,[5,5])
    assert np.max(np.abs(point_line_residuals(l,vp))) < 1e-10


def test_infinite_intersection_not_treated_as_finite():
    l=segments_to_lines(np.array([[0,0,10,0],[0,10,10,10]]))
    assert intersect_lines(*l) is None


def test_cross_ratio_equispaced_and_projective_invariance():
    x=np.array([0.,1.,2.,3.])
    assert cross_ratio(x) == pytest.approx(4/3)
    mapped=(2*x+7)/(.1*x+1)
    assert cross_ratio(mapped)==pytest.approx(4/3)


def test_cross_ratio_invalid():
    with pytest.raises(ValueError):
        cross_ratio([1,1,1,1])


def test_pinhole_projection():
    K=np.array([[800.,0,640],[0,800.,360],[0,0,1]])
    p=project_points(np.array([[0.,0.,10.],[1.,0.,10.]]),K)
    assert np.allclose(p,[[640,360],[720,360]])
