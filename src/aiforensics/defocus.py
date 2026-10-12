"""P4-O02 thin-lens *geometric* defocus; conditionally measured evidence.

All distances are millimetres unless suffixed '_px'. This does not infer
image authenticity, estimate depth maps, or account for diffraction/aberrations.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import math
import numpy as np
from scipy.optimize import least_squares


class DefocusError(ValueError):
    pass


def _positive(value, name, allow_inf=False):
    try:
        value=float(value)
    except (TypeError, ValueError, OverflowError) as e:
        raise DefocusError(f"{name} must be positive") from e
    if (not math.isfinite(value) and not (allow_inf and value == float('inf'))) or value<=0:
        raise DefocusError(f"{name} must be positive and finite unless explicitly infinity")
    return value


@dataclass(frozen=True)
class ThinLens:
    focal_mm: float
    f_number: float
    pixel_pitch_um: float
    focus_distance_mm: float

    def __post_init__(self):
        f=_positive(self.focal_mm,'focal_mm')
        _positive(self.f_number,'f_number')
        _positive(self.pixel_pitch_um,'pixel_pitch_um')
        s=_positive(self.focus_distance_mm,'focus_distance_mm',allow_inf=True)
        if s <= f:
            raise DefocusError('focus_distance_mm must exceed focal_mm (real positive image distance)')

    @property
    def aperture_diameter_mm(self):
        return self.focal_mm/self.f_number

    @property
    def sensor_distance_mm(self):
        if math.isinf(self.focus_distance_mm):
            return self.focal_mm
        return self.focal_mm*self.focus_distance_mm/(self.focus_distance_mm-self.focal_mm)

    def image_distance_mm(self, depth_mm):
        z=_positive(depth_mm,'depth_mm',allow_inf=True)
        if z <= self.focal_mm:
            raise DefocusError('depth_mm must be greater than focal_mm')
        if math.isinf(z):
            return self.focal_mm
        return self.focal_mm*z/(z-self.focal_mm)

    def coc_mm(self, depth_mm):
        z=_positive(depth_mm,'depth_mm',allow_inf=True)
        if z <= self.focal_mm:
            raise DefocusError('depth_mm must be greater than focal_mm')
        # Formula uses an infinity-safe ratio and sensor-plane displacement.
        inv_z=0. if math.isinf(z) else 1/z
        inv_s=0. if math.isinf(self.focus_distance_mm) else 1/self.focus_distance_mm
        return self.aperture_diameter_mm * self.sensor_distance_mm * abs(inv_z-inv_s)

    def coc_px(self, depth_mm):
        return self.coc_mm(depth_mm)*1000/self.pixel_pitch_um

    def dof_limits_mm(self, permissible_coc_px):
        c=_positive(permissible_coc_px,'permissible_coc_px')*self.pixel_pitch_um/1000
        f,N,s=self.focal_mm,self.f_number,self.focus_distance_mm
        if math.isinf(s):
            near=f*f/(N*c)
            return float(near),float('inf')
        factor=N*c*(s-f)
        near=f*f*s/(f*f+factor)
        far=float('inf') if factor >= f*f else f*f*s/(f*f-factor)
        return float(near),float(far)

    def hyperfocal_mm(self, permissible_coc_px):
        c=_positive(permissible_coc_px,'permissible_coc_px')*self.pixel_pitch_um/1000
        return self.focal_mm**2/(self.f_number*c)+self.focal_mm

    def as_dict(self):
        return {"focal_mm":self.focal_mm,"f_number":self.f_number,
                "pixel_pitch_um":self.pixel_pitch_um,
                "focus_distance_mm": None if math.isinf(self.focus_distance_mm) else self.focus_distance_mm,
                "sensor_distance_mm":self.sensor_distance_mm,
                "aperture_diameter_mm":self.aperture_diameter_mm}


def circular_psf(diameter_px:float, *, max_kernel:int=201, supersample:int=8):
    """Unit-sum circular aperture PSF; subpixel coverage via supersampling.

    A very large CoC should not silently become a truncated PSF.
    """
    d=float(diameter_px)
    if not math.isfinite(d) or d<0:
        raise DefocusError('diameter_px must be nonnegative and finite')
    if d<=0.25:
        return np.ones((1,1),np.float64)
    radius=d/2
    half=int(math.ceil(radius+1))
    side=2*half+1
    if side>max_kernel:
        raise DefocusError('defocus PSF exceeds max_kernel: downsample explicitly')
    if supersample<2 or supersample>32:
        raise DefocusError('supersample must be in [2,32]')
    y,x=np.mgrid[-half:half+1,-half:half+1]
    p=np.zeros((side,side),np.float64)
    o=(np.arange(supersample)+.5)/supersample-.5
    for sy in o:
        for sx in o:
            p+=((x+sx)**2+(y+sy)**2<=radius*radius)
    p/=supersample**2
    total=p.sum()
    if total<=0: # very small diameters compared with subpixel sampling
        p[half,half]=1
        total=1
    return p/total


def _finite_positive_or_zero(value,name):
    v=float(value)
    if not math.isfinite(v) or v<0:
        raise DefocusError(f'{name} must be finite and >=0')
    return v


def _records(data):
    samples=data.get('samples')
    if not isinstance(samples,list) or not samples:
        raise DefocusError('samples must be a nonempty array')
    ids=set()
    for r in samples:
        if not isinstance(r,dict):
            raise DefocusError('sample must be a dictionary')
        label=str(r.get('id',''))
        if not label or label in ids:
            raise DefocusError('nonempty unique sample IDs required')
        ids.add(label)
        z=_positive(r.get('depth_mm'),'depth_mm')
        if r.get('role','holdout') not in ('train','holdout'):
            raise DefocusError('role must be train or holdout')
        _finite_positive_or_zero(r.get('depth_sigma_mm',0),'depth_sigma_mm')
        if 'observed_coc_px' in r:
            _finite_positive_or_zero(r['observed_coc_px'],'observed_coc_px')
            _positive(r.get('observed_sigma_px'),'observed_sigma_px')
    return samples


def _estimate_focus(data, records, base):
    train=[r for r in records if r.get('role')=='train' and 'observed_coc_px' in r]
    hold=[r for r in records if r.get('role')=='holdout' and 'observed_coc_px' in r]
    if len(train)<5 or len(hold)<3:
        raise DefocusError('focus fitting requires >=5 train and >=3 independent holdout observations')
    depths=np.array([r['depth_mm'] for r in train],float)
    if len(np.unique(np.round(depths,5)))<5 or np.max(depths)/np.min(depths)<1.3:
        raise DefocusError('focus fitting needs at least five distinct and sufficiently spread depths')
    targets=np.array([r['observed_coc_px'] for r in train],float)
    sigmas=np.array([r['observed_sigma_px'] for r in train],float)
    f,N,pitch=base
    lo=max(float(f*1.001),float(np.min(depths)*.5))
    hi=float(np.max(depths)*3)
    if lo>=hi:
        raise DefocusError('invalid identifiable focus search interval')
    # Multi-start objective: unsigned CoC can admit aliased focus hypotheses.
    def residual(v):
        lens=ThinLens(f,N,pitch,float(v[0]))
        return (np.array([lens.coc_px(z) for z in depths])-targets)/sigmas
    result=[]
    for x0 in np.geomspace(lo,hi,11):
        sol=least_squares(residual,[x0],bounds=([lo],[hi]),max_nfev=120,
                          ftol=1e-11,xtol=1e-11,gtol=1e-11)
        if sol.success and np.isfinite(sol.cost):
            result.append((float(sol.cost),float(sol.x[0])))
    if not result:
        raise DefocusError('numerical focus estimation failed')
    result.sort()
    best=result[0]
    # Competing, well-separated focus modes with indistinguishable cost: abstain.
    for cost,focus in result[1:]:
        if abs(focus-best[1])>max(5.,best[1]*.05) and cost-best[0]<1.0:
            raise DefocusError('focus distance is ambiguous for provided CoC samples')
    if best[1] <= lo*1.002 or best[1]>=hi*.998:
        raise DefocusError('focus optimizer reached search boundary')
    return best[1], {'fit_train_count':len(train),'holdout_count':len(hold),
                     'weighted_train_cost':best[0], 'focus_search_bounds_mm':[lo,hi]}


def analyze_defocus(data, *, seed=2202, mc_samples=512, tolerance_sigma=3.0):
    """Known optical parameters + calibrated independent CoC measurements.

    Anomalies are conditional on known depth, PSF separation, pitch and focus.
    """
    if not isinstance(data,dict):
        raise DefocusError('manifest must be a JSON object')
    if int(mc_samples)<64 or int(mc_samples)>10000:
        raise DefocusError('mc_samples must be 64..10000')
    if _positive(tolerance_sigma,'tolerance_sigma')>10:
        raise DefocusError('tolerance_sigma exceeds supported bound')
    optic=data.get('optics')
    if not isinstance(optic,dict):
        raise DefocusError('optics must be an object')
    records=_records(data)
    f=_positive(optic.get('focal_mm'),'focal_mm')
    N=_positive(optic.get('f_number'),'f_number')
    pitch=_positive(optic.get('pixel_pitch_um'),'pixel_pitch_um')
    estimated=False
    fit_info=None
    if optic.get('focus_distance_mm') is None:
        s,fit_info=_estimate_focus(data,records,(f,N,pitch))
        estimated=True
    else:
        s=_positive(optic.get('focus_distance_mm'),'focus_distance_mm')
    lens=ThinLens(f,N,pitch,s)
    c_limit=_positive(data.get('acceptable_coc_px',2.0),'acceptable_coc_px')
    # Model-prediction uncertainty is conditional; lens parameter uncertainties
    # are not included unless encoded in input with explicit sigma fields.
    sigma_s=_finite_positive_or_zero(optic.get('focus_sigma_mm',0.),'focus_sigma_mm')
    rng=np.random.default_rng(int(seed))
    results=[]
    for r in records:
        z=float(r['depth_mm'])
        expected=lens.coc_px(z)
        measured=r.get('observed_coc_px')
        provenance=r.get('measurement_provenance')
        role=r.get('role','holdout')
        z_sigma=float(r.get('depth_sigma_mm',0.))
        predicted_sigma=0.
        qlo=qhi=float(expected)
        if z_sigma>0 or sigma_s>0:
            zs=rng.normal(z,z_sigma,int(mc_samples)) if z_sigma>0 else np.full(int(mc_samples),z)
            ss=rng.normal(s,sigma_s,int(mc_samples)) if sigma_s>0 else np.full(int(mc_samples),s)
            if np.any(zs<=f) or np.any(ss<=f):
                row_valid=False
            else:
                cp=f*f/(N*(ss-f)) * np.abs(zs-ss)/zs * (1000/pitch)
                predicted_sigma=float(np.std(cp,ddof=1))
                qlo,qhi=map(float,np.quantile(cp,[.025,.975]))
                row_valid=True
        else:
            row_valid=True
        row={'id':str(r['id']),'role':role,'depth_mm':z,
             'predicted_coc_mm':lens.coc_mm(z),'predicted_coc_px':expected,
             'predicted_coc_95pct_conditional_px':[qlo,qhi],
             'prediction_sigma_px':predicted_sigma,
             'within_acceptable_coc':expected<=c_limit,
             'observed_coc_px':None if measured is None else float(measured),
             'state':'INDETERMINATE','reason':None,'z_score':None}
        if not row_valid:
            row['reason']='depth or focus uncertainty reaches nonphysical object distance'
        elif measured is None:
            row['reason']='no observed calibrated CoC'
        elif provenance!='calibrated_coc_diameter':
            row['reason']='blur observation is not independently calibrated optical CoC; PSF/depth confounds remain'
        elif role=='train' and estimated:
            row['reason']='train measurement used to estimate focus; excluded from evidence'
        else:
            denom=math.hypot(float(r['observed_sigma_px']),predicted_sigma)
            zscore=abs(float(measured)-expected)/denom
            row['z_score']=float(zscore)
            row['state']='CONSISTENT' if zscore<=tolerance_sigma else 'INCONSISTENT_UNDER_ASSUMPTIONS'
            row['reason']='calibrated measurement compared with conditioned thin-lens hypothesis'
        results.append(row)
    independent=[r for r in results if r['state']!='INDETERMINATE' and (not estimated or r['role']=='holdout')]
    counts={'consistent':sum(r['state']=='CONSISTENT' for r in independent),
            'inconsistent':sum(r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for r in independent),
            'indeterminate':sum(r['state']=='INDETERMINATE' for r in results)}
    near,far=lens.dof_limits_mm(c_limit)
    status=('INDETERMINATE' if not independent else
            'INCONSISTENT_UNDER_ASSUMPTIONS' if counts['inconsistent'] else 'CONSISTENT')
    return {'module':'P4_O02_THIN_LENS_DEFOCUS','state':status,
            'decision':'NO_AI_ORIGIN_CONCLUSION','lens':lens.as_dict(),
            'focus_estimated_from_train':estimated,'focus_fit':fit_info,
            'acceptable_coc_px':c_limit,
            'depth_of_field_near_mm':near,
            'depth_of_field_far_mm':None if math.isinf(far) else far,
            'hyperfocal_mm':lens.hyperfocal_mm(c_limit),
            'results':results,'counts':counts,
            'assumptions':['paraxial thin lens and circular uniform exit pupil (pupil magnification 1)',
                           'axial depths measured from lens principal plane, focal and sensor geometry independently known',
                           'pixel pitch is native physical pitch; no resize or post-crop scaling',
                           'measurements have independently calibrated optical CoC and valid sigma',
                           'defocus-only ideal geometric PSF, no diffraction, aberration, motion, denoising or sharpening'],
            'limitations':['PSF diameter is not equivalent to edge transition width or Gaussian sigma',
                           'depth of field is threshold-dependent, not a binary physical sharpness property',
                           'train observations never count as independent evidence when focus is fitted',
                           'Monte Carlo 95 percent ranges are conditional on given sigma inputs, not empirical coverage',
                           'absence of physical agreement does not establish AI origin; AI renderings may obey optics']}


def run_defocus_manifest(input_path, out, *, tolerance_sigma=3., seed=2202, mc_samples=512):
    src=Path(input_path)
    data=json.loads(src.read_text(encoding='utf-8'))
    report=analyze_defocus(data, tolerance_sigma=tolerance_sigma,seed=seed,mc_samples=mc_samples)
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    report['manifest_sha256']=hashlib.sha256(src.read_bytes()).hexdigest()
    report['validation_type']='synthetic_or_conditional_annotations; not real-photo acceptance'
    path=out/'p4_o02_report.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
