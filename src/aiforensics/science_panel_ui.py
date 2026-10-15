"""P9-I09 offline Tk scientific plots: no invented pixels, error bars or scores."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from .science_panel_data import recorded_calibrations,residual_groups
from .ui_polish import latest_e03

BG="#0a1420";PANEL="#142639";NAV="#0d1e30";CYAN="#19c5ff"
INK="#e7f2fa";MUTED="#abbfd1";AMBER="#f3bf66"

def panel(root,title):
    box=tk.Frame(root,bg=PANEL,padx=12,pady=10)
    box.pack(fill="x",pady=8)
    text(box,title,CYAN).pack(anchor="w")
    return box

def text(root,msg,color=INK):
    return tk.Label(root,text=str(msg),bg=root.cget("bg"),fg=color,
                    anchor="w",justify="left",wraplength=790,
                    font=("Segoe UI",10))

def chart(root):
    c=tk.Canvas(root,bg=NAV,height=218,highlightthickness=0)
    c.pack(fill="x",expand=True,pady=7)
    return c

def axes(c,w,h,left=56):
    c.create_line(left,12,left,h-34,fill="#6a889c")
    c.create_line(left,h-34,w-12,h-34,fill="#6a889c")

def show_vps(c,points):
    c.delete("all");w=max(c.winfo_width(),360);h=max(c.winfo_height(),218)
    axes(c,w,h)
    if not points:
        c.create_text(w/2,h/2,text="Kayıtlı sonlu kaçış noktası yok",fill=MUTED)
        return
    xlo=min(x for x,y in points);xhi=max(x for x,y in points)
    ylo=min(y for x,y in points);yhi=max(y for x,y in points)
    dx=max(1,xhi-xlo);dy=max(1,yhi-ylo)
    for i,(x,y) in enumerate(points):
        px=60+(x-xlo)/dx*(w-100);py=18+(y-ylo)/dy*(h-70)
        c.create_oval(px-5,py-5,px+5,py+5,fill=CYAN,outline="")
        c.create_text(px+7,py-9,anchor="w",text=f"VP{i+1}: {x:.1f},{y:.1f} px",fill=INK)
    c.create_text(w-15,h-13,anchor="e",text="Görüntü koordinatları: px",fill=MUTED)

def show_holdout(c,errors,threshold):
    c.delete("all");w=max(c.winfo_width(),360);h=max(c.winfo_height(),218)
    axes(c,w,h)
    if not errors:
        c.create_text(w/2,h/2,text="Bağımsız holdout hata dizisi yok",fill=MUTED)
        return
    series=errors[:300]
    maximum=max(max(series),threshold or 0,1e-6)*1.2
    for i,val in enumerate(series):
        x=58+(i+.5)*(w-76)/len(series)
        y=h-34-(val/maximum)*(h-60)
        c.create_line(x,h-34,x,y,fill=CYAN,width=2)
    if threshold is not None:
        y=h-34-threshold/maximum*(h-60)
        c.create_line(56,y,w-15,y,fill=AMBER,dash=(5,3))
        c.create_text(w-18,y-9,anchor="e",text=f"Beyan eşiği {threshold:.3g} px",fill=AMBER)
    c.create_text(w-15,h-12,anchor="e",text="Holdout ölçüm sırası",fill=MUTED)

def show_residuals(c,items,unit):
    c.delete("all");w=max(c.winfo_width(),540);h=max(c.winfo_height(),235)
    axes(c,w,h,left=98)
    if not items:
        c.create_text(w/2,h/2,text="Bu birimde ölçüm yok",fill=MUTED)
        return
    series=items[:24];bounds=[0.0]
    for r in series:
        bounds.append(r["residual"])
        if r["ci95"] is not None:bounds+=r["ci95"]
    peak=max(1e-7,max(abs(v) for v in bounds))*1.2
    xzero=98+(w-117)/2
    step=(w-117)/(2*peak)
    c.create_line(xzero,14,xzero,h-38,fill="#7892a8",dash=(3,3))
    for i,item in enumerate(series):
        y=25+(i+.5)*(h-75)/len(series)
        c.create_text(94,y,anchor="e",text=item["record_id"][:14],fill=MUTED)
        interval=item["ci95"]
        if interval is not None:
            xa=xzero+interval[0]*step;xb=xzero+interval[1]*step
            c.create_line(xa,y,xb,y,fill=AMBER,width=2)
            c.create_line(xa,y-4,xa,y+4,fill=AMBER)
            c.create_line(xb,y-4,xb,y+4,fill=AMBER)
        x=xzero+item["residual"]*step
        c.create_oval(x-4,y-4,x+4,y+4,fill=CYAN,outline="")
    c.create_text(w-14,h-13,anchor="e",text=f"Artık ({unit}) · 95% aralık yalnız kaynakta varsa",fill=MUTED)
    if len(items)>len(series):
        c.create_text(w-14,16,anchor="ne",text=f"İlk {len(series)}/{len(items)}",fill=AMBER)

def attach_calibration(app):
    root=panel(app.page,"G01 / G02 KAÇIŞ NOKTALARI · G04 REPROJEKSİYON")
    text(root,"Yalnız kaydedilmiş modül çıktıları; bağımsız kamera geçerliliği iddiası yok.",MUTED).pack(anchor="w")
    by=recorded_calibrations(app.project)
    tabs=ttk.Notebook(root);tabs.pack(fill="x",pady=8)
    for mid,caption in (("P1-G01","G01 VP"),("P1-G02","G02 Kamera K"),("P1-G04","G04 Holdout")):
        frame=tk.Frame(tabs,bg=PANEL,padx=8,pady=6);tabs.add(frame,text=caption)
        item=by.get(mid)
        if item is None:
            text(frame,"Geçerli kayıt bulunmadı.",MUTED).pack(anchor="w")
            continue
        text(frame,f"{item['run_id']} / {item['file']} · SHA-256 {item['sha256'][:14]}…",MUTED).pack(anchor="w")
        if mid!="P1-G04":
            if item.get("K") is not None:
                text(frame,"K (piksel): "+str([[round(v,3) for v in row] for row in item["K"]])).pack(anchor="w")
            elif mid=="P1-G02":text(frame,"K yok / bağımsız kalibrasyon henüz sağlanmadı.",AMBER).pack(anchor="w")
            c=chart(frame)
            c.bind("<Configure>",lambda event,c=c,points=item.get("vps",[]):show_vps(c,points))
        else:
            text(frame,"Train RMSE: "+str(item.get("train_reprojection_rmse_px"))+
                 " px | Holdout RMSE: "+str(item.get("holdout_reprojection_rmse_px"))+" px").pack(anchor="w")
            c=chart(frame)
            c.bind("<Configure>",lambda event,c=c,d=item:
                show_holdout(c,d.get("errors_px",[]),d.get("holdout_threshold_px")))
    return by

def attach_residuals(app):
    root=panel(app.page,"ARTIK / BELİRSİZLİK GRAFİĞİ  ·  E03 KANIT RAPORU")
    latest=latest_e03(app.project)
    if latest is None:
        text(root,"Kayıtlı E03 raporu yok; veri veya belirsizlik uydurulmaz.",MUTED).pack(anchor="w")
        return {}
    try:groups=residual_groups(latest["report"])
    except (ValueError,TypeError,KeyError):groups={}
    if not groups:
        text(root,"E03 raporunda sayısal artık bulunmuyor.",MUTED).pack(anchor="w")
        return groups
    text(root,"Fiziksel birimler ayrı sekmelerde; sarı çizgi yalnız raporda bulunan %95 aralıktır.",MUTED).pack(anchor="w")
    tabs=ttk.Notebook(root);tabs.pack(fill="x",pady=7)
    for unit,entries in list(sorted(groups.items()))[:10]:
        tab=tk.Frame(tabs,bg=PANEL);tabs.add(tab,text=unit)
        c=chart(tab)
        c.bind("<Configure>",lambda event,c=c,entries=entries,unit=unit:
               show_residuals(c,entries,unit))
    return groups
