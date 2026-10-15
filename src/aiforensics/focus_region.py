"""P9-I09: explicit user-drawn E03 image ROI. No inferred image location."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile

from .science_panel_data import ScientificViewError,valid_roi
from .review_workspace import read_bindings,read_report,_image_match

SCHEMA="fakeproof.focus.v1"

def _context(project,report_id,record_id,image_sha):
    path,_=_image_match(project,image_sha)
    report=read_report(project,report_id)
    if report.get("schema_version")!="p8.e03.v1" or not any(
        x.get("record_id")==record_id for x in report.get("findings",[])
        if isinstance(x,dict)):
        raise ScientificViewError("Recorded E03 finding required")
    if not any(x.get("report_id")==report_id and x.get("record_id")==record_id
               and x.get("image_sha256")==image_sha
               and x.get("link_type")=="user_asserted_not_verified"
               for x in read_bindings(project)):
        raise ScientificViewError("Explicit unverified finding/image link required")
    return path

def _file(project):return project.root/"review_focus.json"

def list_focus(project):
    path=_file(project)
    if not path.exists():return []
    if path.is_symlink() or path.stat().st_size>2*1024*1024:
        raise ScientificViewError("Unsafe focus file")
    def bad_constant(x):raise ScientificViewError("Nonfinite focus value")
    d=json.loads(path.read_text(encoding="utf-8"),parse_constant=bad_constant)
    if not isinstance(d,dict) or d.get("schema_version")!=SCHEMA or \
       d.get("decision")!="NO_AI_ORIGIN_CONCLUSION" or \
       not isinstance(d.get("items"),list) or len(d["items"])>5000:
        raise ScientificViewError("Invalid focus schema")
    return d["items"]

def get_focus(project,report_id,record_id,image_sha):
    path=_context(project,report_id,record_id,image_sha)
    from PIL import Image
    with Image.open(path) as im:wh=im.size
    for item in list_focus(project):
        if isinstance(item,dict) and (item.get("report_id"),item.get("record_id"),
            item.get("image_sha256"))==(report_id,record_id,image_sha) and \
            item.get("provenance")=="user_asserted_not_verified":
            valid_roi(wh,item.get("roi_xyxy_px"))
            return item
    return None

def save_focus(project,report_id,record_id,image_sha,roi):
    path=_context(project,report_id,record_id,image_sha)
    from PIL import Image
    with Image.open(path) as im:wh=im.size
    box=valid_roi(wh,roi)
    item={"report_id":report_id,"record_id":record_id,"image_sha256":image_sha,
          "roi_xyxy_px":box,"provenance":"user_asserted_not_verified"}
    existing=[x for x in list_focus(project) if not(isinstance(x,dict) and
        (x.get("report_id"),x.get("record_id"),x.get("image_sha256"))==
        (report_id,record_id,image_sha))]
    if len(existing)>=5000:raise ScientificViewError("Maximum focus records reached")
    fd,temp=tempfile.mkstemp(dir=project.root,prefix=".focus-",suffix=".tmp")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"schema_version":SCHEMA,"decision":"NO_AI_ORIGIN_CONCLUSION",
                       "items":existing+[item]},f,ensure_ascii=False,allow_nan=False,indent=2)
        os.replace(temp,_file(project))
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return item
