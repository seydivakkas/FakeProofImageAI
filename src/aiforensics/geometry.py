"""Projective geometry primitives. All pixel coordinates use (x right, y down)."""
from __future__ import annotations
import numpy as np


def segments_to_lines(segments: np.ndarray) -> np.ndarray:
    """Nx4 segments -> Nx3 homogeneous lines, normalized so ||(a,b)||=1.

    The sign is immaterial. Reject zero-length and non-finite segments.
    """
    s = np.asarray(segments, dtype=float)
    if s.ndim != 2 or s.shape[1] != 4:
        raise ValueError("segments must have shape (N, 4)")
    if not np.all(np.isfinite(s)):
        raise ValueError("segments must be finite")
    p1 = np.column_stack((s[:, 0:2], np.ones(len(s))))
    p2 = np.column_stack((s[:, 2:4], np.ones(len(s))))
    line = np.cross(p1, p2)
    norm = np.linalg.norm(line[:, :2], axis=1)
    if np.any(norm <= 1e-10):
        raise ValueError("zero-length segment encountered")
    return line / norm[:, None]


def intersect_lines(l1: np.ndarray, l2: np.ndarray, eps: float = 1e-12):
    """Return finite intersection in pixels or None for parallel/near-infinite."""
    p = np.cross(l1, l2)
    if abs(p[2]) <= eps:
        return None
    out = p[:2] / p[2]
    return out if np.all(np.isfinite(out)) else None


def point_line_residuals(lines: np.ndarray, vp: np.ndarray) -> np.ndarray:
    """Signed perpendicular distances from finite VP to each infinite line, in px."""
    v = np.asarray(vp, dtype=float)
    if v.shape != (2,) or not np.all(np.isfinite(v)):
        raise ValueError("vp must be a finite x,y pair")
    return lines[:, 0] * v[0] + lines[:, 1] * v[1] + lines[:, 2]


def cross_ratio(values: np.ndarray) -> float:
    """Cross-ratio of four scalar 1D projective coordinates in ordered correspondence.

    For equally spaced [0,d,2d,3d], returns 4/3.
    """
    x = np.asarray(values, dtype=float)
    if x.shape != (4,) or not np.all(np.isfinite(x)):
        raise ValueError("requires four finite scalar positions")
    denom = (x[3] - x[0]) * (x[2] - x[1])
    if abs(denom) < 1e-12:
        raise ValueError("degenerate point configuration")
    return float(((x[2] - x[0]) * (x[3] - x[1])) / denom)


def project_points(points_xyz: np.ndarray, K: np.ndarray) -> np.ndarray:
    """Project points already expressed in camera coordinates, positive Z."""
    points = np.asarray(points_xyz, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or np.any(points[:, 2] <= 0):
        raise ValueError("points must be Nx3 with positive depth")
    q = (np.asarray(K, dtype=float) @ points.T).T
    return q[:, :2] / q[:, 2:3]
