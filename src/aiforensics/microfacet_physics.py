"""P6-M02: isotropic single-scattering GGX Cook-Torrance *specular* BRDF.

The BRDF and linear-radiance evidence require independently known light,
view, surface normals, incident irradiance, and F0. Image RGB is not radiance.
No AI-image origin decision is made. Geometric/energy checks are conditional.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math

import numpy as np
from scipy.optimize import least_squares
from .material_physics import hemisphere_quadrature


class MicrofacetError(ValueError):
    pass


@dataclass(frozen=True)
class MicrofacetConfig:
    consistent_sigma: float = 2.5
    inconsistent_sigma: float = 4.5
    min_train: int = 14
    min_holdout: int = 6
    roughness_min: float = .07
    roughness_max: float = .98
    max_roughness_sigma: float = .065


def _rgb(value, name: str, low=0.0, high=None):
    v=np.asarray(value, dtype=float)
    if v.shape!=(3,) or not np.all(np.isfinite(v)) or np.any(v<low) or (high is not None and np.any(v>high)):
        raise MicrofacetError(f'{name} must be finite RGB within physical bounds')
    return v


def _unit(value, name: str):
    v=np.asarray(value,dtype=float)
    if v.shape!=(3,) or not np.all(np.isfinite(v)) or np.linalg.norm(v)<1e-12:
        raise MicrofacetError(f'{name} must be a finite nonzero 3-vector')
    return v/np.linalg.norm(v)


def _roughness(roughness):
    try: a=float(roughness)
    except (TypeError,ValueError) as exc:raise MicrofacetError('roughness must be a scalar') from exc
    if not math.isfinite(a) or not .045<=a<=1.:
        raise MicrofacetError('roughness must be in [0.045,1]; ideal delta mirrors are excluded')
    return a


def fresnel_schlick(cos_theta, f0_rgb):
    """F = F0 + (1-F0)(1-cos(theta))^5; RGB F0 is independently known."""
    f0=_rgb(f0_rgb,'f0_rgb',high=1.)
    cos=float(cos_theta)
    if not math.isfinite(cos) or cos < 0 or cos > 1+1e-12:
        raise MicrofacetError('cos_theta must be in [0,1]')
    return f0+(1-f0)*(1-min(1.,cos))**5


def ggx_ndf(n_dot_h, roughness):
    """Isotropic Trowbridge-Reitz D; alpha=perceptual_roughness^2."""
    rough=_roughness(roughness)
    nh=float(n_dot_h)
    if not math.isfinite(nh) or not 0<=nh<=1:
        raise MicrofacetError('n_dot_h must be in [0,1]')
    alpha=rough*rough
    aa=alpha*alpha
    return aa/(math.pi*(nh*nh*(aa-1.)+1.)**2)


def smith_ggx_g1(n_dot_w, roughness):
    """Exact Smith GGX G1 for isotropic height-uncorrelated G=G1(wi)G1(wo)."""
    rough=_roughness(roughness)
    mu=float(n_dot_w)
    if not math.isfinite(mu) or not 0<=mu<=1:
        raise MicrofacetError('n_dot_w must be in [0,1]')
    if mu==0:return 0.
    alpha=rough*rough
    return 2*mu/(mu+math.sqrt(alpha*alpha+(1-alpha*alpha)*mu*mu))


def cook_torrance_specular(normal, to_light, to_camera, roughness, f0_rgb):
    """Reciprocal single-scatter specular BRDF RGB [sr^-1], nonnegative.

    Incoming and outgoing *directions both point away from the surface*.
    Illumination must later multiply this value by E_perpendicular*cos(theta_i).
    Below-surface rays are not physically visible; return zero.
    """
    n=_unit(normal,'normal'); l=_unit(to_light,'to_light');v=_unit(to_camera,'to_camera')
    rough=_roughness(roughness); f0=_rgb(f0_rgb,'f0_rgb',high=1.)
    nl=float(n@l);nv=float(n@v)
    if nl<=0 or nv<=0:return np.zeros(3)
    half=l+v
    if np.linalg.norm(half)<=1e-12:return np.zeros(3)
    h=half/np.linalg.norm(half)
    nh=max(0.,float(n@h)); vh=float(v@h)
    D=ggx_ndf(nh,rough)
    G=smith_ggx_g1(nl,rough)*smith_ggx_g1(nv,rough)
    F=fresnel_schlick(np.clip(vh,0,1),f0)
    return (D*G/(4*nl*nv))*F


def specular_radiance(normal, to_light, to_camera, incident_irradiance_rgb, roughness, f0_rgb,
                      *, visible_fraction=1.):
    """Single directional source, incident E defined normal to illumination rays.

    No diffuse/clearcoat term and no tone-mapping or gamma encoding.
    """
    n=_unit(normal,'normal');l=_unit(to_light,'to_light')
    E=_rgb(incident_irradiance_rgb,'incident_irradiance_rgb')
    vis=float(visible_fraction)
    if not math.isfinite(vis) or not 0<=vis<=1:
        raise MicrofacetError('visible_fraction must be in [0,1]')
    return cook_torrance_specular(n,l,to_camera,roughness,f0_rgb)*E*max(0.,float(n@l))*vis


def _sample_records(manifest):
    if not isinstance(manifest.get('samples'),list):raise MicrofacetError('samples must be a list')
    seen=set();train=[];hold=[]
    for item in manifest['samples']:
        if not isinstance(item,dict):raise MicrofacetError('sample must be an object')
        sid=item.get('id');role=item.get('role')
        if not isinstance(sid,str) or not sid or sid in seen or role not in ('train','holdout'):
            raise MicrofacetError('unique IDs and disjoint train/holdout roles required')
        seen.add(sid)
        sig=_rgb(item.get('sigma_radiance_rgb'),f'{sid} sigma',low=0)
        if np.any(sig<=0):raise MicrofacetError('sigma must be positive')
        vis=float(item.get('visible_fraction',1))
        if not math.isfinite(vis) or not 0<=vis<=1:raise MicrofacetError('visibility out of bounds')
        rec=dict(id=sid,role=role,
                 normal=_unit(item.get('normal_world'),f'{sid} normal'),
                 light=_unit(item.get('to_light_world'),f'{sid} light'),
                 view=_unit(item.get('to_camera_world'),f'{sid} view'),
                 observed=_rgb(item.get('observed_radiance_rgb'),f'{sid} observed'),
                 sigma=sig,visibility=vis,
                 verified=(item.get('geometry_provenance') in ('synthetic_ground_truth','independent_metric_normal_and_view') and
                           item.get('radiometry_provenance') in ('synthetic_ground_truth','independent_linear_calibration')))
        (train if role=='train' else hold).append(rec)
    return train,hold


def _predict(rec,rough,f0,E):
    return specular_radiance(rec['normal'],rec['light'],rec['view'],E,rough,f0,
                             visible_fraction=rec['visibility'])


def _fit(train,f0,E,config):
    """Robust scalar nonlinear estimation; reject nearly flat information and boundaries."""
    def residual(rr):
        return np.concatenate([(_predict(rec,rr[0],f0,E)-rec['observed'])/rec['sigma'] for rec in train])
    result=least_squares(residual,[.38],bounds=([config.roughness_min],[config.roughness_max]),
                         loss='soft_l1',f_scale=2.,max_nfev=350,xtol=1e-11,ftol=1e-11)
    if not result.success:raise MicrofacetError('roughness optimization did not converge')
    rough=float(result.x[0]);
    if rough<config.roughness_min+.015 or rough>config.roughness_max-.015:
        raise MicrofacetError('roughness solution at parameter boundary')
    # Robust data diversity: geometry must generate distinguishable BRDF observations.
    step=0.0002
    dr=(residual([rough+step])-residual([rough-step]))/(2*step)
    fisher=float(np.sum(dr**2))
    sigma_rough=1/math.sqrt(max(fisher,1e-20))
    if sigma_rough>config.max_roughness_sigma or np.linalg.norm(dr)<1e-5:
        raise MicrofacetError('roughness not identifiable from training illumination/view variation')
    return rough,sigma_rough


def analyze_microfacet_manifest(manifest,config=MicrofacetConfig()):
    if not isinstance(manifest,dict):raise MicrofacetError('manifest must be an object')
    if not 0<config.consistent_sigma<config.inconsistent_sigma or config.min_holdout<1:
        raise MicrofacetError('invalid error thresholds')
    train,hold=_sample_records(manifest)
    E=_rgb(manifest.get('incident_irradiance_rgb'),'incident_irradiance_rgb')
    if max(E)<=0:raise MicrofacetError('irradiance must be positive in at least one channel')
    f0=_rgb(manifest.get('f0_rgb'),'f0_rgb',high=1.)
    mode=manifest.get('calibration_mode','known_roughness')
    if mode not in ('known_roughness','fit_roughness'):
        raise MicrofacetError('invalid calibration_mode')
    diagnostics=[]
    if len(hold)<config.min_holdout:diagnostics.append('insufficient independent holdout samples')
    if manifest.get('light_provenance') not in ('synthetic_ground_truth','independent_irradiance_measurement'):
        diagnostics.append('incident irradiance / illumination not independent')
    if manifest.get('f0_provenance') not in ('synthetic_ground_truth','independent_material_measurement'):
        diagnostics.append('F0 not independently measured (F0/roughness/light ambiguity)')
    rough=None;sigma_rough=0.
    if mode=='known_roughness':
        if manifest.get('roughness_provenance') not in ('synthetic_ground_truth','independent_material_measurement'):
            diagnostics.append('roughness not independently established')
        try:rough=_roughness(manifest.get('roughness'))
        except MicrofacetError:diagnostics.append('roughness missing or invalid')
    else:
        if len(train)<config.min_train:diagnostics.append('insufficient independent train samples')
        if any(not r['verified'] for r in train):diagnostics.append('unverified training sample geometry/radiometry')
        if not diagnostics:
            try:rough,sigma_rough=_fit(train,f0,E,config)
            except MicrofacetError as exc:diagnostics.append(str(exc))
    usable=(rough is not None and not diagnostics)
    measurements=[]
    for rec in hold:
        pred=_predict(rec,rough,f0,E) if rough is not None else None
        if pred is not None:
            if mode=='fit_roughness':
                dr=(_predict(rec,min(1,rough+0.0001),f0,E)-_predict(rec,max(.045,rough-0.0001),f0,E))/.0002
                combined_sigma=np.sqrt(rec['sigma']**2+(dr*sigma_rough)**2)
            else:combined_sigma=rec['sigma']
            z=float(np.max(np.abs((rec['observed']-pred)/combined_sigma)))
        else:z=None
        state=('INDETERMINATE' if not usable or not rec['verified'] else
               'CONSISTENT' if z<=config.consistent_sigma else
               'INCONSISTENT_UNDER_ASSUMPTIONS' if z>=config.inconsistent_sigma else
               'INDETERMINATE')
        measurements.append({'id':rec['id'],'state':state,'independent_measurements':rec['verified'],
                             'observed_radiance_rgb':rec['observed'].tolist(),
                             'predicted_specular_radiance_rgb':pred.tolist() if pred is not None else None,
                             'max_normalized_residual':z})
    counts={state:sum(r['state']==state for r in measurements)
            for state in ('CONSISTENT','INCONSISTENT_UNDER_ASSUMPTIONS','INDETERMINATE')}
    state=('INDETERMINATE' if not usable or not measurements or counts['INDETERMINATE']>0 else
           'INCONSISTENT_UNDER_ASSUMPTIONS' if counts['INCONSISTENT_UNDER_ASSUMPTIONS'] else 'CONSISTENT')
    return {'module':'P6_M02_GGX_COOK_TORRANCE_SPECULAR','state':state,
            'decision':'NO_AI_ORIGIN_CONCLUSION','calibration_mode':mode,
            'fitted_or_known_roughness':rough,'roughness_sigma_local_linear_approximation':sigma_rough,
            'f0_rgb':f0.tolist(),'observations':measurements,'counts':counts,'diagnostics':diagnostics,
            'assumptions':['independent calibrated linear incident irradiance and outgoing radiance',
             'isotropic opaque single-scattering specular microfacets','GGX D with alpha=roughness^2',
             'height-uncorrelated exact Smith GGX masking-shadowing','Schlick Fresnel approximation and known F0',
             'known per-sample geometry; directional light; no diffuse term in model'],
            'limitations':['no diffuse term, multiple scattering, subsurface scattering, thin films, anisotropy or clearcoat',
             'no measured lens/sensor imaging PSF or exposure/tone mapping effects',
             'a large residual is only conditional disagreement, not AI-image provenance evidence']}


def run_microfacet_manifest(input_path:Path,out_dir:Path,config=MicrofacetConfig()):
    manifest=json.loads(Path(input_path).read_text(encoding='utf-8'))
    report=analyze_microfacet_manifest(manifest,config)
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/'p6_m02_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report


def audit_ggx_energy(roughness,f0_rgb,*,mu_view=(.3,.6,.9),n_mu=40,n_phi=96):
    """Numerical hemispherical-directional reflectance (specular-only).

    Compare Gauss/phi meshes to detect unresolved sharp/highly specular lobes.
    Sufficient accuracy is NOT guaranteed by a single sample grid.
    """
    rough=_roughness(roughness);f0=_rgb(f0_rgb,'f0_rgb',high=1.)
    if n_mu<8 or n_phi<16 or n_mu>256 or n_phi>512:
        raise MicrofacetError('quadrature resolution out of bounds')
    if not mu_view or any(not 0.1<=float(mu)<=1 for mu in mu_view):
        raise MicrofacetError('mu_view must contain cosines in [0.1,1]')

    def integrate(mu,nm,np_):
        dirs,weights=hemisphere_quadrature(nm,np_)
        v=np.array([math.sqrt(max(0,1-mu*mu)),0,mu])
        # Vectorized stable specular expression, upper hemisphere.
        half=dirs+v
        half/=np.linalg.norm(half,axis=1)[:,None]
        nh=half[:,2]
        vh=np.clip(half@v,0,1)
        nl=dirs[:,2]
        alpha=rough**2; a2=alpha**2
        D=a2/(math.pi*(nh**2*(a2-1)+1)**2)
        G_l=2*nl/(nl+np.sqrt(a2+(1-a2)*nl**2))
        G_v=2*mu/(mu+math.sqrt(a2+(1-a2)*mu**2))
        spec=D*G_l*G_v/(4*nl*mu)
        F=f0[None,:]+(1-f0[None,:])*(1-vh[:,None])**5
        return (weights*nl)@(spec[:,None]*F)

    audits=[]
    for val in mu_view:
        mu=float(val)
        coarse=integrate(mu,n_mu,n_phi)
        fine=integrate(mu,2*n_mu,2*n_phi)
        discrepancy=float(np.max(np.abs(coarse-fine)))
        # Plain angle-grid quadrature may miss a needle-like specular peak at *both*
        # resolutions, creating false convergence. Abstain below the safe roughness
        # range unless importance sampling / an analytic bound is implemented.
        if rough < .18 or discrepancy>0.015:
            state='INDETERMINATE'
            reason='sharp lobe or unresolved quadrature; no energy certification'
        elif np.max(fine)>1+.015:
            state='INCONSISTENT_UNDER_ASSUMPTIONS';reason='hemispherical reflectance exceeds one'
        else:
            state='CONSISTENT';reason='discrete single-scattering GGX energy audit within resolution'
        audits.append({'cos_view':mu,'directional_hemispherical_reflectance_rgb':fine.tolist(),
                       'quadrature_discrepancy':discrepancy,'state':state,'reason':reason})
    summary=('INDETERMINATE' if any(a['state']=='INDETERMINATE' for a in audits) else
             'INCONSISTENT_UNDER_ASSUMPTIONS' if any(a['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for a in audits)
             else 'CONSISTENT')
    return {'module':'P6_M02_GGX_SPECULAR_ENERGY_AUDIT','state':summary,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'roughness':rough,'f0_rgb':f0.tolist(),'view_samples':audits,
            'notes':['only single-scattering specular BRDF; no diffuse term',
                     'two resolutions compared; discrete quadrature, not analytic energy proof']}
