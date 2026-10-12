"""Designed grid fixture showing automatic pattern candidate detection."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from aiforensics.auto_patterns import analyze_auto_pattern_file,PatternConfig
from aiforensics.imaging import write_image

def main():
    out=ROOT/'outputs'/'g03_auto_demo';out.mkdir(parents=True,exist_ok=True)
    image=np.full((640,880,3),(32,38,43),np.uint8)
    for x in (180,440,700):cv2.line(image,(x,30),(x,600),(235,230,210),2,cv2.LINE_AA)
    for y in (100,170,240,310,380,450,520):cv2.line(image,(80,y),(780,y),(235,230,210),2,cv2.LINE_AA)
    p=out/'synthetic_repeated_grid.png';write_image(p,image)
    r=analyze_auto_pattern_file(p,out,PatternConfig(min_support_length_px=150,min_marks=5))
    print(json.dumps({'candidate_count':r['candidate_count'],'state':r['status'],
                      'first_marks':r['patterns'][0]['count'] if r['patterns'] else 0},indent=2))

if __name__=='__main__':main()
