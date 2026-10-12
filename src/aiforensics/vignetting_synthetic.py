"""Controlled synthetic radiometrically linear flat field; not camera validation."""
from __future__ import annotations
import numpy as np
import cv2
from .vignetting import relative_illumination, analyze_vignetting_manifest, correct_linear_field


def synthetic_vignetting_fixture(seed=1801,mode='fit_radial',corrupt=3,noise_sigma=.0015):
    rng=np.random.default_rng(seed)
    W,H=1280,800
    K=[[850.,0.,629.],[0.,840.,398.],[0.,0.,1.]]
    a2,a4=(-.57,-.23)
    cc=(.045,-.034) if mode=='fit_radial_and_center' else (0.,0.)
    coords=[]
    # Well-spaced pixel neighborhoods: enough radial and angular diversity.
    for j,y in enumerate(np.linspace(28,H-29,10)):
        for i,x in enumerate(np.linspace(28,W-29,14)):
            coords.append((float(x),float(y),j,i))
    rows=[];bad=[]
    hold_ids=[]
    for idx,(x,y,j,i) in enumerate(coords):
        hold=(i+2*j)%4==0
        ident=f'grid_{j:02d}_{i:02d}'
        if hold:hold_ids.append(ident)
        expected=float(.80*relative_illumination([x,y],K,a2,a4,cc))
        value=float(expected+rng.normal(0,noise_sigma))
        rows.append({'id':ident,'xy_px':[x,y], 'role':'holdout' if hold else 'train',
                     'observed_linear':value,'reference_linear':1.,'sigma_linear':.0045,
                     'measurement_provenance':'synthetic_known_flat_field'})
    if corrupt>len(hold_ids):raise ValueError('too many corruptions')
    bad=list(rng.choice(hold_ids,size=corrupt,replace=False))
    for record in rows:
        if record['id'] in bad:record['observed_linear']*=.80
    manifest={'module':'P4_O04','image_size_wh':[W,H],'K':K,
              'calibration_mode':mode,'pixel_coordinate_domain':'undistorted_pinhole',
              'photometric_provenance':'SYNTHETIC_LINEAR_DARK_CORRECTED_FLAT_FIELD',
              'samples':rows}
    return manifest,{'a2':a2,'a4':a4,'center_xy':list(cc), 'scale':.8,'corrupted_ids':bad}


def render_vignetting_demo(data, report):
    W,H=data['image_size_wh'];K=np.asarray(data['K'],float)
    y,x=np.indices((H,W),float)
    gain=relative_illumination(np.stack((x,y),axis=-1),K,-.57,-.23,
                                (.045,-.034) if data['calibration_mode']=='fit_radial_and_center' else (0.,0.))
    # Independent synthetic texture; it is known uniform for analysis.
    base=np.asarray(.82*gain,dtype=np.float32)
    p=report.get('parameters',{})
    if p:
        corrected=correct_linear_field(base,K,p['radial_log_a2'],p['radial_log_a4'],p['radial_center_offset_normalized_xy'])
    else:corrected=base
    orig=cv2.cvtColor(np.uint8(np.clip(base*255,0,255)),cv2.COLOR_GRAY2BGR)
    fix=cv2.cvtColor(np.uint8(np.clip(corrected*255,0,255)),cv2.COLOR_GRAY2BGR)
    for im,label in ((orig,'SYNTHETIC LINEAR FLAT-FIELD : VIGNETTED BRIGHTNESS'),
                     (fix,'CALIBRATED RELATIVE ILLUMINATION : CORRECTED')):
        cv2.rectangle(im,(6,8),(850,43),(24,35,48),-1)
        cv2.putText(im,label,(19,34),cv2.FONT_HERSHEY_SIMPLEX,.67,(255,255,255),2,cv2.LINE_AA)
    combined=np.concatenate((orig,fix),axis=1)
    return combined


def render_vignetting_radial_profile(report):
    """Simple static visualization of cos4 versus fitted radial photometry."""
    width,height=1050,590
    canvas=np.full((height,width,3),(26,32,39),dtype=np.uint8)
    records=report.get('positive_x_radial_profile',[])
    if not records:return canvas
    origin=(100,470);right=950;top=85
    max_r=max(p['normalized_image_radius'] for p in records)
    def xy(radius,gain):
        return (int(origin[0]+(right-origin[0])*radius/max_r),
                int(origin[1]-(origin[1]-top)*gain/1.04))
    for yyval in np.arange(0.,1.01,.2):
        cv2.line(canvas,xy(0,yyval),xy(max_r,yyval),(65,70,75),1)
        cv2.putText(canvas,f'{yyval:.1f}',(40,xy(0,yyval)[1]+7),cv2.FONT_HERSHEY_SIMPLEX,.58,(220,220,220),1)
    cv2.line(canvas,xy(0,0),xy(max_r,0),(230,230,230),2)
    cv2.line(canvas,xy(0,0),xy(0,1),(230,230,230),2)
    for key,color in [('cos4_only',(242,180,60)),('calibrated_relative_illumination',(95,225,125))]:
        pts=[xy(v['normalized_image_radius'],v[key]) for v in records]
        cv2.polylines(canvas,[np.array(pts,np.int32)],False,color,4,cv2.LINE_AA)
    cv2.putText(canvas,'P4-O04  |  CONTROLLED SYNTHETIC RELATIVE ILLUMINATION',(85,49),cv2.FONT_HERSHEY_SIMPLEX,.79,(235,240,245),2,cv2.LINE_AA)
    cv2.putText(canvas,'cos^4 geometric reference',(180,529),cv2.FONT_HERSHEY_SIMPLEX,.68,(242,180,60),2,cv2.LINE_AA)
    cv2.putText(canvas,'cos^4 + calibrated radial correction',(555,529),cv2.FONT_HERSHEY_SIMPLEX,.62,(95,225,125),2,cv2.LINE_AA)
    cv2.putText(canvas,'normalized image-plane radius along +x',(285,570),cv2.FONT_HERSHEY_SIMPLEX,.68,(230,230,230),1,cv2.LINE_AA)
    return canvas
