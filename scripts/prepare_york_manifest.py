"""Prepare G02 real-data manifests from *original* York Urban camera calibration.

Must be used with independently HUMAN-labeled 3 orthogonal line families.
Do NOT assign groups from K-derived ground-truth vanishing points: that
would leak the calibration reference into the test.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
import cv2
from scipy.io import loadmat


def prepare(image:Path, camera_parameters:Path, labels:Path, out:Path|None=None)->dict:
    from aiforensics.real_validation import RealValidationError
    image=image.resolve();out=(out or image.with_suffix('.g02_manifest.json')).resolve()
    if out.parent!=image.parent:
        raise RealValidationError('Manifest must be next to image for safe relative image resolution')
    if not image.is_file():raise FileNotFoundError(image)
    raw=cv2.imread(str(image),cv2.IMREAD_COLOR)
    if raw is None:raise RealValidationError('Image could not be decoded')
    mat=loadmat(camera_parameters)
    f=float(np.asarray(mat['focal']).reshape(-1)[0]);pixel_size=float(np.asarray(mat['pixelSize']).reshape(-1)[0]); pp=np.asarray(mat['pp'],float).reshape(-1)
    if not np.isfinite([f,pixel_size,*pp[:2]]).all() or f<=0 or pixel_size<=0 or len(pp)<2:raise RealValidationError('Invalid camera calibration')
    intr=f/pixel_size
    K=[[intr,0.,float(pp[0])],[0.,intr,float(pp[1])],[0.,0.,1.]]
    annotation=json.loads(labels.read_text(encoding='utf-8'))
    if annotation.get('group_label_provenance')!='human_independently_annotated':
        raise RealValidationError('Labels must be independently human annotated; K-derived labels leak ground truth')
    groups=annotation['orthogonal_groups']
    if len(groups)!=3:raise RealValidationError('Exactly three human-verified Manhattan line groups required')
    train=[];holdout=[]
    for i,g in enumerate(groups):
        segs=np.asarray(g,float)
        if segs.ndim!=2 or segs.shape[1]!=4 or len(segs)<6 or not np.isfinite(segs).all():
            raise RealValidationError(f'Group {i} needs at least six finite segments')
        # Deterministic disjoint split avoids posthoc choice of favorable lines.
        rng=np.random.default_rng(2026+i)
        order=rng.permutation(len(segs));num=max(3,int(len(segs)*.7))
        train.append(segs[order[:num]].tolist());holdout.append(segs[order[num:]].tolist())
    manifest={'image':image.name,'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
          'image_shape_hw':list(raw.shape[:2]),'capture_type':'real_camera',
          'known_intrinsics_K':K,'train_orthogonal_groups':train,
          'holdout_orthogonal_groups':holdout,
          'source':'York Urban Line Segment Database: original photographic capture',
          'capture_and_calibration_provenance':f'External original cameraParameters.mat: {camera_parameters.name}; groups annotated independently: {labels.name}',
          'label_provenance':'human_independently_annotated',
          'restrictions':['Any K-derived line labels invalidate independence.',
                          'Check camera distortion status before quantitative acceptance.']}
    out.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--camera-parameters',type=Path,required=True)
    p.add_argument('--labels',type=Path,required=True)
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    d=prepare(args.image,args.camera_parameters,args.labels,args.out)
    print(json.dumps({'created':str(args.out or args.image.with_suffix('.g02_manifest.json')),
                      'train_counts':[len(x) for x in d['train_orthogonal_groups']],
                      'holdout_counts':[len(x) for x in d['holdout_orthogonal_groups']],
                      'real_performance':'NOT_MEASURED_UNTIL_EXECUTING_G02'},indent=2))

if __name__=='__main__':main()
