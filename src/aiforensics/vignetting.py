"""P4-O04: conditional radiometric flat-field/vignetting consistency.

The cos^4 component is an idealized *image-space chief-ray* model. An optional
radial log-gain accounts for extra falloff, and may have a shifted center.
Nothing here infers image provenance. Input must be linear, dark-corrected, and
have independently justified flat-field target irradiance.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from scipy.optimize import least_squares

class VignettingError(ValueError):
    pass

@dataclass(frozen=True)
class VignettingConfig:
    sigma_threshold: float=3.5
    min_holdout: int=12
    min_train: int=35
    max_inverse_gain: float=8.0


def camera_K(mat):
    k=np.asarray(mat,dtype=float)
    if k.shape!=(3,3) or not np.isfinite(k).all() or abs(np.linalg.det(k))<1e-10:
        raise VignettingError('K must be finite invertible 3x3 matrix')
    if k[0,0]<=0 or k[1,1]<=0 or abs(k[2,0])>1e-10 or abs(k[2,1])>1e-10 or abs(k[2,2]-1)>1e-10:
        raise VignettingError('K must be a standard positive-focal pinhole intrinsic matrix')
    return k


def normalized_coordinates(uv, K):
    K=camera_K(K)
    pts=np.asarray(uv,dtype=float)
    if pts.shape[-1]!=2 or not np.isfinite(pts).all():
        raise VignettingError('pixel coordinates must have finite last dimension two')
    y=(pts[...,1]-K[1,2])/K[1,1]
    x=(pts[...,0]-K[0,2]-K[0,1]*y)/K[0,0]
    return np.stack((x,y),axis=-1)


def cos4_gain(uv,K):
    xy=normalized_coordinates(uv,K)
    return (1.0+np.sum(xy**2,axis=-1))**(-2)


def relative_illumination(uv,K,a2=0.,a4=0.,center_xy=(0.,0.)):
    """Gain normalized at the camera principal point; valid for an undistorted K domain."""
    xy=normalized_coordinates(uv,K)
    cc=np.asarray(center_xy,dtype=float)
    if cc.shape!=(2,) or not np.isfinite(cc).all() or not np.isfinite([a2,a4]).all():
        raise VignettingError('invalid radial model parameters')
    r2=np.sum((xy-cc)**2,axis=-1)
    r02=float(cc@cc)
    exponent=a2*(r2-r02)+a4*(r2*r2-r02*r02)
    if np.any(np.abs(exponent)>100):
        raise VignettingError('unphysical/extrapolated gain exponent')
    return cos4_gain(uv,K)*np.exp(exponent)


def predict_irradiance(uv,K, reference, log_scale, a2=0., a4=0., center_xy=(0.,0.)):
    ref=np.asarray(reference,dtype=float)
    if np.any(~np.isfinite(ref)) or np.any(ref<=0) or not np.isfinite(log_scale):
        raise VignettingError('reference irradiance and scale must be valid positive finite')
    return ref*np.exp(log_scale)*relative_illumination(uv,K,a2,a4,center_xy)


def _records(data):
    samples=data.get('samples')
    if not isinstance(samples,list):raise VignettingError('samples list is required')
    train=[];hold=[];seen=set()
    for record in samples:
        if not isinstance(record,dict):raise VignettingError('invalid sample record')
        id_=record.get('id');role=record.get('role')
        if not isinstance(id_,str) or not id_ or id_ in seen or role not in ('train','holdout'):
            raise VignettingError('disjoint unique train/holdout IDs are required')
        seen.add(id_)
        uv=np.asarray(record.get('xy_px'),dtype=float)
        if uv.shape!=(2,) or not np.isfinite(uv).all():raise VignettingError('sample xy_px must be two finite coordinates')
        try:
            obs=float(record['observed_linear']);ref=float(record['reference_linear']);sigma=float(record['sigma_linear'])
        except (KeyError,TypeError,ValueError) as e:raise VignettingError('sample requires observed_linear, reference_linear, sigma_linear') from e
        if any(not np.isfinite(q) or q<=0 for q in (obs,ref,sigma)):
            raise VignettingError('linear measurements and sigma must be finite positive')
        if obs>=1.0 and data.get('linear_scale','relative_0_to_1')=='relative_0_to_1':
            raise VignettingError('saturated or unnormalized observation >=1; linear 0..1 input required')
        if record.get('measurement_provenance') not in ('synthetic_known_flat_field','independent_flat_field_measurement'):
            # This is an epistemic failure, not a numeric error.
            record_prov=False
        else:record_prov=True
        target=(id_,uv,obs,ref,sigma,record_prov)
        (train if role=='train' else hold).append(target)
    return train,hold


def _array(records):
    return (np.asarray([r[1] for r in records],float),
            np.asarray([r[2] for r in records],float),
            np.asarray([r[3] for r in records],float),
            np.asarray([r[4] for r in records],float))


def _validate_coverage(records,K,center_fit=False):
    xy=normalized_coordinates(_array(records)[0],K)
    radial=np.linalg.norm(xy,axis=1)
    # Different radii, both image dimensions, and quadrants prevent trivial constant-field fitting.
    if np.ptp(radial)<.25 or np.linalg.matrix_rank(np.column_stack((xy,np.ones(len(xy)))))<3:
        raise VignettingError('insufficient radial/spatial calibration diversity')
    if np.ptp(xy[:,0])<.25 or np.ptp(xy[:,1])<.25:
        raise VignettingError('train samples do not span both image axes')
    if center_fit:
        if any(not np.any((np.sign(xy[:,i])==sgn)) for i in range(2) for sgn in (-1,1)):
            raise VignettingError('shifted center requires samples on both sides of each axis')
        if len(records)<55:raise VignettingError('shifted center requires >=55 train samples')


def _estimate(train,K,mode):
    xy,obs,ref,sigma=_array(train)
    y=np.log(obs/ref)-np.log(cos4_gain(xy,K))
    eps=np.maximum(sigma/obs,.002)
    fit_shift=(mode=='fit_radial_and_center')
    _validate_coverage(train,K,fit_shift)
    if mode=='cos4_only':
        logscale=float(np.median(y))
        rmse=float(np.sqrt(np.mean((logscale-y)**2)))
        return np.array([logscale,0.,0.,0.,0.]),{'train_log_rmse':rmse, 'parameter_covariance':np.diag([rmse**2/max(1,len(y)),0,0,0,0]).tolist()}
    if mode not in ('fit_radial','fit_radial_and_center'):
        raise VignettingError('calibration_mode must be cos4_only, fit_radial or fit_radial_and_center')
    position=normalized_coordinates(xy,K)
    d=np.sum(position**2,axis=1)
    A=np.column_stack((np.ones(len(d)),d,d*d))
    if np.linalg.cond(A)>5000:
        raise VignettingError('ill-conditioned radial calibration design')
    initial=np.linalg.lstsq(A,y,rcond=None)[0]
    def resid(p):
        logscale,a2,a4=p[:3]
        cx,cy=(p[3],p[4]) if fit_shift else (0.,0.)
        rs=np.sum((position-(cx,cy))**2,axis=1)
        r0=cx*cx+cy*cy
        pred=logscale+a2*(rs-r0)+a4*(rs*rs-r0*r0)
        return (pred-y)/eps
    x0=np.r_[initial,np.zeros(2)] if fit_shift else initial
    lo=[-5,-8,-8,-.16,-.16] if fit_shift else [-5,-8,-8]
    hi=[5,8,8,.16,.16] if fit_shift else [5,8,8]
    result=least_squares(resid,x0=np.clip(x0,np.array(lo)+1e-6,np.array(hi)-1e-6),
                         bounds=(lo,hi),loss='soft_l1',f_scale=1.3,max_nfev=900,
                         xtol=1e-11,ftol=1e-11,gtol=1e-11)
    if not result.success or not np.isfinite(result.x).all():
        raise VignettingError('photometric radial fit did not converge')
    if np.any(np.isclose(result.x,np.array(lo),atol=1e-4)) or np.any(np.isclose(result.x,np.array(hi),atol=1e-4)):
        raise VignettingError('photometric optimum is at calibration parameter boundary')
    sv=np.linalg.svd(result.jac,compute_uv=False)
    if len(sv)<len(result.x) or sv[-1]<=max(sv[0],1.)*1e-7:
        raise VignettingError('calibration parameters not independently identifiable')
    p=np.r_[result.x,np.zeros(2)] if not fit_shift else result.x
    rmse=float(np.sqrt(np.mean((resid(result.x)*eps)**2)))
    # Asymptotic local covariance; this is NOT externally calibrated confidence.
    covariance=np.linalg.pinv(result.jac.T@result.jac)*max(1.0,2*result.cost/max(1,len(y)-len(result.x)))
    if not fit_shift:
        full=np.zeros((5,5));full[:3,:3]=covariance;covariance=full
    return p,{'train_log_rmse':rmse,'weighted_fit_cost':float(result.cost),'jacobian_condition':float(sv[0]/sv[-1]),
              'parameter_covariance':covariance.tolist()}


def analyze_vignetting_manifest(data,config=VignettingConfig()):
    if not isinstance(data,dict):raise VignettingError('manifest must be JSON object')
    K=camera_K(data.get('K'))
    dims=data.get('image_size_wh')
    if not isinstance(dims,list) or len(dims)!=2 or any(not isinstance(x,int) or x<2 for x in dims):
        raise VignettingError('image_size_wh must contain positive integer width and height')
    if not np.isfinite([config.sigma_threshold,config.max_inverse_gain]).all() or config.sigma_threshold<=0 or config.max_inverse_gain<1:
        raise VignettingError('invalid thresholds')
    if data.get('pixel_coordinate_domain')!='undistorted_pinhole':
        return {'module':'P4_O04','state':'INDETERMINATE','reason':'pixel coordinates must be registered to independently calibrated undistorted K (P4-O01)',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    if data.get('photometric_provenance') not in ('SYNTHETIC_LINEAR_DARK_CORRECTED_FLAT_FIELD',
                                                 'INDEPENDENT_LINEAR_DARK_CORRECTED_FLAT_FIELD'):
        return {'module':'P4_O04','state':'INDETERMINATE','reason':'unknown radiance, tone curves, exposure or dark offset: calibrated flat-field provenance required',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    train,hold=_records(data)
    if len(train)<config.min_train or len(hold)<config.min_holdout:
        return {'module':'P4_O04','state':'INDETERMINATE','reason':'insufficient separated train/holdout regions',
                'train_count':len(train),'holdout_count':len(hold),'decision':'NO_AI_ORIGIN_CONCLUSION'}
    if not all(r[5] for r in train+hold):
        return {'module':'P4_O04','state':'INDETERMINATE','reason':'one or more measurements lack independent flat-field correspondence provenance',
                'decision':'NO_AI_ORIGIN_CONCLUSION'}
    for r in train+hold:
        if not (0<=r[1][0]<dims[0] and 0<=r[1][1]<dims[1]):
            raise VignettingError('measurement outside calibrated image')
    mode=data.get('calibration_mode','fit_radial')
    try:
        p,diagnostics=_estimate(train,K,mode)
    except (VignettingError,ValueError) as e:
        return {'module':'P4_O04','state':'INDETERMINATE','reason':str(e),'decision':'NO_AI_ORIGIN_CONCLUSION'}
    logscale,a2,a4,cx,cy=map(float,p)
    xy,obs,ref,sigma=_array(hold)
    expected=predict_irradiance(xy,K,ref,logscale,a2,a4,(cx,cy))
    # Parameter uncertainty from training fit (delta method on log intensity).
    position=normalized_coordinates(xy,K)
    r2=np.sum((position-(cx,cy))**2,axis=1);r02=cx*cx+cy*cy
    grad=np.column_stack((np.ones(len(r2)),r2-r02,r2*r2-r02*r02,
                          a2*(-2*(position[:,0]-cx)-2*cx)+a4*(-4*r2*(position[:,0]-cx)-4*r02*cx),
                          a2*(-2*(position[:,1]-cy)-2*cy)+a4*(-4*r2*(position[:,1]-cy)-4*r02*cy)))
    cov=np.asarray(diagnostics['parameter_covariance'])
    pred_log_variance=np.maximum(np.einsum('ni,ij,nj->n',grad,cov,grad),0.)
    effective_sigma=np.sqrt(sigma*sigma+(expected*np.sqrt(pred_log_variance))**2)
    standardized=(obs-expected)/effective_sigma
    results=[]
    for record,pred,z in zip(hold,expected,standardized):
        id_,coord,val,radiance,unc,_=record
        bad=abs(z)>config.sigma_threshold
        results.append({'id':id_,'xy_px':coord.tolist(),'observed_linear':val,
                        'predicted_linear':float(pred),'absolute_residual_linear':abs(float(val-pred)),
                        'standardized_residual':float(z),'measurement_sigma_linear':unc,'combined_model_and_measurement_sigma_linear':float(effective_sigma[len(results)]),
                        'state':'INCONSISTENT_UNDER_ASSUMPTIONS' if bad else 'CONSISTENT'})
    # The cos4/radial model can overfit if the optical center is unidentifiable;
    # do not let low holdout residuals conceal physically implausible gain fields.
    yy,xx=np.mgrid[0:dims[1]:complex(0,17),0:dims[0]:complex(0,23)]
    sample_positions=np.column_stack([xx.ravel(),yy.ravel()]);g=relative_illumination(sample_positions,K,a2,a4,(cx,cy))
    max_inverse=float(1/np.min(g))
    min_gain=float(np.min(g)); max_gain=float(np.max(g))
    if min_gain<=0 or max_inverse>config.max_inverse_gain or max_gain>1.2:
        state='INDETERMINATE';reason='extreme or nonphysical relative gain: correction/claim unsafe'
    elif any(q['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for q in results):
        state='INCONSISTENT_UNDER_ASSUMPTIONS';reason='held-out linear flat-field measurements exceed declared uncertainty'
    else:state='CONSISTENT';reason='independent flat-field holdouts agree under calibrated conditional model'
    errors=(obs-expected)
    radii=np.linspace(0.,max(0.,(dims[0]-1-K[0,2])/K[0,0]),41)
    profile_uv=np.column_stack((K[0,2]+K[0,0]*radii,np.full_like(radii,K[1,2])))
    profile_gain=relative_illumination(profile_uv,K,a2,a4,(cx,cy))
    profile_cos4=cos4_gain(profile_uv,K)
    radial_profile=[{'normalized_image_radius':float(radius),'cos4_only':float(g0),
                     'calibrated_relative_illumination':float(g)}
                    for radius,g0,g in zip(radii,profile_cos4,profile_gain)]
    return {'module':'P4_O04','state':state,'reason':reason,'calibration_mode':mode,
            'parameters':{'K':K.tolist(),'log_on_axis_scale':logscale,'on_axis_scale':float(np.exp(logscale)),
                          'radial_log_a2':a2,'radial_log_a4':a4,
                          'radial_center_offset_normalized_xy':[cx,cy]},
            'train_count':len(train),'holdout_count':len(hold),
            'holdout_linear_rmse':float(np.sqrt(np.mean(errors**2))),
            'holdout_standardized_rmse':float(np.sqrt(np.mean(standardized**2))),
            'inconsistent_count':sum(r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' for r in results),
            'max_inverse_gain_sampled':max_inverse,'sampled_relative_gain_range':[min_gain,max_gain],
            'diagnostics':diagnostics,'holdout_results':results,
            'positive_x_radial_profile':radial_profile,
            'assumptions':['radiometrically linear dark-corrected unclipped pixels','independently known flat-field irradiance',
                           'same exposure/gain between flat-field regions','known K and undistorted pixel coordinates',
                           'idealized cos^4 chief-ray geometry plus a conditional radial residual'],
            'limitations':['cannot prove AI-image origin','true scene texture or lighting variation invalidates flat-field assumption',
                           'cos^4 is not universal to real wide-angle, telecentric or computational cameras',
                           'mechanical clipping, color-channel microlenses, white balance and ISP are outside the model',
                           'holdout regions must be physically independent of training regions'],
            'decision':'NO_AI_ORIGIN_CONCLUSION'}


def run_vignetting_manifest(input_path:Path,out:Path,config=VignettingConfig()):
    data=json.loads(Path(input_path).read_text(encoding='utf-8'))
    report=analyze_vignetting_manifest(data,config)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'p4_o04_report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report


def sample_linear_regions(npy_path,regions_path,out_path):
    """Extract independent non-overlapping rectangular ROIs from linear sensor field.

    Does NOT label a scene as uniform: requires independent target reference per region.
    """
    image=np.load(npy_path,allow_pickle=False)
    if image.ndim!=2 or not np.isfinite(image).all() or np.any(image<0):
        raise VignettingError('npy must be nonnegative finite 2D linear flat-field')
    data=json.loads(Path(regions_path).read_text(encoding='utf-8'))
    W,H=image.shape[1],image.shape[0]
    rectangles=[];result=[]
    for item in data.get('regions',[]):
        x,y,w,h=item['xywh']
        if any(not isinstance(v,int) for v in (x,y,w,h)) or w<3 or h<3 or x<0 or y<0 or x+w>W or y+h>H:
            raise VignettingError('invalid ROI')
        for X,Y,WW,HH in rectangles:
            if x<X+WW and x+w>X and y<Y+HH and y+h>Y:
                raise VignettingError('overlapping train/holdout regions prohibited')
        rectangles.append((x,y,w,h))
        block=image[y:y+h,x:x+w]
        if np.any(block<=0) or np.any(block>=1):
            raise VignettingError('dark-clipped, saturated or zero-valued linear ROI')
        obs=float(np.median(block))
        sample=dict(id=item['id'],role=item['role'],xy_px=[x+(w-1)/2,y+(h-1)/2],
                    observed_linear=obs,reference_linear=item['reference_linear'],
                    sigma_linear=item['sigma_linear'],measurement_provenance=item['measurement_provenance'])
        result.append(sample)
    manifest={key:val for key,val in data.items() if key!='regions'}
    manifest.update(image_size_wh=[W,H],samples=result)
    path=Path(out_path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8')
    return manifest


def correct_linear_field(image,K, a2,a4,center_xy=(0.,0.),max_inverse_gain=8.):
    image=np.asarray(image,dtype=float)
    if image.ndim!=2 or not np.isfinite(image).all() or np.any(image<0):
        raise VignettingError('correction input must be a finite nonnegative 2D linear image')
    h,w=image.shape
    yy,xx=np.indices((h,w),dtype=float)
    gain=relative_illumination(np.stack((xx,yy),axis=-1),K,a2,a4,center_xy)
    if np.min(gain)<=0 or np.max(1/gain)>max_inverse_gain:
        raise VignettingError('excessive amplification: refusing unsafe correction')
    return image/gain
