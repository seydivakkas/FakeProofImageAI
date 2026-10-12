"""P7-S02: conditional RAW PRNU/DSNU fixed-pattern estimation.

A reference dark/flat stack and a disjoint query dark/flat stack are REQUIRED.
Not a single-photo camera identifier and not proof of AI origin.

DSNU map: per-pixel dark mean minus spatial mean (electrons at fixed exposure).
PRNU map: (per-pixel flat mean minus per-pixel dark mean) divided by
          spatial mean dark-subtracted flat response, minus one.
Only flat-field conditions, linear sensor data and matching geometry make
these definitions meaningful. Fixed-pattern maps are separate from temporal
Poisson/Gaussian noise (P7-S01).
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import math
import hashlib
import numpy as np
from scipy.ndimage import gaussian_filter
from .sensor_noise import SensorParameters


class FingerprintError(ValueError):
    pass


@dataclass(frozen=True)
class FingerprintConfig:
    min_frames: int = 8
    min_pixels: int = 256
    min_signal_adu: float = 30.0
    max_clipped_fraction: float = 0.001
    min_pattern_snr: float = 1.5
    # These are only descriptive thresholds for controlled independent-pixel
    # synthetic cases. They are not forensic FPR-calibrated detection thresholds.
    exploratory_match_corr: float = 0.55
    exploratory_nonmatch_corr: float = 0.20


def validate_stack(stack: np.ndarray, sensor: SensorParameters, config: FingerprintConfig,
                   name: str) -> np.ndarray:
    raw = np.asarray(stack)
    if raw.ndim != 3 or raw.shape[0] < config.min_frames or min(raw.shape[1:]) < 2:
        raise FingerprintError(f'{name}: expected [T>=min_frames,H,W]')
    if raw.shape[1]*raw.shape[2] < config.min_pixels:
        raise FingerprintError(f'{name}: insufficient independent spatial samples')
    if not np.issubdtype(raw.dtype, np.number) or not np.all(np.isfinite(raw)):
        raise FingerprintError(f'{name}: non-finite/non-numeric RAW')
    if (np.min(raw) < 0 or np.max(raw) > sensor.adc_max_adu or
            np.any(raw != np.rint(raw))):
        raise FingerprintError(f'{name}: RAW must be integer ADU within ADC limits')
    return raw.astype(np.float64)


def estimate_fingerprint(dark: np.ndarray, flat: np.ndarray, sensor: SensorParameters,
                         config: FingerprintConfig | None = None) -> dict:
    c = config or FingerprintConfig()
    d = validate_stack(dark, sensor, c, 'dark')
    f = validate_stack(flat, sensor, c, 'flat')
    if d.shape[1:] != f.shape[1:]:
        raise FingerprintError('dark and flat pixel grids must match')
    if np.array_equal(d[:min(len(d),len(f))], f[:min(len(d),len(f))]):
        raise FingerprintError('dark and flat are identical; invalid calibration set')
    clipped = float(np.mean((d >= sensor.adc_max_adu) | (d <= 0))) if d.shape==f.shape else max(float(np.mean(d>=sensor.adc_max_adu)),float(np.mean(d<=0)))
    clipped = max(clipped, float(np.mean(f>=sensor.adc_max_adu)), float(np.mean(f<=0)))
    if clipped > c.max_clipped_fraction:
        raise FingerprintError('clipped black/white codes invalidate linear pattern estimation')
    dark_mean=d.mean(axis=0)
    flat_mean=f.mean(axis=0)
    response=flat_mean-dark_mean
    signal=float(response.mean())
    if not math.isfinite(signal) or signal < c.min_signal_adu or np.any(response <= 0):
        raise FingerprintError('flat signal too weak or not positive across pixels')
    # Quantitative pattern maps: zero spatial mean by construction.
    dsnu=(dark_mean-dark_mean.mean())*sensor.gain_e_per_adu
    prnu=response/signal-1.0
    # Noise uncertainty on per-pixel map from independent temporal frames.
    # For PRNU the normalization uncertainty is a common-mode nuisance; these
    # are approximate SNR diagnostics, not certified uncertainty intervals.
    dvar=d.var(axis=0,ddof=1)
    fvar=f.var(axis=0,ddof=1)
    dsnu_noise=float(np.sqrt(np.mean(dvar)/d.shape[0])*sensor.gain_e_per_adu)
    response_noise=float(np.sqrt(np.mean(dvar)/d.shape[0]+np.mean(fvar)/f.shape[0]))
    prnu_noise=response_noise/signal
    prnu_sd=float(np.std(prnu,ddof=1))
    dsnu_sd=float(np.std(dsnu,ddof=1))
    return {'prnu_map':prnu,'dsnu_map_e':dsnu,
            'prnu_match_map':prnu-gaussian_filter(prnu,sigma=3.0),
            'dsnu_match_map_e':dsnu-gaussian_filter(dsnu,sigma=3.0),
            'prnu_rms_fraction':prnu_sd,'dsnu_rms_e':dsnu_sd,
            'prnu_noise_se_fraction_approx':prnu_noise,
            'dsnu_noise_se_e_approx':dsnu_noise,
            'prnu_snr_approx':prnu_sd/max(prnu_noise,1e-12),
            'dsnu_snr_approx':dsnu_sd/max(dsnu_noise,1e-12),
            'dark_temporal_variance_adu2':float(dvar.mean()),
            'flat_temporal_variance_adu2':float(fvar.mean()),
            'dark_frame_count':int(len(d)),'flat_frame_count':int(len(f)),
            'shape_hw':list(d.shape[1:]),'mean_dark_adu':float(dark_mean.mean()),
            'mean_illuminated_signal_adu':signal}


def pearson_map(a: np.ndarray, b: np.ndarray) -> float | None:
    x=np.asarray(a,dtype=float).ravel();y=np.asarray(b,dtype=float).ravel()
    if x.shape != y.shape or len(x)<2 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        return None
    x=x-x.mean();y=y-y.mean();d=np.linalg.norm(x)*np.linalg.norm(y)
    if d <= 1e-12:return None
    return float(np.clip(x.dot(y)/d,-1.,1.))


def compare_fingerprints(ref: dict, query: dict, config: FingerprintConfig | None=None,
                         *, synthetic_independent_pixels: bool=False) -> dict:
    c=config or FingerprintConfig()
    if ref['shape_hw'] != query['shape_hw']:
        return {'state':'INDETERMINATE','reason':'misaligned image grids / different resolution',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    rp=pearson_map(ref['prnu_match_map'],query['prnu_match_map'])
    rd=pearson_map(ref['dsnu_match_map_e'],query['dsnu_match_map_e'])
    low_snr=(min(ref['prnu_snr_approx'],query['prnu_snr_approx'],
                 ref['dsnu_snr_approx'],query['dsnu_snr_approx']) < c.min_pattern_snr)
    result={'state':'INDETERMINATE','prnu_pearson_r':rp,'dsnu_pearson_r':rd,
            'reference_prnu_snr':ref['prnu_snr_approx'],
            'query_prnu_snr':query['prnu_snr_approx'],
            'reference_dsnu_snr':ref['dsnu_snr_approx'],
            'correlation_preprocessing':'spatial Gaussian highpass sigma=3 native pixels',
            'query_dsnu_snr':query['dsnu_snr_approx'],
            'effective_pixels':int(np.prod(ref['shape_hw'])),
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'identity_claim':'NOT_CALIBRATED_FOR_REAL_CAMERAS'}
    if rp is None or rd is None or low_snr:
        result['reason']='insufficient stable pattern energy / estimation SNR'
        return result
    if not synthetic_independent_pixels:
        result['reason']='descriptive correlations only; no independently calibrated real-sensor false-match thresholds'
        return result
    if min(rp,rd)>=c.exploratory_match_corr:
        result.update(state='CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS',
                      reason='both fixed-pattern maps agree under controlled independent-pixel synthetic truth')
    elif max(rp,rd)<=c.exploratory_nonmatch_corr:
        result.update(state='INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS',
                      reason='neither fixed-pattern map agrees under controlled independent-pixel synthetic truth')
    else:
        result['reason']='ambiguous one-channel/cross-channel correlation or not safely separated'
    return result


def _load_npz(p:Path, config:FingerprintConfig, sensor:SensorParameters)->dict:
    if not p.is_file():raise FingerprintError(f'file missing: {p}')
    with np.load(p,allow_pickle=False) as z:
        if 'dark' not in z.files or 'flat' not in z.files:
            raise FingerprintError(f'{p}: NPZ must contain dark and flat arrays')
        fp=estimate_fingerprint(z['dark'],z['flat'],sensor,config)
        digest=hashlib.sha256()
        for name in ('dark','flat'):
            array=np.ascontiguousarray(z[name]);digest.update(str(array.shape).encode())
            digest.update(array.tobytes())
        fp['_source_stacks_sha256']=digest.hexdigest()
        return fp


def _summary(fp:dict)->dict:
    return {k:(v.tolist() if isinstance(v,np.ndarray) else v)
            for k,v in fp.items() if k not in ('prnu_map','dsnu_map_e','prnu_match_map','dsnu_match_map_e','_source_stacks_sha256')}


def analyze_fingerprint_manifest(manifest:dict, *, base_dir:Path|None=None,
                                 config:FingerprintConfig|None=None,
                                 controlled_synthetic_evaluation:bool=False)->dict:
    c=config or FingerprintConfig()
    if not isinstance(manifest,dict) or not isinstance(manifest.get('sensor'),dict):
        raise FingerprintError('manifest must contain sensor parameters')
    s=SensorParameters(**manifest['sensor'])
    if manifest.get('input_domain')!='linear_native_raw_adu':
        raise FingerprintError('only linear native RAW ADU supported')
    base=base_dir or Path('.')
    path=lambda v:(base/str(v)).resolve()
    ref=_load_npz(path(manifest['reference_npz']),c,s)
    conditions=('uniform_flat_field','matched_exposure_and_gain',
                'matched_temperature','spatial_alignment_verified',
                'independent_capture_stacks','unprocessed_native_raw')
    assumptions_ok=all(manifest.get(a) is True for a in conditions)
    # Claimed synthetic provenance cannot be established from arbitrary JSON;
    # this field gates the *demonstration* statuses, not forensic certification.
    synthetic=(controlled_synthetic_evaluation and
               manifest.get('provenance')=='synthetic_ground_truth' and assumptions_ok)
    queries=manifest.get('queries')
    if not isinstance(queries,list) or not queries:
        raise FingerprintError('at least one query NPZ is required')
    outputs=[];seen=set()
    for item in queries:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id']:
            raise FingerprintError('queries require nonempty string IDs')
        if item['id'] in seen:raise FingerprintError('duplicate query ID')
        seen.add(item['id'])
        try:
            fp=_load_npz(path(item['npz']),c,s)
            if fp['_source_stacks_sha256']==ref['_source_stacks_sha256']:
                raise FingerprintError('query reuses the reference frames; holdout leakage')
            result=compare_fingerprints(ref,fp,c,synthetic_independent_pixels=synthetic)
            result['query_diagnostics']=_summary(fp)
        except (FingerprintError,KeyError,OSError,ValueError) as e:
            result={'state':'INDETERMINATE','reason':str(e),'decision':'NO_AI_ORIGIN_CONCLUSION'}
        result['id']=item['id'];outputs.append(result)
    counts={state:sum(q['state']==state for q in outputs)
            for state in ('CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS',
                          'INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS','INDETERMINATE')}
    return {'module':'P7_S02_PRNU_DSNU_FIXED_PATTERN','state':'MEASURED' if assumptions_ok else 'INDETERMINATE',
            'reference_diagnostics':_summary(ref),'queries':outputs,'counts':counts,
            'assumptions_claimed':{k:manifest.get(k) is True for k in conditions},
            'provenance_claimed':manifest.get('provenance'),
            'controlled_synthetic_evaluation':bool(synthetic),
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'limitations':['raw field provenance is asserted, not independently verified',
                'synthetic-only exploratory cutoffs are NOT calibrated camera identification thresholds',
                'requires stationary uniform flat field and matched exposure/gain/temperature',
                'DSNU at fixed exposure and PRNU relative sensitivity are separate from temporal noise',
                'demosaicing, resampling, denoising, JPEG and cropping invalidate native pixel correspondence',
                'highpass mitigates but does not prove removal of illumination/camera-processing artifacts',
                'real-camera matching needs independent multi-sensor null calibration and PCE/false-match analysis',
                'a camera match is not proof of authentic photo or AI generation']}


def run_fingerprint_manifest(input_path:str|Path,out_dir:str|Path,config:FingerprintConfig|None=None,
                             *,controlled_synthetic_evaluation:bool=False)->dict:
    p=Path(input_path);out=Path(out_dir)
    report=analyze_fingerprint_manifest(json.loads(p.read_text(encoding='utf-8')),
                                         base_dir=p.parent,config=config,
                                         controlled_synthetic_evaluation=controlled_synthetic_evaluation)
    out.mkdir(parents=True,exist_ok=True)
    (out/'p7_s02_report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report
