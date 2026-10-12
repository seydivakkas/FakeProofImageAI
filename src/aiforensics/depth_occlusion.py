"""P5-D02: conditional 3-D visibility constraints, never AI-origin attribution.

Each probe compares independent annotations against a calibrated, externally
measured *finite* collection of planar opaque surfaces. Image overlap alone is
never treated as evidence of metric depth. Measurements close to occlusion
boundaries or coincident depths are reported as INDETERMINATE.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .depth_contact import (DepthContactError, PinholeCamera, SupportPlane,
                            DepthContactConfig, evaluate_contact)


class OcclusionGeometryError(ValueError):
    pass


@dataclass(frozen=True)
class OcclusionConfig:
    pixel_tolerance: float = 3.0
    surface_tolerance_world: float = 0.025
    min_depth_gap_world: float = 0.04
    sigma_multiplier: float = 3.0
    max_ray_distance_world: float = 10000.0

    def __post_init__(self):
        vals = [self.pixel_tolerance, self.surface_tolerance_world,
                self.min_depth_gap_world, self.sigma_multiplier,
                self.max_ray_distance_world]
        if any(not np.isfinite(v) or v <= 0 for v in vals):
            raise OcclusionGeometryError('occlusion tolerances must be positive finite values')


def _point3(raw, name):
    x = np.asarray(raw, dtype=float)
    if x.shape != (3,) or not np.all(np.isfinite(x)):
        raise OcclusionGeometryError(f'{name} must contain three finite coordinates')
    return x


def _probe_pixel(raw, cam):
    x = np.asarray(raw, dtype=float)
    h, w = cam.image_shape_hw
    if x.shape != (2,) or not np.all(np.isfinite(x)) or not (0 <= x[0] < w and 0 <= x[1] < h):
        raise OcclusionGeometryError('probe pixel must be finite and inside image')
    return x


def _sigma(raw):
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise OcclusionGeometryError('pixel_sigma_px must be numeric') from exc
    if not np.isfinite(value) or value < 0 or value > 20:
        raise OcclusionGeometryError('pixel_sigma_px must be finite in [0,20]')
    return value


def _scene(data):
    try:
        camera = PinholeCamera(data['camera'], data['image_shape_hw'])
        records = data['surfaces']
    except (KeyError, TypeError, DepthContactError) as exc:
        raise OcclusionGeometryError(f'bad camera or surfaces: {exc}') from exc
    if not isinstance(records, list) or not records:
        raise OcclusionGeometryError('nonempty surfaces list required')
    planes = {}
    meta = {}
    for record in records:
        try:
            surf = SupportPlane(record)
        except (TypeError, ValueError, KeyError, DepthContactError) as exc:
            raise OcclusionGeometryError(f'invalid planar surface: {exc}') from exc
        if surf.id in planes or not surf.id:
            raise OcclusionGeometryError('duplicate or empty surface id')
        opaque = record.get('opaque', True)
        double_sided = record.get('double_sided', True)
        if not isinstance(opaque, bool) or not isinstance(double_sided, bool):
            raise OcclusionGeometryError('opaque/double_sided must be booleans')
        planes[surf.id] = surf
        meta[surf.id] = {'opaque': opaque, 'double_sided': double_sided,
                         'independent': record.get('geometry_provenance') == 'independent_metric'}
    return camera, planes, meta


def _intersections(camera, planes, meta, pixel, config):
    ray = camera.ray(pixel)
    results = []
    for name, plane in planes.items():
        dot = float(plane.n @ ray)
        if abs(dot) < 1e-10:
            continue
        if not meta[name]['double_sided'] and dot >= -1e-10:
            continue
        distance = -(float(plane.n @ camera.C) + plane.d) / dot
        if not (1e-8 < distance <= config.max_ray_distance_world):
            continue
        point = camera.C + distance * ray
        if not plane.contains(point, margin=1e-7):
            continue
        results.append({'surface_id': name, 'ray_depth_world': float(distance),
                        'world_xyz': point.tolist(), 'opaque': meta[name]['opaque'],
                        'independent_geometry': meta[name]['independent']})
    return sorted(results, key=lambda x: (x['ray_depth_world'], x['surface_id']))


def _front(hits, gap):
    """Nearest *opaque* layer only; transparent polygons do not hide others."""
    opaque = [x for x in hits if x['opaque']]
    if not opaque:
        return None, False
    ambiguous = len(opaque) > 1 and (opaque[1]['ray_depth_world'] - opaque[0]['ray_depth_world']) <= gap
    return opaque[0]['surface_id'], ambiguous


def _sample_stability(camera, planes, meta, xy, sigma, cfg, baseline):
    # Even nominally zero-uncertainty pixels need a subpixel boundary guard.
    delta = max(0.5, sigma * cfg.sigma_multiplier)
    offsets = [(delta, 0), (-delta, 0), (0, delta), (0, -delta),
               (delta, delta), (-delta, -delta), (delta, -delta), (-delta, delta)]
    h, w = camera.image_shape_hw
    for dx, dy in offsets:
        shifted = xy + [dx, dy]
        if not (0 <= shifted[0] < w and 0 <= shifted[1] < h):
            return False
        hits = _intersections(camera, planes, meta, shifted, cfg)
        front, tie = _front(hits, cfg.min_depth_gap_world)
        if tie or front != baseline:
            return False
    return True


def _state(evidence, reasons, ambiguity):
    if reasons:
        return 'INCONSISTENT_UNDER_ASSUMPTIONS'
    if ambiguity or not evidence:
        return 'INDETERMINATE'
    return 'CONSISTENT'


def evaluate_occlusion(data: dict, cfg: OcclusionConfig = OcclusionConfig()):
    if not isinstance(data, dict):
        raise OcclusionGeometryError('manifest must be an object')
    cam, planes, meta = _scene(data)
    probes = data.get('visibility_probes', [])
    anchors = data.get('metric_anchors', [])
    if not isinstance(probes, list) or not isinstance(anchors, list) or not (probes or anchors):
        raise OcclusionGeometryError('visibility_probes or metric_anchors required')
    ids = set()
    rows = []
    for p in probes:
        if not isinstance(p, dict):
            raise OcclusionGeometryError('visibility probes must be objects')
        pid = str(p.get('id', ''))
        if not pid or pid in ids:
            raise OcclusionGeometryError('duplicate or missing observation id')
        ids.add(pid)
        xy = _probe_pixel(p.get('pixel_xy'), cam)
        sigma = _sigma(p.get('pixel_sigma_px', 0))
        claimed = p.get('observed_front_surface_id')
        if claimed is not None and (not isinstance(claimed, str) or not claimed):
            raise OcclusionGeometryError('observed front surface id must be a name')
        hits = _intersections(cam, planes, meta, xy, cfg)
        front, tie = _front(hits, cfg.min_depth_gap_world)
        stable = _sample_stability(cam, planes, meta, xy, sigma, cfg, front)
        evidence = []
        errors = []
        unknown = []
        all_metric = all(meta[x['surface_id']]['independent'] for x in hits)
        if tie:
            unknown.append('opaque surface depths are too close to order reliably')
        if not stable:
            unknown.append('front surface changes under declared pixel uncertainty')
        if not all_metric:
            unknown.append('intersected surface geometry lacks independent metric provenance')
        if p.get('visibility_provenance') != 'independent_annotation' or claimed is None:
            unknown.append('no independent front-layer annotation; predicted ray order is descriptive only')
        elif claimed not in planes:
            unknown.append('annotation refers to a surface not in the declared 3D model')
        elif not unknown:
            if front is None:
                # Scene may not contain all real objects: a label with no predicted
                # intersection cannot establish a discrepancy unless completeness asserted.
                if data.get('declared_scene_complete') is True:
                    errors.append('independently observed front layer absent from complete declared geometry')
                else:
                    unknown.append('no opaque intersection; scene coverage is not independently complete')
            elif claimed == front:
                evidence.append('observed visible layer agrees with closest independently measured opaque surface')
            else:
                claim_hit = next((x for x in hits if x['surface_id'] == claimed), None)
                if claim_hit is not None and claim_hit['opaque']:
                    front_hit = next(x for x in hits if x['surface_id'] == front)
                    if (claim_hit['ray_depth_world'] - front_hit['ray_depth_world'] > cfg.min_depth_gap_world):
                        errors.append('annotated far surface is blocked by independently measured opaque foreground')
                    else:
                        unknown.append('multiple layers have insufficient independent depth separation')
                elif data.get('declared_scene_complete') is True:
                    errors.append('independently annotated layer is not the predicted opaque foreground')
                else:
                    unknown.append('annotation cannot be checked without complete visible surface geometry')
        rows.append({'id': pid, 'kind': 'visibility', 'state': _state(evidence, errors, unknown),
                     'pixel_xy': xy.tolist(), 'pixel_sigma_px': sigma,
                     'observed_front_surface_id': claimed, 'predicted_front_opaque_surface_id': front,
                     'ray_intersections': hits, 'stable_under_pixel_noise': stable,
                     'physical_checks': evidence, 'inconsistency_reasons': errors,
                     'limitations': unknown})
    for a in anchors:
        if not isinstance(a, dict):
            raise OcclusionGeometryError('metric anchors must be objects')
        aid = str(a.get('id', ''))
        if not aid or aid in ids:
            raise OcclusionGeometryError('duplicate or missing observation id')
        ids.add(aid)
        surf_id = a.get('surface_id')
        if surf_id not in planes:
            raise OcclusionGeometryError('anchor references undeclared surface')
        xyz = _point3(a.get('independent_world_xyz'), 'independent_world_xyz')
        xy = _probe_pixel(a.get('pixel_xy'), cam)
        sigma = _sigma(a.get('pixel_sigma_px', 0))
        expected = None
        errors, evidence, unknown = [], [], []
        plane = planes[surf_id]
        if a.get('anchor_provenance') != 'independent_metric' or not meta[surf_id]['independent']:
            unknown.append('3D anchor and surface must be independently measured')
        else:
            distance = plane.signed_distance(xyz)
            if abs(distance) > cfg.surface_tolerance_world or not plane.contains(xyz, cfg.surface_tolerance_world):
                errors.append('independent 3D anchor lies outside its declared finite planar surface')
            else:
                evidence.append('independent 3D anchor belongs to its declared finite surface')
            try:
                expected = cam.project(xyz)
                residual = float(np.linalg.norm(expected - xy))
                if residual > cfg.pixel_tolerance + cfg.sigma_multiplier * sigma:
                    errors.append('independently measured 3D anchor fails image reprojection check')
                elif residual > cfg.pixel_tolerance:
                    unknown.append('anchor residual falls within pixel uncertainty band')
                else:
                    evidence.append('independent 3D anchor reprojects to observation')
            except DepthContactError:
                errors.append('independent 3D anchor cannot be projected in front of camera')
            if a.get('claimed_visible') is True:
                if a.get('visibility_provenance') != 'independent_annotation':
                    unknown.append('visible anchor requires independent visibility provenance')
                else:
                    layer_hits = _intersections(cam, planes, meta, xy, cfg)
                    front_id, tie = _front(layer_hits, cfg.min_depth_gap_world)
                    stable = _sample_stability(cam, planes, meta, xy, sigma, cfg, front_id)
                    if tie or not stable:
                        unknown.append('anchor occlusion ordering ambiguous at pixel uncertainty scale')
                    elif not all(meta[h['surface_id']]['independent'] for h in layer_hits):
                        unknown.append('anchor occlusion requires independently measured foreground surfaces')
                    elif front_id is not None and front_id != surf_id:
                        # Only an existing nearer opaque geometry yields a contradiction.
                        front_distance = next(h['ray_depth_world'] for h in layer_hits if h['surface_id'] == front_id)
                        anchor_distance = float(np.linalg.norm(xyz-cam.C))
                        if anchor_distance-front_distance > cfg.min_depth_gap_world:
                            errors.append('independently visible 3D anchor is hidden behind opaque measured geometry')
                        else:
                            unknown.append('anchor depth too close to occluder for a firm decision')
                    elif front_id == surf_id:
                        evidence.append('independently visible 3D anchor is the nearest modeled opaque layer')
                    else:
                        unknown.append('anchor visibility cannot be established from incomplete opaque geometry')
        rows.append({'id': aid, 'kind': 'metric_anchor', 'state': _state(evidence, errors, unknown),
                     'surface_id': surf_id, 'pixel_xy': xy.tolist(),
                     'projected_world_anchor_pixel_xy': expected.tolist() if expected is not None else None,
                     'physical_checks': evidence, 'inconsistency_reasons': errors,
                     'limitations': unknown})
    counts = {s: sum(r['state'] == s for r in rows) for s in
              ['CONSISTENT', 'INCONSISTENT_UNDER_ASSUMPTIONS', 'INDETERMINATE']}
    overall = ('INCONSISTENT_UNDER_ASSUMPTIONS' if counts['INCONSISTENT_UNDER_ASSUMPTIONS']
               else 'INDETERMINATE' if counts['INDETERMINATE'] else 'CONSISTENT')
    report = {'module': 'P5_D02_MULTIPLANE_OCCLUSION', 'state': overall,
              'counts': counts, 'observations': rows,
              'assumptions': ['calibrated camera K/R/t and any known distortion',
                              'finite convex planar objects externally measured in one world frame',
                              'opaque/double-sided surface definitions correspond to physical scene',
                              'visibility annotation independently observed, not inferred from same ray model'],
              'limitations': ['unknown surfaces and unmeasured depth cannot be reconstructed from one photo',
                              'pixel uncertainty is guarded by discrete perturbations, not calibrated probability',
                              'planar opacity approximation excludes translucency and volumetric geometry',
                              'a geometry-consistency finding never authenticates image provenance'],
              'decision': 'NO_AI_ORIGIN_CONCLUSION'}
    if 'd01_observations' in data:
        try:
            d01_data = {'camera': data['camera'], 'image_shape_hw': data['image_shape_hw'],
                        'gravity_world': data['gravity_world'],
                        'support_surfaces': data.get('support_surfaces', data['surfaces']),
                        'observations': data['d01_observations']}
            parent = evaluate_contact(d01_data, DepthContactConfig(pixel_tolerance=cfg.pixel_tolerance))
            report['p5_d01_integration'] = {'state': parent['state'], 'counts': parent['counts'],
                                             'observations': parent['observations']}
        except (KeyError, TypeError, DepthContactError) as exc:
            raise OcclusionGeometryError(f'P5-D01 integration invalid: {exc}') from exc
    return report


def run_occlusion_manifest(path, out, cfg: OcclusionConfig = OcclusionConfig()):
    source = Path(path)
    data = json.loads(source.read_text(encoding='utf-8'))
    result = evaluate_occlusion(data, cfg)
    result['input_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    (dest/'p5_d02_report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                                     allow_nan=False), encoding='utf-8')
    return result
