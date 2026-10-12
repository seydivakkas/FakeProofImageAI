"""G01: RANSAC finite vanishing-point estimator.

IMPORTANT: automatic fitting finds geometric structures, not synthetic image origin.
Different 3-D line directions legitimately produce distinct VPs.
Infinite VPs and curved/uncorrected lens models are outside the v0.1 contract.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.optimize import least_squares
from .geometry import segments_to_lines, intersect_lines, point_line_residuals


@dataclass(frozen=True)
class VPConfig:
    threshold_px: float = 3.0
    max_trials: int = 1600
    min_inliers: int = 5
    min_angular_spread_deg: float = 5.0
    max_radius_diagonals: float = 8.0
    random_seed: int = 2026
    bootstrap_trials: int = 50


@dataclass
class VPResult:
    xy: tuple[float, float]
    inlier_indices: list[int]
    residual_rmse_px: float
    residual_median_px: float
    residual_p90_px: float
    inlier_ratio: float
    angular_spread_deg: float
    bootstrap_std_px: tuple[float, float] | None
    finite_model_only: bool = True

    def to_dict(self) -> dict:
        return {
            "vp_xy_px": list(self.xy),
            "inlier_indices": self.inlier_indices,
            "inlier_count": len(self.inlier_indices),
            "inlier_ratio": self.inlier_ratio,
            "inlier_residual_rmse_px": self.residual_rmse_px,
            "inlier_residual_median_px": self.residual_median_px,
            "inlier_residual_p90_px": self.residual_p90_px,
            "inlier_line_orientation_spread_deg": self.angular_spread_deg,
            "bootstrap_std_px_exploratory": list(self.bootstrap_std_px) if self.bootstrap_std_px else None,
            "finite_model_only": self.finite_model_only,
        }


def _orientation_spread(segments: np.ndarray) -> float:
    """Orientation range modulo 180 deg; calculated as shortest containing arc."""
    d = segments[:, 2:4] - segments[:, 0:2]
    angle = np.mod(np.degrees(np.arctan2(d[:, 1], d[:, 0])), 180.0)
    sorted_angle = np.sort(angle)
    gaps = np.diff(np.r_[sorted_angle, sorted_angle[0] + 180.0])
    return float(180.0 - np.max(gaps))


def _refine(lines: np.ndarray, x0: np.ndarray, scale: float) -> np.ndarray:
    opt = least_squares(
        lambda xy: point_line_residuals(lines, xy),
        np.asarray(x0, dtype=float),
        jac=lambda xy: lines[:, :2],
        method="trf", loss="huber", f_scale=max(scale, 0.1), max_nfev=150,
    )
    return opt.x


def fit_vp(segments: np.ndarray, image_shape: tuple[int, int], config: VPConfig = VPConfig()) -> VPResult | None:
    """Estimate ONE dominant *finite* VP. Returns None for insufficient evidence.

    Segments may contain different real 3-D direction families; these are outliers
    *to this particular direction fit*, not evidence of manipulation.
    """
    segs = np.asarray(segments, dtype=float)
    if segs.ndim != 2 or segs.shape[1] != 4:
        raise ValueError("segments must be Nx4")
    if len(segs) < config.min_inliers or config.threshold_px <= 0:
        return None
    length = np.linalg.norm(segs[:, 2:4] - segs[:, 0:2], axis=1)
    valid = np.isfinite(segs).all(axis=1) & (length > 1e-7)
    idx_map = np.flatnonzero(valid)
    good = segs[valid]
    if len(good) < config.min_inliers:
        return None
    lines = segments_to_lines(good)
    h, w = image_shape[:2]
    diag = float(np.hypot(w, h))
    center = np.array([w / 2.0, h / 2.0])
    max_radius = config.max_radius_diagonals * diag
    rng = np.random.default_rng(config.random_seed)
    n = len(good)
    best_mask = None
    best_xy = None
    best_rank = (-1, -np.inf)
    for _ in range(config.max_trials):
        i, j = rng.choice(n, 2, replace=False)
        # Exclude almost parallel image lines: their intersection is poorly constrained.
        if abs(np.linalg.det(lines[[i, j], :2])) < 0.015:
            continue
        xy = intersect_lines(lines[i], lines[j])
        if xy is None or np.linalg.norm(xy - center) > max_radius:
            continue
        res = np.abs(point_line_residuals(lines, xy))
        mask = res <= config.threshold_px
        count = int(mask.sum())
        rank = (count, -float(np.median(res[mask])) if count else -np.inf)
        if rank > best_rank:
            best_mask, best_xy, best_rank = mask, xy, rank
    if best_mask is None or best_mask.sum() < config.min_inliers:
        return None
    refined = _refine(lines[best_mask], best_xy, config.threshold_px / 2)
    for _ in range(3):
        mask = np.abs(point_line_residuals(lines, refined)) <= config.threshold_px
        if mask.sum() < config.min_inliers:
            return None
        refined = _refine(lines[mask], refined, config.threshold_px / 2)
    mask = np.abs(point_line_residuals(lines, refined)) <= config.threshold_px
    if mask.sum() < config.min_inliers or np.linalg.norm(refined - center) > max_radius:
        return None
    spread = _orientation_spread(good[mask])
    if spread < config.min_angular_spread_deg:
        return None
    residuals = np.abs(point_line_residuals(lines[mask], refined))
    boot = None
    if config.bootstrap_trials > 0:
        samples = []
        inlier_lines = lines[mask]
        for _ in range(config.bootstrap_trials):
            drawn = rng.integers(0, len(inlier_lines), size=len(inlier_lines))
            if np.linalg.matrix_rank(inlier_lines[drawn, :2], tol=1e-6) < 2:
                continue
            est = _refine(inlier_lines[drawn], refined, config.threshold_px / 2)
            if np.all(np.isfinite(est)):
                samples.append(est)
        if len(samples) >= 3:
            std = np.std(np.array(samples), axis=0, ddof=1)
            boot = (float(std[0]), float(std[1]))
    return VPResult(
        xy=(float(refined[0]), float(refined[1])),
        inlier_indices=idx_map[mask].tolist(),
        residual_rmse_px=float(np.sqrt(np.mean(residuals**2))),
        residual_median_px=float(np.median(residuals)),
        residual_p90_px=float(np.percentile(residuals, 90)),
        inlier_ratio=float(mask.sum() / len(good)),
        angular_spread_deg=spread,
        bootstrap_std_px=boot,
    )


def _combine_nearby(a: VPResult, b: VPResult, segments: np.ndarray,
                    config: VPConfig) -> VPResult:
    """Combine nearly indistinguishable finite VP hypotheses in pixel space."""
    indices = np.unique(np.asarray(a.inlier_indices + b.inlier_indices, dtype=int))
    lines = segments_to_lines(segments[indices])
    start = np.average(np.array([a.xy, b.xy]), axis=0,
                       weights=[len(a.inlier_indices), len(b.inlier_indices)])
    est = _refine(lines, start, config.threshold_px / 2)
    residual = np.abs(point_line_residuals(lines, est))
    mask = residual <= config.threshold_px
    # Do not lose the stronger hypothesis to an unstable attempt at merging.
    if int(mask.sum()) < max(len(a.inlier_indices), len(b.inlier_indices)):
        return a if len(a.inlier_indices) >= len(b.inlier_indices) else b
    r = residual[mask]
    return VPResult(
        xy=(float(est[0]), float(est[1])),
        inlier_indices=indices[mask].tolist(),
        residual_rmse_px=float(np.sqrt(np.mean(r**2))),
        residual_median_px=float(np.median(r)),
        residual_p90_px=float(np.percentile(r, 90)),
        inlier_ratio=float(mask.sum() / len(segments)),
        angular_spread_deg=_orientation_spread(segments[indices[mask]]),
        bootstrap_std_px=None,  # bootstrap must be recomputed after merging
    )


def find_vps(segments: np.ndarray, image_shape: tuple[int, int], max_models: int = 3,
             config: VPConfig = VPConfig(), min_support_fraction: float = 0.07,
             merge_distance_px: float = 12.) -> list[VPResult]:
    """Descriptive dominant finite VP discovery, with duplicate-hypothesis merging.

    Small accidental intersections are suppressed by minimum support relative
    to the *original* population. True but rare structures can be missed.
    A second genuine VP is common and NOT evidence of manipulation.
    """
    segs = np.asarray(segments, dtype=float)
    remaining = np.arange(len(segs))
    results = []
    for model_no in range(max_models):
        if len(remaining) < config.min_inliers:
            break
        cfg = VPConfig(**{**config.__dict__, "random_seed": config.random_seed + model_no})
        fit = fit_vp(segs[remaining], image_shape, cfg)
        if fit is None:
            break
        original_inliers = remaining[np.array(fit.inlier_indices, dtype=int)]
        if len(original_inliers) < max(config.min_inliers,
                                      int(np.ceil(len(segs) * min_support_fraction))):
            break
        fit.inlier_indices = original_inliers.tolist()
        fit.inlier_ratio = len(original_inliers) / len(segs)
        nearest = next((k for k, prev in enumerate(results)
                        if np.linalg.norm(np.array(prev.xy) - np.array(fit.xy))
                           <= merge_distance_px), None)
        if nearest is None:
            results.append(fit)
        else:
            results[nearest] = _combine_nearby(results[nearest], fit, segs, config)
        remaining = remaining[~np.isin(remaining, original_inliers)]
    return results
