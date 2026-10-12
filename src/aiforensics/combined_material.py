"""P6-M03: conditional, energy-bounded mixture of Lambert and single-scatter GGX.

A convex combination of separately passive reflection BRDFs is passive.
An optional *phenomenological*, diffuse multiscattering proxy is NOT an
actual microfacet multiscattering solution and requires independent evidence.
Radiance must be linear and scene-referred, with independently known lighting.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import math
import numpy as np
from scipy.optimize import least_squares
from .microfacet_physics import cook_torrance_specular, audit_ggx_energy
from .material_physics import hemisphere_quadrature


class CombinedMaterialError(ValueError):
    pass


@dataclass(frozen=True)
class CombinedMaterialConfig:
    consistent_sigma: float = 2.5
    inconsistent_sigma: float = 4.5
    min_train: int = 12
    min_holdout: int = 8
    max_albedo_sigma: float = 0.10
    min_train_surfaces: int = 1
    min_holdout_surfaces: int = 2


def _rgb(value, label: str, *, positive=False, max_value=None):
    x = np.asarray(value, dtype=float)
    if x.shape != (3,) or not np.all(np.isfinite(x)) or np.any(x < 0):
        raise CombinedMaterialError(f'{label} requires nonnegative finite RGB')
    if positive and np.any(x <= 0):
        raise CombinedMaterialError(f'{label} must be positive in every channel')
    if max_value is not None and np.any(x > max_value):
        raise CombinedMaterialError(f'{label} must be <= {max_value}')
    return x


def _unit(v, name):
    x=np.asarray(v,dtype=float)
    if x.shape!=(3,) or not np.all(np.isfinite(x)) or np.linalg.norm(x)<1e-12:
        raise CombinedMaterialError(f'{name} must be a nonzero finite 3-vector')
    return x/np.linalg.norm(x)


def _fraction(v,name):
    x=float(v)
    if not math.isfinite(x) or not 0<=x<=1:
        raise CombinedMaterialError(f'{name} outside [0,1]')
    return x


def _material(raw, name):
    if not isinstance(raw,dict):raise CombinedMaterialError(f'{name} must be an object')
    rho=_rgb(raw.get('diffuse_albedo_rgb'),name+'.diffuse_albedo_rgb',max_value=1)
    f0=_rgb(raw.get('f0_rgb'),name+'.f0_rgb',max_value=1)
    rough=float(raw.get('roughness',float('nan')))
    if not math.isfinite(rough) or not .045<=rough<=1:
        raise CombinedMaterialError(f'{name}.roughness outside supported [.045,1]')
    ws=_fraction(raw.get('specular_weight'),name+'.specular_weight')
    wm=_fraction(raw.get('multiscatter_proxy_weight',0),name+'.multiscatter_proxy_weight')
    if ws+wm>1+1e-12:
        raise CombinedMaterialError('sum of reflection lobe weights exceeds one')
    policy=raw.get('multiscattering_policy','assumed_negligible')
    if policy not in ('assumed_negligible','unknown','bounded_diffuse_proxy'):
        raise CombinedMaterialError('unrecognized multiple scattering policy')
    if wm>0 and policy!='bounded_diffuse_proxy':
        raise CombinedMaterialError('proxy weight requires bounded_diffuse_proxy')
    proxy=_rgb(raw.get('multiscatter_proxy_albedo_rgb',[0,0,0]),'multiscatter_proxy_albedo_rgb',max_value=1)
    if policy=='bounded_diffuse_proxy':
        if raw.get('multiscatter_proxy_provenance') not in ('synthetic_ground_truth','independently_characterized_proxy'):
            # do not silently bless an unverified phenomenological fit
            verified_proxy=False
        else:verified_proxy=True
    else:verified_proxy=(policy=='assumed_negligible')
    if raw.get('material_provenance') not in ('synthetic_ground_truth','independent_material_measurement'):
        verified_material=False
    else:verified_material=True
    return {'rho':rho,'f0':f0,'rough':rough,'ws':ws,'wm':wm,'proxy':proxy,
            'policy':policy,'verified_proxy':verified_proxy,'verified_material':verified_material}


def combined_brdf(normal,to_light,to_camera,diffuse_albedo_rgb,roughness,f0_rgb,
                  *,specular_weight=0.3,multiscatter_proxy_weight=0.,
                  multiscatter_proxy_albedo_rgb=(0.,0.,0.)):
    """Passive reciprocal BRDF mixture. Proxy term is a model, not true GGX multisct."""
    n=_unit(normal,'normal');l=_unit(to_light,'to_light');v=_unit(to_camera,'to_camera')
    rho=_rgb(diffuse_albedo_rgb,'diffuse_albedo',max_value=1)
    proxy=_rgb(multiscatter_proxy_albedo_rgb,'proxy_albedo',max_value=1)
    ws=_fraction(specular_weight,'specular_weight')
    wm=_fraction(multiscatter_proxy_weight,'multiscatter_proxy_weight')
    if ws+wm>1+1e-12:raise CombinedMaterialError('lobe weights must sum <= one')
    if n@l<=0 or n@v<=0:return np.zeros(3)
    spec=cook_torrance_specular(n,l,v,roughness,f0_rgb)
    return (1-ws-wm)*rho/math.pi + ws*spec + wm*proxy/math.pi


def combined_radiance(normal,to_light,to_camera,incident_irradiance_rgb,
                     diffuse_albedo_rgb,roughness,f0_rgb,*,specular_weight=.3,
                     multiscatter_proxy_weight=0.,multiscatter_proxy_albedo_rgb=(0,0,0),
                     visible_fraction=1.):
    n=_unit(normal,'normal');l=_unit(to_light,'to_light')
    E=_rgb(incident_irradiance_rgb,'incident_irradiance')
    vis=_fraction(visible_fraction,'visible_fraction')
    return E*max(0.,float(n@l))*vis*combined_brdf(
        n,l,to_camera,diffuse_albedo_rgb,roughness,f0_rgb,
        specular_weight=specular_weight,
        multiscatter_proxy_weight=multiscatter_proxy_weight,
        multiscatter_proxy_albedo_rgb=multiscatter_proxy_albedo_rgb)


def _predict(rec,material,E,rho_override=None):
    return combined_radiance(rec['n'],rec['l'],rec['v'],E,
        material['rho'] if rho_override is None else rho_override,
        material['rough'],material['f0'],specular_weight=material['ws'],
        multiscatter_proxy_weight=material['wm'],
        multiscatter_proxy_albedo_rgb=material['proxy'],visible_fraction=rec['visibility'])


def _records(manifest, materials):
    if not isinstance(manifest.get('samples'),list):raise CombinedMaterialError('samples must be a list')
    seen=set();train={k:[] for k in materials};hold={k:[] for k in materials}
    for row in manifest['samples']:
        if not isinstance(row,dict):raise CombinedMaterialError('sample must be object')
        sid=row.get('id');role=row.get('role');mid=row.get('material_id');surface=row.get('surface_id')
        if not isinstance(sid,str) or not sid or sid in seen:raise CombinedMaterialError('duplicate/empty ID')
        seen.add(sid)
        if role not in ('train','holdout') or mid not in materials:
            raise CombinedMaterialError('invalid role or material_id')
        if not isinstance(surface,str) or not surface:raise CombinedMaterialError('surface_id required')
        sigma=_rgb(row.get('sigma_radiance_rgb'),sid+'.sigma',positive=True)
        rec={'id':sid,'material':mid,'role':role,'surface':surface,
             'n':_unit(row.get('normal_world'),sid+'.normal'),
             'l':_unit(row.get('to_light_world'),sid+'.light'),
             'v':_unit(row.get('to_camera_world'),sid+'.view'),
             'observed':_rgb(row.get('observed_radiance_rgb'),sid+'.observed'),
             'sigma':sigma,'visibility':_fraction(row.get('visible_fraction',1),sid+'.visibility'),
             'verified':(row.get('geometry_provenance') in ('synthetic_ground_truth','independent_metric_geometry') and
                         row.get('radiometry_provenance') in ('synthetic_ground_truth','independent_linear_calibration'))}
        (train if role=='train' else hold)[mid].append(rec)
    return train,hold


def _fit_diffuse_albedo(train,mat,E,config):
    # Fit RGB albedo on train only; known F0, roughness, weights and lighting.
    # Non-identifiability manifests as nearly zero diffuse fraction or exposure.
    wd=1-mat['ws']-mat['wm']
    if wd<=1e-5:raise CombinedMaterialError('zero diffuse fraction: diffuse albedo not identifiable')
    if len(train)<config.min_train:raise CombinedMaterialError('insufficient train observations')
    if any(not r['verified'] for r in train):raise CombinedMaterialError('unverified train geometry/radiometry')
    design=[]; observed=[];sig=[]
    for r in train:
        g=E*max(0.,float(r['n']@r['l']))*r['visibility']
        base=_predict(r,mat,E,np.zeros(3))
        design.append(g*wd/math.pi);observed.append(r['observed']-base);sig.append(r['sigma'])
    A=np.asarray(design);Y=np.asarray(observed);sigma=np.asarray(sig)
    rho=np.zeros(3);unc=np.zeros(3)
    for c in range(3):
        info=float(np.sum((A[:,c]/sigma[:,c])**2))
        if info<1/(config.max_albedo_sigma**2):
            raise CombinedMaterialError('diffuse albedo vs illumination not identifiable')
        unc[c]=1/math.sqrt(info)
        def fun(x):return (A[:,c]*x[0]-Y[:,c])/sigma[:,c]
        result=least_squares(fun,[.45],bounds=([0.],[1.]),loss='soft_l1',f_scale=2.)
        if not result.success:raise CombinedMaterialError('albedo optimization did not converge')
        rho[c]=float(result.x[0])
        if rho[c]<.005 or rho[c]>.995:
            raise CombinedMaterialError('albedo estimate at boundary; cannot distinguish clipping')
    return rho,unc


def analyze_combined_manifest(manifest,config=CombinedMaterialConfig()):
    if not isinstance(manifest,dict):raise CombinedMaterialError('manifest must be object')
    if not (0<config.consistent_sigma<config.inconsistent_sigma):
        raise CombinedMaterialError('invalid thresholds')
    E=_rgb(manifest.get('incident_irradiance_rgb'),'incident_irradiance',positive=True)
    raw=manifest.get('materials')
    if not isinstance(raw,dict) or not raw:raise CombinedMaterialError('materials must be nonempty mapping')
    materials={key:_material(val,str(key)) for key,val in raw.items() if isinstance(key,str) and key}
    if len(materials)!=len(raw):raise CombinedMaterialError('invalid material keys')
    mode=manifest.get('calibration_mode','known_material')
    if mode not in ('known_material','fit_diffuse_albedo'):
        raise CombinedMaterialError('invalid calibration_mode')
    trains,holds=_records(manifest,materials)
    light_verified=manifest.get('light_provenance') in ('synthetic_ground_truth','independent_irradiance_measurement')
    all_obs=[];diagnostics=[];fitted={};uncertainties={};surface_reports={}
    if not light_verified:diagnostics.append('light intensity/direction not independently known: material-light scale ambiguity')
    for mid,mat in materials.items():
        tr=trains[mid]; ho=holds[mid];local=[]
        if not mat['verified_material']:
            local.append('F0/roughness/mixing fractions not independently established')
        if mat['policy']=='unknown':local.append('unmodeled multiple scattering could alter BRDF')
        if not mat['verified_proxy']:local.append('multiple scattering proxy not independently characterized')
        if len(ho)<config.min_holdout:local.append('insufficient holdout')
        surf=set(r['surface'] for r in ho)
        if len(surf)<config.min_holdout_surfaces:local.append('cross-surface test needs distinct holdout surfaces')
        rho=mat['rho'].copy();unc=np.zeros(3)
        if mode=='fit_diffuse_albedo':
            try:rho,unc=_fit_diffuse_albedo(tr,mat,E,config)
            except CombinedMaterialError as err:local.append(str(err))
        fitted[mid]=rho.tolist();uncertainties[mid]=unc.tolist()
        if any(not r['verified'] for r in ho):local.append('some holdout provenance is unverified')
        for rec in ho:
            pred=_predict(rec,mat,E,rho)
            factor=E*max(0.,float(rec['n']@rec['l']))*rec['visibility']*(1-mat['ws']-mat['wm'])/math.pi
            combined_sigma=np.sqrt(rec['sigma']**2+(factor*unc)**2)
            z=float(np.max(abs(rec['observed']-pred)/combined_sigma))
            state=('INDETERMINATE' if local or not light_verified or not rec['verified'] else
                   'CONSISTENT' if z<=config.consistent_sigma else
                   'INCONSISTENT_UNDER_ASSUMPTIONS' if z>=config.inconsistent_sigma else 'INDETERMINATE')
            all_obs.append({'id':rec['id'],'material_id':mid,'surface_id':rec['surface'],
                            'state':state,'observed_radiance_rgb':rec['observed'].tolist(),
                            'predicted_radiance_rgb':pred.tolist(),
                            'max_normalized_residual':z,'independent_measurements':rec['verified']})
        sr={}
        for r in all_obs:
            if r['material_id']==mid:
                s=r['surface_id'];entry=sr.setdefault(s,{'total':0,'consistent':0,'inconsistent':0,'indeterminate':0})
                entry['total']+=1
                key={'CONSISTENT':'consistent','INCONSISTENT_UNDER_ASSUMPTIONS':'inconsistent','INDETERMINATE':'indeterminate'}[r['state']]
                entry[key]+=1
        surface_reports[mid]=sr
        diagnostics.extend(f'{mid}: {d}' for d in local)
    counts={state:sum(o['state']==state for o in all_obs)
            for state in ('CONSISTENT','INCONSISTENT_UNDER_ASSUMPTIONS','INDETERMINATE')}
    summary=('INDETERMINATE' if diagnostics or not light_verified or not all_obs or counts['INDETERMINATE'] else
             'INCONSISTENT_UNDER_ASSUMPTIONS' if counts['INCONSISTENT_UNDER_ASSUMPTIONS'] else 'CONSISTENT')
    return {'module':'P6_M03_ENERGY_BOUNDED_COMBINED_BRDF','state':summary,
            'decision':'NO_AI_ORIGIN_CONCLUSION','calibration_mode':mode,
            'albedo_rgb_by_material':fitted,'albedo_sigma_approx_by_material':uncertainties,
            'counts':counts,'surfaces_by_material':surface_reports,
            'observations':all_obs,'diagnostics':diagnostics,
            'model':['convex mixture of Lambert and single-scattering Smith-GGX Cook-Torrance',
                     'optional energy-bounded *phenomenological Lambertian* multiple-scattering proxy',
                     'all lobe weights nonnegative and sum at most one'],
            'limitations':['mixture fractions and F0/roughness must be independently characterized',
                           'unknown multiple scattering leads to INDETERMINATE, not fake physical violation',
                           'no actual microfacet multiple-scattering transport or Kulla-Conty LUT',
                           'only linear calibrated radiometry; no JPEG pixel brightness as radiance',
                           'no definitive AI-generated image decision']}


def run_combined_manifest(input_path,out_dir,config=CombinedMaterialConfig()):
    manifest=json.loads(Path(input_path).read_text(encoding='utf-8'))
    report=analyze_combined_manifest(manifest,config)
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    (out/'p6_m03_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report


def audit_combined_energy(material,*,mu_view=(.3,.6,.9),n_mu=40,n_phi=96):
    """Audit sampled directional hemispherical reflectance, not a universal certificate."""
    mat=_material(material,'material')
    core=audit_ggx_energy(mat['rough'],mat['f0'],mu_view=mu_view,n_mu=n_mu,n_phi=n_phi)
    wd=1-mat['ws']-mat['wm']
    audit=[]
    for sample in core['view_samples']:
        spec=np.asarray(sample['directional_hemispherical_reflectance_rgb'])
        total=wd*mat['rho']+mat['ws']*spec+mat['wm']*mat['proxy']
        state=('INDETERMINATE' if sample['state']=='INDETERMINATE' or mat['policy']=='unknown' or not mat['verified_proxy'] else
               'INCONSISTENT_UNDER_ASSUMPTIONS' if np.max(total)>1.015 else 'CONSISTENT')
        audit.append({'cos_view':sample['cos_view'],'integrated_reflectance_rgb':total.tolist(),
                      'state':state,'single_specular_quadrature_discrepancy':sample['quadrature_discrepancy']})
    state=('INDETERMINATE' if any(x['state']=='INDETERMINATE' for x in audit) else
           'INCONSISTENT_UNDER_ASSUMPTIONS' if any(x['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for x in audit) else 'CONSISTENT')
    return {'module':'P6_M03_SAMPLED_ENERGY_AUDIT','state':state,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'view_samples':audit,'assumptions':['energy-bounded BRDF lobe mixture',
              'finite angular quadrature only, not global proof for all directions'],
            'limitations':['thin GGX peaks may be missed; abstain if roughness too small or quadrature unresolved',
                           'diffuse proxy is not a validated multiple scattering solver']}
