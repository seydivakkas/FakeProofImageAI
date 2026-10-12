"""G03a: automatic candidate *image* intersection patterns, not evidence of
world-space equal spacing or AI generation.

Each rail is a visible detected segment. Nearby transverse segments are
intersected with its supporting line; duplicate image crossings are clustered.
An inferred unit lattice is explicitly hypothetical: absent external
measurements, projective fit residuals cannot establish physical authenticity.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from .imaging import load_bgr, detect_segments, write_image
from .cross_ratio import analyze_repeated_landmarks, ProjectiveEvidenceError


@dataclass(frozen=True)
class PatternConfig:
    min_support_length_px: float = 80.0
    min_transverse_length_px: float = 22.0
    min_crossing_angle_deg: float = 22.0
    cluster_distance_px: float = 6.0
    min_marks: int = 5
    max_candidates: int = 5
    max_segments: int = 700


def _intersections(support: np.ndarray, segments: np.ndarray, config: PatternConfig):
    a = support[:2]; d = support[2:] - a
    len_a=float(np.linalg.norm(d))
    if len_a < config.min_support_length_px: return np.empty((0,2))
    marks=[]
    for cross in segments:
        b=cross[:2]; e=cross[2:]-b
        le=float(np.linalg.norm(e))
        if le<config.min_transverse_length_px: continue
        cosine=abs(float(d@e))/(len_a*le)
        if cosine>np.cos(np.deg2rad(config.min_crossing_angle_deg)):continue
        det=float(d[0]*e[1]-d[1]*e[0])
        if abs(det)<1e-8*len_a*le:continue
        diff=b-a
        t=float((diff[0]*e[1]-diff[1]*e[0])/det)
        u=float((diff[0]*d[1]-diff[1]*d[0])/det)
        margin=min(0.04, 4.0/max(1,len_a))
        transverse_margin=min(.08,4.0/max(1,le))
        if margin<=t<=1-margin and -transverse_margin<=u<=1+transverse_margin:
            marks.append((t,float(len_a*t)))
    if not marks:return np.empty((0,2))
    marks.sort()
    clusters=[]
    for t, dist in marks:
        if not clusters or dist-clusters[-1][-1][1]>config.cluster_distance_px:
            clusters.append([(t,dist)])
        else:clusters[-1].append((t,dist))
    fractions=np.array([np.median([q[0] for q in cluster]) for cluster in clusters],float)
    return a[None,:]+fractions[:,None]*d[None,:]


def detect_repeated_candidates(image: np.ndarray, config: PatternConfig = PatternConfig(),
                               segments: np.ndarray | None = None) -> list[dict]:
    if image.ndim!=3 or image.shape[2]!=3: raise ValueError('Expected BGR HxWx3 image')
    if config.min_marks<4 or config.max_candidates<1 or config.cluster_distance_px<=0:
        raise ValueError('Invalid pattern configuration')
    if segments is None:
        seg_lsd=detect_segments(image, min_length_px=config.min_transverse_length_px,method='lsd')
        # LSD typically splits straight lines at junctions; Hough bridges them.
        seg_hough=detect_segments(image,min_length_px=config.min_transverse_length_px,method='hough')
        seg=np.vstack([seg_lsd,seg_hough])
    else:seg=np.asarray(segments,float)
    if seg.ndim!=2 or seg.shape[1]!=4 or not np.isfinite(seg).all():
        raise ValueError('Detected segments must be finite (N,4) array')
    lengths=np.linalg.norm(seg[:,2:]-seg[:,:2],axis=1)
    candidates=[]
    # Avoid highly cluttered photographs: longest detected segments are strongest supports.
    ordering=np.argsort(-lengths,kind='stable')[:config.max_segments]
    for i in ordering:
        if lengths[i]<config.min_support_length_px:break
        crossing=_intersections(seg[i],seg,config)
        if len(crossing)<config.min_marks:continue
        support=seg[i]
        # Redundant nearly coincident rail fragments should not flood output.
        if any(np.linalg.norm(crossing.mean(axis=0)-np.mean(np.array(c['points_xy']),axis=0))<7.0
               and abs(len(c['points_xy'])-len(crossing))<=1 for c in candidates):continue
        result={'support_segment_xyxy':support.tolist(),'points_xy':crossing.tolist(),
                'count':int(len(crossing)),
                'evidence_state':'CANDIDATE_ONLY_UNVERIFIED_WORLD_SPACING',
                'source':'Unsupervised LSD line intersections; no semantic identification of parquet/window/column.',
                'assumed_world_lattice':'Consecutive equal step indices are a HYPOTHESIS, not a measured fact.',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
        if len(crossing)>=5:
            # Separate fitting and evaluation marks. Only evaluate an equal-spacing
            # hypothesis; never call it verified physical ground truth.
            n=len(crossing)
            train=sorted(set([0,n//2,n-1]))
            try:
                fit=analyze_repeated_landmarks(crossing,training_indices=train,
                       bootstrap_samples=0,max_line_rms_px=4.0)
                result['hypothetical_lattice_fit']={
                  'state':fit['state'],
                  'holdout_rmse_px':fit['holdout']['reprojection_rmse_px'],
                  'cross_ratio_abs_error':fit['cross_ratio_abs_error'],
                  'note':'Exploratory only; regularity selection and assumed lattice mean this is NOT independent evidence.'}
            except (ProjectiveEvidenceError,ValueError) as e:
                result['hypothetical_lattice_fit']={'state':'INDETERMINATE','reason':str(e)}
        candidates.append(result)
        if len(candidates)>=config.max_candidates:break
    return candidates


def analyze_auto_pattern_file(image_file:Path,out:Path,config:PatternConfig=PatternConfig()) -> dict:
    im=load_bgr(image_file)
    patterns=detect_repeated_candidates(im,config)
    marked=im.copy()
    for i,item in enumerate(patterns):
        s=np.round(item['support_segment_xyxy']).astype(int)
        cv2.line(marked,tuple(s[:2]),tuple(s[2:]),(255,180,30),2,cv2.LINE_AA)
        for idx,(x,y) in enumerate(item['points_xy']):
            p=(int(round(x)),int(round(y)))
            cv2.circle(marked,p,4,(20,220,255),-1,cv2.LINE_AA)
            cv2.putText(marked,str(idx), (p[0]+3,p[1]-4),cv2.FONT_HERSHEY_SIMPLEX,.35,(0,0,0),1,cv2.LINE_AA)
    out.mkdir(parents=True,exist_ok=True)
    write_image(out/'g03_auto_candidates.png',marked)
    report={'module':'G03_AUTOMATIC_REPETITION_CANDIDATES',
            'image_sha256':hashlib.sha256(image_file.read_bytes()).hexdigest(),
            'image_dimensions_hw':list(im.shape[:2]),
            'candidate_count':len(patterns),
            'patterns':patterns,
            'status':'CANDIDATE_ONLY' if patterns else 'INDETERMINATE',
            'limits':['No object class identification: parquet, tiles, window/column not separately certified.',
                      'Equal world spacing cannot be established by detecting repeated marks in one image.',
                      'False candidate intersections are possible in cluttered scenes.',
                      'No real-photo false-positive evaluation yet.'],
            'decision':'NO_AI_ORIGIN_CONCLUSION','overlay':'g03_auto_candidates.png'}
    (out/'g03_auto_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
