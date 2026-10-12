"""P5-D03: conservative conditional static feasibility of rigid objects.

Finite *point* contacts, rigid object, Coulomb friction, known forces/torques.
Inner friction polyhedral cone is sufficient for feasible equilibrium.
Outer cone is necessary for feasible equilibrium. Consequently:
  inner feasible => CONSISTENT (under declared complete physical assumptions)
  outer infeasible => INCONSISTENT_UNDER_ASSUMPTIONS
  undecidable gap / insufficient evidence / numerical failure => INDETERMINATE.
This is NOT a reconstruction from RGB imagery or an AI-origin classifier.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from .depth_contact import SupportPlane, DepthContactError


class StaticEquilibriumError(ValueError):
    pass


@dataclass(frozen=True)
class EquilibriumConfig:
    cone_sides: int = 16
    contact_surface_tolerance_world: float = 1e-5
    relative_balance_tolerance: float = 1e-7

    def __post_init__(self):
        if self.cone_sides < 8 or self.cone_sides % 4 != 0:
            raise StaticEquilibriumError('cone_sides must be a multiple of 4 and at least 8')
        if self.contact_surface_tolerance_world <= 0 or self.relative_balance_tolerance <= 0:
            raise StaticEquilibriumError('tolerances must be positive')


def vector(values, label):
    v = np.asarray(values, dtype=float)
    if v.shape != (3,) or not np.isfinite(v).all():
        raise StaticEquilibriumError(f'{label} must be 3 finite values')
    return v


def unit(values, label):
    v = vector(values, label)
    norm = float(np.linalg.norm(v))
    if norm <= 1e-12:
        raise StaticEquilibriumError(f'{label} cannot be zero')
    return v / norm


def _basis(n):
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < .8 else np.array([0.0, 1.0, 0.0])
    t1 = np.cross(n, ref)
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    return t1, t2


def _residual(A, x, b):
    return float(np.linalg.norm(A @ x - b))


def _linprog(Aeq, rhs, Aub=None, bub=None, bounds=None):
    return linprog(np.zeros(Aeq.shape[1]), A_eq=Aeq, b_eq=rhs,
                   A_ub=Aub, b_ub=bub, bounds=bounds, method='highs',
                   options={'primal_feasibility_tolerance': 1e-8,
                            'dual_feasibility_tolerance': 1e-8})


def _contact_validate(raw, surfaces, cfg):
    try:
        support = surfaces[str(raw['support_id'])]
        point = vector(raw['point_world_xyz'], 'contact point')
        n = unit(raw['reaction_normal_world'], 'contact reaction normal')
        mu = float(raw['friction_coefficient'])
    except (KeyError, TypeError, ValueError, DepthContactError) as exc:
        raise StaticEquilibriumError(f'invalid contact definition: {exc}') from exc
    if not np.isfinite(mu) or mu < 0 or mu > 10:
        raise StaticEquilibriumError('friction coefficient must be in [0,10]')
    if abs(float(n @ support.n)) < 1 - 1e-6:
        raise StaticEquilibriumError('reaction normal must align with support plane normal')
    if abs(support.signed_distance(point)) > cfg.contact_surface_tolerance_world:
        return (point, n, mu), 'contact point does not lie on claimed support plane'
    if not support.contains(point, margin=cfg.contact_surface_tolerance_world):
        return (point, n, mu), 'contact point lies outside finite support polygon'
    return (point, n, mu), None


def _system(contacts, com, gravity, mass, externals):
    # Equilibrium equations relative to center of mass, to reduce numerical conditioning.
    total_force = mass * gravity.copy()
    total_torque = np.zeros(3)
    for f, p in externals:
        total_force += f
        total_torque += np.cross(p-com, f)
    return np.r_[-total_force, -total_torque]


def _inner_problem(contacts, com, sides):
    cols = []
    for p, n, mu in contacts:
        t1, t2 = _basis(n)
        for j in range(sides):
            angle = (j * 2 * np.pi / sides)
            force = n + mu * (t1 * np.cos(angle) + t2 * np.sin(angle))
            cols.append(np.r_[force, np.cross(p-com, force)])
    return np.column_stack(cols)


def _outer_problem(contacts, com, sides):
    nct = len(contacts)
    Aeq = np.zeros((6, 3*nct), dtype=float)
    Aub = []
    for i, (p, n, mu) in enumerate(contacts):
        sl = slice(i*3, (i+1)*3)
        Aeq[:3,sl] = np.eye(3)
        for j, axis in enumerate(np.eye(3)):
            Aeq[3:, i*3+j] = np.cross(p-com, axis)
        # Force lies in a conservative *outer* approximation to exact Coulomb cone.
        # All physical forces pass: n.F >=0, t(theta).F <=mu*n.F.
        row = np.zeros(3*nct)
        row[sl] = -n
        Aub.append(row)
        t1, t2 = _basis(n)
        for j in range(sides):
            angle = (j*2*np.pi/sides)
            row = np.zeros(3*nct)
            row[sl] = np.cos(angle)*t1 + np.sin(angle)*t2 - mu*n
            Aub.append(row)
    return Aeq, np.asarray(Aub)


def evaluate_static_equilibrium(data: dict, cfg: EquilibriumConfig = EquilibriumConfig()):
    """Evaluate a manifest; all claims explicitly conditional on complete 3D inputs."""
    if not isinstance(data, dict):
        raise StaticEquilibriumError('manifest must be a JSON object')
    try:
        gravity = vector(data['gravity_acceleration_world_m_s2'], 'gravity acceleration')
        if np.linalg.norm(gravity) <= 1e-9:
            raise StaticEquilibriumError('gravity magnitude must be positive')
        surfaces = [SupportPlane(x) for x in data['support_surfaces']]
        objects = data['objects']
    except (KeyError, TypeError, DepthContactError) as exc:
        raise StaticEquilibriumError(f'invalid manifest: {exc}') from exc
    if not surfaces or len({s.id for s in surfaces}) != len(surfaces):
        raise StaticEquilibriumError('at least one unique support plane is required')
    if not isinstance(objects, list) or not objects:
        raise StaticEquilibriumError('objects must be a nonempty array')
    smap = {s.id:s for s in surfaces}
    used = set()
    results = []
    for obj in objects:
        if not isinstance(obj, dict):
            raise StaticEquilibriumError('each object must be a JSON object')
        oid = str(obj.get('id', ''))
        if not oid or oid in used:
            raise StaticEquilibriumError('object IDs must be unique and nonempty')
        used.add(oid)
        provenance = obj.get('geometry_provenance', 'image_only')
        complete = obj.get('all_contacts_declared') is True
        eligible = provenance in ('independent_metric', 'synthetic_ground_truth') and complete
        reasons = []
        diagnostics = {}
        if provenance not in ('independent_metric','synthetic_ground_truth'):
            reasons.append('independent metric center-of-mass/contact evidence unavailable')
        if not complete:
            reasons.append('contact set or external restraint completeness not independently established')
        if obj.get('center_of_mass_uncertainty_radius_world',0) is not None:
            unc=float(obj.get('center_of_mass_uncertainty_radius_world',0))
            if not np.isfinite(unc) or unc < 0:
                raise StaticEquilibriumError(f'{oid}: center-of-mass uncertainty radius must be finite and nonnegative')
            if unc>0:
                eligible=False
                reasons.append('nonzero center-of-mass uncertainty requires interval feasibility analysis not supplied by D03')
        if obj.get('external_force_uncertainty_newton',0) is not None:
            unc=float(obj.get('external_force_uncertainty_newton',0))
            if not np.isfinite(unc) or unc < 0:
                raise StaticEquilibriumError(f'{oid}: external force uncertainty must be finite and nonnegative')
            if unc>0:
                eligible=False
                reasons.append('nonzero force uncertainty requires interval equilibrium analysis')
        try:
            mass_components = obj.get('mass_components')
            if mass_components is not None:
                if not isinstance(mass_components, list) or not mass_components:
                    raise StaticEquilibriumError(f'{oid}: mass_components must be a nonempty list')
                component_masses = []
                component_centers = []
                for component in mass_components:
                    mpart = float(component['mass_kg'])
                    if not np.isfinite(mpart) or mpart <= 0:
                        raise StaticEquilibriumError(f'{oid}: component mass must be positive')
                    component_masses.append(mpart)
                    component_centers.append(vector(component['center_world_xyz'], 'component center'))
                derived_mass = float(np.sum(component_masses))
                derived_com = np.average(component_centers, axis=0, weights=component_masses)
                diagnostics['mass_distribution_derived_mass_kg'] = derived_mass
                diagnostics['mass_distribution_derived_center_of_mass_xyz'] = derived_com.tolist()
                if obj.get('mass_kg') is not None and not np.isclose(float(obj['mass_kg']), derived_mass, rtol=1e-7, atol=1e-9):
                    reasons.append('independent total mass conflicts with declared mass distribution')
                    results.append({'id':oid,'state': 'INCONSISTENT_UNDER_ASSUMPTIONS' if eligible else 'INDETERMINATE',
                                    'reasons':reasons,'diagnostics':diagnostics})
                    continue
                if obj.get('center_of_mass_world_xyz') is not None and np.linalg.norm(vector(obj['center_of_mass_world_xyz'],'claimed center of mass') - derived_com) > cfg.contact_surface_tolerance_world:
                    reasons.append('declared center of mass conflicts with independent component mass distribution')
                    results.append({'id':oid,'state': 'INCONSISTENT_UNDER_ASSUMPTIONS' if eligible else 'INDETERMINATE',
                                    'reasons':reasons,'diagnostics':diagnostics})
                    continue
                mass = derived_mass
                com = derived_com
            else:
                if obj.get('mass_kg') is None or obj.get('center_of_mass_world_xyz') is None:
                    reasons.append('mass and/or center of mass is unknown')
                    results.append({'id':oid, 'state':'INDETERMINATE', 'reasons':reasons,
                                    'diagnostics':diagnostics})
                    continue
                mass = float(obj['mass_kg'])
                com = vector(obj['center_of_mass_world_xyz'],'center of mass')
            if not np.isfinite(mass) or mass <= 0:
                raise StaticEquilibriumError(f'{oid}: mass must be positive')
            raw_contacts = obj.get('contacts', [])
            if not isinstance(raw_contacts, list):
                raise StaticEquilibriumError('contacts must be an array')
            if len(raw_contacts)==0:
                reasons.append('no independent load-bearing contact points')
                results.append({'id':oid,'state':'INDETERMINATE','reasons':reasons,'diagnostics':diagnostics})
                continue
            contact_data = [_contact_validate(row,smap,cfg) for row in raw_contacts]
            contacts = [t[0] for t in contact_data]
            failures = [t[1] for t in contact_data if t[1] is not None]
            if failures:
                reasons.extend(sorted(set(failures)))
                state = 'INCONSISTENT_UNDER_ASSUMPTIONS' if eligible else 'INDETERMINATE'
                results.append({'id':oid,'state':state,'reasons':reasons,'diagnostics':diagnostics})
                continue
            externals=[]
            for load in obj.get('external_forces', []):
                externals.append((vector(load['force_world_newton'],'external force'),
                                  vector(load['application_point_world_xyz'],'external force location')))
            # External point *couples* are supported as independent applied torque loads.
            applied_torque = vector(obj.get('external_torque_world_newton_metre',[0,0,0]),'external torque')
            rhs = _system(contacts,com,gravity,mass,externals)
            rhs[3:] -= applied_torque
            diagnostics['required_contact_wrench'] = rhs.tolist()
            diagnostics['mass_kg'] = mass
            diagnostics['number_of_point_contacts'] = len(contacts)
            diagnostics['friction_cone_sides'] = cfg.cone_sides
            diagnostics['model'] = 'rigid body, quasi-static, unilateral point contacts, Coulomb friction'
            if not eligible:
                results.append({'id':oid,'state':'INDETERMINATE','reasons':reasons,
                                'diagnostics':diagnostics})
                continue
            A_inner = _inner_problem(contacts,com,cfg.cone_sides)
            res_inner = _linprog(A_inner,rhs,bounds=[(0,None)]*A_inner.shape[1])
            tol = cfg.relative_balance_tolerance * max(1.,np.linalg.norm(rhs))
            diagnostics['inner_solver_status'] = int(res_inner.status)
            if res_inner.success and _residual(A_inner,res_inner.x,rhs) <= tol:
                diagnostics['balance_residual'] = _residual(A_inner,res_inner.x,rhs)
                coefficients=res_inner.x.reshape(len(contacts),cfg.cone_sides)
                witness=[]
                for i, (p,n,mu) in enumerate(contacts):
                    t1,t2=_basis(n)
                    basis=np.array([n+mu*(t1*np.cos(2*np.pi*j/cfg.cone_sides)+t2*np.sin(2*np.pi*j/cfg.cone_sides)) for j in range(cfg.cone_sides)])
                    witness.append((coefficients[i]@basis).tolist())
                diagnostics['witness_contact_forces_world_newton']=witness
                state='CONSISTENT'
                reasons.append('an admissible force and moment balance witness exists within conservative inner friction cones')
            else:
                A_outer, B_outer=_outer_problem(contacts,com,cfg.cone_sides)
                res_outer=_linprog(A_outer,rhs,B_outer,np.zeros(len(B_outer)),bounds=[(None,None)]*A_outer.shape[1])
                diagnostics['outer_solver_status']=int(res_outer.status)
                if res_outer.status==2:
                    state='INCONSISTENT_UNDER_ASSUMPTIONS'
                    reasons.append('even relaxed outer friction cones cannot balance the declared forces and torques')
                else:
                    state='INDETERMINATE'
                    reasons.append('friction cone approximation gap or numerical solver cannot establish a definitive balance')
            results.append({'id':oid,'state':state,'reasons':reasons,'diagnostics':diagnostics})
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc,StaticEquilibriumError):
                raise
            raise StaticEquilibriumError(f'{oid}: invalid object definition: {exc}') from exc
    counts={k:sum(r['state']==k for r in results) for k in
            ('CONSISTENT','INCONSISTENT_UNDER_ASSUMPTIONS','INDETERMINATE')}
    state=('INCONSISTENT_UNDER_ASSUMPTIONS' if counts['INCONSISTENT_UNDER_ASSUMPTIONS']
           else 'CONSISTENT' if counts['CONSISTENT'] and not counts['INDETERMINATE']
           else 'INDETERMINATE')
    return {'module':'P5_D03_STATIC_EQUILIBRIUM','state':state,'objects':results,
            'counts':counts,'decision':'NO_AI_ORIGIN_CONCLUSION',
            'assumptions':['rigid quasi-static bodies','all physical contacts and external restraints specified for definite verdict',
                'metric center of mass and independent support geometry','dry Coulomb contact friction and unilateral normal reaction',
                'support polygon and contact sites must be independently known'],
            'limitations':['image appearance cannot uniquely determine mass, contact or friction',
                'no dynamic equilibrium, adhesion, distributed pressure, deformable body or hidden restraints',
                'uncertain COM/forces are explicitly deferred to interval-robust mechanics; not converted to certain evidence',
                'a mechanically valid synthetic scene can be generated by AI',
                'inner/outer cone relaxation gap is indeterminate, never an automatic physical contradiction']}


def run_static_manifest(path: str | Path, out: str | Path, cfg: EquilibriumConfig = EquilibriumConfig()):
    path=Path(path); out=Path(out)
    data=json.loads(path.read_text(encoding='utf-8'))
    report=evaluate_static_equilibrium(data,cfg)
    report['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    out.mkdir(parents=True,exist_ok=True)
    (out/'p5_d03_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
