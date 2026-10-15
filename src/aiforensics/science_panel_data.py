"""P9-I09: display-only, source-backed G01/G02/G04 and E03 residual views."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re

REPORTS={"P1-G01":"g01_report.json","P1-G02":"g01_g02_report.json","P1-G04":"g04_homography_report.json"}
RUN_RE=re.compile(r"[A-Za-z0-9_-]{1,96}\Z")

class ScientificViewError(ValueError):pass

def number(x):return type(x) in (float,int) and math.isfinite(x)

def no_constant(x):raise ScientificViewError("nonfinite constant "+x)

def recorded_calibrations(project):
    """Last *recorded* successful module report; never assume camera identity."""
    results={}
    root=(project.root/"runs").resolve()
    for run in project.data.get("runs",[]):
        if not isinstance(run,dict) or run.get("state")!="SUCCEEDED":continue
        mid=run.get("module_id")
        rid=run.get("run_id")
        if mid not in REPORTS or not isinstance(rid,str) or not RUN_RE.fullmatch(rid):continue
        folder=root/rid
        path=folder/REPORTS[mid]
        if folder.is_symlink() or path.is_symlink() or not path.is_file():continue
        if folder.resolve().parent!=root or path.resolve().parent!=folder.resolve():continue
        if not 0<path.stat().st_size<=16*1024*1024:continue
        raw=path.read_bytes()
        try:d=json.loads(raw,parse_constant=no_constant)
        except (ValueError,UnicodeError):continue
        if not isinstance(d,dict) or d.get("decision")!="NO_AI_ORIGIN_CONCLUSION":continue
        result={"run_id":rid,"file":REPORTS[mid],"sha256":hashlib.sha256(raw).hexdigest(),
                "state":d.get("state","INDETERMINATE"),"image_sha256":d.get("image_sha256")
                if isinstance(d.get("image_sha256"),str) and re.fullmatch(r"[a-f0-9]{64}",d["image_sha256"]) else None}
        if mid in ("P1-G01","P1-G02"):
            vps=d.get("vp_models",[]) if mid=="P1-G01" else d.get("g01_models",[])
            result["vps"]=[]
            if isinstance(vps,list):
                for item in vps[:64]:
                    if not isinstance(item,dict):continue
                    point=item.get("vp_xy_px")
                    if isinstance(point,list) and len(point)==2 and all(number(x) for x in point):
                        result["vps"].append(point)
            if mid=="P1-G02":
                cal=d.get("g02_calibration",{})
                if not isinstance(cal,dict):cal={}
                k=cal.get("K")
                result["K"]=k if isinstance(k,list) and len(k)==3 and all(
                    isinstance(row,list) and len(row)==3 and all(number(v) for v in row) for row in k) else None
                result["assumptions"]=cal.get("assumptions",[])
                result["calibration_state"]=cal.get("state","INDETERMINATE")
        else:
            arr=d.get("holdout_reprojection_errors_px",[])
            result["errors_px"]=arr if isinstance(arr,list) and len(arr)<=100000 and all(
                number(x) and x>=0 for x in arr) else []
            for name in ("train_reprojection_rmse_px","holdout_reprojection_rmse_px","holdout_threshold_px"):
                val=d.get(name)
                result[name]=val if number(val) and val>=0 else None
        results[mid]=result
    return results

def residual_groups(report):
    """Never mix units; do not synthesize CI when missing."""
    if not isinstance(report,dict) or report.get("schema_version")!="p8.e03.v1" or \
       report.get("decision")!="NO_AI_ORIGIN_CONCLUSION" or not isinstance(report.get("findings"),list):
        raise ScientificViewError("E03 source report required")
    groups={}
    for f in report["findings"][:2000]:
        if not isinstance(f,dict):continue
        m=f.get("measurement") or {}
        if not isinstance(m,dict):continue
        val,unit=m.get("signed_residual"),m.get("unit")
        if not number(val) or not isinstance(unit,str) or not 0<len(unit)<48:continue
        ci=m.get("confidence_interval_95_for_residual")
        ci=ci if isinstance(ci,list) and len(ci)==2 and all(number(x) for x in ci) and ci[0]<=ci[1] else None
        u=f.get("uncertainty") or {}
        sd=u.get("residual_std") if isinstance(u,dict) else None
        groups.setdefault(unit,[]).append({
            "record_id":str(f.get("record_id",""))[:128],"residual":val,
            "ci95":ci,"residual_std":sd if number(sd) and sd>0 else None,
            "state":(f.get("single_test") or {}).get("state","INDETERMINATE")})
    return groups

def valid_roi(image_wh,roi):
    if not isinstance(image_wh,(list,tuple)) or len(image_wh)!=2 or any(type(v)!=int or v<1 for v in image_wh):
        raise ScientificViewError("invalid image size")
    if not isinstance(roi,(tuple,list)) or len(roi)!=4 or not all(number(x) for x in roi):
        raise ScientificViewError("invalid ROI")
    x0,y0,x1,y1=roi
    if not (0<=x0<x1<=image_wh[0] and 0<=y0<y1<=image_wh[1]):
        raise ScientificViewError("ROI outside native pixels")
    return [float(v) for v in roi]
