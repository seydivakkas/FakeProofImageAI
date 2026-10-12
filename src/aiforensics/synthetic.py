"""Deterministic ground-truth controlled synthetic line cases and rendered corridor."""
from __future__ import annotations
import numpy as np
import cv2
from .geometry import project_points


def noisy_vp_case(image_shape=(720, 1280), vp=(640.0, 300.0),
                  inlier_count=35, outlier_count=20,
                  endpoint_sigma_px=0.5, seed=42):
    """Return (segments, inlier_ground_truth_mask, ground_truth_vp).

    Lines geometrically share a finite VP before endpoint perturbation.
    """
    rng = np.random.default_rng(seed)
    h, w = image_shape
    center = np.asarray(vp, dtype=float)
    segs = []
    masks = []
    for _ in range(inlier_count):
        # Draw radiating lines in broad angular range, with endpoints inside image.
        angle = rng.uniform(0, 2 * np.pi)
        direction = np.array([np.cos(angle), np.sin(angle)])
        extent = rng.uniform(190, 490)
        a = center + direction * extent * 0.34
        b = center + direction * extent * 0.84
        s = np.r_[a, b] + rng.normal(0, endpoint_sigma_px, 4)
        segs.append(s)
        masks.append(True)
    for _ in range(outlier_count):
        # Distractors with randomly oriented segments, not constrained by the VP.
        a = np.array([rng.uniform(0,w), rng.uniform(0,h)])
        theta = rng.uniform(0, 2*np.pi)
        length = rng.uniform(75,320)
        b = a + length*np.array([np.cos(theta), np.sin(theta)])
        segs.append(np.r_[a,b])
        masks.append(False)
    perm = rng.permutation(len(segs))
    return np.asarray(segs)[perm], np.asarray(masks)[perm], center


def render_corridor(width=1280, height=720):
    """Project a straight-line corridor under a pinhole camera; return image, VP."""
    image = np.full((height, width, 3), (36, 43, 48), dtype=np.uint8)
    K = np.array([[850., 0., width/2], [0., 850., height/2], [0.,0.,1.]])
    def line(A, B, color, thick=2):
        xy = project_points(np.array([A,B], dtype=float), K)
        a,b= [tuple(np.round(p).astype(int)) for p in xy]
        cv2.line(image,a,b,color,thick,cv2.LINE_AA)
    # Corridor coordinates: +y downward. Depth increases along +z.
    near,far=3.4,26.
    walls=[(-2.6,-1.65),(-2.6,1.65),(2.6,-1.65),(2.6,1.65)]
    for x,y in walls:
        line((x,y,near),(x,y,far),(220,205,170),3)
    for x in [-2.1,-1.4,-0.7,0,0.7,1.4,2.1]:
        line((x,1.65,near),(x,1.65,far),(160,180,190),2)
    for x in [-1.6,-0.8,0,0.8,1.6]:
        line((x,-1.65,near),(x,-1.65,far),(95,145,190),2)
    for z in [3.5,4.5,5.7,7.2,9.2,12.,16.,21.,26.]:
        line((-2.6,1.65,z),(2.6,1.65,z),(110,125,140),2)
        line((-2.6,-1.65,z),(2.6,-1.65,z),(100,125,155),2)
    for z in [4.,6.,9.,13.5,19.,25.]:
        for x in [-2.6,2.6]:
            line((x,-1.3,z),(x,1.65,z),(105,155,165),2)
    cv2.putText(image,"SYNTHETIC PINHOLE CORRIDOR - NOT REAL EVIDENCE",(24,33),
                cv2.FONT_HERSHEY_SIMPLEX,0.65,(235,225,215),2,cv2.LINE_AA)
    return image, (width/2,height/2)
