"""P2-S02: robust multiple *projected* shadow-ray convergence models.

Input requires independently annotated object -> cast-shadow point correspondences.
Models describe 2D concurrence, not the number, type or 3D position of physical
light sources. A sample consensus cannot establish image authenticity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json

import cv2
import numpy as np

from .shadow_geometry import (
    ShadowConfig, ShadowEvidenceError, _parse_pairs, _normalised_lines,
    _angular_residuals_deg, _canonical_homogeneous, _fit_nullspace,
    _convergence_label,
)


@dataclass(frozen=True)
class MultiLightConfig:
    angle_threshold_deg: float = 2.0
    ransac_trials: int = 1100
    max_models: int = 3
    min_pairs_per_model: int = 5
    min_model_support_fraction: float = .16
    min_total_support_fraction: float = .55
    ambiguity_margin_deg: float = .45
    min_model_separation_deg: float = 4.0
    min_pair_separation_px: float = 5.0
    bootstrap_trials: int = 75
    seed: int = 2026

    def __post_init__(self):
        if not (0 < self.angle_threshold_deg <= 20):
            raise ShadowEvidenceError('angle_threshold_deg must be in (0,20]')
        if self.ransac_trials < 1 or self.max_models < 1 or self.max_models > 8:
            raise ShadowEvidenceError('invalid RANSAC or max_models')
        if self.min_pairs_per_model < 3 or self.bootstrap_trials < 0:
            raise ShadowEvidenceError('invalid minimum support or bootstrap trials')
        if not (0 < self.min_model_support_fraction <= 1) or not (0 < self.min_total_support_fraction <= 1):
            raise ShadowEvidenceError('support fractions must be in (0,1]')
        if not (0 <= self.ambiguity_margin_deg < self.angle_threshold_deg):
            raise ShadowEvidenceError('ambiguity_margin_deg must be in [0, angle_threshold_deg)')
        if self.min_model_separation_deg < 0 or self.min_pair_separation_px <= 0:
            raise ShadowEvidenceError('invalid separation threshold')


def _rank_ok(lines, weights):
    if len(lines) < 2:
        return False
    try:
        sv = np.linalg.svd(lines * np.sqrt(weights[:, None]), compute_uv=False)
        return bool(sv[0] > 1e-12 and sv[1] > 1e-6 * sv[0])
    except np.linalg.LinAlgError:
        return False


def _refine(v, eligible, lines, unit, mids, weights, config):
    for _ in range(4):
        residual = _angular_residuals_deg(v, unit, mids)
        keep = eligible & (residual <= config.angle_threshold_deg)
        if keep.sum() < config.min_pairs_per_model or not _rank_ok(lines[keep], weights[keep]):
            return None
        updated = _fit_nullspace(lines[keep], weights[keep])
        if updated is None:
            return None
        v = updated
    residual = _angular_residuals_deg(v, unit, mids)
    keep = eligible & (residual <= config.angle_threshold_deg)
    if keep.sum() < config.min_pairs_per_model or not _rank_ok(lines[keep], weights[keep]):
        return None
    return v, keep


def _propose(eligible, lines, unit, mids, weights, config, rng):
    ids = np.flatnonzero(eligible)
    if len(ids) < config.min_pairs_per_model:
        return None
    best = None
    candidates = []
    direct = _fit_nullspace(lines[eligible], weights[eligible])
    if direct is not None:
        candidates.append(direct)
    for _ in range(config.ransac_trials):
        i, j = rng.choice(ids, size=2, replace=False)
        proposed = _canonical_homogeneous(np.cross(lines[i], lines[j]))
        if proposed is not None:
            candidates.append(proposed)
    for candidate in candidates:
        res = _angular_residuals_deg(candidate, unit, mids)
        ok = eligible & (res <= config.angle_threshold_deg)
        if ok.sum() < config.min_pairs_per_model or not _rank_ok(lines[ok], weights[ok]):
            continue
        # An inlier count, NOT a calibrated likelihood: use conservative count/weight support.
        quality = (float(weights[ok].sum()), int(ok.sum()), -float(np.median(res[ok])))
        if best is None or quality > best[0]:
            best = (quality, candidate)
    if best is None:
        return None
    return _refine(best[1], eligible, lines, unit, mids, weights, config)


def _angular_model_separation(a, b, mids):
    # Compare *unoriented* projected rays at the same image locations.
    tests = np.column_stack([mids, np.zeros(len(mids))])
    out = []
    for v in [a, b]:
        v = _canonical_homogeneous(v)
        if abs(v[2]) > 1e-8 and np.linalg.norm(v[:2] / v[2]) < 50:
            vec = v[:2] / v[2] - tests[:, :2]
        else:
            vec = np.broadcast_to(v[:2], (len(mids), 2)).copy()
        lengths = np.linalg.norm(vec, axis=1)
        vec = np.divide(vec, lengths[:, None], out=np.zeros_like(vec), where=lengths[:, None] > 1e-10)
        out.append(vec)
    cross = np.abs(out[0][:, 0] * out[1][:, 1] - out[0][:, 1] * out[1][:, 0])
    return float(np.median(np.rad2deg(np.arcsin(np.clip(cross, 0, 1)))))


def _assign(models, unit, mids, threshold, margin):
    res = np.column_stack([_angular_residuals_deg(m, unit, mids) for m in models])
    best_ids = np.argmin(res, axis=1)
    smallest = res[np.arange(len(unit)), best_ids]
    assignments = np.where(smallest <= threshold, best_ids, -1)
    ambiguous = np.zeros(len(unit), dtype=bool)
    if len(models) > 1:
        next_best = np.partition(res, 1, axis=1)[:, 1]
        ambiguous = (assignments >= 0) & ((next_best - smallest) <= margin)
        assignments[ambiguous] = -1
    return assignments, ambiguous, res


def _model_dispersion(v, ids, lines, weights, center, scale, rng, trials):
    if not trials:
        return None
    cls, point, _ = _convergence_label(v, center, scale)
    if cls != 'FINITE_PROJECTED_POINT':
        return None
    pts = []
    for _ in range(trials):
        sample = rng.choice(ids, size=len(ids), replace=True)
        if not _rank_ok(lines[sample], weights[sample]):
            continue
        candidate = _fit_nullspace(lines[sample], weights[sample])
        if candidate is None:
            continue
        kind, pos, _ = _convergence_label(candidate, center, scale)
        if kind == 'FINITE_PROJECTED_POINT' and np.linalg.norm(np.asarray(pos) - point) < 10 * scale:
            pts.append(pos)
    if len(pts) < 4:
        return None
    return np.std(np.asarray(pts), axis=0, ddof=1).tolist()


def fit_multiple_projected_lights(data: dict, config: MultiLightConfig | None = None) -> dict:
    """Extract up to `max_models` concurrent image-plane ray families, with abstention.

    Greedy consensus proposals use previously unassigned lines; then an
    exclusive, ambiguity-aware assignment/refinement step discourages duplicate
    hypotheses. No model is treated as an independently confirmed light source.
    """
    config = config or MultiLightConfig()
    validator = ShadowConfig(min_pairs=3, min_pair_separation_px=config.min_pair_separation_px)
    shape, p, q, weights, ids = _parse_pairs(data, validator)
    n = len(ids)
    lines, unit, mids, center, scale = _normalised_lines(p, q, shape)
    rng = np.random.default_rng(config.seed)
    total_weight = float(weights.sum())
    min_abs_weight = config.min_model_support_fraction * total_weight
    models = []
    remaining = np.ones(n, dtype=bool)
    for _ in range(config.max_models):
        result = _propose(remaining, lines, unit, mids, weights, config, rng)
        if result is None:
            break
        v, members = result
        if float(weights[members].sum()) < min_abs_weight:
            break
        if any(_angular_model_separation(v, old, mids) < config.min_model_separation_deg for old in models):
            # Too close to distinguish under chosen precision; do not invent extra sources.
            break
        models.append(v)
        remaining[members] = False
    if not models:
        return {'module': 'P2_S02_MULTIPLE_PROJECTED_SHADOW_CONVERGENCES',
                'state': 'INDETERMINATE', 'reason': 'No sufficiently supported identifiable projected-ray family',
                'image_shape_hw': list(shape), 'correspondence_count': n,
                'models': [], 'model_count': 0, 'unassigned_ids': ids, 'ambiguous_ids': [],
                'decision': 'NO_AI_ORIGIN_CONCLUSION',
                'real_validation': 'DEFERRED'}

    # EM-like robust reassignment, always keep observations exclusive per family.
    for _ in range(6):
        assigned, ambiguous, residuals = _assign(models, unit, mids, config.angle_threshold_deg,
                                                  config.ambiguity_margin_deg)
        updated = []
        for k, v in enumerate(models):
            take = assigned == k
            if (take.sum() < config.min_pairs_per_model or
                    float(weights[take].sum()) < min_abs_weight or not _rank_ok(lines[take], weights[take])):
                continue
            estimate = _fit_nullspace(lines[take], weights[take])
            if estimate is not None:
                updated.append(estimate)
        if not updated:
            models = []
            break
        models = updated
    if not models:
        return {'module': 'P2_S02_MULTIPLE_PROJECTED_SHADOW_CONVERGENCES',
                'state': 'INDETERMINATE', 'reason': 'Models failed exclusive consensus refinement',
                'image_shape_hw': list(shape), 'correspondence_count': n,
                'models': [], 'model_count': 0, 'unassigned_ids': ids, 'ambiguous_ids': [],
                'decision': 'NO_AI_ORIGIN_CONCLUSION', 'real_validation': 'DEFERRED'}

    assignment, ambiguity, residual_matrix = _assign(models, unit, mids, config.angle_threshold_deg,
                                                      config.ambiguity_margin_deg)
    # A model can lose support after competition: prune and rescore.
    supported = []
    for k in range(len(models)):
        mask = assignment == k
        if (mask.sum() >= config.min_pairs_per_model and
                float(weights[mask].sum()) >= min_abs_weight and _rank_ok(lines[mask], weights[mask])):
            supported.append(k)
    if len(supported) != len(models):
        models = [models[k] for k in supported]
        if models:
            assignment, ambiguity, residual_matrix = _assign(models, unit, mids, config.angle_threshold_deg,
                                                              config.ambiguity_margin_deg)
        else:
            assignment = np.full(n, -1)
            ambiguity = np.zeros(n, dtype=bool)

    out_models = []
    for k, v in enumerate(models):
        keep = np.flatnonzero(assignment == k)
        if len(keep) < config.min_pairs_per_model:
            continue
        cls, point, direction = _convergence_label(v, center, scale)
        out_models.append({
            'model_id': f'projected_family_{len(out_models)+1:02d}',
            'model_class': cls,
            'projected_convergence_xy_px': point,
            'image_direction_at_infinity_xy': direction,
            'inlier_count': int(len(keep)),
            'weight_fraction': float(weights[keep].sum() / total_weight),
            'member_ids': [ids[i] for i in keep],
            'median_angular_residual_deg': float(np.median(residual_matrix[keep, k])),
            'p90_angular_residual_deg': float(np.percentile(residual_matrix[keep, k], 90)),
            'bootstrap_dispersion_xy_px_exploratory': _model_dispersion(
                v, keep, lines, weights, center, scale, rng, config.bootstrap_trials),
        })
    taken = {name for m in out_models for name in m['member_ids']}
    if not out_models:
        assignment = np.full(n, -1)
    support_fraction = float(sum(m['weight_fraction'] for m in out_models))
    enough = bool(out_models and support_fraction >= config.min_total_support_fraction)
    if not enough:
        state = 'INDETERMINATE'
        reason = 'Low total support: projected families may be chance alignments or bad annotations'
    else:
        state = 'MEASURED'
        reason = None
    ambiguous_ids = [ids[i] for i in range(n) if ambiguity[i] and ids[i] not in taken]
    unassigned_ids = [ids[i] for i in range(n) if ids[i] not in taken and not ambiguity[i]]
    return {
        'module': 'P2_S02_MULTIPLE_PROJECTED_SHADOW_CONVERGENCES',
        'state': state,
        'reason': reason,
        'interpretation': ('MULTIPLE_SUPPORTED_PROJECTED_RAY_FAMILIES' if len(out_models) > 1
                           else 'SINGLE_SUPPORTED_PROJECTED_RAY_FAMILY' if out_models else 'NO_SUPPORTED_FAMILY'),
        'image_shape_hw': list(shape), 'correspondence_count': n,
        'models': out_models, 'model_count': len(out_models),
        'assignment_by_id': {name: next((m['model_id'] for m in out_models if name in m['member_ids']),
                                        'AMBIGUOUS' if name in ambiguous_ids else 'UNASSIGNED') for name in ids},
        'unassigned_ids': unassigned_ids, 'ambiguous_ids': ambiguous_ids,
        'overall_weight_support_fraction': support_fraction,
        'angle_threshold_deg': config.angle_threshold_deg,
        'model_selection': 'greedy RANSAC, conservative minimum support/separation, exclusive robust reassignment',
        'config': asdict(config),
        'assumptions': ['input object/shadow point pairs are independently identified',
                        'rectilinear perspective; no uncorrected wide-angle distortion',
                        'each true direct-illumination hypothesis produces a straight projected ray'],
        'limitations': ['each fitted family is a 2D geometrical hypothesis, NOT proof of a separate physical light',
                        'false ray matches, reflections, geometry, or synthetic editing may mimic distinct families',
                        'finite convergence does not distinguish a point source from distant directional illumination',
                        'source count and residual thresholds lack real-photo calibration',
                        'weakly separated sources can merge; chance structures can produce spurious hypotheses',
                        'not an AI image classifier; no physical violation verdict'],
        'real_validation': 'DEFERRED',
        'decision': 'NO_AI_ORIGIN_CONCLUSION',
    }


def draw_multilight_overlay(image: np.ndarray, data: dict, report: dict):
    image = image.copy()
    palette = [(48, 190, 80), (210, 155, 48), (170, 70, 215), (60, 180, 230), (190, 140, 120)]
    colors = {m['model_id']: palette[k % len(palette)] for k, m in enumerate(report.get('models', []))}
    for i, pair in enumerate(data['correspondences']):
        name = str(pair.get('id', f'pair_{i:02d}'))
        match = report.get('assignment_by_id', {}).get(name, 'UNASSIGNED')
        color = colors.get(match, (128, 128, 128) if match == 'AMBIGUOUS' else (32, 48, 240))
        a = tuple(int(round(v)) for v in pair['object_xy'])
        b = tuple(int(round(v)) for v in pair['shadow_xy'])
        cv2.line(image, a, b, color, 2, cv2.LINE_AA)
        cv2.circle(image, a, 4, (220, 240, 240), -1, cv2.LINE_AA)
        cv2.circle(image, b, 4, color, -1, cv2.LINE_AA)
    for model in report.get('models', []):
        pt = model['projected_convergence_xy_px']
        if pt is not None and all(-5000 <= x <= max(image.shape[:2]) + 5000 for x in pt):
            xy = tuple(int(round(z)) for z in pt)
            cv2.drawMarker(image, xy, colors[model['model_id']], cv2.MARKER_CROSS, 23, 2, cv2.LINE_AA)
    cv2.rectangle(image, (0, 0), (min(image.shape[1], 1200), 34), (20, 28, 32), -1)
    cv2.putText(image, 'P2-S02 PROJECTED RAY FAMILIES / NOT AN AI VERDICT',
                (8, 23), cv2.FONT_HERSHEY_SIMPLEX, .55, (235, 235, 235), 1, cv2.LINE_AA)
    return image


def run_multilight_manifest(path: Path, out: Path, image_path: Path | None = None,
                            config: MultiLightConfig | None = None) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    report = fit_multiple_projected_lights(data, config)
    out.mkdir(parents=True, exist_ok=True)
    report['input_file'] = str(path)
    if image_path is not None:
        raw = image_path.read_bytes()
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ShadowEvidenceError('image could not be decoded')
        if tuple(img.shape[:2]) != tuple(report['image_shape_hw']):
            raise ShadowEvidenceError('image dimensions and manifest mismatch')
        report['image_sha256'] = hashlib.sha256(raw).hexdigest()
        fname = 'p2_s02_overlay.png'
        if not cv2.imwrite(str(out / fname), draw_multilight_overlay(img, data, report)):
            raise ShadowEvidenceError('could not write P2-S02 overlay')
        report['overlay_file'] = fname
    (out / 'p2_s02_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return report
