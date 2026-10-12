"""Illustrative 2D plan diagram from synthetic known metric support points."""
from pathlib import Path
import argparse
import cv2
import numpy as np
from aiforensics.static_equilibrium_synthetic import synthetic_equilibrium_fixture
from aiforensics.static_equilibrium import evaluate_static_equilibrium


def create(path: Path):
    data,truth=synthetic_equilibrium_fixture()
    r=evaluate_static_equilibrium(data)
    lookup={item['id']:item for item in r['objects']}
    cases=['balanced','com_outside','no_provenance']
    canvas=np.full((680,1140,3),(35,40,46),dtype=np.uint8)
    scale=180
    for i,oid in enumerate(cases):
        orig=(190+i*380,345)
        ob=next(item for item in data['objects'] if item['id']==oid)
        half=0.5
        quad=np.array([[orig[0]+int(x*scale),orig[1]-int(y*scale)] for x,y in
                       [(-half,-half),(half,-half),(half,half),(-half,half)]],dtype=np.int32)
        cv2.fillConvexPoly(canvas,quad,(65,75,85))
        cv2.polylines(canvas,[quad],True,(220,200,160),2,cv2.LINE_AA)
        for contact in ob['contacts']:
            p=contact['point_world_xyz']
            cv2.circle(canvas,(orig[0]+int(p[0]*scale),orig[1]-int(p[1]*scale)),5,(220,225,230),-1,cv2.LINE_AA)
        c=ob['center_of_mass_world_xyz'];pos=(orig[0]+int(c[0]*scale),orig[1]-int(c[1]*scale))
        state=lookup[oid]['state']
        color={'CONSISTENT':(105,230,105),'INCONSISTENT_UNDER_ASSUMPTIONS':(45,170,245),
               'INDETERMINATE':(50,220,230)}[state]
        if abs(c[0])>.75:
            cv2.arrowedLine(canvas,(orig[0]+95,orig[1]),(orig[0]+146,orig[1]),color,2,cv2.LINE_AA)
            cv2.putText(canvas,'COM x=1.8m ->',(orig[0]-90,465),cv2.FONT_HERSHEY_SIMPLEX,.48,color,1,cv2.LINE_AA)
        else:
            cv2.drawMarker(canvas,pos,color,cv2.MARKER_CROSS,24,3)
        cv2.putText(canvas,oid.replace('_',' ').upper(),(orig[0]-150,100),cv2.FONT_HERSHEY_SIMPLEX,.66,(235,240,245),2,cv2.LINE_AA)
        cv2.putText(canvas,lookup[oid]['state'].replace('_UNDER_ASSUMPTIONS',''),(orig[0]-150,530),cv2.FONT_HERSHEY_SIMPLEX,.52,(200,225,230),1,cv2.LINE_AA)
    cv2.putText(canvas,'P5-D03 SYNTHETIC METRIC TOP VIEW - NOT IMAGE-BASED MASS INFERENCE',(45,620),cv2.FONT_HERSHEY_SIMPLEX,.62,(220,230,230),2,cv2.LINE_AA)
    path.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(path),canvas):raise RuntimeError('failed to write diagram')
    return path

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('outputs/p5_d03_demo/p5_d03_support_topview.png'))
    args=parser.parse_args();print(create(args.out))
