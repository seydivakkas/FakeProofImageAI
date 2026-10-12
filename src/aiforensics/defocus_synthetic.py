"""Deterministic ground-truth thin-lens fixtures; not real imagery."""
from __future__ import annotations
import cv2
import numpy as np
from .defocus import ThinLens, circular_psf


def synthetic_defocus_fixture(seed=1402, *, fit_focus=False, corrupt=3, noise_px=.12):
    rng=np.random.default_rng(int(seed))
    lens=ThinLens(35.,5.6,4.0,2500.)
    depths=np.linspace(1100.,7400.,32)
    # Explicit training and independent holdouts for focus estimation.
    samples=[]
    for i,z in enumerate(depths):
        role='train' if i%2==0 else 'holdout'
        truth=lens.coc_px(z)
        bad=(role=='holdout' and i in (7,15,23,29)[:corrupt])
        samples.append({'id':f'patch_{i:02d}','role':role,'depth_mm':float(z),
                        'depth_sigma_mm':0.,
                        'observed_coc_px':max(0.,float(truth+rng.normal(0,noise_px)+(5.0 if bad else 0))),
                        'observed_sigma_px':max(.2,float(noise_px*2)),
                        'measurement_provenance':'calibrated_coc_diameter'})
    data={'schema_version':'p4-o02-v1','optics':{'focal_mm':lens.focal_mm,'f_number':lens.f_number,
          'pixel_pitch_um':lens.pixel_pitch_um,
          'focus_distance_mm':None if fit_focus else lens.focus_distance_mm},
          'acceptable_coc_px':2.,'samples':samples,
          'dataset':'synthetic thin-lens forward simulator; known ground truth; no camera photographs'}
    expected={'focus_distance_mm':2500.,'corrupted_ids':[r['id'] for r in samples if
         r['role']=='holdout' and int(r['id'][-2:]) in (7,15,23,29)[:corrupt]]}
    return data,expected


def render_defocus_comparison(lens=None):
    """Independent synthetic textures per depth; NOT compositing occluding 3D geometry."""
    if lens is None: lens=ThinLens(35.,5.6,4.,2500.)
    depth_set=[1250.,1800.,2500.,4000.,7000.]
    w,h=240,300
    img=np.zeros((h+75,w*len(depth_set),3),np.uint8)
    for i,z in enumerate(depth_set):
        tile=np.full((h,w,3),(44,47,51),np.uint8)
        for j in range(9,w,18):
            cv2.line(tile,(j,0),(j,h-1),(210,220,233),3,cv2.LINE_8)
        for j in range(10,h,24):
            cv2.line(tile,(0,j),(w-1,j),(190,200,210),2,cv2.LINE_8)
        cv2.circle(tile,(120,155),47,(100,200,255),-1,cv2.LINE_8)
        diameter=lens.coc_px(z)
        kernel=circular_psf(min(diameter,160.),max_kernel=201)
        smooth=cv2.filter2D(tile,-1,kernel.astype(np.float32),borderType=cv2.BORDER_REFLECT)
        img[75:75+h,i*w:(i+1)*w]=smooth
        cv2.putText(img,f'z={z/1000:.2f} m',(i*w+14,27),cv2.FONT_HERSHEY_SIMPLEX,.60,(235,235,235),2,cv2.LINE_AA)
        cv2.putText(img,f'CoC={diameter:.2f}px',(i*w+14,55),cv2.FONT_HERSHEY_SIMPLEX,.52,(200,220,220),1,cv2.LINE_AA)
    return img
