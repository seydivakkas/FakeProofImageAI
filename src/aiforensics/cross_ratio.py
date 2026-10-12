"""P1-G03 projective invariants of aligned, assumed equally-spaced landmarks.

Only a geometric hypothesis test. Image landmarks need externally justified
physical equality and verified correspondence ordering. Not an AI-origin test.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


class ProjectiveEvidenceError(ValueError):
    """Invalid or unidentifiable projective-geometry input."""


def _points(points):
    p = np.asarray(points, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 2 or p.shape[0] < 4 or not np.isfinite(p).all():
        raise ProjectiveEvidenceError('Expected at least 4 finite 2D image points (N,2).')
    return p


def cross_ratio_1d(values):
    """CR(a,b,c,d) = (c-a)(d-b)/[(d-a)(c-b)]."""
    x=np.asarray(values,dtype=np.float64)
    if x.shape != (4,) or not np.isfinite(x).all():
        raise ProjectiveEvidenceError('Cross-ratio requires four finite 1D coordinates.')
    scale=max(float(np.ptp(x)), 1.)
    # Normalize to guard extreme units; reject coinciding cross-ratio endpoints.
    z=(x-x[0])/scale
    den=(z[3]-z[0])*(z[2]-z[1])
    if abs(den)<1.e-12:
        raise ProjectiveEvidenceError('Degenerate cross-ratio denominator.')
    return float((z[2]-z[0])*(z[3]-z[1])/den)


def _line_frame(points):
    mu=points.mean(axis=0)
    _,s,vt=np.linalg.svd(points-mu,full_matrices=False)
    if s[0]<1.e-9:
        raise ProjectiveEvidenceError('Coincident 2D landmarks do not determine a line.')
    axis=vt[0]
    orth=vt[1]
    t=(points-mu)@axis
    perp=(points-mu)@orth
    return mu, axis, orth, t, perp


def _projective_fit(x,y):
    """Homography on 1D coordinate: (a*x+b)/(c*x+d); stable normalized DLT."""
    x=np.asarray(x,dtype=float)
    y=np.asarray(y,dtype=float)
    if len(x)<3 or len(np.unique(x))<3:
        raise ProjectiveEvidenceError('At least three distinct training lattice indices needed.')
    x_mu,x_scale=np.mean(x),max(np.std(x),1.e-12)
    y_mu,y_scale=np.mean(y),max(np.std(y),1.e-12)
    xn=(x-x_mu)/x_scale; yn=(y-y_mu)/y_scale
    A=np.column_stack([xn,np.ones(len(x)), -xn*yn,-yn])
    _, sv, vh=np.linalg.svd(A, full_matrices=True)
    if sv[0] == 0 or (len(sv)>=3 and sv[2]/sv[0]<1.e-13):
        raise ProjectiveEvidenceError('Degenerate projective landmark configuration.')
    h=vh[-1].reshape(2,2)
    T_x=np.array([[1/x_scale, -x_mu/x_scale],[0,1.]])
    T_y_inv=np.array([[y_scale,y_mu],[0,1.]])
    H=T_y_inv@h@T_x
    if not np.isfinite(H).all() or abs(np.linalg.det(H))<1.e-12:
        raise ProjectiveEvidenceError('Projective mapping is singular.')
    return H


def _predict_h(H,index):
    v=np.array([float(index),1.])
    z=H@v
    if abs(z[1])<1.e-10 or not np.isfinite(z).all():
        raise ProjectiveEvidenceError('Landmark projects to infinity.')
    return float(z[0]/z[1])


def analyze_repeated_landmarks(points_xy, lattice_indices=None,
                               training_indices=None, pixel_sigma=0.5,
                               bootstrap_samples=400, seed=2026,
                               max_line_rms_px=2.0):
    """Check collinearity + cross-ratio + optional holdout 1D projective fit.

    Point order must match world lattice indices, not automatically sorted by x/y.
    A train/holdout fit is independently scored only if holdout points are not
    used for fitting the line axis. To avoid leakage, line axis is derived only
    from training points in holdout mode.
    """
    p=_points(points_xy)
    n=len(p)
    lattice=np.arange(n,dtype=float) if lattice_indices is None else np.asarray(lattice_indices,dtype=float)
    if lattice.shape!=(n,) or not np.isfinite(lattice).all() or len(np.unique(lattice))!=n:
        raise ProjectiveEvidenceError('Lattice indices must be distinct finite values, one per landmark.')
    if pixel_sigma<0 or not np.isfinite(pixel_sigma):
        raise ProjectiveEvidenceError('pixel_sigma must be finite and nonnegative.')
    if int(bootstrap_samples)!=bootstrap_samples or bootstrap_samples<0:
        raise ProjectiveEvidenceError('bootstrap_samples must be a nonnegative integer.')
    if training_indices is not None:
        train=np.asarray(training_indices,dtype=int)
        if train.ndim!=1 or len(train)<3 or len(set(train.tolist()))!=len(train) or np.any(train<0) or np.any(train>=n):
            raise ProjectiveEvidenceError('Training indices must be >=3 distinct indices into landmarks.')
        holdout=np.asarray([i for i in range(n) if i not in set(train.tolist())],dtype=int)
        if not len(holdout):
            raise ProjectiveEvidenceError('A disjoint holdout landmark is required for independent validation.')
    else:
        train=np.arange(n)
        holdout=np.array([],dtype=int)
    _,axis,orth,_,perp_train=_line_frame(p[train])
    origin=p[train].mean(axis=0)
    t=(p-origin)@axis
    perpendicular=(p-origin)@orth
    t_range=max(float(np.ptp(t)),1.)
    ordered_t=t[np.argsort(lattice)]
    monotonic=bool(np.all(np.diff(ordered_t)>0) or np.all(np.diff(ordered_t)<0))
    if np.min(np.abs(np.diff(np.sort(t)))) < t_range*1.e-9:
        raise ProjectiveEvidenceError('Overlapping projected landmarks make the invariant unstable.')
    line_rms=float(np.sqrt(np.mean(perpendicular**2)))
    line_inliers=bool(line_rms <= max_line_rms_px)
    cr_observed=cross_ratio_1d(t[:4]); cr_reference=cross_ratio_1d(lattice[:4])
    cr_abs_err=abs(cr_observed-cr_reference)
    # Simple Monte Carlo propagation of assumed isotropic landmark location error.
    if bootstrap_samples:
        rng=np.random.default_rng(seed)
        samples=[]
        for _ in range(bootstrap_samples):
            pj=p+rng.normal(scale=pixel_sigma,size=p.shape)
            try:
                frame=_line_frame(pj[train]); tt=(pj-pj[train].mean(axis=0))@frame[1]
                samples.append(cross_ratio_1d(tt[:4]))
            except ProjectiveEvidenceError:
                continue
        interval=np.percentile(samples,[2.5,97.5]).tolist() if len(samples)>=max(10,bootstrap_samples//2) else None
    else:
        interval=None
    holdout_data=None
    if len(holdout):
        H=_projective_fit(lattice[train],t[train])
        pred_t=np.array([_predict_h(H,lattice[i]) for i in holdout],dtype=float)
        pred_xy=origin[None,:]+pred_t[:,None]*axis[None,:]
        err=np.linalg.norm(pred_xy-p[holdout],axis=1)
        holdout_data={
            'count':int(len(holdout)),
            'point_indices':holdout.tolist(),
            'reprojection_error_px':err.tolist(),
            'reprojection_rmse_px':float(np.sqrt(np.mean(err**2))),
            'reprojection_median_px':float(np.median(err)),
            'predicted_image_points_xy':pred_xy.tolist(),
            'leakage_note':'The fitting line and 1D projectivity use only training landmarks.',
        }
    # Distinguish an unidentifiable training line from a holdout anomaly.
    # Holdout error is checked as an exploratory threshold, not a calibrated p-value.
    training_line_rms=float(np.sqrt(np.mean(perpendicular[train]**2)))
    if training_line_rms > max_line_rms_px:
        state='INDETERMINATE'
        reason='Training landmarks do not determine a sufficiently consistent 1D line.'
    elif holdout_data is not None and holdout_data['reprojection_rmse_px'] > max(max_line_rms_px*2, 4*pixel_sigma):
        state='INCONSISTENT_UNDER_ASSUMPTIONS'
        reason='Held-out repeated landmarks violate the training projective model.'
    elif not monotonic:
        state='INDETERMINATE'
        reason='Landmark world ordering cannot be represented as a continuous finite projective line.'
    elif not line_inliers:
        state='INCONSISTENT_UNDER_ASSUMPTIONS'
        reason='Independently observed landmarks deviate from the straight-line model.'
    elif interval is None and cr_abs_err > 1.e-6:
        state='INDETERMINATE'
        reason='Observed cross-ratio differs but uncertainty sampling was disabled.'
    elif interval is not None and not (interval[0]-1e-10<=cr_reference<=interval[1]+1e-10):
        state='INCONSISTENT_UNDER_ASSUMPTIONS'
        reason='Equal-spacing cross-ratio is outside assumed measurement-noise interval.'
    else:
        state='MEASURED'
        reason='No statistically resolved cross-ratio violation; not evidence of photographic authenticity.'
    return {
        'module':'G03_1D_PROJECTIVE_INVARIANTS',
        'state':state,'reason':reason,
        'physical_assumption':'Input indices mark equal world distances along the SAME 3D straight line.',
        'image_point_count':n,
        'lattice_indices':lattice.tolist(),
        'collinearity_rms_px':line_rms,
        'training_collinearity_rms_px':float(np.sqrt(np.mean(perpendicular[train]**2))),
        'collinearity_max_abs_px':float(np.max(np.abs(perpendicular))),
        'world_order_monotonic_in_image':monotonic,
        'cross_ratio_observed':cr_observed,
        'cross_ratio_expected':cr_reference,
        'cross_ratio_abs_error':cr_abs_err,
        'cross_ratio_monte_carlo_95pct_interval':interval,
        'measurement_sigma_px':float(pixel_sigma),
        'uncertainty_samples':int(bootstrap_samples),
        'holdout':holdout_data,
        'warnings':['No physical equal-spacing evidence is inferred from the image itself.',
                    'A discrepancy is not proof of AI generation or manipulation.',
                    'Holdout anomaly threshold is exploratory, not statistically calibrated.',
                    'The 95% Monte Carlo interval assumes independent Gaussian endpoint errors.',
                    'This is a single predeclared four-point check; multiple-testing adjustment is not applied.'],
        'decision':'NO_AI_ORIGIN_CONCLUSION',
    }
