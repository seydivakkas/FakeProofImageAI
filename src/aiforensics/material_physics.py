"""P6-M01: conditional diffuse BRDF and independently measured linear radiance.

Inputs are independent **linear calibrated** irradiance/radiance and geometrical
normals. Neither material identity, albedo, nor image provenance is inferred
from RGB pixels alone. The known-light / fitted-albedo model is Lambertian only.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import math
import numpy as np
from scipy.optimize import least_squares


class MaterialPhysicsError(ValueError):
    pass


@dataclass(frozen=True)
class MaterialConfig:
    consistent_sigma: float = 2.5
    inconsistent_sigma: float = 4.5
    min_train: int = 12
    min_holdout: int = 6


def _vec3(value, label: str, *, min_value=None, max_value=None):
    v = np.asarray(value, dtype=float)
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise MaterialPhysicsError(f'{label} must be a finite 3-vector')
    if min_value is not None and np.any(v < min_value):
        raise MaterialPhysicsError(f'{label} below physical lower bound')
    if max_value is not None and np.any(v > max_value):
        raise MaterialPhysicsError(f'{label} above physical upper bound')
    return v


def _direction(value, label):
    v = _vec3(value, label)
    norm = float(np.linalg.norm(v))
    if norm < 1e-12:
        raise MaterialPhysicsError(f'{label} must be nonzero')
    return v / norm


def lambertian_brdf(albedo_rgb):
    """Spectrally sampled Lambert BRDF [sr^-1]; rho/pi (not rho)."""
    return _vec3(albedo_rgb, 'albedo_rgb', min_value=0.0, max_value=1.0) / math.pi


def lambertian_radiance(normal_world, direction_to_light, direct_irradiance_rgb,
                         ambient_irradiance_rgb, albedo_rgb, *, visible_fraction=1.0):
    """L_o = (rho/pi) (E_ambient + V E_normal max(0,n.l)).

    Direct E_normal is incident irradiance on surface normal to incoming rays,
    NOT irradiance already multiplied by cos(theta). Ambient is hemispherically
    integrated irradiance and **not** a constant radiance to add after reflection.
    """
    n = _direction(normal_world, 'normal_world')
    l = _direction(direction_to_light, 'light_direction_world')
    direct = _vec3(direct_irradiance_rgb, 'direct_irradiance_rgb', min_value=0)
    ambient = _vec3(ambient_irradiance_rgb, 'ambient_irradiance_rgb', min_value=0)
    visibility = float(visible_fraction)
    if not math.isfinite(visibility) or not 0 <= visibility <= 1:
        raise MaterialPhysicsError('visible_fraction must be in [0,1]')
    irradiance = ambient + direct * max(0., float(n @ l)) * visibility
    return lambertian_brdf(albedo_rgb) * irradiance


def hemisphere_quadrature(n_mu=6, n_phi=12):
    """Positive quadrature weights in sr, integrating over cosine z in [0,1]."""
    if not isinstance(n_mu, int) or not isinstance(n_phi, int) or n_mu < 2 or n_phi < 4:
        raise MaterialPhysicsError('quadrature resolution too small')
    mu, weight = np.polynomial.legendre.leggauss(n_mu)
    mu = (mu + 1.0)/2.0
    weight = weight/2.0
    phi = 2 * math.pi * np.arange(n_phi) / n_phi
    dirs = np.array([(math.sqrt(1-m*m)*math.cos(p),
                      math.sqrt(1-m*m)*math.sin(p), m) for m in mu for p in phi])
    weights = np.repeat(weight, n_phi) * 2*math.pi/n_phi
    return dirs, weights


def audit_brdf_matrix(values, directions, solid_angle_weights, *, tolerance=1e-7):
    """Tabulated BRDF f[wo,wi] audit: positivity, reciprocity, conservation.

    Discrete energy sum over incoming directions: sum(f[wo,wi]*cos_i*domega_i).
    Works for arbitrary nonnegative *tabulated* BRDF, not just diffuse model.
    A sufficiently sampled hemisphere is required for specular/sharp lobes.
    """
    dirs = np.asarray(directions, float)
    weights = np.asarray(solid_angle_weights, float)
    f = np.asarray(values, float)
    if dirs.ndim != 2 or dirs.shape[1] != 3:
        raise MaterialPhysicsError('directions must be N x 3')
    n = len(dirs)
    if f.shape != (n,n) or weights.shape != (n,) or n < 8:
        raise MaterialPhysicsError('BRDF matrix/weights shape mismatch')
    if not np.isfinite(f).all() or not np.isfinite(dirs).all() or not np.isfinite(weights).all():
        raise MaterialPhysicsError('BRDF samples must be finite')
    if (weights <= 0).any() or (dirs[:,2] < -1e-10).any() or np.max(np.abs(np.linalg.norm(dirs,axis=1)-1)) > 1e-6:
        raise MaterialPhysicsError('invalid quadrature directions/weights')
    if abs(float(np.sum(weights))-2*math.pi) > 1e-5:
        raise MaterialPhysicsError('hemispherical solid angle weights must integrate to 2pi')
    if (f < -tolerance).any():
        return {'state':'INCONSISTENT_UNDER_ASSUMPTIONS','reason':'negative BRDF samples',
                'max_hemispherical_reflectance':None, 'reciprocity_max_abs_error':None}
    cosine_weights=weights*np.maximum(0,dirs[:,2])
    energy = f@cosine_weights
    rec_err = float(np.max(np.abs(f-f.T)))
    max_energy = float(np.max(energy))
    reasons=[]
    if max_energy>1+tolerance:reasons.append('hemispherical reflectance exceeds 1')
    if rec_err>tolerance:reasons.append('BRDF reciprocity violation')
    return {'state':'INCONSISTENT_UNDER_ASSUMPTIONS' if reasons else 'CONSISTENT',
            'reason':'; '.join(reasons) if reasons else 'nonnegative, reciprocal and energy-conserving within discrete quadrature',
            'max_hemispherical_reflectance': max_energy,
            'reciprocity_max_abs_error':rec_err,
            'quadrature_directions':n,
            'discrete_audit_only':True}


def _records(manifest):
    if not isinstance(manifest.get('samples'), list):
        raise MaterialPhysicsError('samples list required')
    train,hold=[],[]
    seen=set()
    for item in manifest['samples']:
        if not isinstance(item,dict):raise MaterialPhysicsError('sample must be object')
        sid=item.get('id')
        role=item.get('role')
        if not isinstance(sid,str) or not sid or sid in seen or role not in ('train','holdout'):
            raise MaterialPhysicsError('unique sample IDs and train/holdout roles required')
        seen.add(sid)
        normal = _direction(item.get('normal_world'), f'{sid}.normal_world')
        observed = _vec3(item.get('observed_radiance_rgb'), f'{sid}.observed_radiance_rgb',min_value=0)
        sigma = _vec3(item.get('sigma_radiance_rgb'), f'{sid}.sigma_radiance_rgb')
        if np.min(sigma) <= 0:raise MaterialPhysicsError('sigma must be positive')
        vis=float(item.get('visible_fraction',1))
        if not math.isfinite(vis) or vis<0 or vis>1:raise MaterialPhysicsError('visible_fraction must be [0,1]')
        verified=(item.get('geometry_provenance') in ('synthetic_ground_truth','independent_metric_normal') and
                  item.get('radiometry_provenance') in ('synthetic_ground_truth','independent_linear_calibration'))
        rec={'id':sid,'role':role,'normal':normal,'observed':observed,
             'sigma':sigma,'visible_fraction':vis,'verified':verified}
        (train if role=='train' else hold).append(rec)
    return train,hold


def _irradiance(rec,l,direct,ambient):
    return ambient+direct*max(0,float(rec['normal']@l))*rec['visible_fraction']


def _fit_albedo(train,l,direct,ambient):
    factors=np.array([_irradiance(r,l,direct,ambient)/math.pi for r in train])
    obs=np.array([r['observed'] for r in train]);sigma=np.array([r['sigma'] for r in train])
    if np.any(np.max(factors,axis=0) < 1e-8):
        raise MaterialPhysicsError('illumination does not identify all albedo channels')
    first=np.sum(factors*obs/(sigma**2),axis=0)/np.maximum(np.sum(factors**2/sigma**2,axis=0),1e-20)
    if np.any(first < -.05) or np.any(first>1.05):
        raise MaterialPhysicsError('train measurements imply impossible diffuse albedo')
    opt=least_squares(lambda rho:((factors*rho-obs)/sigma).ravel(),
                      np.clip(first,0,1),bounds=(np.zeros(3),np.ones(3)),
                      loss='soft_l1',f_scale=1.5,max_nfev=250)
    if not opt.success:raise MaterialPhysicsError('albedo fit did not converge')
    if np.any(opt.x<1e-5) or np.any(opt.x>1-1e-5):
        raise MaterialPhysicsError('albedo optimum at physical boundary: ambiguous model')
    info=np.sum(factors**2/sigma**2,axis=0)
    sigma_rho=np.sqrt(1/np.maximum(info,1e-20))
    if np.any(sigma_rho>.08):
        raise MaterialPhysicsError('albedo uncertainty exceeds identifiability guard')
    return opt.x,sigma_rho


def analyze_material_manifest(manifest,config=MaterialConfig()):
    if not isinstance(manifest,dict):raise MaterialPhysicsError('manifest must be object')
    if not 0<config.consistent_sigma<config.inconsistent_sigma or config.min_holdout<1:
        raise MaterialPhysicsError('invalid configuration thresholds')
    train,hold = _records(manifest)
    l = _direction(manifest.get('light_direction_world'), 'light_direction_world')
    direct=_vec3(manifest.get('direct_irradiance_rgb'), 'direct_irradiance_rgb',min_value=0)
    ambient=_vec3(manifest.get('ambient_irradiance_rgb'), 'ambient_irradiance_rgb',min_value=0)
    if np.max(direct+ambient)<=0:raise MaterialPhysicsError('zero incident illumination')
    mode=manifest.get('calibration_mode','known_albedo')
    if mode not in ('known_albedo','fit_albedo'):
        raise MaterialPhysicsError('calibration_mode must be known_albedo or fit_albedo')
    rho=None; sigma_rho=np.zeros(3)
    diagnostics=[]
    sufficient=len(hold)>=config.min_holdout and (mode=='known_albedo' or len(train)>=config.min_train)
    if not sufficient:diagnostics.append('insufficient disjoint train and holdout observations')
    independent_lighting=manifest.get('light_provenance') in ('synthetic_ground_truth','independent_irradiance_measurement')
    if not independent_lighting:diagnostics.append('illumination not independently established: albedo/light ambiguity')
    if mode=='known_albedo':
        if manifest.get('albedo_provenance') not in ('synthetic_ground_truth','independent_material_measurement'):
            diagnostics.append('albedo not independently known')
        if manifest.get('albedo_rgb') is None:
            diagnostics.append('albedo_rgb absent')
        else:rho=lambertian_brdf(manifest['albedo_rgb'])*math.pi
    else:
        if len(train)>=config.min_train and independent_lighting and all(x['verified'] for x in train):
            try:rho,sigma_rho=_fit_albedo(train,l,direct,ambient)
            except MaterialPhysicsError as exc:diagnostics.append(str(exc))
        else:diagnostics.append('cannot fit albedo without known lighting and independent train measurements')
    usable=bool(sufficient and independent_lighting and rho is not None and not diagnostics)
    observations=[]
    for r in hold:
        predicted=(rho/math.pi)*_irradiance(r,l,direct,ambient) if rho is not None else None
        if predicted is not None:
            factor=_irradiance(r,l,direct,ambient)/math.pi
            total_sigma=np.sqrt(r['sigma']**2+(factor*sigma_rho)**2)
            residual=(r['observed']-predicted)/total_sigma
            z=float(np.max(np.abs(residual)))
        else:z=None
        state=('INDETERMINATE' if not usable or not r['verified'] else
               'CONSISTENT' if z<=config.consistent_sigma else
               'INCONSISTENT_UNDER_ASSUMPTIONS' if z>=config.inconsistent_sigma else
               'INDETERMINATE')
        observations.append({'id':r['id'],'state':state,'geometry_and_radiometry_verified':r['verified'],
                             'observed_radiance_rgb':r['observed'].tolist(),
                             'predicted_radiance_rgb':predicted.tolist() if predicted is not None else None,
                             'normalized_residual_rgb':residual.tolist() if predicted is not None else None,
                             'max_abs_normalized_residual':z,
                             'reason':('independent inputs insufficient' if not usable or not r['verified'] else
                                       'outside model + measurement uncertainty' if state=='INCONSISTENT_UNDER_ASSUMPTIONS' else
                                       'inside model uncertainty' if state=='CONSISTENT' else
                                       'near decision threshold')})
    counts={state:sum(x['state']==state for x in observations) for state in
            ('CONSISTENT','INCONSISTENT_UNDER_ASSUMPTIONS','INDETERMINATE')}
    if not usable:overall='INDETERMINATE'
    elif counts['INCONSISTENT_UNDER_ASSUMPTIONS'] and counts['CONSISTENT']:
        overall='MIXED_CONDITIONAL_EVIDENCE'
    elif counts['INCONSISTENT_UNDER_ASSUMPTIONS']:
        overall='INCONSISTENT_UNDER_ASSUMPTIONS'
    elif counts['CONSISTENT'] and not counts['INDETERMINATE']:overall='CONSISTENT'
    else:overall='INDETERMINATE'
    return {'module':'P6_M01_LAMBERTIAN_BRDF_ENERGY', 'state':overall,'calibration_mode':mode,
            'fitted_or_known_albedo_rgb':rho.tolist() if rho is not None else None,
            'conditional_albedo_standard_error_rgb':sigma_rho.tolist() if rho is not None else None,
            'brdf_sr_inverse_rgb':(rho/math.pi).tolist() if rho is not None else None,
            'train_count':len(train),'holdout_count':len(hold), 'counts':counts,
            'observations':observations,'diagnostics':diagnostics,
            'assumptions':['Lambertian diffuse reflection only','one distant directional light and known ambient irradiance',
                           'linear calibrated RGB radiance and irradiance in consistent physical units',
                           'known measured surface normal and visibility fraction','material constant albedo across samples',
                           'no specular/interreflection, gamma, tone mapping, saturation or cast shadows beyond supplied visibility',
                           'train IDs never included in holdout metrics'],
            'decision':'NO_AI_ORIGIN_CONCLUSION',
            'limitations':['An observed brightness inconsistency does not prove image generation.',
                           'Estimated albedo uncertainties are conditional, not externally calibrated confidence intervals.',
                           'Light intensity/albedo scaling is non-identifiable without independent radiometry.',
                           'Numerical energy audit is not proof for all incoming and outgoing directions.']}


def run_material_manifest(input_path,output_dir,config=MaterialConfig()):
    data=json.loads(Path(input_path).read_text(encoding='utf-8'))
    report=analyze_material_manifest(data,config)
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'p6_m01_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
