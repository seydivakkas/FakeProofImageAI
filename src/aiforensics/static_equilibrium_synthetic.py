"""Controlled synthetic ground truth; no photographic evidence or image classifier."""
from __future__ import annotations
import copy
import numpy as np


def synthetic_equilibrium_fixture(seed: int = 0, *, noise_newton: float = 0.0):
    rng=np.random.default_rng(seed)
    ground={'id':'ground','normal_world':[0,0,1],'offset_world':0.,
            'polygon_world_xyz':[[-3,-3,0],[3,-3,0],[3,3,0],[-3,3,0]]}
    corners=[[-.5,-.5,0],[.5,-.5,0],[.5,.5,0],[-.5,.5,0]]
    contacts=[{'support_id':'ground','point_world_xyz':p,
               'reaction_normal_world':[0,0,1],'friction_coefficient':0.6} for p in corners]
    def item(id, com=(0,0,1), forces=(), torque=None, provenance='synthetic_ground_truth',complete=True):
        obj={'id':id,'mass_kg':10., 'center_of_mass_world_xyz':list(com),
             'geometry_provenance':provenance,'all_contacts_declared':complete,
             'contacts':copy.deepcopy(contacts), 'external_forces':[],
             'external_torque_world_newton_metre':list(torque or [0,0,0])}
        for f,p in forces:
            obj['external_forces'].append({'force_world_newton':list(f),'application_point_world_xyz':list(p)})
        return obj
    n=float(noise_newton)
    objects=[
        item('balanced'),
        item('horizontal_load_feasible',forces=[([16+rng.normal(0,n),0,0],[0,0,1])]),
        item('no_friction_slide',forces=[([110+rng.normal(0,n),0,0],[0,0,1])]),
        item('tipping',forces=[([100+rng.normal(0,n),0,0],[0,0,2])]),
        item('com_outside',com=(1.8,0,1)),
        item('no_provenance',provenance='image_only'),
        item('missing_contacts',complete=False),
        item('unknown_com')
    ]
    objects[-1]['center_of_mass_world_xyz']=None
    objects.append(item('contact_outside_support'))
    objects[-1]['contacts'][0]['point_world_xyz']=[5,0,0]
    truth={'balanced':'CONSISTENT','horizontal_load_feasible':'CONSISTENT',
           'no_friction_slide':'INCONSISTENT_UNDER_ASSUMPTIONS',
           'tipping':'INCONSISTENT_UNDER_ASSUMPTIONS',
           'com_outside':'INCONSISTENT_UNDER_ASSUMPTIONS',
           'no_provenance':'INDETERMINATE','missing_contacts':'INDETERMINATE',
           'unknown_com':'INDETERMINATE',
           'contact_outside_support':'INCONSISTENT_UNDER_ASSUMPTIONS'}
    return {'gravity_acceleration_world_m_s2':[0,0,-9.81],
            'support_surfaces':[ground], 'objects':objects,
            'dataset_type':'controlled_synthetic_3d_mechanics'},truth
