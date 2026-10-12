"""P7-S01 reproducible, controlled sensor measurements (NOT real photographs)."""
from __future__ import annotations
import numpy as np
import cv2
from .sensor_noise import SensorParameters, sample_sensor, summarize_codes


def synthetic_sensor_fixture(*, seed=3101, mode='known_parameters', corrupted=3, n_samples=4096):
    if mode not in ('known_parameters','fit_train_parameters'):
        raise ValueError('invalid mode')
    truth=SensorParameters(gain_e_per_adu=2.0,read_noise_e=4.5,
        dark_current_e_per_s=1.65,black_level_adu=128.,full_well_e=25000.,adc_max_adu=16383)
    rng=np.random.default_rng(seed)
    train_conditions=[(0.,0.),(0.,0.),(0.,0.),(0.,.5),(0.,1.),(0.,2.),
                      (60.,.5),(180.,.5),(380.,.6),(750.,.75),
                      (1500.,1.),(3100.,1.2),(4800.,1.5),(6200.,1.75)]
    hold_conditions=[(0.,0.),(0.,1.),(0.,2.),
                     (40.,.4),(90.,.5),(150.,.7),(240.,.6),(400.,.8),
                     (600.,.75),(800.,.9),(1100.,1.),(1450.,.8),
                     (1900.,.75),(2300.,.8),(2700.,1.),(3200.,1.1),
                     (3700.,1.2),(4200.,1.4),(4600.,1.5),(5100.,1.6),
                     (5500.,1.7),(5900.,1.85),(6300.,1.8),(6700.,1.9)]
    rows=[];states={}
    for role,conditions in [('train',train_conditions),('holdout',hold_conditions)]:
        for i,(photo,t) in enumerate(conditions):
            sid=f'{role}_{i:02d}'
            raw=sample_sensor(photo,t,truth,size=n_samples,seed=seed*100+i+(0 if role=='train' else 20000))
            stats=summarize_codes(raw,truth)
            if role=='holdout' and i>=len(conditions)-corrupted:
                # Deliberate model mismatch in independent summaries; never used to fit.
                if i%2:stats['observed_variance_adu2']*=1.55
                else:stats['observed_mean_adu']+=22.0
                states[sid]='INCONSISTENT_UNDER_ASSUMPTIONS'
            elif role=='holdout':
                states[sid]='CONSISTENT'
            rows.append({'id':sid,'role':role,'kind':'dark' if photo==0 else 'flat',
                         'expected_photoelectrons':photo,'exposure_s':t,
                         'photoelectron_provenance':'synthetic_ground_truth',
                         'sample_provenance':'synthetic_ground_truth',**stats})
    manifest={'version':'P7_S01_v0.24.0','sensor':{
              'gain_e_per_adu':truth.gain_e_per_adu if mode=='known_parameters' else 2.4,
              'read_noise_e':truth.read_noise_e if mode=='known_parameters' else 7.,
              'dark_current_e_per_s':truth.dark_current_e_per_s if mode=='known_parameters' else 3.2,
              'black_level_adu':truth.black_level_adu,
              'full_well_e':truth.full_well_e,'adc_max_adu':truth.adc_max_adu},
              'sensor_provenance':'synthetic_ground_truth' if mode=='known_parameters' else 'train_only_estimation',
              'calibration_mode':mode,'input_domain':'linear_raw_adu',
              'stable_temperature':True,'temporally_independent':True,
              'uniform_flat_field':True,'fixed_gain_mode':True,
              'prnu_or_fpn_controlled':True,'measurements':rows}
    return manifest,{'true_sensor':truth.__dict__,'expected_states':states,
                     'seed':seed,'mode':mode}


def render_sensor_demo(manifest, report, out_path):
    """Draw the photon transfer mean/variance plot using the actual fixture/report."""
    H,W=680,1050
    canvas=np.full((H,W,3),(25,32,39),dtype=np.uint8)
    left,top,width,height=95,100,860,450
    cv2.rectangle(canvas,(left,top),(left+width,top+height),(95,102,110),1)
    cv2.putText(canvas,'P7-S01 - SENSOR PHOTON TRANSFER (SYNTHETIC)',(48,40),
                cv2.FONT_HERSHEY_SIMPLEX,.82,(230,235,240),2,cv2.LINE_AA)
    rows={r['id']:r for r in manifest['measurements']}
    points=report['observations']
    xval=[r['observed_mean_adu']-manifest['sensor']['black_level_adu'] for r in rows.values()]
    yval=[r['observed_variance_adu2'] for r in rows.values()]
    xm=max(1.,max(xval)*1.15);ym=max(1.,max(yval)*1.3)
    def xy(x,y):
        return (int(left+max(0.,x)/xm*width),int(top+height-max(0.,y)/ym*height))
    for r in manifest['measurements']:
        if r['role']!='train':continue
        cv2.circle(canvas,xy(r['observed_mean_adu']-128,r['observed_variance_adu2']),4,(215,195,90),-1,cv2.LINE_AA)
    for r in points:
        original=rows[r['id']]
        color=(85,205,115) if r['state']=='CONSISTENT' else (50,130,235) if r['state']=='INCONSISTENT_UNDER_ASSUMPTIONS' else (50,205,230)
        cv2.circle(canvas,xy(original['observed_mean_adu']-128,original['observed_variance_adu2']),6,color,-1,cv2.LINE_AA)
        cv2.circle(canvas,xy(original['observed_mean_adu']-128,original['observed_variance_adu2']),8,(220,220,220),1,cv2.LINE_AA)
    s=report['parameters'];g=s['gain_e_per_adu'];read=s['read_noise_e'];dark=s['dark_current_e_per_s']
    # Illustrative t=1s photon-transfer family; actual exposure times vary.
    pts=[]
    for photo in np.linspace(0,6900,90):
        x=(photo+dark)/g
        y=(photo+dark+read*read)/g**2+1/12
        pts.append(xy(x,y))
    cv2.polylines(canvas,[np.array(pts,np.int32)],False,(150,200,245),2,cv2.LINE_AA)
    cv2.putText(canvas,'ADU above black level  ->',(left+250,H-53),cv2.FONT_HERSHEY_SIMPLEX,.64,(226,229,233),1,cv2.LINE_AA)
    cv2.putText(canvas,'Temporal variance (ADU^2)',(left,top-18),cv2.FONT_HERSHEY_SIMPLEX,.62,(226,229,233),1,cv2.LINE_AA)
    cv2.putText(canvas,'yellow=train  green=consistent  orange=corrupted  cyan=uncertain',
                (left,H-18),cv2.FONT_HERSHEY_SIMPLEX,.5,(210,210,212),1,cv2.LINE_AA)
    out_path.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(out_path),canvas):raise OSError('cannot write sensor plot')
    return out_path
