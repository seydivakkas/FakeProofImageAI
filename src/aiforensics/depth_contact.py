"""P5-D01: conditional single-view ground reconstruction and physical-contact evidence.

A ground-plane ray intersection is a *hypothesis*, never proof of contact.
Independent metric anchors and/or independently measured heights are required
for a geometric consistency verdict. No claim about AI origin is produced.
Camera: X_cam = R_world_to_camera X_world + t_world_to_camera.
Plane: normal_world dot X + offset_world = 0; units set by the manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .lens_distortion import distort_pixels, undistort_pixels, LensGeometryError


class DepthContactError(ValueError):
    pass


@dataclass(frozen=True)
class DepthContactConfig:
    pixel_tolerance: float = 3.0
    contact_tolerance_world: float = 0.03
    support_margin_world: float = 1e-6
    max_ray_distance_world: float = 10000.0

    def __post_init__(self):
        vals = (self.pixel_tolerance, self.contact_tolerance_world,
                self.support_margin_world, self.max_ray_distance_world)
        if any(not np.isfinite(x) for x in vals) or self.pixel_tolerance <= 0 or self.contact_tolerance_world <= 0 or self.support_margin_world < 0 or self.max_ray_distance_world <= 0:
            raise DepthContactError('invalid positive geometric tolerances')


def _array(x, size, label):
    a = np.asarray(x, dtype=float)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise DepthContactError(f'{label} must be {size} finite numbers')
    return a


def _unit(v, label):
    x = _array(v, 3, label)
    length = float(np.linalg.norm(x))
    if length <= 1e-12:
        raise DepthContactError(f'{label} cannot be zero')
    return x / length


class PinholeCamera:
    def __init__(self, data: dict, image_shape_hw: list[int]):
        if not isinstance(data, dict):
            raise DepthContactError('camera must be an object')
        try:
            self.K = np.asarray(data['K'], dtype=float)
            self.R = np.asarray(data['R_world_to_camera'], dtype=float)
            self.t = _array(data['t_world_to_camera'], 3, 'camera translation')
        except (KeyError, TypeError, ValueError) as exc:
            raise DepthContactError(f'invalid camera: {exc}') from exc
        if self.K.shape != (3, 3) or self.R.shape != (3, 3) or not np.isfinite(self.K).all() or not np.isfinite(self.R).all():
            raise DepthContactError('K and R must be finite 3x3 matrices')
        if self.K[0, 0] <= 0 or self.K[1, 1] <= 0 or not np.allclose(self.K[2], [0, 0, 1], atol=1e-10) or abs(np.linalg.det(self.K)) < 1e-12:
            raise DepthContactError('invalid intrinsic K')
        if not np.allclose(self.R.T @ self.R, np.eye(3), atol=1e-6) or abs(float(np.linalg.det(self.R)) - 1) > 1e-6:
            raise DepthContactError('R must be a proper orthogonal rotation')
        if len(image_shape_hw) != 2 or any(not isinstance(z, int) or z <= 0 for z in image_shape_hw):
            raise DepthContactError('image_shape_hw must be two positive integers')
        self.image_shape_hw = list(image_shape_hw)
        self.C = -self.R.T @ self.t
        self.distortion = data.get('distortion_coefficients_k1_k2_p1_p2_k3')
        if self.distortion is not None:
            coeff = np.asarray(self.distortion, dtype=float)
            if coeff.shape not in ((4,), (5,)) or not np.isfinite(coeff).all() or abs(self.K[0, 1]) > 1e-10 or abs(self.K[1, 0]) > 1e-10:
                raise DepthContactError('Brown-Conrady distortion requires finite 4/5 coefficients and zero skew')

    def normalized_pixel(self, p):
        p = _array(p, 2, 'pixel')
        try:
            if self.distortion is not None:
                p = undistort_pixels(p.reshape(1, 2), self.K, self.distortion)[0]
        except LensGeometryError as exc:
            raise DepthContactError(f'lens inversion failed: {exc}') from exc
        return p

    def ray(self, pixel):
        p = self.normalized_pixel(pixel)
        v = np.linalg.solve(self.K, np.r_[p, 1.0])
        v = self.R.T @ v
        return v / np.linalg.norm(v)

    def project(self, world_xyz):
        xyz = _array(world_xyz, 3, 'world point')
        cam = self.R @ xyz + self.t
        if cam[2] <= 1e-9:
            raise DepthContactError('point is not in front of camera')
        uvw = self.K @ (cam / cam[2])
        pix = uvw[:2]
        if self.distortion is not None:
            try:
                pix = distort_pixels(pix.reshape(1, 2), self.K, self.distortion)[0]
            except LensGeometryError as exc:
                raise DepthContactError(f'lens forward projection failed: {exc}') from exc
        return pix


class SupportPlane:
    def __init__(self, record: dict):
        try:
            self.id = str(record['id'])
            raw_normal = _array(record['normal_world'], 3, 'support normal')
            offset = float(record['offset_world'])
            raw_polygon = np.asarray(record['polygon_world_xyz'], dtype=float)
        except (KeyError, TypeError, ValueError) as exc:
            raise DepthContactError(f'invalid support surface: {exc}') from exc
        scale = float(np.linalg.norm(raw_normal))
        if not self.id or scale < 1e-12 or not np.isfinite(offset):
            raise DepthContactError('invalid support normal/offset/id')
        self.n = raw_normal / scale
        self.d = offset / scale
        if raw_polygon.ndim != 2 or raw_polygon.shape[1:] != (3,) or len(raw_polygon) < 3 or not np.isfinite(raw_polygon).all():
            raise DepthContactError('support polygon must contain >=3 finite world XYZ vertices')
        self.poly = raw_polygon
        if float(np.max(np.abs(self.poly @ self.n + self.d))) > 1e-7:
            raise DepthContactError('support polygon vertices do not lie on their declared plane')
        sides = np.roll(self.poly, -1, axis=0) - self.poly
        cross = np.cross(sides, np.roll(sides, -1, axis=0)) @ self.n
        if np.any(np.abs(cross) < 1e-12) or not (np.all(cross > 0) or np.all(cross < 0)):
            raise DepthContactError('support polygon must be strictly convex and non-degenerate')

    def signed_distance(self, world_xyz):
        return float(self.n @ world_xyz + self.d)

    def contains(self, xyz, margin=1e-6):
        x = _array(xyz, 3, 'surface point')
        if abs(self.signed_distance(x)) > margin:
            return False
        edges = np.roll(self.poly, -1, axis=0) - self.poly
        signed_edge_dist = (np.cross(edges, x - self.poly) @ self.n) / np.linalg.norm(edges, axis=1)
        return bool((np.min(signed_edge_dist) >= -margin) or (np.max(signed_edge_dist) <= margin))

    def intersection(self, camera: PinholeCamera, px, cfg: DepthContactConfig):
        v = camera.ray(px)
        den = float(self.n @ v)
        if abs(den) < 1e-9:
            return None, 'view ray parallel to support plane'
        depth_ray = -(float(self.n @ camera.C) + self.d) / den
        if depth_ray <= 1e-7:
            return None, 'support plane is behind camera or not visible along ray'
        if depth_ray > cfg.max_ray_distance_world:
            return None, 'ray-plane range exceeds validated scene extent'
        return camera.C + depth_ray * v, None


def _status_from(errors: list[str], checks: list[str]):
    if errors:
        return 'INCONSISTENT_UNDER_ASSUMPTIONS'
    return 'CONSISTENT' if checks else 'INDETERMINATE'


def evaluate_contact(data: dict, cfg: DepthContactConfig = DepthContactConfig()):
    if not isinstance(data, dict):
        raise DepthContactError('manifest must be an object')
    try:
        cam = PinholeCamera(data['camera'], data['image_shape_hw'])
        gravity = _unit(data['gravity_world'], 'gravity_world')
        supports = [SupportPlane(x) for x in data['support_surfaces']]
        observations = data['observations']
    except (KeyError, TypeError) as exc:
        raise DepthContactError(f'invalid P5-D01 manifest: {exc}') from exc
    if not supports or len(set(s.id for s in supports)) != len(supports):
        raise DepthContactError('support surfaces must have unique nonempty ids')
    if not isinstance(observations, list) or not observations:
        raise DepthContactError('observations must be a nonempty list')
    plane_map = {s.id: s for s in supports}
    result = []
    ids = set()
    for obs in observations:
        if not isinstance(obs, dict):
            raise DepthContactError('observations must be objects')
        try:
            oid = str(obs['id'])
            plane = plane_map[str(obs['support_id'])]
            px = _array(obs['base_pixel_xy'], 2, 'base_pixel_xy')
        except (KeyError, ValueError, TypeError) as exc:
            raise DepthContactError(f'invalid observation: {exc}') from exc
        if not oid or oid in ids:
            raise DepthContactError('observation IDs must be unique and nonempty')
        ids.add(oid)
        errors = []
        checks = []
        uncertain = []
        notes = []
        if not (0 <= px[0] < cam.image_shape_hw[1] and 0 <= px[1] < cam.image_shape_hw[0]):
            raise DepthContactError(f'{oid}: base pixel outside image bounds')
        footprint, issue = plane.intersection(cam, px, cfg)
        row = {'id': oid, 'support_id': plane.id,
               'state': 'INDETERMINATE', 'ray_plane_point_world_xyz': None,
               'conditional_ray_depth_world': None, 'physical_checks': [],
               'inconsistency_reasons': [], 'limitations': []}
        if issue:
            notes.append(issue)
        else:
            # A depth recovered by imposing a plane is not ground truth. Pixel
            # uncertainty is propagated through the same conditional model.
            sigma_px = obs.get('base_pixel_sigma_px')
            if sigma_px is not None:
                sigma_px = float(sigma_px)
                if not np.isfinite(sigma_px) or not (0 < sigma_px <= 25):
                    raise DepthContactError(f'{oid}: base_pixel_sigma_px must be in (0,25]')
                jac = np.zeros((3, 2), dtype=float)
                for axis in range(2):
                    delta = np.zeros(2); delta[axis] = 0.5
                    plus, pos_issue = plane.intersection(cam, px + delta, cfg)
                    minus, neg_issue = plane.intersection(cam, px - delta, cfg)
                    if pos_issue or neg_issue:
                        notes.append('conditional depth pixel uncertainty ill-conditioned near plane horizon')
                        jac = None
                        break
                    jac[:, axis] = plus-minus
                if jac is not None:
                    covariance = sigma_px*sigma_px * jac @ jac.T
                    row['conditional_ground_xyz_std_world'] = np.sqrt(np.maximum(0, np.diag(covariance))).tolist()
                    row['conditional_ground_covariance_world2'] = covariance.tolist()
                    row['conditional_range_sigma_world'] = float(np.linalg.norm(jac.T @ ((footprint-cam.C)/np.linalg.norm(footprint-cam.C))) * sigma_px)
                    notes.append('conditional covariance assumes independent isotropic Gaussian base-pixel noise and exact camera/plane')
            row['ray_plane_point_world_xyz'] = footprint.tolist()
            row['conditional_ray_depth_world'] = float(np.linalg.norm(footprint-cam.C))
            row['inside_support_polygon'] = plane.contains(footprint, cfg.support_margin_world)
            if not row['inside_support_polygon']:
                notes.append('ray intersects the infinite plane outside the finite support polygon; does not prove floating')
            else:
                notes.append('ray-plane intersection is conditional, not an independently observed physical contact')
        if 'independent_base_world_xyz' in obs:
            if obs.get('base_world_provenance') != 'independent_metric':
                notes.append('3D anchor lacks declared independent_metric provenance; excluded from physical verdict')
            else:
                base3 = _array(obs['independent_base_world_xyz'], 3, f'{oid} independent 3D anchor')
                dist = plane.signed_distance(base3)
                row['independent_anchor_plane_signed_distance_world'] = dist
                row['independent_anchor_inside_polygon'] = plane.contains(base3, cfg.contact_tolerance_world)
                if abs(dist) > cfg.contact_tolerance_world or not row['independent_anchor_inside_polygon']:
                    errors.append('independent 3D anchor does not contact declared finite support plane')
                else:
                    checks.append('independently measured metric anchor contacts support plane')
                try:
                    projected = cam.project(base3)
                    p_error = float(np.linalg.norm(projected-px))
                    row['independent_anchor_reprojection_error_px'] = p_error
                    if p_error > cfg.pixel_tolerance:
                        sigma_base = float(obs.get('base_pixel_sigma_px', 0))
                        if sigma_base > 0 and p_error <= cfg.pixel_tolerance + 3*sigma_base:
                            uncertain.append('independent anchor reprojection residual falls in pixel-noise ambiguity band')
                        else:
                            errors.append('independent 3D anchor fails base-pixel reprojection holdout')
                    else:
                        checks.append('independent 3D anchor independently reprojects to base pixel')
                except DepthContactError as exc:
                    errors.append(f'independent 3D anchor cannot be projected: {exc}')
        if 'top_pixel_xy' in obs or 'known_height_world' in obs:
            if 'top_pixel_xy' not in obs or 'known_height_world' not in obs:
                notes.append('upright top-height check requires both top pixel and independent physical height')
            elif obs.get('height_provenance') != 'independent_metric' or obs.get('upright_gravity_aligned') is not True:
                notes.append('top-height check excluded: height not independently known or object not declared gravity-upright')
            elif footprint is None:
                notes.append('upright height cannot be checked because support intersection is unavailable')
            elif not plane.contains(footprint, cfg.support_margin_world):
                notes.append('upright height cannot be checked outside finite support polygon')
            else:
                height = float(obs['known_height_world'])
                if not np.isfinite(height) or height <= 0:
                    raise DepthContactError(f'{oid}: known height must be finite and positive')
                upper = footprint-gravity*height
                top_obs = _array(obs['top_pixel_xy'], 2, f'{oid} top_pixel_xy')
                if not (0 <= top_obs[0] < cam.image_shape_hw[1] and 0 <= top_obs[1] < cam.image_shape_hw[0]):
                    raise DepthContactError(f'{oid}: top pixel outside image bounds')
                try:
                    predicted = cam.project(upper)
                    e = float(np.linalg.norm(predicted-top_obs))
                    row['upright_top_expected_pixel_xy'] = predicted.tolist()
                    row['upright_top_reprojection_error_px'] = e
                    row['conditional_top_world_xyz'] = upper.tolist()
                    if e > cfg.pixel_tolerance:
                        sigma_base=float(obs.get('base_pixel_sigma_px', 0))
                        sigma_top=float(obs.get('top_pixel_sigma_px', sigma_base))
                        if not (np.isfinite(sigma_top) and 0 <= sigma_top <= 25):
                            raise DepthContactError(f'{oid}: invalid top_pixel_sigma_px')
                        sigma_effective=float(np.hypot(sigma_base,sigma_top))
                        # Approximate conditioning of the ground-ray -> top-projection
                        # chain. Deliberately conservative to avoid unsupported violations.
                        if sigma_base > 0:
                            J=np.zeros((2,2))
                            for axis in range(2):
                                delta=np.zeros(2);delta[axis]=0.5
                                plus,err_plus=plane.intersection(cam,px+delta,cfg)
                                minus,err_minus=plane.intersection(cam,px-delta,cfg)
                                if err_plus or err_minus:
                                    sigma_effective=float('inf');break
                                try:
                                    J[:,axis]=(cam.project(plus-gravity*height)-cam.project(minus-gravity*height))
                                except DepthContactError:
                                    sigma_effective=float('inf');break
                            if np.isfinite(sigma_effective):
                                sigma_effective=float(np.sqrt(sigma_base**2*np.linalg.norm(J,'fro')**2+2*sigma_top**2))
                        row['upright_top_noise_guard_px']=float(3*sigma_effective) if np.isfinite(sigma_effective) else None
                        if not np.isfinite(sigma_effective) or e <= cfg.pixel_tolerance+3*sigma_effective:
                            uncertain.append('upright top reprojection falls in noisy/ill-conditioned ambiguity band')
                        else:
                            errors.append('upright top point inconsistent with known height / camera / support geometry')
                    else:
                        checks.append('independent object height agrees with projected upright top point')
                except DepthContactError as exc:
                    notes.append(f'top-point projection unavailable: {exc}')
        if 'center_of_mass_world_xyz' in obs:
            if obs.get('com_provenance') != 'independent_metric' or not obs.get('static_unanchored', False):
                notes.append('COM support check requires independent COM and explicit static_unanchored hypothesis')
            else:
                com = _array(obs['center_of_mass_world_xyz'], 3, f'{oid} COM')
                dg = float(plane.n @ gravity)
                if abs(dg) < 1e-9:
                    notes.append('gravity direction parallel to support plane; COM projection not identified')
                elif dg >= -0.05:
                    notes.append('support normal does not face against gravity; free-standing static support not established')
                else:
                    lam = -(float(plane.n @ com)+plane.d)/dg
                    support_point = com + lam*gravity
                    stable = plane.contains(support_point, cfg.support_margin_world) and lam >= -cfg.contact_tolerance_world
                    row['gravity_projected_center_of_mass_xyz'] = support_point.tolist()
                    row['gravity_static_support_possible'] = stable
                    if not stable:
                        errors.append('static unanchored COM gravity projection outside the finite support polygon')
                    else:
                        checks.append('static-unanchored COM gravity projection is inside support polygon')
        row['state'] = ('INCONSISTENT_UNDER_ASSUMPTIONS' if errors else 'INDETERMINATE' if uncertain else _status_from(errors, checks))
        row['measurement_ambiguities'] = uncertain
        row['physical_checks'] = checks
        row['inconsistency_reasons'] = errors
        row['limitations'] = notes
        result.append(row)
    count = {x: sum(r['state'] == x for r in result) for x in
             ['CONSISTENT', 'INCONSISTENT_UNDER_ASSUMPTIONS', 'INDETERMINATE']}
    state = ('INCONSISTENT_UNDER_ASSUMPTIONS' if count['INCONSISTENT_UNDER_ASSUMPTIONS']
             else 'INDETERMINATE' if count['INDETERMINATE'] else 'CONSISTENT')
    return {'module': 'P5_D01_DEPTH_CONTACT_SUPPORT', 'state': state,
            'counts': count, 'observations': result,
            'assumptions': ['externally calibrated K/R/t; distortion coefficients if supplied',
                            'metric 3D support plane/polygon independently known',
                            'known gravity direction; physically appropriate rigid-object model',
                            'independently measured anchor/height required for consistency conclusions',
                            'explicit static unanchored model and outward/upward surface normal required for COM criterion'],
            'limitations': ['single image cannot uniquely recover unconstrained 3D depth',
                            'ray-plane intersection alone does not prove contact or detect floating',
                            'finite support polygon and COM are simplified physical hypotheses',
                            'occlusion, segmentation, friction, external forces, camera uncertainty not resolved',
                            'the supplied annotation cannot independently verify its own assumptions',
                            'no AI-origin attribution or real-image accuracy has been measured'],
            'decision': 'NO_AI_ORIGIN_CONCLUSION'}


def run_depth_contact_manifest(path, out, cfg: DepthContactConfig = DepthContactConfig()):
    src = Path(path)
    data = json.loads(src.read_text(encoding='utf-8'))
    report = evaluate_contact(data, cfg)
    report['input_sha256'] = hashlib.sha256(src.read_bytes()).hexdigest()
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    (dest/'p5_d01_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return report
