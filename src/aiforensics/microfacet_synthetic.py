"""Controlled P6-M02 measurements, not a real material/camera experiment."""
from __future__ import annotations

import math
import numpy as np
from .microfacet_physics import specular_radiance


def synthetic_microfacet_fixture(*, seed=2702,mode='fit_roughness',n_train=56,n_holdout=24,
                                 corrupted=3,noise_sigma=.012):
    if mode not in ('known_roughness','fit_roughness') or n_train<0 or n_holdout<corrupted:
        raise ValueError('invalid generator arguments')
    rng=np.random.default_rng(seed)
    rough=.43
    f0=np.array([.08,.14,.20]); E=np.array([16.,15.,13.])
    n=[0.,0.,1.]
    samples=[];truth={}
    for i in range(n_train+n_holdout):
        # angular diversity: near and off-specular directions with distinct lobes
        theta=float(rng.uniform(.1,.8))
        alpha=float(rng.uniform(0,2*math.pi))
        l=np.array([math.sin(theta)*math.cos(alpha),math.sin(theta)*math.sin(alpha),math.cos(theta)])
        delta=float(rng.uniform(-.48,.48))
        vtheta=float(np.clip(theta+delta,.02,1.3))
        vaz=alpha+math.pi+float(rng.uniform(-.4,.4))
        v=np.array([math.sin(vtheta)*math.cos(vaz),math.sin(vtheta)*math.sin(vaz),math.cos(vtheta)])
        ref=specular_radiance(n,l,v,E,rough,f0)
        measured=np.maximum(0.,ref+rng.normal(0,noise_sigma,3))
        role='train' if i<n_train else 'holdout'
        sid=f's-{i:03d}'
        bad=role=='holdout' and i>=n_train+n_holdout-corrupted
        if bad:measured=measured+np.array([.35,.35,.35])
        samples.append({'id':sid,'role':role,'normal_world':n,
                        'to_light_world':l.tolist(),'to_camera_world':v.tolist(),
                        'observed_radiance_rgb':measured.tolist(),
                        'sigma_radiance_rgb':[noise_sigma]*3,
                        'geometry_provenance':'synthetic_ground_truth',
                        'radiometry_provenance':'synthetic_ground_truth'})
        if role=='holdout':truth[sid]='INCONSISTENT_UNDER_ASSUMPTIONS' if bad else 'CONSISTENT'
    manifest={'dataset_type':'controlled_synthetic_ggx_single_scatter','calibration_mode':mode,
              'light_provenance':'synthetic_ground_truth','f0_provenance':'synthetic_ground_truth',
              'roughness_provenance':'synthetic_ground_truth','roughness':rough,
              'f0_rgb':f0.tolist(),'incident_irradiance_rgb':E.tolist(),'samples':samples}
    return manifest,{'seed':seed,'roughness':rough,'corrupted':corrupted,'expected_holdout_states':truth}


def render_microfacet_report(path,report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    points=report['observations'];states=['CONSISTENT','INDETERMINATE','INCONSISTENT_UNDER_ASSUMPTIONS']
    fig,ax=plt.subplots(figsize=(10,4.5))
    for state,marker in zip(states,['o','^','x']):
        chosen=[(i,r['max_normalized_residual']) for i,r in enumerate(points)
                if r['state']==state and r['max_normalized_residual'] is not None]
        if chosen:
            xy=np.array(chosen)
            ax.scatter(xy[:,0],xy[:,1],label=state,marker=marker)
    ax.axhline(2.5,ls='--',color='gray',lw=1)
    ax.axhline(4.5,ls=':',color='gray',lw=1)
    ax.set(xlabel='Holdout observation index',ylabel='Maximum standardized residual',
           title='P6-M02 GGX: controlled synthetic specular holdout measurements')
    ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(path,dpi=140);plt.close(fig)
