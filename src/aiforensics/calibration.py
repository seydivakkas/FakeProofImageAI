"""P1-G02: zero-skew, square-pixel camera calibration from 3 orthogonal finite VPs.

Independent implementation of standard image-of-absolute-conic geometry.
EyeLib (Carlos Beltran-Gonzalez) is a mathematical reference, NOT vendored code.

The calibration is exactly determined by 3 VP pairs; fitting residuals on the
same three VPs are NOT independent evidence of photographic authenticity.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


class CalibrationError(ValueError):
    """Inputs violate declared camera-model assumptions or are degenerate."""


@dataclass(frozen=True)
class CalibrationConfig:
    max_condition_number: float = 1.0e7
    min_focal_ratio_to_diagonal: float = 0.02
    max_focal_ratio_to_diagonal: float = 30.0
    max_principal_offset_diagonals: float = 3.0


@dataclass(frozen=True)
class CalibrationResult:
    K: np.ndarray
    R: np.ndarray
    omega: np.ndarray
    principal_point_xy: tuple[float, float]
    focal_length_px: float
    condition_number: float
    orthogonality_residuals: tuple[float, float, float]
    rotation_orthogonality_error: float
    rotation_determinant: float
    image_shape_hw: tuple[int, int]

    def to_dict(self) -> dict:
        return {
            'state': 'MEASURED',
            'assumptions': ['three independently established mutually orthogonal 3D directions',
                            'three finite vanishing points', 'pinhole projection',
                            'zero skew', 'square pixels (fx=fy)',
                            'lens distortion corrected or negligible'],
            'K': self.K.tolist(), 'R_world_to_camera_axes': self.R.tolist(),
            'omega_image_absolute_conic': self.omega.tolist(),
            'focal_length_px': self.focal_length_px,
            'principal_point_xy_px': list(self.principal_point_xy),
            'design_matrix_condition_number': self.condition_number,
            'pairwise_orthogonality_residuals': list(self.orthogonality_residuals),
            'rotation_orthogonality_frobenius': self.rotation_orthogonality_error,
            'rotation_determinant': self.rotation_determinant,
            'notes': [
                'Three orthogonal VP pairs determine three unknown intrinsics under these assumptions.',
                'The three fitted VP constraints have no independent degrees of freedom for model validation.',
                'Rotation axes have discrete sign ambiguities; their world orientation is not uniquely known.',
                'A valid calibration is NOT proof of a real photo and does NOT imply AI origin.',
            ],
            'decision': 'NO_AI_ORIGIN_CONCLUSION',
        }


def calibrate_three_orthogonal_vps(vps_xy: np.ndarray, image_shape: tuple[int, int],
                                   config: CalibrationConfig = CalibrationConfig()) -> CalibrationResult:
    """Estimate K and a right-handed R from mutually orthogonal finite VPs.

    Reject ill-conditioned, non-physical, or non-finite solutions. The input
    direction-group orthogonality is an *external scene assumption*, not
    something inferred from arbitrary triples of line intersections.
    """
    vps = np.asarray(vps_xy, dtype=np.float64)
    if vps.shape != (3, 2) or not np.all(np.isfinite(vps)):
        raise CalibrationError('Expected three finite vanishing points as an (3,2) array.')
    if len(image_shape) < 2:
        raise CalibrationError('image_shape must supply positive height and width')
    h, w = map(int, image_shape[:2])
    if h <= 0 or w <= 0:
        raise CalibrationError('Image dimensions must be positive.')
    diag = float(np.hypot(w, h))
    center = np.array([w / 2., h / 2.])
    # Center and scale BEFORE linear solving; pixel coordinates may be huge.
    q = (vps - center) / diag
    pairs = ((0, 1), (0, 2), (1, 2))
    A = np.array([[q[i, 0] + q[j, 0], q[i, 1] + q[j, 1], -1.] for i, j in pairs])
    b = np.array([q[i] @ q[j] for i, j in pairs], dtype=float)
    cond = float(np.linalg.cond(A))
    if not np.isfinite(cond) or cond > config.max_condition_number:
        raise CalibrationError(f'Degenerate finite VP triple: condition number {cond:.3g}.')
    try:
        cx, cy, D = np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise CalibrationError('Singular three-direction calibration system.') from exc
    focal2 = float(D - cx * cx - cy * cy)
    if not np.isfinite(focal2) or focal2 <= 0:
        raise CalibrationError(f'Non-positive squared focal length ({focal2:.4g}).')
    focal = float(np.sqrt(focal2) * diag)
    principal = center + diag * np.array([cx, cy])
    if not config.min_focal_ratio_to_diagonal <= focal / diag <= config.max_focal_ratio_to_diagonal:
        raise CalibrationError('Focal length outside configurable numerical plausibility range.')
    if np.linalg.norm(principal - center) > config.max_principal_offset_diagonals * diag:
        raise CalibrationError('Principal point outside configurable plausibility range.')

    K = np.array([[focal, 0., principal[0]],
                  [0., focal, principal[1]],
                  [0., 0., 1.]], dtype=float)
    omega = np.linalg.inv(K).T @ np.linalg.inv(K)
    omega /= omega[2, 2]
    hvps = np.column_stack((vps, np.ones(3)))
    rays = np.linalg.solve(K, hvps.T)
    rays /= np.linalg.norm(rays, axis=0)
    # VP directions have unknown individual signs. Choose a right-handed
    # coordinate-frame representative, orthogonalized numerically by SVD.
    if np.linalg.det(rays) < 0:
        rays[:, 2] *= -1
    U, _, Vt = np.linalg.svd(rays)
    R = U @ np.diag([1., 1., np.linalg.det(U @ Vt)]) @ Vt
    residuals = []
    for i, j in pairs:
        r1, r2 = np.linalg.solve(K, hvps[[i, j]].T).T
        residuals.append(float(abs(r1 @ r2) / (np.linalg.norm(r1) * np.linalg.norm(r2))))
    return CalibrationResult(
        K=K, R=R, omega=omega,
        principal_point_xy=(float(principal[0]), float(principal[1])),
        focal_length_px=focal,
        condition_number=cond,
        orthogonality_residuals=tuple(residuals),
        rotation_orthogonality_error=float(np.linalg.norm(R.T @ R - np.eye(3), ord='fro')),
        rotation_determinant=float(np.linalg.det(R)),
        image_shape_hw=(h, w),
    )


def calibrate_from_g01_groups(groups: list[np.ndarray], image_shape: tuple[int, int],
                              vp_config=None, calibration_config: CalibrationConfig = CalibrationConfig()) -> dict:
    """Fit one G01 VP per externally assigned 3D direction group and run G02.

    Calling code must establish that groups represent perpendicular world axes.
    This function NEVER infers orthogonality merely from three detected VPs.
    """
    from .vp import VPConfig, fit_vp
    vp_config = vp_config or VPConfig()
    if len(groups) != 3:
        raise CalibrationError('Exactly three independently labeled orthogonal direction groups required.')
    fits = []
    for group_no, group in enumerate(groups):
        try:
            f = fit_vp(np.asarray(group, dtype=float), image_shape, vp_config)
        except ValueError as e:
            raise CalibrationError(f'G01 group {group_no}: {e}') from e
        if f is None:
            return {'state': 'INDETERMINATE', 'reason': f'G01 could not fit a finite VP for group {group_no}.',
                    'decision': 'NO_AI_ORIGIN_CONCLUSION'}
        fits.append(f)
    try:
        cal = calibrate_three_orthogonal_vps(np.array([f.xy for f in fits]), image_shape, calibration_config)
    except CalibrationError as e:
        return {'state': 'INDETERMINATE', 'reason': str(e), 'g01_models': [f.to_dict() for f in fits],
                'decision': 'NO_AI_ORIGIN_CONCLUSION'}
    return {
        'state': 'MEASURED',
        'module': 'G01_TO_G02_ORTHOGONAL_CALIBRATION',
        'g01_models': [f.to_dict() for f in fits],
        'g02_calibration': cal.to_dict(),
        'independent_scene_label_requirement': 'The three supplied groups MUST correspond to mutually perpendicular 3D directions.',
        'decision': 'NO_AI_ORIGIN_CONCLUSION',
    }
