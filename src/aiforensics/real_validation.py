"""P1-G02 real camera evaluation from externally labelled disjoint segment sets.

No claim of real-camera validation is made without a supplied photographic
frame, independently calibrated intrinsics and held-out orthogonal lines.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import json
import numpy as np
from .calibration import calibrate_from_g01_groups
from .vp import VPConfig
from .geometry import segments_to_lines, point_line_residuals


class RealValidationError(ValueError):
    pass


def evaluate_real_case(data: dict, base_dir: Path, vp_config: VPConfig | None = None)->dict:
    """Fitted G01->G02, versus independently calibrated K and unseen line segments.

    Input schema: image (relative path), known_intrinsics_K (3x3), image_shape_hw,
    train_orthogonal_groups (list of 3 Nx4), holdout_orthogonal_groups (3 Nx4),
    source, capture_and_calibration_provenance. Does not infer scene labels.
    """
    required=('image','known_intrinsics_K','image_shape_hw','train_orthogonal_groups',
              'holdout_orthogonal_groups','source','capture_and_calibration_provenance')
    for k in required:
        if k not in data:
            return {'state':'INDETERMINATE','reason':f'Missing required real validation field: {k}',
                    'decision':'NO_AI_ORIGIN_CONCLUSION'}
    imgpath=(base_dir/data['image']).resolve()
    if not imgpath.is_relative_to(base_dir.resolve()):
        raise RealValidationError('Image path must be inside the manifest directory.')
    if not imgpath.is_file():
        return {'state':'INDETERMINATE','reason':f'Real photographic image unavailable: {data["image"]}',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    import cv2
    im=cv2.imread(str(imgpath),cv2.IMREAD_COLOR)
    if im is None:
        return {'state':'INDETERMINATE','reason':'Image cannot be decoded.',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    if list(im.shape[:2])!=list(data['image_shape_hw']):
        raise RealValidationError('Image dimensions do not match the manifest.')
    if not str(data['source']).strip() or not str(data['capture_and_calibration_provenance']).strip():
        return {'state':'INDETERMINATE','reason':'Real capture and independent calibration provenance required.',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    gt=np.asarray(data['known_intrinsics_K'],float)
    if gt.shape!=(3,3) or not np.isfinite(gt).all() or gt[0,0]<=0 or gt[1,1]<=0 or not np.isclose(gt[2,2],1):
        raise RealValidationError('Invalid independently calibrated K.')
    if abs(gt[0,0]-gt[1,1])>0.05*gt[0,0] or abs(gt[0,1])>1.e-5:
        return {'state':'INDETERMINATE','reason':'Reference intrinsics violate G02 square-pixel zero-skew constraints.',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    if len(data['train_orthogonal_groups'])!=3 or len(data['holdout_orthogonal_groups'])!=3:
        raise RealValidationError('Three orthogonal direction groups required for both train and holdout.')
    train=[np.asarray(g,float) for g in data['train_orthogonal_groups']]
    holdout=[np.asarray(g,float) for g in data['holdout_orthogonal_groups']]
    if any(g.ndim!=2 or g.shape[1]!=4 or len(g)<2 or not np.isfinite(g).all() for g in train+holdout):
        raise RealValidationError('Each train/holdout group must contain >=2 finite segments (N,4).')
    # Disjoint segments: exact duplicates are rejected, including reversed endpoints.
    def segs_key(seg):
        return tuple(sorted(((round(float(seg[0]),4),round(float(seg[1]),4)),
                             (round(float(seg[2]),4),round(float(seg[3]),4)))))
    tr={segs_key(s) for g in train for s in g}
    ho={segs_key(s) for g in holdout for s in g}
    if tr&ho:
        raise RealValidationError('Calibration segments overlap holdout segments (data leakage).')
    vp_cfg=vp_config or VPConfig()
    fit=calibrate_from_g01_groups(train, tuple(data['image_shape_hw']),vp_cfg)
    if fit['state']!='MEASURED':
        return {'state':'INDETERMINATE','reason':'G01-G02 calibration failed: '+fit.get('reason',''),
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    k=np.asarray(fit['g02_calibration']['K'],float)
    vps=[m['vp_xy_px'] for m in fit['g01_models']]
    # Holdout edge directions measure physically independent observations, not
    # calibration constraints; group labels remain an externally verified premise.
    group_metrics=[]
    for idx,(grp,vp) in enumerate(zip(holdout,vps)):
        lines=segments_to_lines(grp)
        errs=np.abs(point_line_residuals(lines,np.asarray(vp)))
        group_metrics.append({'group':idx,'segments':int(len(grp)),
                              'holdout_line_to_vp_median_px':float(np.median(errs)),
                              'holdout_line_to_vp_rmse_px':float(np.sqrt(np.mean(errs**2)))})
    return {'state':'MEASURED','module':'G02_REAL_CAMERA_INDEPENDENT_VALIDATION',
            'dataset_source':data['source'],
            'capture_and_calibration_provenance':data['capture_and_calibration_provenance'],
            'image_sha256':hashlib.sha256(imgpath.read_bytes()).hexdigest(),
            'image_dimensions_hw':list(im.shape[:2]),
            'reference_K':gt.tolist(), 'estimated_K':k.tolist(),
            'absolute_focal_error_px':float(abs(k[0,0]-gt[0,0])),
            'relative_focal_error_pct':float(100*abs(k[0,0]-gt[0,0])/gt[0,0]),
            'principal_point_error_px':float(np.linalg.norm(k[:2,2]-gt[:2,2])),
            'independent_holdout_group_metrics':group_metrics,
            'assumptions':['Same known calibrated camera and dimensions','Optical distortion negligible or image rectified',
                           'Manhattan groups are independently annotated and mutually orthogonal',
                           'Holdout segments were not used for camera fit'],
            'limitations':['One real example cannot establish false-positive rate or generalization.',
                           'A camera model agreeing with observed lines cannot prove image authenticity.'],
            'decision':'NO_AI_ORIGIN_CONCLUSION'}


def run_real_manifest(input_path:Path,out:Path)->dict:
    data=json.loads(input_path.read_text(encoding='utf-8'))
    result=evaluate_real_case(data,input_path.parent)
    out.mkdir(parents=True,exist_ok=True)
    (out/'g02_real_independent_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result


def batch_real_validation(manifest_paths:list[Path], out:Path,
                          vp_config:VPConfig|None=None)->dict:
    """Aggregate externally calibrated photographic cases without claiming that
    the mere presence of paths or human-written provenance proves authenticity.
    Each case must explicitly declare provenance type; synthetic and missing data
    remain separate from measured photographic results.
    """
    results=[]
    for mp in manifest_paths:
        mp=Path(mp)
        try:
            data=json.loads(mp.read_text(encoding='utf-8'))
            result=evaluate_real_case(data,mp.parent,vp_config)
            if result['state']=='MEASURED' and data.get('capture_type')!='real_camera':
                result={'state':'INDETERMINATE',
                        'reason':'capture_type=real_camera declaration required for real dataset reporting',
                        'decision':'NO_AI_ORIGIN_CONCLUSION'}
            if result.get('state')=='MEASURED' and data.get('image_sha256'):
                if data['image_sha256']!=result['image_sha256']:
                    result={'state':'INDETERMINATE',
                            'reason':'Photographic SHA256 does not match externally declared identity',
                            'decision':'NO_AI_ORIGIN_CONCLUSION'}
        except (OSError,ValueError,KeyError) as e:
            result={'state':'INDETERMINATE','reason':str(e),
                    'decision':'NO_AI_ORIGIN_CONCLUSION'}
        results.append({'manifest':str(mp),'result':result})
    successful=[x['result'] for x in results if x['result']['state']=='MEASURED']
    out.mkdir(parents=True,exist_ok=True)
    summary={'module':'G02_EXTERNAL_REAL_CAMERA_BATCH',
        'declared_camera_cases':len(results),'measured_declared_camera_cases':len(successful),
        'unmeasured_cases':len(results)-len(successful),
        'state':'MEASURED' if successful else 'NOT_MEASURED',
        'focal_error_median_px':float(np.median([r['absolute_focal_error_px'] for r in successful])) if successful else None,
        'principal_error_median_px':float(np.median([r['principal_point_error_px'] for r in successful])) if successful else None,
        'limitations':['Declared real-camera provenance is not cryptographically verified.',
                       'No global accuracy or false-positive claim is justified from a small or biased batch.',
                       'Calibration groups must be independently labelled and verified.'],
        'results':results,'decision':'NO_AI_ORIGIN_CONCLUSION'}
    (out/'g02_batch_real_validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return summary
