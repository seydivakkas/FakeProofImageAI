"""P9-I09 native-pixel ROI editor for explicitly linked E03 findings."""
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox

from .focus_region import get_focus,save_focus
from .review_workspace import _image_match
from .science_panel_data import valid_roi

BG="#0a1420";PANEL="#142639";INK="#e7f2fa";CYAN="#19c5ff";MUTED="#abbfd1"

class FindingFocusWindow(tk.Toplevel):
    def __init__(self,master,project,report_id,record_id,image_sha):
        super().__init__(master)
        self.project=project;self.report_id=report_id;self.record_id=record_id
        self.image_sha=image_sha
        from PIL import Image
        path,_=_image_match(project,image_sha)
        with Image.open(path) as f:self.original=f.convert("RGB")
        self.wh=self.original.size
        self.focus=get_focus(project,report_id,record_id,image_sha)
        self.selection=None;self.drag_origin=None;self.photo=None
        self.view=[0.,0.,float(self.wh[0]),float(self.wh[1])]
        self.title("FakeProofImageAI — Kullanıcı tanımlı bulgu ROI")
        self.geometry("1000x720");self.minsize(720,520);self.configure(bg=BG)
        top=tk.Frame(self,bg=PANEL,padx=12,pady=8);top.pack(fill="x")
        tk.Label(top,text="Kanıt: "+record_id,bg=PANEL,fg=CYAN,
                 font=("Segoe UI",13,"bold")).pack(anchor="w")
        tk.Label(top,text="Bölge kullanıcı beyanıdır; bağımsız kamera veya geometri kanıtı değildir.",
                 bg=PANEL,fg=MUTED).pack(anchor="w")
        bar=tk.Frame(self,bg=PANEL);bar.pack(fill="x")
        for label,action in (("Tam görüntü",self.show_full),
                             ("ROI alanına git",self.show_region),
                             ("ROI kaydet",self.save)):
            tk.Button(bar,text=label,bg="#1976d2",fg="white",command=action,
                      padx=12,pady=6,relief="flat").pack(side="left",padx=7,pady=5)
        self.status=tk.StringVar(value="Fareyle görüntü üzerinde dikdörtgen seçiniz.")
        tk.Label(self,textvariable=self.status,bg=BG,fg=INK,anchor="w").pack(fill="x",padx=12,pady=5)
        self.canvas=tk.Canvas(self,bg=BG,cursor="crosshair",highlightthickness=0)
        self.canvas.pack(fill="both",expand=True,padx=10,pady=10)
        self.canvas.bind("<Configure>",lambda event:self.draw())
        self.canvas.bind("<ButtonPress-1>",self.begin)
        self.canvas.bind("<B1-Motion>",self.drag)
        self.canvas.bind("<ButtonRelease-1>",self.end)
        self.after_idle(self.draw)

    def mapping(self):
        x0,y0,x1,y1=self.view
        w,h=max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())
        scale=min(w/max(x1-x0,1),h/max(y1-y0,1))
        return (w-(x1-x0)*scale)/2,(h-(y1-y0)*scale)/2,scale

    def pixel(self,x,y):
        left,top,scale=self.mapping()
        return (min(self.view[2],max(self.view[0],self.view[0]+(x-left)/scale)),
                min(self.view[3],max(self.view[1],self.view[1]+(y-top)/scale)))

    def draw(self):
        if not hasattr(self,"canvas") or not self.canvas.winfo_exists():return
        from PIL import Image,ImageTk
        self.canvas.delete("all")
        x0,y0,x1,y1=self.view
        left,top,scale=self.mapping()
        rendered=self.original.crop(tuple(self.view))
        size=(max(1,round((x1-x0)*scale)),max(1,round((y1-y0)*scale)))
        rendered=rendered.resize(size,Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(rendered)
        self.canvas.create_image(left,top,anchor="nw",image=self.photo)
        for box,color in ((self.focus["roi_xyxy_px"] if self.focus else None,"#f3bf66"),
                          (self.selection,"#19c5ff")):
            if box is None:continue
            a=left+(box[0]-x0)*scale;b=top+(box[1]-y0)*scale
            c=left+(box[2]-x0)*scale;d=top+(box[3]-y0)*scale
            self.canvas.create_rectangle(a,b,c,d,outline=color,width=3)

    def show_full(self):
        self.view=[0.,0.,float(self.wh[0]),float(self.wh[1])]
        self.draw()

    def show_region(self):
        box=self.selection or (self.focus["roi_xyxy_px"] if self.focus else None)
        if box is None:
            self.status.set("Önce ROI çizilmesi veya kaydedilmiş seçim gerekir")
            return
        x0,y0,x1,y1=box
        dx=(x1-x0)*.25;dy=(y1-y0)*.25
        self.view=[max(0.,x0-dx),max(0.,y0-dy),
                   min(self.wh[0],x1+dx),min(self.wh[1],y1+dy)]
        self.draw()

    def begin(self,event):
        self.drag_origin=self.pixel(event.x,event.y)
        self.selection=None

    def drag(self,event):
        if self.drag_origin is None:return
        x0,y0=self.drag_origin;x1,y1=self.pixel(event.x,event.y)
        if abs(x1-x0)<1 or abs(y1-y0)<1:return
        self.selection=[min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1)]
        self.draw()

    def end(self,event):
        self.drag(event);self.drag_origin=None
        if self.selection:
            self.status.set("Seçili özgün piksel ROI: "+str([round(v,1) for v in self.selection]))

    def save(self):
        if not self.selection:
            messagebox.showinfo("ROI","Önce bir dikdörtgen çiziniz.",parent=self)
            return
        try:
            valid_roi(self.wh,self.selection)
            self.focus=save_focus(self.project,self.report_id,self.record_id,
                                  self.image_sha,self.selection)
            self.status.set("Kayıt: user_asserted_not_verified · AI köken kararı YOK")
            self.draw()
        except (ValueError,OSError,TypeError) as exc:
            messagebox.showerror("ROI kaydedilmedi",str(exc),parent=self)
