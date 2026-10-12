"""P8-E01: conservative, independently auditable physical evidence contract.

A residual tests a SPECIFIED physical null, never image authenticity or AI origin.
E02 will handle dependence and multiple comparisons; this module never fuses p values.
Only independently calibrated, pre-registered tests can return a conditional verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 'p8.e01.v1'
MODULES: dict[str, str] = {
    'P1-G01': 'Vanishing point geometry',
    'P1-G02': 'Orthogonal camera calibration',
    'P1-G03': 'Projective cross-ratio invariants',
    'P1-G04': 'Planar homography',
    'P2-S01': 'Projected shadow convergence',
    'P2-S02': 'Multiple projected light families',
    'P2-S03': 'Calibrated 3D lighting',
    'P2-S04': 'Solar shadow direction',
    'P2-S05': 'Penumbra and angular light size',
    'P3-R01': 'Planar mirror',
    'P3-R02': 'Refraction',
    'P3-R03': 'Multiple mirrors',
    'P4-O01': 'Lens distortion',
    'P4-O02': 'Depth of field',
    'P4-O03': 'Focal length and FoV',
    'P4-O04': 'Vignetting',
    'P5-D01': '3D depth and contact',
    'P5-D02': 'Multi-plane occlusion',
    'P5-D03': 'Static equilibrium',
    'P6-M01': 'Lambertian BRDF',
    'P6-M02': 'GGX microfacet BRDF',
    'P6-M03': 'Combined material BRDF',
    'P7-S01': 'Poisson-Gaussian sensor noise',
    'P7-S02': 'PRNU and DSNU fingerprint',
}
STATES = ('CONSISTENT_UNDER_ASSUMPTIONS',
          'INCONSISTENT_UNDER_ASSUMPTIONS', 'INDETERMINATE', 'NOT_APPLICABLE')


class EvidenceContractError(ValueError):
    """The input is malformed; this is distinct from scientifically inconclusive."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise EvidenceContractError(f'{name} must be a finite number, not boolean')
    try:
        x = float(value)
    except (ValueError, TypeError) as exc:
        raise EvidenceContractError(f'{name} must be a finite number') from exc
    if not math.isfinite(x):
        raise EvidenceContractError(f'{name} must be finite')
    return x


def _mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise EvidenceContractError(f'{name} must be an object')
    return value


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceContractError(f'{name} must be a nonempty string')
    return value.strip()


def _must_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise EvidenceContractError(f'{name} must be boolean')
    return value


def _gate_assumptions(assumptions: Any) -> list[str]:
    if not isinstance(assumptions, list) or not assumptions:
        raise EvidenceContractError('assumptions must contain independently checkable items')
    reasons = []
    seen = set()
    for a in assumptions:
        a = _mapping(a, 'assumption')
        name = _nonempty(a.get('name'), 'assumption.name')
        if name in seen:
            raise EvidenceContractError('duplicate assumption name')
        seen.add(name)
        status = a.get('status')
        if status not in ('supported', 'unsupported', 'unknown'):
            raise EvidenceContractError('assumption.status must be supported/unsupported/unknown')
        _nonempty(a.get('source'), 'assumption.source')
        if status != 'supported':
            reasons.append(f'{name}: {status}')
    return reasons


def analyze_evidence_record(record: dict, *, dataset_scope: str = 'synthetic_controlled') -> dict:
    """Test one externally supplied, scalar, independently calibrated holdout residual.

    Null: measured - predicted ~ Normal(0, sigma_total^2), *conditional*
    on stated geometry, calibration, reference, covariance and holdout design.
    Not rejecting this null never proves model truth. No multiple-testing claims.
    """
    item = _mapping(record, 'record')
    module = _nonempty(item.get('module_id'), 'module_id')
    if module not in MODULES:
        raise EvidenceContractError(f'unknown module_id: {module}')
    obs_id = _nonempty(item.get('observation_id'), 'observation_id')
    unit = _nonempty(item.get('unit'), 'unit')
    reasons = _gate_assumptions(item.get('assumptions'))
    provenance = _mapping(item.get('provenance'), 'provenance')
    _nonempty(provenance.get('source_id'), 'provenance.source_id')
    _nonempty(provenance.get('calibration_id'), 'provenance.calibration_id')
    if provenance.get('split') != 'holdout':
        reasons.append('measurement not in independent holdout split')
    if not _must_bool(provenance.get('independent_of_training'), 'provenance.independent_of_training'):
        reasons.append('train/holdout leakage or independence not established')
    if not _must_bool(provenance.get('external_reference_verified'), 'provenance.external_reference_verified'):
        reasons.append('physical reference has not been independently verified')
    if dataset_scope not in ('synthetic_controlled', 'real_unverified', 'real_verified'):
        raise EvidenceContractError('dataset_scope must be synthetic_controlled/real_unverified/real_verified')
    if dataset_scope == 'real_unverified':
        reasons.append('real data validation has not been completed')
    if dataset_scope == 'real_verified' and not provenance.get('external_reference_verified'):
        reasons.append('real reference incomplete')
    test = _mapping(item.get('test'), 'test')
    if test.get('null_distribution') != 'normal_zero_mean_residual':
        reasons.append('unverified test null distribution')
    if not _must_bool(test.get('pre_registered'), 'test.pre_registered'):
        reasons.append('test not pre-registered')
    if not _must_bool(test.get('distribution_independently_checked'), 'test.distribution_independently_checked'):
        reasons.append('null distribution not independently checked')
    alpha = _finite(test.get('alpha', 0.01), 'test.alpha')
    if not 0 < alpha < 1:
        raise EvidenceContractError('alpha must be strictly between 0 and 1')
    unc = _mapping(item.get('uncertainty'), 'uncertainty')
    sm = _finite(unc.get('measurement_std'), 'uncertainty.measurement_std')
    sp = _finite(unc.get('prediction_std'), 'uncertainty.prediction_std')
    rho = unc.get('error_correlation')
    if rho is None:
        reasons.append('measurement/prediction error correlation unknown')
    else:
        rho = _finite(rho, 'uncertainty.error_correlation')
        if abs(rho) > 1:
            raise EvidenceContractError('error correlation must lie in [-1,1]')
    if sm < 0 or sp < 0:
        raise EvidenceContractError('standard deviations cannot be negative')
    measured = _finite(item.get('measured'), 'measured')
    predicted = _finite(item.get('predicted'), 'predicted')
    residual = measured - predicted
    total_variance = None if rho is None else sm * sm + sp * sp - 2 * rho * sm * sp
    if total_variance is not None and total_variance <= 1e-24:
        reasons.append('zero or near-zero residual variance: test is not identifiable')
    output = {
        'schema_version': SCHEMA_VERSION, 'module_id': module,
        'module_label': MODULES[module], 'observation_id': obs_id,
        'unit': unit, 'measured': measured, 'predicted': predicted,
        'effect_size_absolute': abs(residual), 'signed_residual': residual,
        'assumptions': item['assumptions'], 'provenance': provenance,
        'test': {'null_hypothesis': 'residual is zero-mean normal with specified covariance under physical assumptions',
                 'alternative_hypothesis': 'a nonzero mean residual under the same fixed physical assumptions',
                 'alpha': alpha, 'null_distribution': test.get('null_distribution')},
        'uncertainty': {'measurement_std': sm, 'prediction_std': sp,
                        'error_correlation': rho,
                        'residual_std': math.sqrt(total_variance) if total_variance is not None and total_variance > 0 else None},
        'state': 'INDETERMINATE', 'reasons': reasons,
        'standardized_effect': None, 'p_value_two_sided': None,
        'confidence_interval_95_for_residual': None,
        'decision': 'NO_AI_ORIGIN_CONCLUSION',
        'interpretation_limit': 'Individual conditional null test only; no multi-test calibration or evidence fusion',
        'dataset_scope': dataset_scope,
    }
    if reasons:
        return output
    sigma = math.sqrt(total_variance)
    z = residual / sigma
    p = math.erfc(abs(z) / math.sqrt(2))
    # 95% central normal error interval, descriptive under specified null.
    output.update(
        standardized_effect=z,
        p_value_two_sided=p,
        confidence_interval_95_for_residual=[residual - 1.959963984540054 * sigma,
                                             residual + 1.959963984540054 * sigma],
        state=('INCONSISTENT_UNDER_ASSUMPTIONS' if p < alpha else 'CONSISTENT_UNDER_ASSUMPTIONS'),
        reasons=[('rejects pre-registered conditional normal null at alpha'
                  if p < alpha else 'does not reject conditional null; NOT proof of model truth')],
    )
    return output


def normalize_legacy_report(module_id: str, report: dict, *, report_id: str) -> dict:
    """Expose pre-P8 reports without inventing missing uncertainty or calibration.

    Legacy data are structured descriptive evidence only until independently
    calibrated, provenance-checked holdout measurements become available.
    """
    if module_id not in MODULES:
        raise EvidenceContractError('unrecognized module')
    _mapping(report, 'legacy report')
    _nonempty(report_id, 'report_id')
    old = str(report.get('state', report.get('status', 'UNKNOWN')))
    return {'schema_version': SCHEMA_VERSION, 'module_id': module_id,
            'observation_id': report_id, 'state': 'INDETERMINATE',
            'legacy_state': old, 'reasons': ['legacy report lacks verified independent calibration and full P8 uncertainty contract'],
            'legacy_report_sha256': hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False,
                                                           allow_nan=False).encode('utf-8')).hexdigest(),
            'p_value_two_sided': None,
            'decision': 'NO_AI_ORIGIN_CONCLUSION', 'report_mode': 'DESCRIPTIVE_LEGACY_BRIDGE'}


def analyze_evidence_manifest(manifest: dict) -> dict:
    manifest = _mapping(manifest, 'manifest')
    if manifest.get('schema_version') != SCHEMA_VERSION:
        raise EvidenceContractError('wrong schema version')
    scope = manifest.get('dataset_scope', 'real_unverified')
    if scope not in ('synthetic_controlled', 'real_unverified', 'real_verified'):
        raise EvidenceContractError('unsupported dataset_scope')
    records = manifest.get('records')
    if not isinstance(records, list) or not records:
        raise EvidenceContractError('records must be a nonempty list')
    if len(records) > 10000:
        raise EvidenceContractError('records exceeds safe input cap')
    seen = set()
    evaluated = []
    for item in records:
        result = analyze_evidence_record(item, dataset_scope=scope)
        key = (result['module_id'], result['observation_id'])
        if key in seen:
            raise EvidenceContractError('duplicate module/observation identifier: potential double count')
        seen.add(key)
        evaluated.append(result)
    counts = {s: sum(r['state'] == s for r in evaluated) for s in STATES}
    return {'schema_version': SCHEMA_VERSION, 'engine': 'P8-E01',
            'dataset_scope': scope, 'record_count': len(evaluated),
            'coverage': {'registered_modules': len(MODULES),
                         'modules_in_manifest': sorted(set(r['module_id'] for r in evaluated))},
            'summary_counts': counts, 'records': evaluated,
            'fusion_state': 'NOT_PERFORMED',
            'multiple_testing_state': 'NOT_CALIBRATED',
            'decision': 'NO_AI_ORIGIN_CONCLUSION',
            'warnings': ['A small p-value is not an AI-origin likelihood',
                         'Non-rejection is not evidence of authenticity',
                         'Independent physical validation remains a final project phase',
                         'P8-E02 must model shared input and cross-module dependence before aggregation']}


def run_evidence_manifest(input_path: str | Path, out_dir: str | Path) -> dict:
    src = Path(input_path)
    manifest = json.loads(src.read_text(encoding='utf-8'))
    result = analyze_evidence_manifest(manifest)
    result['source_manifest_sha256'] = hashlib.sha256(src.read_bytes()).hexdigest()
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'p8_e01_evidence_report.json').write_text(json.dumps(result, ensure_ascii=False,
                                                        indent=2, allow_nan=False), encoding='utf-8')
    return result