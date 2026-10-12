"""Controlled irradiance-linear, 1-D soft-shadow edge fixtures, not photographs."""
from __future__ import annotations
import numpy as np
from .penumbra import edge_irradiance,penumbra_width_from_angle


def synthetic_penumbra_fixture(angle_deg:float=1.2,seed:int=1,noise_sigma:float=.008,
                                shapes:tuple[str,...]=('UNIFORM_DISK',),
                                heights:tuple[float,...]=(1.6,2.2,3.0,4.0),
                                px_per_meter:float=125.,
                                malformed_source:int|None=None,
                                include_geometry:bool=True,
                                psf_sigma_px:float=0.):
    rng=np.random.default_rng(seed)
    edges=[]
    truths=[]
    for i,h in enumerate(heights):
        sh=shapes[i%len(shapes)]
        beta=angle_deg if i != malformed_source else angle_deg*2.0
        width=penumbra_width_from_angle(beta,px_per_meter,h)
        r=width/2
        span=max(26.,r*4.0)
        x=np.linspace(-span,span,161)
        side='left' if i%2 else 'right'
        dark=.12+i*.012;bright=.88-i*.014
        center=float(3+i*.8)
        levels=edge_irradiance(x,center,r,dark,bright,side,sh)
        if noise_sigma:
            levels=np.clip(levels+rng.normal(0,noise_sigma,len(x)),0,1)
        record={'id':f'edge_{i:02d}','radiometric_space':'LINEAR_RELATIVE_IRRADIANCE',
                'x_px':x.tolist(),'linear_irradiance':levels.tolist(),'source_shape':sh,
                'light_side':side}
        if include_geometry:
            record['metric_geometry']={'model':'NEAR_NORMAL_PARALLEL_RAYS','verified':True,
                'receiver_pixels_per_meter':float(px_per_meter),
                'occluder_receiver_separation_m':float(h),
                'optical_psf_sigma_px':float(psf_sigma_px)}
        edges.append(record)
        truths.append({'id':record['id'],'angular_diameter_deg':beta,
                       'penumbra_fullwidth_px':width,'occluder_height_m':h})
    return ({'schema':'P2_S05_EDGE_PROFILES_V1',
             'scenario':'controlled synthetic uniform extended-source knife edges',
             'declared_common_source':True,
             'edges':edges},
            {'source_angular_diameter_deg':angle_deg,'edges':truths})
