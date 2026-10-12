"""Controlled P6-M01 photometric test data (not a real-camera experiment)."""
from __future__ import annotations
import copy
import numpy as np
from .material_physics import lambertian_radiance


def synthetic_material_fixture(*, seed=2601, mode='fit_albedo',
                               n_train=50, n_holdout=24, corrupted=3,
                               noise_sigma=.018):
    if n_train < 0 or n_holdout < corrupted:raise ValueError('invalid sample counts')
    rng=np.random.default_rng(seed)
    rho=np.array([.63,.38,.22])
    light=[.48,.20,.854]
    d=[16.0,13.0,11.0];ambient=[2.0,2.3,2.1]
    samples=[]; truth={}
    for i in range(n_train+n_holdout):
        x,y=rng.uniform(-.9,.9,2)
        normal=np.array([x,y,1.2]);normal/=np.linalg.norm(normal)
        reference=lambertian_radiance(normal,light,d,ambient,rho)
        measured=np.maximum(0,reference+rng.normal(0,noise_sigma,3))
        role='train' if i<n_train else 'holdout'
        if role=='holdout' and i>=n_train+n_holdout-corrupted:
            measured+=np.array([.60,-.45,.48])
            measured=np.maximum(0,measured)
        sid=f'm-{i:03d}'
        samples.append({'id':sid,'role':role,'normal_world':normal.tolist(),
                        'observed_radiance_rgb':measured.tolist(),
                        'sigma_radiance_rgb':[noise_sigma]*3,
                        'visible_fraction':1.0,
                        'geometry_provenance':'synthetic_ground_truth',
                        'radiometry_provenance':'synthetic_ground_truth'})
        if role=='holdout':truth[sid]=('INCONSISTENT_UNDER_ASSUMPTIONS' if i>=n_train+n_holdout-corrupted else 'CONSISTENT')
    fixture={'dataset_type':'controlled_synthetic_lambertian','calibration_mode':mode,
             'light_direction_world':light,'light_provenance':'synthetic_ground_truth',
             'direct_irradiance_rgb':d,'ambient_irradiance_rgb':ambient,
             'albedo_provenance':'synthetic_ground_truth','albedo_rgb':rho.tolist(),
             'samples':samples}
    return fixture, {'albedo_rgb':rho.tolist(),'expected_holdout_states':truth,
                     'corrupted_holdout_count':corrupted,'seed':seed}


def draw_material_demo(path,fixture,report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    l=np.asarray(fixture['light_direction_world'],float);l=l/np.linalg.norm(l)
    rho=np.asarray(report['fitted_or_known_albedo_rgb'])
    degrees=np.linspace(0,90,250)
    normals=np.column_stack((np.sin(np.deg2rad(degrees)),
                             np.zeros(len(degrees)),np.cos(np.deg2rad(degrees))))
    normals/=np.linalg.norm(normals,axis=1,keepdims=True)
    fig,axs=plt.subplots(1,2,figsize=(11.5,4.3))
    d=fixture['direct_irradiance_rgb'];a=fixture['ambient_irradiance_rgb']
    for channel,label in enumerate(['R','G','B']):
        values=np.array([lambertian_radiance(n,l,d,a,rho)[channel] for n in normals])
        axs[0].plot(degrees,values,label=f'{label} (model)')
    axs[0].set(xlabel='Yuzey normali egimi (derece)',ylabel='Lineer cikis radiansi',title='Lambertian tahmin: bilinen isik + albedo')
    axs[0].grid(alpha=.25);axs[0].legend()
    data=report['observations']
    for group,label in [('CONSISTENT','Kosullu uyumlu'),('INCONSISTENT_UNDER_ASSUMPTIONS','Kosullu uyumsuz'),('INDETERMINATE','Belirsiz')]:
        chosen=[(i,r['max_abs_normalized_residual']) for i,r in enumerate(data) if r['state']==group and r['max_abs_normalized_residual'] is not None]
        if chosen:axs[1].scatter(*np.array(chosen).T,label=label,alpha=.85)
    axs[1].axhline(2.5,ls='--',c='gray',lw=1);axs[1].axhline(4.5,ls='--',c='gray',lw=1)
    axs[1].set(xlabel='Bagimsiz holdout gozlem indeksi',ylabel='Maksimum |normalize artik|',title='Kalibrasyonda kullanilmayan noktalar')
    axs[1].legend(fontsize=8);axs[1].grid(alpha=.25)
    fig.suptitle('P6-M01 — SENTETIK FIZIK TESTI / GERCEK FOTOGRAF DEGIL',fontsize=12)
    fig.tight_layout();fig.savefig(path,dpi=160);plt.close(fig)
