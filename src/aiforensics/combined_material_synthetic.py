"""Reproducible P6-M03 synthetic surface measurements; not real-camera validation."""
from __future__ import annotations
import math
import numpy as np
from .combined_material import combined_radiance


def synthetic_combined_fixture(*,seed=2803,mode='fit_diffuse_albedo',n_train=30,
                               n_holdout=24,corrupted=3,sigma=.007,policy='assumed_negligible'):
    if mode not in ('fit_diffuse_albedo','known_material') or n_train<0 or n_holdout<=corrupted:
        raise ValueError('invalid generator parameters')
    rng=np.random.default_rng(seed)
    rho=[.52,.38,.27];rough=.47;f0=[.05,.08,.12];ws=.34
    E=[7.,6.,5.]
    mat={'diffuse_albedo_rgb':rho,'roughness':rough,'f0_rgb':f0,
         'specular_weight':ws,'material_provenance':'synthetic_ground_truth',
         'multiscattering_policy':policy}
    if policy=='bounded_diffuse_proxy':
        mat.update(multiscatter_proxy_weight=.12,
                   multiscatter_proxy_albedo_rgb=[.3,.35,.4],
                   multiscatter_proxy_provenance='synthetic_ground_truth')
    wm=mat.get('multiscatter_proxy_weight',0.)
    proxy=mat.get('multiscatter_proxy_albedo_rgb',[0.,0.,0.])
    # Deliberately provide an incorrect placeholder in fit mode to prove the fit
    # derives its albedo from TRAIN measurements, not from the input albedo.
    if mode=='fit_diffuse_albedo':mat['diffuse_albedo_rgb']=[.40,.40,.40]
    samples=[];truth={}
    for i in range(n_train+n_holdout):
        role='train' if i<n_train else 'holdout'
        surface=('panel_A' if (i%2)==0 else 'panel_B') if role=='holdout' else 'reference_coupon'
        n=np.array([0,0,1.])
        theta=float(rng.uniform(.10,.75));phi=float(rng.uniform(0,2*math.pi))
        l=np.array([math.sin(theta)*math.cos(phi),math.sin(theta)*math.sin(phi),math.cos(theta)])
        vth=float(rng.uniform(.09,.85));vp=phi+math.pi+float(rng.uniform(-.5,.5))
        v=np.array([math.sin(vth)*math.cos(vp),math.sin(vth)*math.sin(vp),math.cos(vth)])
        pred=combined_radiance(n,l,v,E,rho,rough,f0,specular_weight=ws,
                               multiscatter_proxy_weight=wm,multiscatter_proxy_albedo_rgb=proxy)
        y=np.maximum(0,pred+rng.normal(0,sigma,3))
        sid=f'patch-{i:03d}'
        bad=role=='holdout' and i>=n_train+n_holdout-corrupted
        if bad:y=y+np.array([.35,.37,.34])
        samples.append({'id':sid,'role':role,'surface_id':surface,'material_id':'paint01',
                        'normal_world':n.tolist(),'to_light_world':l.tolist(),
                        'to_camera_world':v.tolist(),'observed_radiance_rgb':y.tolist(),
                        'sigma_radiance_rgb':[sigma]*3,
                        'geometry_provenance':'synthetic_ground_truth',
                        'radiometry_provenance':'synthetic_ground_truth'})
        if role=='holdout':truth[sid]='INCONSISTENT_UNDER_ASSUMPTIONS' if bad else 'CONSISTENT'
    fixture={'dataset_type':'controlled_synthetic_multisurface_combined_BRDF',
             'calibration_mode':mode,'incident_irradiance_rgb':E,
             'light_provenance':'synthetic_ground_truth','materials':{'paint01':mat},
             'samples':samples}
    return fixture,{'seed':seed,'true_diffuse_albedo_rgb':rho,'corrupted':corrupted,
                    'expected_holdout_states':truth,'policy':policy}


def render_combined_report(path,report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    allobs=report['observations']
    fig,ax=plt.subplots(figsize=(10,4.6))
    for state,mark in [('CONSISTENT','o'),('INDETERMINATE','^'),('INCONSISTENT_UNDER_ASSUMPTIONS','x')]:
        items=[(i,p['max_normalized_residual']) for i,p in enumerate(allobs) if p['state']==state]
        if items:
            arr=np.array(items);ax.scatter(arr[:,0],arr[:,1],s=38,marker=mark,label=state)
    ax.axhline(2.5,ls='--',color='gray',lw=1)
    ax.axhline(4.5,ls=':',color='gray',lw=1)
    ax.set(xlabel='Independent holdout patch index',ylabel='Max normalized RGB residual',
           title='P6-M03: two surfaces, shared material and independent holdout')
    ax.grid(alpha=.25);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(path,dpi=140);plt.close(fig)
