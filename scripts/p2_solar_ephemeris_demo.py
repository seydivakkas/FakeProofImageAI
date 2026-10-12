"""Reproducible NOAA solar claim comparisons using ONLY synthetic 3D scenes."""
from __future__ import annotations
import json
from pathlib import Path
import argparse
import cv2
from aiforensics.solar_synthetic import synthetic_solar_scene
from aiforensics.solar_geometry import run_solar_manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('outputs/p2_s04_ephemeris_demo'))
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    claim={'latitude_deg':41.,'longitude_deg':29.,'timestamp_utc':'2025-06-21T09:00:00Z'}
    manifest,img,truth=synthetic_solar_scene(n=21,noise_px=.15,wrong_pairs=3,solar_claim=claim)
    path=args.out/'fixture_with_utc_claim.json';path.write_text(json.dumps(manifest,indent=2,allow_nan=False))
    image=args.out/'fixture.png';cv2.imwrite(str(image),img)
    result=run_solar_manifest(path,args.out/'correct_claim',image)
    mismatch=json.loads(json.dumps(manifest));mismatch['solar_claim']['timestamp_utc']='2025-06-21T06:00:00Z'
    path2=args.out/'fixture_with_wrong_time.json';path2.write_text(json.dumps(mismatch,indent=2,allow_nan=False))
    wrong=run_solar_manifest(path2,args.out/'wrong_claim',image)
    summary={'known_true_sun':truth,'correct_claim_comparison':result['ephemeris_comparison'],
             'wrong_time_claim_comparison':wrong['ephemeris_comparison'],
             'decision':'NO_AI_ORIGIN_CONCLUSION','validation':'SYNTHETIC_ONLY'}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
