"""P7-S01 conditional linear RAW sensor shot/read/dark noise physics.

Not a PRNU detector, not a JPEG statistics validator, not an AI-origin detector.
Gain is ELECTRONS PER ADU (not ADU per electron).  The forward generator
models independent Poisson photo/dark electrons, Gaussian read noise,
full-well saturation, ADC quantization and output code clipping.
Moment formulas assume UNSATURATED, approximately dithered quantization.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import json
import math
import numpy as np
from scipy.optimize import least_squares


class SensorNoiseError(ValueError):
    pass


@dataclass(frozen=True)
class SensorParameters:
    gain_e_per_adu: float = 2.0
    read_noise_e: float = 4.0
    dark_current_e_per_s: float = 1.5
    black_level_adu: float = 128.0
    full_well_e: float = 26000.0
    adc_max_adu: int = 16383

    def __post_init__(self):
        a = (self.gain_e_per_adu, self.read_noise_e, self.dark_current_e_per_s,
             self.black_level_adu, self.full_well_e)
        if not all(math.isfinite(float(x)) for x in a):
            raise SensorNoiseError('sensor parameters must be finite')
        if not (.01 <= self.gain_e_per_adu <= 100 and self.read_noise_e >= 0
                and self.dark_current_e_per_s >= 0 and self.full_well_e > 10
                and 0 <= self.black_level_adu < self.adc_max_adu
                and isinstance(self.adc_max_adu, int) and self.adc_max_adu >= 255):
            raise SensorNoiseError('invalid gain/noise/dark/bias/well/ADC parameters')


def _nonnegative(x, label: str) -> float:
    try:
        f = float(x)
    except (TypeError, ValueError) as e:
        raise SensorNoiseError(f'{label} must be finite nonnegative') from e
    if not math.isfinite(f) or f < 0:
        raise SensorNoiseError(f'{label} must be finite nonnegative')
    return f


def ideal_moments(photoelectrons: float, exposure_s: float, sensor: SensorParameters) -> dict:
    """Unclipped ADU mean/variance, approximation q²/12 under sufficient dither.

    Temporal samples must have identical illumination/gain/temp; no PRNU/FPN.
    """
    photo = _nonnegative(photoelectrons, 'photoelectrons')
    t = _nonnegative(exposure_s, 'exposure_s')
    dark = sensor.dark_current_e_per_s*t
    mean_e = photo + dark
    variance_e = mean_e + sensor.read_noise_e**2
    g = sensor.gain_e_per_adu
    mean = sensor.black_level_adu + mean_e/g
    variance = variance_e/g**2 + 1/12
    snr_e = photo / math.sqrt(variance_e) if variance_e > 0 else None
    # SNR in raw ADU accounts for approximately independent 1/12 ADU² quantization noise.
    snr_quantized = (photo/g) / math.sqrt(variance) if variance > 0 else None
    return {'photoelectrons': photo, 'dark_electrons_mean': dark,
            'total_mean_electrons': mean_e, 'variance_e2': variance_e,
            'expected_mean_adu': mean, 'expected_variance_adu2': variance,
            'expected_std_adu': math.sqrt(variance),
            'snr_electrons': snr_e, 'snr_quantized_adu': snr_quantized,
            'quantization_variance_adu2_approx': 1/12}


def sample_sensor(photoelectrons: float, exposure_s: float, sensor: SensorParameters,
                  *, size: int | tuple[int, ...] = 1024, seed: int = 0) -> np.ndarray:
    """Generate a controlled RAW-like sensor output in nonnegative integer ADU.

    Independent photons, dark electrons and read-noise are used. Fixed-pattern
    noise/PRNU, demosaicing, compression, nonlinearity and rolling shutter are absent.
    """
    photo = _nonnegative(photoelectrons, 'photoelectrons')
    t = _nonnegative(exposure_s, 'exposure_s')
    rng = np.random.default_rng(seed)
    mean_charge = photo + sensor.dark_current_e_per_s*t
    if mean_charge > 1e9:
        raise SensorNoiseError('Poisson simulation is limited to <=1e9 electrons')
    charges = rng.poisson(mean_charge, size=size).astype(float)
    charges = np.minimum(charges, sensor.full_well_e)
    electrons = charges + rng.normal(0, sensor.read_noise_e, size=size)
    adu = np.rint(electrons/sensor.gain_e_per_adu + sensor.black_level_adu)
    # Choose a representable integer format; explicit ceiling avoids wraparound.
    adu = np.clip(adu, 0, sensor.adc_max_adu)
    return adu.astype(np.uint16 if sensor.adc_max_adu <= 65535 else np.uint32)


def summarize_codes(codes: np.ndarray, sensor: SensorParameters) -> dict:
    arr = np.asarray(codes, dtype=float)
    if arr.size < 2 or not np.all(np.isfinite(arr)):
        raise SensorNoiseError('at least two finite codes required')
    flat = arr.ravel()
    return {'observed_mean_adu': float(flat.mean()),
            'observed_variance_adu2': float(flat.var(ddof=1)),
            'n_samples': int(flat.size),
            'saturation_fraction': float(np.mean(flat >= sensor.adc_max_adu)),
            'zero_code_fraction': float(np.mean(flat <= 0))}


def _row(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise SensorNoiseError('measurement must be an object')
    sid = raw.get('id')
    if not isinstance(sid, str) or not sid:
        raise SensorNoiseError('each measurement requires a nonempty ID')
    role = raw.get('role')
    if role not in ('train', 'holdout'):
        raise SensorNoiseError(f'{sid}: role must be train or holdout')
    kind = raw.get('kind')
    if kind not in ('flat', 'dark'):
        raise SensorNoiseError(f'{sid}: kind must be flat or dark')
    photo = _nonnegative(raw.get('expected_photoelectrons'), sid+'.photoelectrons')
    if kind == 'dark' and photo != 0:
        raise SensorNoiseError(f'{sid}: dark frame cannot contain photoelectrons')
    t = _nonnegative(raw.get('exposure_s'), sid+'.exposure')
    m = _nonnegative(raw.get('observed_mean_adu'), sid+'.mean')
    v = _nonnegative(raw.get('observed_variance_adu2'), sid+'.variance')
    n = raw.get('n_samples')
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise SensorNoiseError(f'{sid}: n_samples must be integer >=2')
    sat = _nonnegative(raw.get('saturation_fraction', 0), sid+'.saturation_fraction')
    zero = _nonnegative(raw.get('zero_code_fraction', 0), sid+'.zero_code_fraction')
    if sat > 1 or zero > 1:
        raise SensorNoiseError('clipping fractions must be <=1')
    provenance_ok = (raw.get('photoelectron_provenance') in
                     ('synthetic_ground_truth', 'independent_photon_calibration') and
                     raw.get('sample_provenance') in
                     ('synthetic_ground_truth', 'independent_temporal_raw_measurement'))
    return {'id': sid, 'role': role, 'kind': kind, 'photo': photo, 'exposure': t,
            'mean': m, 'variance': v, 'n': n, 'sat': sat, 'zero': zero,
            'provenance_ok': provenance_ok}


def _moment_standard_errors(photo: float, t: float, sensor: SensorParameters, n: int):
    m = ideal_moments(photo,t,sensor)
    # Fourth cumulant of Poisson is lambda; independent Gaussian fourth cumulant = 0.
    # The uniform quantization cumulant (-1/120) is an approximation valid under dither.
    variance = m['expected_variance_adu2']
    fourth_cumulant = (m['total_mean_electrons']/sensor.gain_e_per_adu**4 - 1/120)
    fourth_central = 3*variance**2 + fourth_cumulant
    var_of_var = (fourth_central - (n-3)/(n-1)*variance**2)/n
    return max(math.sqrt(variance/n),1e-8), max(math.sqrt(max(var_of_var,0)),1e-8)


def _fit_parameters(train: list[dict], basis: SensorParameters, min_train: int):
    if len(train) < min_train:
        raise SensorNoiseError('not enough independent calibration train rows')
    if any(not r['provenance_ok'] or r['sat'] > .001 or r['zero'] > .001 for r in train):
        raise SensorNoiseError('train set must be verified and unsaturated')
    if not any(r['kind']=='dark' and r['exposure']==0 for r in train):
        raise SensorNoiseError('zero-duration dark reference required for read noise')
    if len({r['photo'] for r in train if r['kind']=='flat'}) < 3:
        raise SensorNoiseError('at least three distinct flat-field levels required')
    if len({r['exposure'] for r in train if r['kind']=='dark'}) < 2:
        raise SensorNoiseError('two distinct dark exposures required')
    X = np.array([[r['photo'],r['exposure']] for r in train], float)
    if np.linalg.matrix_rank(X) != 2 or np.linalg.cond(X.T@X) > 1e10:
        raise SensorNoiseError('unidentifiable photon/exposure design')
    y = np.array([r['mean']-basis.black_level_adu for r in train])
    coefs = np.linalg.lstsq(X,y,rcond=None)[0]
    if coefs[0] <= 0 or coefs[1] < -.01:
        raise SensorNoiseError('nonphysical gain/dark-current estimate')
    gain0 = float(np.clip(1/coefs[0],.05,100))
    dark0 = float(max(coefs[1]*gain0, 0))
    # Zero-exposure dark frames directly measure read noise without shot noise.
    var0 = [r['variance'] for r in train if r['kind']=='dark' and r['exposure']==0]
    read0 = math.sqrt(max((float(np.median(var0))-1/12)*gain0**2, 0.25))
    x0=np.array([gain0,float(np.clip(read0,.5,100)),float(np.clip(dark0,0,500))])

    def residual(x):
        s=replace(basis,gain_e_per_adu=x[0],read_noise_e=x[1],dark_current_e_per_s=x[2])
        result=[]
        for row in train:
            expected=ideal_moments(row['photo'],row['exposure'],s)
            se_m,se_v=_moment_standard_errors(row['photo'],row['exposure'],s,row['n'])
            result.extend(((row['mean']-expected['expected_mean_adu'])/se_m,
                           (row['variance']-expected['expected_variance_adu2'])/se_v))
        return np.asarray(result)

    sol=least_squares(residual,x0,bounds=([.05,.05,0.],[100.,100.,500.]),
                      loss='soft_l1',f_scale=2.5,max_nfev=450,xtol=1e-12,ftol=1e-12)
    if not sol.success or np.linalg.matrix_rank(sol.jac) != 3:
        raise SensorNoiseError('parameter fitting did not converge or is rank-deficient')
    # Normalized residual Jacobian yields a conservative local uncertainty estimate.
    jac=sol.jac
    cov=np.linalg.pinv(jac.T@jac,rcond=1e-12)
    if not np.all(np.isfinite(cov)) or np.linalg.cond(jac.T@jac)>1e11:
        raise SensorNoiseError('calibration uncertainties not identifiable')
    s=replace(basis,gain_e_per_adu=float(sol.x[0]),read_noise_e=float(sol.x[1]),
              dark_current_e_per_s=float(sol.x[2]))
    return s, cov, {'fit_train_rows':len(train),'fit_nonlinear_residual_cost':float(sol.cost),
                    'estimated_parameter_std':np.sqrt(np.diag(cov)).tolist(),
                    'parameter_order':['gain_e_per_adu','read_noise_e','dark_current_e_per_s']}


def _predictive_uncertainty(row, sensor, cov):
    if cov is None:
        return 0.,0.
    x=np.array([sensor.gain_e_per_adu,sensor.read_noise_e,sensor.dark_current_e_per_s])
    # Numerical uncertainty propagation in ADU and ADU², based on TRAIN data only.
    gradient=np.zeros((2,3))
    for j in range(3):
        h=max(abs(x[j]),1.)*1e-5
        xp=x.copy();xm=x.copy();xp[j]+=h;xm[j]-=h
        if xm[j]<0: xm[j]=x[j]
        sp=replace(sensor,gain_e_per_adu=xp[0],read_noise_e=xp[1],dark_current_e_per_s=xp[2])
        sm=replace(sensor,gain_e_per_adu=xm[0],read_noise_e=xm[1],dark_current_e_per_s=xm[2])
        a=ideal_moments(row['photo'],row['exposure'],sp)
        b=ideal_moments(row['photo'],row['exposure'],sm)
        den=xp[j]-xm[j]
        gradient[:,j]=[(a['expected_mean_adu']-b['expected_mean_adu'])/den,
                       (a['expected_variance_adu2']-b['expected_variance_adu2'])/den]
    errors=np.einsum('ij,jk,ik->i',gradient,cov,gradient)
    return float(math.sqrt(max(errors[0],0))),float(math.sqrt(max(errors[1],0)))


@dataclass(frozen=True)
class SensorNoiseConfig:
    consistent_sigma: float=2.5
    inconsistent_sigma: float=5.0
    min_train: int=10
    min_holdout: int=6
    min_samples: int=256

    def __post_init__(self):
        if not (0<self.consistent_sigma<self.inconsistent_sigma and
                self.min_train>=4 and self.min_holdout>=1 and self.min_samples>=4):
            raise SensorNoiseError('invalid analysis thresholds/sample minima')


def analyze_sensor_manifest(manifest: dict, config: SensorNoiseConfig | None=None) -> dict:
    config=config or SensorNoiseConfig()
    if not isinstance(manifest,dict):raise SensorNoiseError('manifest must be object')
    sensor_raw=manifest.get('sensor')
    if not isinstance(sensor_raw,dict):raise SensorNoiseError('sensor object required')
    try:
        sensor=SensorParameters(**sensor_raw)
    except TypeError as exc:
        raise SensorNoiseError(f'invalid sensor schema: {exc}') from exc
    mode=manifest.get('calibration_mode','known_parameters')
    if mode not in ('known_parameters','fit_train_parameters'):
        raise SensorNoiseError('unknown calibration_mode')
    if not isinstance(manifest.get('measurements'),list):
        raise SensorNoiseError('measurements must be a list')
    rows=[_row(r) for r in manifest['measurements']]
    ids=[r['id'] for r in rows]
    if len(set(ids))!=len(ids):raise SensorNoiseError('duplicate measurement IDs')
    train=[r for r in rows if r['role']=='train']
    hold=[r for r in rows if r['role']=='holdout']
    if len(hold)<config.min_holdout:
        raise SensorNoiseError('insufficient independent holdout measurements')
    fit_extra={}; cov=None
    if mode=='fit_train_parameters':
        sensor,cov,fit_extra=_fit_parameters(train,sensor,config.min_train)
    params={'gain_e_per_adu':sensor.gain_e_per_adu,
            'read_noise_e':sensor.read_noise_e,'dark_current_e_per_s':sensor.dark_current_e_per_s,
            'black_level_adu':sensor.black_level_adu,'full_well_e':sensor.full_well_e,
            'adc_max_adu':sensor.adc_max_adu}
    known_ok=(manifest.get('sensor_provenance') in
              ('synthetic_ground_truth','independent_sensor_calibration'))
    raw_ok=(manifest.get('input_domain')=='linear_raw_adu' and
            manifest.get('stable_temperature') is True and
            manifest.get('temporally_independent') is True and
            manifest.get('uniform_flat_field') is True and
            manifest.get('fixed_gain_mode') is True and
            manifest.get('prnu_or_fpn_controlled') is True)
    counts={'CONSISTENT':0,'INCONSISTENT_UNDER_ASSUMPTIONS':0,'INDETERMINATE':0}
    results=[]
    for r in hold:
        predicted=ideal_moments(r['photo'],r['exposure'],sensor)
        v=predicted['expected_variance_adu2']
        se_mean,se_var=_moment_standard_errors(r['photo'],r['exposure'],sensor,r['n'])
        pm,pv=_predictive_uncertainty(r,sensor,cov)
        se_mean=math.hypot(se_mean,pm)
        se_var=math.hypot(se_var,pv)
        z_mean=abs(r['mean']-predicted['expected_mean_adu'])/se_mean
        z_variance=abs(r['variance']-v)/se_var
        z=max(z_mean,z_variance)
        reasons=[]
        if not raw_ok: reasons.append('RAW temporal linear uniform calibrated acquisition not established')
        if not r['provenance_ok']:reasons.append('independent photon calibration or temporal sample provenance missing')
        if mode=='known_parameters' and not known_ok:reasons.append('sensor calibration provenance missing')
        if r['n']<config.min_samples:reasons.append('insufficient independent temporal samples')
        if r['sat']>.001 or r['zero']>.001:reasons.append('observed saturation/black clipping censors moments')
        # Six standard deviations short of full well/ADC clipping.
        high_charge=predicted['total_mean_electrons']+6*math.sqrt(predicted['variance_e2'])
        if high_charge>=sensor.full_well_e or predicted['expected_mean_adu']+6*math.sqrt(v)>=sensor.adc_max_adu:
            reasons.append('predicted signal near full-well or ADC saturation')
        if predicted['expected_mean_adu']-6*math.sqrt(v)<=0:
            reasons.append('predicted black clipping')
        if sensor.read_noise_e/sensor.gain_e_per_adu < .9:
            reasons.append('quantization uniform-noise approximation is not supported')
        if not math.isfinite(z):reasons.append('nonfinite statistical residual')
        if reasons:state='INDETERMINATE'
        elif z>=config.inconsistent_sigma:state='INCONSISTENT_UNDER_ASSUMPTIONS'
        elif z<=config.consistent_sigma:state='CONSISTENT'
        else:state='INDETERMINATE';reasons.append('measurement falls in uncertainty guard band')
        counts[state]+=1
        results.append({'id':r['id'],'kind':r['kind'],'state':state,
                        'expected_mean_adu':predicted['expected_mean_adu'],
                        'observed_mean_adu':r['mean'],
                        'expected_variance_adu2':v,'observed_variance_adu2':r['variance'],
                        'mean_z':float(z_mean),'variance_z':float(z_variance),
                        'n_samples':r['n'],'predicted_snr_electrons':predicted['snr_electrons'],
                        'reason':'; '.join(reasons) if reasons else 'conditional sensor moment agreement' if state=='CONSISTENT' else 'conditional sensor moment mismatch'})
    overall=('INCONSISTENT_UNDER_ASSUMPTIONS' if counts['INCONSISTENT_UNDER_ASSUMPTIONS'] else
             'CONSISTENT' if counts['CONSISTENT'] == len(hold) else 'INDETERMINATE')
    return {'module':'P7_S01_SENSOR_SHOT_READ_DARK_GAIN','state':overall,
            'decision':'NO_AI_ORIGIN_CONCLUSION','calibration_mode':mode,
            'parameters':params,'fit_diagnostics':fit_extra,'counts':counts,'observations':results,
            'assumptions':['RAW linear ADU prior to demosaic/gamma/compression',
                           'independent temporal measurements under uniform stable illumination',
                           'independent photon means known in photoelectrons',
                           'Poisson photo+dark electrons; Gaussian read noise; constant conversion gain',
                           'approximately uniform independent quantization error (1/12 ADU^2)',
                           'no PRNU/DSNU, hot pixels, nonlinear ADC, correlated row noise or clipping',
                           'moment z scores are approximate, not calibrated image-origin probabilities'],
            'limitations':['fit mode retains local covariance approximation; no real-sensor acceptance',
                           'unknown irradiance, compression and fixed pattern noise can mimic disagreement',
                           'cannot establish image synthesis or manipulation origin']}


def run_sensor_manifest(input_path: str | Path,out_dir: str | Path,
                        config: SensorNoiseConfig | None=None) -> dict:
    data=json.loads(Path(input_path).read_text(encoding='utf-8'))
    result=analyze_sensor_manifest(data,config)
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/'p7_s01_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return result


def summarize_temporal_raw_stack(stack: np.ndarray, sensor: SensorParameters,
                                 roi_xyxy: tuple[int,int,int,int] | None=None) -> dict:
    """RAW temporal moments at fixed pixels; avoids spatial FPN contaminating variance.

    Stack: [T,H,W] independent constant-exposure linear RAW frames. This function
    only extracts measured moments, not a photon calibration nor a provenance claim.
    """
    frames=np.asarray(stack)
    if frames.ndim != 3 or frames.shape[0] < 4 or min(frames.shape[1:]) < 2:
        raise SensorNoiseError('RAW stack must be [>=4 frames,H>=2,W>=2]')
    if not np.issubdtype(frames.dtype,np.number):
        raise SensorNoiseError('RAW codes must be numeric')
    if not np.all(np.isfinite(frames)):
        raise SensorNoiseError('RAW stack has nonfinite values')
    if (np.min(frames)<0 or np.max(frames)>sensor.adc_max_adu or
        np.any(frames!=np.rint(frames))):
        raise SensorNoiseError('RAW stack must contain integer codes within sensor ADC limits')
    if roi_xyxy is not None:
        if len(roi_xyxy)!=4 or any(isinstance(i,bool) or not isinstance(i,int) for i in roi_xyxy):
            raise SensorNoiseError('ROI must be integer [x0,y0,x1,y1]')
        x0,y0,x1,y1=roi_xyxy
        if not (0<=x0<x1<=frames.shape[2] and 0<=y0<y1<=frames.shape[1]):
            raise SensorNoiseError('ROI outside RAW dimensions')
        frames=frames[:,y0:y1,x0:x1]
    frames=frames.astype(np.float64)
    var_time=frames.var(axis=0,ddof=1)
    mean_time=frames.mean(axis=0)
    return {'observed_mean_adu':float(mean_time.mean()),
            'observed_variance_adu2':float(var_time.mean()),
            'n_samples':int(frames.size),
            'n_frames':int(frames.shape[0]),
            'roi_pixel_count':int(frames.shape[1]*frames.shape[2]),
            'saturation_fraction':float((frames>=sensor.adc_max_adu).mean()),
            'zero_code_fraction':float((frames<=0).mean()),
            'temporal_variance_method':'mean of per-pixel sample variances; not pooled spatial variance',
            'limitations':['FPN cannot be assessed from temporal variance alone',
                           'pixel/row correlations reduce effective independent sample size',
                           'no photon flux provenance or exposure calibration inferred']}
