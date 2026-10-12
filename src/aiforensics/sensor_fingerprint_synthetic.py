"""Independent-reference/query fixed-pattern camera simulation (synthetic only)."""
from __future__ import annotations
from pathlib import Path
import json
import cv2
import numpy as np
from .sensor_noise import SensorParameters


def sensor_pattern(seed:int,shape:tuple[int,int]=(32,32)) -> tuple[np.ndarray,np.ndarray]:
    rng=np.random.default_rng(seed)
    prnu=rng.normal(0,.035,size=shape)
    dsnu=rng.normal(0,8.,size=shape)
    return prnu-prnu.mean(), dsnu-dsnu.mean()


def synthetic_raw_stacks(pattern:tuple[np.ndarray,np.ndarray], *, seed:int,
                         frames:int=20, photoelectrons:float=1800.,
                         sensor:SensorParameters|None=None)->tuple[np.ndarray,np.ndarray]:
    s=sensor or SensorParameters(gain_e_per_adu=2.,read_noise_e=2.2,
              dark_current_e_per_s=50.,black_level_adu=128.,
              full_well_e=20000.,adc_max_adu=16383)
    rng=np.random.default_rng(seed)
    prnu,dsnu=pattern
    if np.any(50.+dsnu<0):raise ValueError('dark current must stay nonnegative')
    dark_e=50.+dsnu
    flat_e=dark_e+photoelectrons*(1.+prnu)
    dark=rng.poisson(dark_e,size=(frames,*dark_e.shape))+rng.normal(0,s.read_noise_e,size=(frames,*dark_e.shape))
    flat=rng.poisson(flat_e,size=(frames,*flat_e.shape))+rng.normal(0,s.read_noise_e,size=(frames,*flat_e.shape))
    code=lambda x:np.rint(np.clip(x/s.gain_e_per_adu+s.black_level_adu,0,s.adc_max_adu)).astype(np.uint16)
    return code(dark),code(flat)


def write_synthetic_fingerprint_fixture(out:Path, *, seed:int=4202, shape:tuple[int,int]=(32,32),
                                        frames:int=20)->tuple[Path,dict]:
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    p_a=sensor_pattern(seed,shape);p_b=sensor_pattern(seed+77,shape)
    inputs=[('reference',p_a,seed+1),('same_sensor',p_a,seed+2),
            ('wrong_sensor',p_b,seed+3)]
    for name,pattern,run_seed in inputs:
        d,f=synthetic_raw_stacks(pattern,seed=run_seed,frames=frames)
        np.savez_compressed(out/f'{name}.npz',dark=d,flat=f)
    sensor=SensorParameters(gain_e_per_adu=2.,read_noise_e=2.2,
              dark_current_e_per_s=50.,black_level_adu=128.,
              full_well_e=20000.,adc_max_adu=16383)
    manifest={'version':'P7_S02_v0.25.0','input_domain':'linear_native_raw_adu',
              'sensor':sensor.__dict__,'reference_npz':'reference.npz',
              'queries':[{'id':'same_sensor','npz':'same_sensor.npz'},
                         {'id':'wrong_sensor','npz':'wrong_sensor.npz'}],
              'provenance':'synthetic_ground_truth',
              'uniform_flat_field':True,'matched_exposure_and_gain':True,
              'matched_temperature':True,'spatial_alignment_verified':True,
              'independent_capture_stacks':True,'unprocessed_native_raw':True}
    p=out/'p7_s02_fixture.json'
    p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return p,{'expected_states':{'same_sensor':'CONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS',
                                 'wrong_sensor':'INCONSISTENT_UNDER_SYNTHETIC_ASSUMPTIONS'},
              'pattern_prnu_std_truth':float(p_a[0].std(ddof=1)),
              'pattern_dsnu_std_e_truth':float(p_a[1].std(ddof=1)),
              'reference_and_query_frame_sources':'separately seeded independent RAW stacks',
              'seed':seed}


def render_fingerprint_summary(manifest_path:Path,report:dict,out_path:Path)->Path:
    """Visualizes measured maps and reference/query correlations, without a detector claim."""
    with np.load(manifest_path.parent/'reference.npz',allow_pickle=False) as z:
        d=z['dark'].mean(axis=0);f=z['flat'].mean(axis=0)
    illum=f-d;prnu=illum/illum.mean()-1;dsnu=d-d.mean()
    panels=[]
    for arr,title in ((prnu,'PRNU reference'),(dsnu,'DSNU reference')):
        span=max(3*np.std(arr),1e-9)
        img=np.clip((arr/span*.45+.5)*255,0,255).astype(np.uint8)
        img=cv2.applyColorMap(cv2.resize(img,(320,320),interpolation=cv2.INTER_NEAREST),cv2.COLORMAP_TURBO)
        cv2.putText(img,title,(12,26),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2,cv2.LINE_AA)
        panels.append(img)
    canvas=np.full((420,820,3),32,dtype=np.uint8)
    canvas[40:360,50:370]=panels[0];canvas[40:360,450:770]=panels[1]
    for i,q in enumerate(report['queries']):
        msg=f"{q['id']}: PRNU r={q.get('prnu_pearson_r',0):.3f}, DSNU r={q.get('dsnu_pearson_r',0):.3f}"
        cv2.putText(canvas,msg,(30,382+23*i),cv2.FONT_HERSHEY_SIMPLEX,.5,(240,240,240),1,cv2.LINE_AA)
    out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(out_path),canvas):raise OSError('cannot write fingerprint plot')
    return out_path
