"""P9-I09: generate genuine CLI synthetic G02/G04/E03 outputs, capture Tk UI.

All images/data are procedurally generated. NOT camera, AI-origin, or Windows
acceptance. Requires Xvfb or desktop display, Pillow and Tkinter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from PIL import Image,ImageDraw,ImageGrab

from aiforensics.desktop_app import DesktopApp
from aiforensics.desktop_core import Project
from aiforensics.integration_flow import run_evidence_chain,save_example
from aiforensics.review_workspace import bind_finding_to_image
from aiforensics.focus_region import save_focus


def synthetic_image(path):
    image=Image.new("RGB",(1280,720),(19,31,44))
    pen=ImageDraw.Draw(image)
    for k in range(8):
        pen.line((0,k*90,1279,k*90),fill=(36,61,80),width=2)
        pen.line((k*160,0,k*160,719),fill=(36,61,80),width=2)
    for x in range(100,1150,100):
        pen.line((x,660,640,320),fill=(54,144,177),width=2)
    pen.text((30,28),"SYNTHETIC GEOMETRY FIXTURE - NOT A PHOTOGRAPH",
             fill=(200,220,231))
    image.save(path)


def seed_project(workspace):
    from importlib.resources import files
    project=Project(workspace,"P9I09_SYNTHETIC")
    synthetic=project.root/"generated_grid.png"
    synthetic_image(synthetic)
    asset=project.import_image(synthetic)
    for module,template in (("P1-G02","P1_G02.json"),("P1-G04","P1_G04.json")):
        input_path=Path(str(files("aiforensics").joinpath("demo_forms",template)))
        result,_=project.run(module,input_path,timeout=240)
        if result["state"]!="SUCCEEDED":
            raise RuntimeError(module+" failed to generate synthetic panel data")
    audit=run_evidence_chain(project,save_example(project))
    report_id=audit["steps"][-1]["run_id"]+"/p8_e03_explainable_report.json"
    report=json.loads((project.root/"runs"/audit["steps"][-1]["run_id"]/
                       "p8_e03_explainable_report.json").read_text(encoding="utf-8"))
    record_id=report["findings"][0]["record_id"]
    bind_finding_to_image(project,report_id,record_id,asset["sha256"])
    save_focus(project,report_id,record_id,asset["sha256"],[180,145,680,520])
    return project,asset["sha256"],report_id,record_id


def capture(root,out,width,height):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    project,digest,report_id,record_id=seed_project(root)
    app=DesktopApp(workspace=root)
    app.project=project
    app.selected_asset_sha=digest
    app.project_tag.configure(text="Proje: "+project.name)
    app.project_choice.set(project.name)
    app.geometry(f"{width}x{height}+0+0")
    app.update()
    shots=[]
    try:
        for key,page in (("calibration","Kalibrasyon"),("measurements","Fiziksel Ölçümler"),
                         ("evidence","Kanıt İnceleme")):
            app.go(page)
            app.update()
            # Capture both top and the dynamically generated scientific panels.
            for label,position in (("top",0.),("scientific",1.)):
                app.page_canvas.yview_moveto(position)
                app.update_idletasks();app.update()
                x,y=app.winfo_rootx(),app.winfo_rooty()
                png=out/(key+"_"+label+".png")
                ImageGrab.grab(bbox=(x,y,x+app.winfo_width(),y+app.winfo_height())).save(png)
                shots.append(png)
        from aiforensics.focus_view_ui import FindingFocusWindow
        window=FindingFocusWindow(app,project,report_id,record_id,digest)
        window.update()
        window.show_region();window.update()
        window.geometry("900x650+0+0");window.update()
        x,y=window.winfo_rootx(),window.winfo_rooty()
        f=out/"linked_roi_focus.png"
        ImageGrab.grab(bbox=(x,y,x+window.winfo_width(),y+window.winfo_height())).save(f)
        shots.append(f)
        window.destroy()
        # P9-I10: capture real E03 review, graph controls and report index.
        from aiforensics.review_ui import ReviewWindow
        review=ReviewWindow(app,project,tab='Kanıt İnceleme',initial_image_sha=digest)
        review.geometry("1180x760+0+0")
        review.update()
        e03_index=next(i for i,x in enumerate(review.reports)
                       if x["schema_version"]=="p8.e03.v1")
        review.select_report(e03_index)
        review.finding_query.set(record_id)
        if review.page_findings:
            review.findings_list.selection_set(0)
            review._finding_chosen(None)
        for label,target in (("evidence_long_review",review.finding_tab),
                             ("dependent_graph_navigation",review.graph_tab),
                             ("report_index",review.report_tab)):
            review.tabs.select(target)
            if target==review.graph_tab:
                review.graph_zoom=1.25
                review._draw_graph()
            review.update_idletasks()
            review.update()
            x,y=review.winfo_rootx(),review.winfo_rooty()
            png=out/(label+".png")
            ImageGrab.grab(bbox=(x,y,x+review.winfo_width(),y+review.winfo_height())).save(png)
            shots.append(png)
        review.destroy()
    finally:
        app.destroy()
    index={"schema":"p9.i09.synthetic_screenshot.v1",
           "data_scope":"synthetic_controlled",
           "real_camera_acceptance":"NOT_PERFORMED",
           "real_windows_acceptance":"NOT_PERFORMED",
           "decision":"NO_AI_ORIGIN_CONCLUSION",
           "screenshots":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in shots}}
    (out/"screenshot_manifest.json").write_text(
        json.dumps(index,ensure_ascii=False,indent=2),encoding="utf-8")
    return index


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default="outputs/p9_i09_visuals")
    parser.add_argument("--width",type=int,default=1366)
    parser.add_argument("--height",type=int,default=768)
    args=parser.parse_args()
    if not 1024<=args.width<=3840 or not 640<=args.height<=2160:
        parser.error("invalid screen size")
    with tempfile.TemporaryDirectory(prefix="fakeproof-i09-") as workspace:
        print(json.dumps(capture(Path(workspace),args.out,args.width,args.height),
                         ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
