"""Sample annotated 1D edge transects from an explicitly calibrated LINEAR .npy image.

No EXIF/gamma guesses, no automatic boundary detections; users provide transects
perpendicular to the shadow boundary and an independently calibrated linear array.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from .penumbra import PenumbraError


def extract_edge_profiles_from_array(image:np.ndarray, transect_manifest:dict) -> dict:
    if transect_manifest.get('schema')!='P2_S05_TRANSECTS_V1':
        raise PenumbraError('unexpected transect schema')
    if transect_manifest.get('radiometric_space')!='LINEAR_RELATIVE_IRRADIANCE':
        raise PenumbraError('image must be independently LINEAR_RELATIVE_IRRADIANCE')
    img=np.asarray(image)
    if img.ndim==3 and img.shape[2]==3:
        img=np.sum(img.astype(float)*np.array([.2126,.7152,.0722]),axis=2)
    if img.ndim!=2 or not np.issubdtype(img.dtype,np.number):
        raise PenumbraError('linear .npy must be HxW or HxWx3 array')
    img=img.astype(float)
    if img.shape[0]<10 or img.shape[1]<10 or not np.all(np.isfinite(img)) or np.any((img<0)|(img>1)):
        raise PenumbraError('invalid finite linear image values/dimensions')
    transects=transect_manifest.get('transects')
    if not isinstance(transects,list) or len(transects)<1 or len(transects)>200:
        raise PenumbraError('transects must have 1..200 items')
    out=[]
    for item in transects:
        if not isinstance(item,dict):
            raise PenumbraError('transect must be a dict')
        a=np.asarray(item.get('start_xy'),dtype=float)
        b=np.asarray(item.get('end_xy'),dtype=float)
        if a.shape!=(2,) or b.shape!=(2,) or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
            raise PenumbraError('start_xy/end_xy must be finite two-dimensional points')
        count=item.get('sample_count',161)
        if not isinstance(count,int) or not 35<=count<=4096:
            raise PenumbraError('sample_count must be int 35..4096')
        if not (np.all(a>=0) and np.all(b>=0) and a[0]<img.shape[1]-1 and b[0]<img.shape[1]-1
                and a[1]<img.shape[0]-1 and b[1]<img.shape[0]-1):
            raise PenumbraError('transect points must lie strictly within image')
        length=float(np.linalg.norm(b-a))
        if length<8:
            raise PenumbraError('transect is too short')
        alpha=np.linspace(0,1,count)
        xy=a[None,:]+alpha[:,None]*(b-a)[None,:]
        vals=cv2.remap(img.astype(np.float32),xy[:,0].astype(np.float32).reshape(1,-1),
                       xy[:,1].astype(np.float32).reshape(1,-1),cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT,borderValue=np.nan)
        if not np.all(np.isfinite(vals)):
            raise PenumbraError('transect samples fell outside image')
        edge={'id':item.get('id'), 'x_px':(alpha*length).tolist(),
              'linear_irradiance':np.clip(vals.ravel(),0,1).tolist(),
              'radiometric_space':'LINEAR_RELATIVE_IRRADIANCE',
              'source_shape':item.get('source_shape'),
              'light_side':item.get('light_side'),
              'transect_start_xy':a.tolist(),'transect_end_xy':b.tolist()}
        if 'metric_geometry' in item:
            edge['metric_geometry']=item['metric_geometry']
        out.append(edge)
    return {'schema':'P2_S05_EDGE_PROFILES_V1',
            'declared_common_source':transect_manifest.get('declared_common_source',False),
            'source_data':'annotated transects sampled from externally verified linear 2D array',
            'edges':out}


def run_sample_transects(npy_path:Path,transect_manifest_path:Path,output_json:Path)->dict:
    if npy_path.suffix.lower() != '.npy':
        raise PenumbraError('only independently linearized .npy images supported')
    image=np.load(npy_path,allow_pickle=False)
    annot=json.loads(transect_manifest_path.read_text(encoding='utf-8'))
    report=extract_edge_profiles_from_array(image,annot)
    report['linear_image_sha256']=hashlib.sha256(npy_path.read_bytes()).hexdigest()
    report['transect_manifest_sha256']=hashlib.sha256(transect_manifest_path.read_bytes()).hexdigest()
    output_json.parent.mkdir(parents=True,exist_ok=True)
    output_json.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report
