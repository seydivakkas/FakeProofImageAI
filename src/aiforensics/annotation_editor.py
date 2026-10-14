"""Tkinter/Pillow native-pixel editor for calibration and physical measurements.

P9-I02: click to set points, drag to draw segments and rectangles, select and
move handles, double-click/Enter to finish poly-lines, wheel zoom, space-pan.
All computations are pixel-only and must not be mistaken for metric inference.
"""
from __future__ import annotations

import math
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .annotation_model import AnnotationDocument, AnnotationError, Viewport

DARK = '#0a1420'
PANEL = '#142639'
INK = '#ecf5ff'
MUTED = '#a5bccf'
BLUE = '#209ce9'
PALETTE = {'point':'#ffdf6f','line':'#4db9fb', 'polyline':'#d594ef',
           'polygon':'#4be0a2','rectangle':'#f2a35e'}
TOOLS = ('select','pan','point','line','polyline','polygon','rectangle')


def _distance_to_segment(p,a,b):
    vx,vy=b[0]-a[0],b[1]-a[1]
    den=vx*vx+vy*vy
    if den<1e-20:return math.dist(p,a)
    t=max(0.,min(1.,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/den))
    return math.dist(p,(a[0]+vx*t,a[1]+vy*t))


def hit_test(marks,point,tolerance):
    """Return nearest (id, vertex_index | None), never infer a spatial 3D contact."""
    best=(None,None,float('inf'))
    for m in reversed(marks):
        points=m['points']
        for i,xy in enumerate(points):
            d=math.dist(point,xy)
            if d<=tolerance and d<best[2]:best=(m['id'],i,d)
        segments=list(zip(points,points[1:]))
        if m['kind']=='rectangle':
            a,b=points
            pts=[a,[b[0],a[1]],b,[a[0],b[1]],a]
            segments=list(zip(pts,pts[1:]))
        elif m['kind']=='polygon':segments.append((points[-1],points[0]))
        for a,b in segments:
            d=_distance_to_segment(point,a,b)
            if d<=tolerance and d<best[2]:best=(m['id'],None,d)
    return best[0],best[1]


class AnnotationEditor(tk.Toplevel):
    """A real edit window opened from P9 desktop calibration/measurement pages."""
    def __init__(self,parent,image_path,annotation_path,*,expected_sha256,on_saved=None):
        super().__init__(parent)
        self.title('FakeProofImageAI · P9-I02 Anotasyon Editörü')
        self.configure(bg=DARK)
        self.geometry('1380x850')
        self.minsize(850,550)
        self.image_path=Path(image_path)
        self.annotation_path=Path(annotation_path)
        self.on_saved=on_saved
        try:
            from PIL import Image, ImageTk
        except ImportError as exc:
            self.destroy()
            raise AnnotationError('Görüntü editörü Pillow gerektirir: pip install -e ".[desktop]"') from exc
        self._Image,self._ImageTk=Image,ImageTk
        self.image=Image.open(self.image_path)
        self.image.load()
        self.image_size=self.image.size
        if self.image.width>200000 or self.image.height>200000:
            raise AnnotationError('Görüntü boyutları çok büyük')
        if self.annotation_path.exists():
            self.doc=AnnotationDocument.load(self.annotation_path,
                image_sha256=expected_sha256,image_size_wh=self.image_size)
        else:
            self.doc=AnnotationDocument(*self.image_size,expected_sha256)
        self.viewport=Viewport()
        self.mode=tk.StringVar(value='select')
        self.family=tk.StringVar(value='Etiketsiz')
        self.status=tk.StringVar(value='Piksel koordinatları · Metrik kalibrasyon doğrulanmadı')
        self.selected=None
        self.pending=[]
        self.drag_anchor=None
        self.drag_mode=None
        self.drag_vertex=None
        self.pan_anchor=None
        self._drag_initial=None
        self._preview=None
        self._photo=None
        self._image_cache=None
        self._image_cache_size=None
        self._make_ui()
        self.after(120,self.fit_image)
        self.protocol('WM_DELETE_WINDOW',self.destroy)

    def _make_ui(self):
        toolbar=tk.Frame(self,bg=PANEL,padx=8,pady=7)
        toolbar.pack(fill='x')
        tk.Label(toolbar,text='P9-I02 · Kalibrasyon / Fiziksel Ölçümler',
                 bg=PANEL,fg=INK,font=('Segoe UI',12,'bold')).pack(side='left',padx=8)
        for item,caption in [('select','Seç/Düzenle'),('pan','Kaydır'),('point','Nokta'),
                             ('line','Çizgi'),('polyline','Çoklu Çizgi'),
                             ('polygon','Çokgen'),('rectangle','ROI')]:
            ttk.Radiobutton(toolbar,text=caption,variable=self.mode,value=item,
                            command=self.change_tool).pack(side='left',padx=3)
        family_select=ttk.Combobox(toolbar,textvariable=self.family,width=12,state='readonly',
                                  values=('Etiketsiz','X','Y','Z'))
        family_select.pack(side='left',padx=8)
        family_select.bind('<<ComboboxSelected>>',lambda e:self.assign_family())
        ttk.Button(toolbar,text='Kaydet',command=self.save).pack(side='right',padx=5)
        ttk.Button(toolbar,text='G02 Taslağı',command=self.export_g02).pack(side='right',padx=5)
        ttk.Button(toolbar,text='Yinele',command=self.redo).pack(side='right',padx=3)
        ttk.Button(toolbar,text='Geri Al',command=self.undo).pack(side='right',padx=3)
        content=tk.PanedWindow(self,orient=tk.HORIZONTAL,bg=DARK,sashwidth=6)
        content.pack(fill='both',expand=True)
        workspace=tk.Frame(content,bg=DARK)
        content.add(workspace,stretch='always')
        self.canvas=tk.Canvas(workspace,bg='#08131e',highlightthickness=0,cursor='crosshair')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.redraw())
        self.canvas.bind('<ButtonPress-1>',self.mouse_down)
        self.canvas.bind('<B1-Motion>',self.mouse_move)
        self.canvas.bind('<ButtonRelease-1>',self.mouse_up)
        self.canvas.bind('<Double-Button-1>',self.finish_multistep)
        self.canvas.bind('<Motion>',self.update_pointer)
        self.canvas.bind('<MouseWheel>',self.scroll_zoom)
        self.canvas.bind('<Button-4>',lambda e:self.zoom_at(e,1.15))
        self.canvas.bind('<Button-5>',lambda e:self.zoom_at(e,1/1.15))
        self.bind('<Return>',self.finish_multistep)
        self.bind('<Escape>',self.cancel)
        self.bind('<Delete>',self.delete_selected)
        self.bind('<Control-z>',self.undo)
        self.bind('<Control-y>',self.redo)
        self.bind('<KeyPress-space>',self.begin_space_pan)
        self.bind('<KeyRelease-space>',self.end_space_pan)
        side=tk.Frame(content,bg=PANEL,width=320,padx=10,pady=10)
        content.add(side,stretch='never')
        tk.Label(side,text='İşaretlemeler',bg=PANEL,fg=INK,
                 font=('Segoe UI',13,'bold')).pack(anchor='w',pady=8)
        self.items=tk.Listbox(side,bg='#0e2031',fg=INK,selectbackground=BLUE,
                              activestyle='none',height=18,exportselection=False)
        self.items.pack(fill='both',expand=True)
        self.items.bind('<<ListboxSelect>>',self.select_from_list)
        ttk.Button(side,text='Seçili İşaretlemeyi Sil',command=self.delete_selected).pack(fill='x',pady=7)
        ttk.Button(side,text='Görüntüye Sığdır',command=self.fit_image).pack(fill='x',pady=4)
        self.detail=tk.Text(side,height=9,bg='#0e2031',fg=INK,wrap='word',state='disabled')
        self.detail.pack(fill='x',pady=10)
        hint=('Çizgi/ROI: sürükle · Nokta: tıkla\n'
              'Çoklu çizgi/çokgen: köşelere tıkla, Enter ile bitir\n'
              'Nokta tutmacı: seç ve sürükle\n'
              'Kaydırma: Fare tekerleği = zoom, Kaydır aracı = pan\n'
              'Geri al: Ctrl+Z · Sil: Delete\n'
              'Uzunluklar px, alan px²; bağımsız ölçüm yok.')
        tk.Label(side,text=hint,bg=PANEL,fg=MUTED,justify='left',
                 wraplength=295).pack(anchor='w')
        tk.Label(self,textvariable=self.status,bg=PANEL,fg=INK,
                 anchor='w',padx=16,pady=7).pack(fill='x')
        self.refresh_list()

    def change_tool(self):
        self.pending=[]
        self.drag_anchor=None
        self.redraw()

    def fit_image(self):
        self.update_idletasks()
        w=max(1,self.canvas.winfo_width())
        h=max(1,self.canvas.winfo_height())
        scale=min((w-30)/self.doc.width,(h-30)/self.doc.height,4.)
        self.viewport=Viewport(max(.025,scale),
            (w-self.doc.width*scale)/2,(h-self.doc.height*scale)/2)
        self.redraw()

    def _point(self,event):
        return self.viewport.from_canvas((event.x,event.y))

    def _valid(self,p):
        return 0<=p[0]<self.doc.width and 0<=p[1]<self.doc.height

    def _bounded(self,p):
        return [max(0.,min(self.doc.width-1.,p[0])),
                max(0.,min(self.doc.height-1.,p[1]))]

    def redraw(self):
        if not hasattr(self,'canvas'):return
        self.canvas.delete('all')
        scale=self.viewport.scale
        size=(max(1,round(self.doc.width*scale)),max(1,round(self.doc.height*scale)))
        # Limit rendered raster pixel count; annotations remain in native coords.
        if size[0]*size[1]>16_000_000:
            # Avoid dishonest overlay positioning due to raster downsampling.
            self.status.set('Zoom görüntü belleği sınırına ulaştı')
            return
        if size!=self._image_cache_size:
            self._image_cache=self.image.resize(size,self._Image.Resampling.BILINEAR)
            self._photo=self._ImageTk.PhotoImage(self._image_cache)
            self._image_cache_size=size
        # Canvas projection compensates if the raster is downsampled for memory.
        self.canvas.create_image(self.viewport.offset_x,self.viewport.offset_y,
                                 image=self._photo,anchor='nw')
        for mark in self.doc.marks:
            self.draw_mark(mark,selected=mark['id']==self.selected)
        if len(self.pending)>0:
            ps=[self.viewport.to_canvas(p) for p in self.pending]
            if len(ps)>1:self.canvas.create_line(*[c for p in ps for c in p],
                                                fill='#fff2a2',width=2,dash=(5,5))
            for x,y in ps:self.canvas.create_oval(x-3,y-3,x+3,y+3,fill='#fff2a2')
        if self._preview:
            kind,points=self._preview
            self.draw_mark({'kind':kind,'points':points,'id':-1,'label':'','family':None},selected=False)

    def draw_mark(self,mark,selected):
        coords=[self.viewport.to_canvas(x) for x in mark['points']]
        color='#ffffff' if selected else PALETTE[mark['kind']]
        kind=mark['kind']
        if kind=='point':
            x,y=coords[0];self.canvas.create_oval(x-5,y-5,x+5,y+5,fill=color,outline='#06101a')
        elif kind=='rectangle':
            a,b=coords;self.canvas.create_rectangle(*a,*b,outline=color,width=2)
        elif len(coords)>=2:
            xy=[c for p in coords for c in p]
            if kind=='polygon':self.canvas.create_polygon(xy,outline=color,fill='',width=2)
            else:self.canvas.create_line(*xy,fill=color,width=2)
        if selected:
            for x,y in coords:
                self.canvas.create_rectangle(x-5,y-5,x+5,y+5,fill=BLUE,outline='white')
        x,y=coords[0]
        self.canvas.create_text(x+7,y-10,anchor='sw',fill=color,
                                text=str(mark['id'])+(' '+str(mark['family']) if mark['family'] else ''),
                                font=('Segoe UI',9,'bold'))

    def mouse_down(self,event):
        self.canvas.focus_set()
        p=self._point(event)
        self.drag_anchor=p
        mode=self.mode.get()
        self.drag_mode=mode
        if mode=='pan':
            self.pan_anchor=(event.x,event.y)
        elif mode=='select':
            self._drag_initial=copy.deepcopy(self.doc.marks)
            self.selected,self.drag_vertex=hit_test(self.doc.marks,p,10/self.viewport.scale)
            self.refresh_list();self.redraw()
        elif mode=='point':
            if self._valid(p):self.add_mark('point',[p])
        elif mode in ('polyline','polygon') and self._valid(p):
            self.pending.append(self._bounded(p));self.redraw()
        elif mode in ('line','rectangle'):
            self._preview=None

    def mouse_move(self,event):
        mode=self.drag_mode
        p=self._point(event)
        if mode=='pan' and self.pan_anchor:
            dx,dy=event.x-self.pan_anchor[0],event.y-self.pan_anchor[1]
            self.viewport.pan(dx,dy)
            self.pan_anchor=event.x,event.y
            self.redraw()
        elif mode=='select' and self.selected is not None and self.drag_anchor is not None:
            mark=next((m for m in self.doc.marks if m['id']==self.selected),None)
            if mark is not None:
                dx,dy=p[0]-self.drag_anchor[0],p[1]-self.drag_anchor[1]
                points=[list(q) for q in mark['points']]
                if self.drag_vertex is None:
                    points=[[q[0]+dx,q[1]+dy] for q in points]
                else:
                    points[self.drag_vertex]=list(p)
                try:
                    self.doc.replace(self.selected,points=points,record_history=False)
                    self.drag_anchor=p
                    self.redraw()
                except AnnotationError:
                    pass
        elif mode in ('line','rectangle') and self.drag_anchor:
            if self._valid(self.drag_anchor):
                self._preview=(mode,[list(self.drag_anchor),self._bounded(p)])
                self.redraw()

    def mouse_up(self,event):
        mode=self.drag_mode
        if mode in ('line','rectangle') and self.drag_anchor and self._valid(self.drag_anchor):
            a=self._bounded(self.drag_anchor)
            b=self._bounded(self._point(event))
            if math.dist(a,b)>=.5:
                self.add_mark(mode,[a,b])
        if mode=='select' and self._drag_initial is not None:
            self.doc.checkpoint(self._drag_initial)
            self._drag_initial=None
        self._preview=None
        self.drag_anchor=None
        self.pan_anchor=None
        self.drag_mode=None
        self.redraw()

    def finish_multistep(self,event=None):
        if self.mode.get() not in ('polygon','polyline'):return
        points=[]
        for p in self.pending:
            if not points or math.dist(p,points[-1])>.5:points.append(p)
        if len(points)>1 and math.dist(points[0],points[-1])<.5:points.pop()
        if len(points)>=(3 if self.mode.get()=='polygon' else 2):
            self.add_mark(self.mode.get(),points)
        self.pending=[];self.redraw()

    def cancel(self,event=None):
        self.pending=[];self._preview=None;self.redraw()

    def update_pointer(self,event):
        p=self._point(event)
        self.status.set(f'Görüntü x={p[0]:.2f}px, y={p[1]:.2f}px'
                        ' · Ölçümler piksel cinsinden · Fiziksel ölçek doğrulanmadı')

    def zoom_at(self,event,factor):
        max_scale=min(8.,math.sqrt(16_000_000/(self.doc.width*self.doc.height)))
        if self.viewport.scale*factor>max_scale:
            factor=max_scale/self.viewport.scale
        self.viewport.zoom_at(factor,(event.x,event.y))
        self.redraw()

    def scroll_zoom(self,event):
        self.zoom_at(event,1.15 if event.delta>0 else 1/1.15)

    def begin_space_pan(self,event=None):
        self._previous_mode=self.mode.get()
        self.mode.set('pan')

    def end_space_pan(self,event=None):
        self.mode.set(getattr(self,'_previous_mode','select'))

    def add_mark(self,kind,points):
        try:
            family=self.family.get() if kind=='line' and self.family.get()!='Etiketsiz' else None
            self.selected=self.doc.add(kind,points,family=family)
            self.refresh_list();self.redraw()
        except AnnotationError as exc:
            self.status.set(str(exc))

    def assign_family(self):
        if self.selected is None:return
        family=self.family.get()
        try:
            self.doc.replace(self.selected,family=None if family=='Etiketsiz' else family)
            self.refresh_list();self.redraw()
        except AnnotationError as exc:
            self.status.set(str(exc))

    def refresh_list(self):
        self.items.delete(0,'end')
        for mark in self.doc.marks:
            self.items.insert('end',f"#{mark['id']:04d}  {mark['kind']}  "
                                   f"{mark['family'] or ''}  {mark['label']}")
        if self.selected is not None:
            idx=next((i for i,m in enumerate(self.doc.marks) if m['id']==self.selected),None)
            if idx is not None:
                self.items.selection_set(idx);self.items.see(idx)
                info=self.doc.inspect(self.selected)
                txt=f"{info['kind']}\nUzunluk: {info['length_px']:.3f} px\n"
                if info['area_px2'] is not None:txt+=f"Alan: {info['area_px2']:.3f} px²\n"
                txt+='Gerçek birim/mesafe: BELİRSİZ'
                self.detail.configure(state='normal')
                self.detail.delete('1.0','end');self.detail.insert('1.0',txt)
                self.detail.configure(state='disabled')

    def select_from_list(self,event=None):
        sel=self.items.curselection()
        if not sel:return
        self.selected=self.doc.marks[sel[0]]['id']
        self.redraw()
        info=self.doc.inspect(self.selected)
        self.detail.configure(state='normal')
        self.detail.delete('1.0','end');self.detail.insert('1.0',str(info))
        self.detail.configure(state='disabled')

    def delete_selected(self,event=None):
        if self.selected and self.doc.delete(self.selected):
            self.selected=None;self.refresh_list();self.redraw()

    def undo(self,event=None):
        if self.doc.undo():self.selected=None;self.refresh_list();self.redraw()

    def redo(self,event=None):
        if self.doc.redo():self.selected=None;self.refresh_list();self.redraw()

    def save(self):
        try:
            self.doc.save(self.annotation_path)
            self.status.set('Anotasyon kaydedildi: '+str(self.annotation_path))
            if self.on_saved:self.on_saved(self.doc,self.annotation_path)
        except (OSError,AnnotationError) as exc:
            messagebox.showerror('Kaydedilemedi',str(exc),parent=self)

    def export_g02(self):
        try:
            draft=self.doc.g02_draft()
        except AnnotationError as exc:
            messagebox.showwarning('G02 taslağı',str(exc),parent=self)
            return
        accepted=messagebox.askyesno('Bağımsız kalibrasyon gerekli',
            'X/Y/Z çizgi ailelerini yalnızca kullanıcı etiketledi. Bu, 3B ortogonalliği '
            'veya metrik kalibrasyonu kanıtlamaz. Taslak JSON dışa aktarılsın mı?',parent=self)
        if not accepted:return
        target=filedialog.asksaveasfilename(parent=self,defaultextension='.json',
                                            filetypes=[('JSON','*.json')])
        if target:
            # G02 CLI requires shape and orthogonal_groups; extra fields are provenance safeguards.
            import json
            Path(target).write_text(json.dumps(draft,indent=2,ensure_ascii=False),encoding='utf-8')
            self.status.set('G02 etiketli çizgi taslağı kaydedildi: bağımsız kalibrasyon değil')