"""Optional external real-data acquisition (no redistribution in project bundle).

York Urban 102 calibrated photographs; this mirror includes imagery and a
GT horizon/zenith subset. It does NOT include independent reference K and
all the per-line Manhattan labels needed for complete G02 validation.
See the official site for original calibration annotations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

BASE='https://raw.githubusercontent.com/trocolit2/vanishing-point-detection/master/resource/datasets/yorkurban/'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--count',type=int,default=5)
    p.add_argument('--out',type=Path,default=Path('data/external/yorkurban'))
    args=p.parse_args()
    if not 1<=args.count<=102: p.error('--count must be 1..102')
    args.out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for i in range(args.count):
        name=f'{i:03d}.jpg';url=BASE+name
        with urlopen(url,timeout=35) as res: data=res.read(2_000_000)
        if len(data)>1_500_000 or not data.startswith(bytes.fromhex('ffd8')):
            raise ValueError(f'Invalid JPEG payload {name}')
        (args.out/name).write_bytes(data)
        manifest.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'url':url})
        print('saved',name)
    with urlopen(BASE+'gt_data.yml',timeout=35) as res: ground=res.read(200_000)
    (args.out/'gt_data.yml').write_bytes(ground)
    (args.out/'download_manifest.json').write_text(json.dumps({'source':'York Urban real photographic dataset mirror',
       'limitations':'Horizon and zenith subset does not supply independent K or full 3 group labels.',
       'images':manifest},indent=2),encoding='utf-8')
    print('Images downloaded; real G02 validation still requires original calibration and orthogonal labels.')

if __name__=='__main__':main()
