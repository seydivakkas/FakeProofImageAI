"""P9-I04 offline Tkinter review window: measured artifacts only, never AI verdicts."""
from __future__ import annotations

import json
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import webbrowser

from .review_workspace import (
    ReviewError, annotation_layers, bind_finding_to_image, dependency_graph,
    image_overlays, linked_images, list_images, read_report, register_overlay,
    report_catalog, _image_match,
)

NAV = '#0d1e30'; BG = '#0a1420'; PANEL = '#142639'; FG = '#eef6ff'
CYAN = '#19c5ff'; BLUE = '#1976d2'; GREY = '#abbfd1'


def initial_image_index(images, selected_sha=None):
    """Find user-selected image. A stale explicit SHA must NOT select another."""
    if not images:
        return None
    if selected_sha is None:
        return 0
    matches=[i for i,item in enumerate(images) if item.get("sha256")==selected_sha]
    return matches[0] if len(matches)==1 else None


class ReviewWindow(tk.Toplevel):
    """One review window: explicit review links and layer visibility per image."""
    def __init__(self, master, project, *, tab='Görsel Katmanlar',
                 initial_image_sha=None):
        super().__init__(master)
        self.project = project
        self.title('FakeProofImageAI — P9-I04 Görsel / Kanıt / Rapor Gezgini')
        self.geometry('1390x850'); self.minsize(1000, 630); self.configure(bg=BG)
        self.status = tk.StringVar(value='Yalnız yerel kaynaklar · AI kökeni kararı YOK')
        self.images = list_images(project)
        self.reports = report_catalog(project)
        self.image_index = None
        self.report_index = None
        self.record_id = None
        self.layer_states = {}
        self.scale = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.tk_image = None
        self._build()
        self.tabs.select({'Görsel Katmanlar':0, 'Kanıt İnceleme':1,
                          'Bağımlılık Grafiği':2, 'Rapor Gezgini':3}.get(tab,0))
        first=initial_image_index(self.images,initial_image_sha)
        if first is not None:
            self.select_image(first)
        elif initial_image_sha is not None:
            self.status.set("Seçili görüntü projede tekil değil veya bulunamadı; kaynak seçiniz")
        if self.reports:self.select_report(0)

    def _button(self, parent, title, action):
        return tk.Button(parent, text=title, command=action, relief='flat',
                         bg=BLUE, fg='white', activebackground='#236c9c', padx=10, pady=7)

    def _label(self, parent, text, size=10, color=FG):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Segoe UI',size), anchor='w', justify='left')

    def _build(self):
        header=tk.Frame(self,bg=NAV,padx=12,pady=8);header.pack(fill='x')
        self._label(header,'P9-I04 · Kanıt ve Görsel İnceleme',16,CYAN).pack(side='left')
        self._label(header,'Sentetik yazılım · Gerçek kamera kabulü en son',10,GREY).pack(side='right')
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=12,pady=8)
        self.layer_tab=tk.Frame(self.tabs,bg=BG)
        self.finding_tab=tk.Frame(self.tabs,bg=BG)
        self.graph_tab=tk.Frame(self.tabs,bg=BG)
        self.report_tab=tk.Frame(self.tabs,bg=BG)
        for name, page in [('Görsel Katmanlar',self.layer_tab),('Kanıt İnceleme',self.finding_tab),
                           ('Bağımlılık Grafiği',self.graph_tab),('Rapor Gezgini',self.report_tab)]:
            self.tabs.add(page,text=name)
        self._make_image_tab();self._make_finding_tab();self._make_graph_tab();self._make_report_tab()
        tk.Label(self,textvariable=self.status,bg=NAV,fg=GREY,
                 anchor='w',padx=14,pady=7).pack(fill='x')

    def _make_image_tab(self):
        left=tk.Frame(self.layer_tab,bg=PANEL,width=320,padx=10,pady=10)
        left.pack(side='left',fill='y',padx=(0,8));left.pack_propagate(False)
        self._label(left,'Projede kayıtlı görüntüler',13,CYAN).pack(anchor='w')
        self.images_list=tk.Listbox(left,bg=NAV,fg=FG,selectbackground=BLUE,
                                     exportselection=False,height=8)
        self.images_list.pack(fill='x',pady=8)
        for entry in self.images:self.images_list.insert('end',entry['name'])
        self.images_list.bind('<<ListboxSelect>>',self._image_chosen)
        self._label(left,'Katmanlar (manuel seçim)',12,CYAN).pack(anchor='w',pady=(12,0))
        self.layer_frame=tk.Frame(left,bg=PANEL);self.layer_frame.pack(fill='x')
        self._button(left,'Görsel Katman PNG Ekle',self._add_overlay).pack(fill='x',pady=8)
        self._label(left,'Ortak koordinat: özgün görüntü pikselleri.\n'
                         'Anotasyon ve PNG kanıtı doğrulanmış sayılmaz.',10,GREY).pack(anchor='w')
        right=tk.Frame(self.layer_tab,bg=BG);right.pack(side='left',fill='both',expand=True)
        bar=tk.Frame(right,bg=PANEL);bar.pack(fill='x')
        for name,command in [('+ Yakınlaştır',lambda:self._zoom(1.2)),
                             ('− Uzaklaştır',lambda:self._zoom(1/1.2)),
                             ('Görüntüye Sığdır',self._fit),('Görünümü Yenile',self._draw)]:
            self._button(bar,name,command).pack(side='left',padx=4,pady=5)
        self.canvas=tk.Canvas(right,bg=NAV,highlightthickness=0,cursor='fleur')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<ButtonPress-1>',self._pan_start)
        self.canvas.bind('<B1-Motion>',self._pan_move)
        self.canvas.bind('<MouseWheel>',self._wheel)
        self.canvas.bind('<Configure>',lambda event:self._draw())

    def _image_chosen(self,event):
        sel=self.images_list.curselection()
        if sel:self.select_image(sel[0])

    def select_image(self,index):
        self.image_index=index
        if self.images_list.curselection()!=(index,):
            self.images_list.selection_clear(0,'end');self.images_list.selection_set(index)
        self.scale=1.;self.pan_x=self.pan_y=0
        for child in self.layer_frame.winfo_children():child.destroy()
        self.layer_states={}
        try:
            img=self.images[index]
            self.annotation=annotation_layers(self.project,img['sha256'])
            self.overlays=image_overlays(self.project,img['sha256'])
            layers=[('Özgün',None)] + [(a['id'],a) for a in self.annotation] + [
                ('PNG: '+a['name'],a) for a in self.overlays]
            for name,item in layers:
                state=tk.BooleanVar(value=True)
                self.layer_states[name]=state
                tk.Checkbutton(self.layer_frame,text=name,variable=state,command=self._draw,
                    fg=FG,bg=PANEL,selectcolor=NAV,activebackground=PANEL,
                    activeforeground=FG,anchor='w').pack(fill='x')
            self.status.set('Görüntü: '+img['name']+' · SHA-256 denetlendi · Katmanlar kullanıcı kaynaklı')
            self._draw()
        except (ReviewError,OSError) as exc:self._error(exc)

    def _draw(self):
        if self.image_index is None or not self.canvas.winfo_exists():return
        try:
            from PIL import Image, ImageDraw, ImageTk
            entry=self.images[self.image_index]
            path,_=_image_match(self.project,entry['sha256'])
            with Image.open(path) as f:base=f.convert('RGBA')
            # Never resample world/pixel geometry before drawing the overlays.
            for overlay in self.overlays:
                key='PNG: '+overlay['name']
                if self.layer_states[key].get():
                    with Image.open(overlay['path']) as f: layer=f.convert('RGBA')
                    if layer.size != base.size:
                        raise ReviewError('Katman çözünürlüğü değişmiş')
                    base=Image.alpha_composite(base,layer)
            ink=Image.new('RGBA',base.size,(0,0,0,0))
            pen=ImageDraw.Draw(ink)
            for annotation in self.annotation:
                if not self.layer_states[annotation['id']].get():continue
                for mark in annotation['marks']:
                    pts=[tuple(p) for p in mark['points']]
                    kind=mark['kind'];color='#11ddff'
                    if kind=='point':
                        x,y=pts[0];pen.ellipse((x-4,y-4,x+4,y+4),outline=color,width=2)
                    elif kind=='rectangle':
                        x1,y1=pts[0];x2,y2=pts[1]
                        pen.rectangle((min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2)),outline=color,width=3)
                    elif kind=='polygon':pen.line(pts+[pts[0]],fill=color,width=3)
                    else:pen.line(pts,fill=color,width=3)
            base=Image.alpha_composite(base,ink)
            w=max(1,int(base.width*self.scale));h=max(1,int(base.height*self.scale))
            if w*h>60_000_000:
                self.status.set('Görünüm belleği limiti; uzaklaştırın');return
            base=base.resize((w,h),resample=Image.Resampling.LANCZOS).convert('RGB')
            self.tk_image=ImageTk.PhotoImage(base)
            self.canvas.delete('all')
            self.canvas.create_image(self.pan_x,self.pan_y,anchor='nw',image=self.tk_image)
        except (ReviewError,OSError,ValueError,ImportError,KeyError) as exc:
            self.status.set('Görsel görüntüleme hatası: '+str(exc))

    def _zoom(self,factor):
        self.scale=min(8.0,max(0.05,self.scale*factor));self._draw()

    def _fit(self):
        if self.image_index is None:return
        try:
            from PIL import Image
            path,_=_image_match(self.project,self.images[self.image_index]['sha256'])
            with Image.open(path) as f:w,h=f.size
            self.scale=max(0.05,min(8.0,self.canvas.winfo_width()/w,self.canvas.winfo_height()/h))
            self.pan_x=self.pan_y=0;self._draw()
        except (ReviewError,OSError,ImportError) as exc:self._error(exc)

    def _wheel(self,event):self._zoom(1.10 if event.delta>0 else 1/1.10)
    def _pan_start(self,event):self.drag=(event.x,event.y,self.pan_x,self.pan_y)
    def _pan_move(self,event):
        if not hasattr(self,'drag'):return
        x,y,x0,y0=self.drag;self.pan_x=x0+event.x-x;self.pan_y=y0+event.y-y;self._draw()

    def _add_overlay(self):
        if self.image_index is None:return
        path=filedialog.askopenfilename(parent=self,filetypes=[('PNG','*.png')])
        if not path:return
        try:
            register_overlay(self.project,self.images[self.image_index]['sha256'],path)
            self.select_image(self.image_index)
        except (ReviewError,OSError) as exc:self._error(exc)

    def _make_finding_tab(self):
        left=tk.Frame(self.finding_tab,bg=PANEL,width=370,padx=8,pady=8)
        left.pack(side='left',fill='y',padx=(0,9));left.pack_propagate(False)
        self._label(left,'E03 raporunu seçin',12,CYAN).pack(anchor='w')
        self.report_select=ttk.Combobox(left,state='readonly',values=[r['id'] for r in self.reports])
        self.report_select.pack(fill='x',pady=5)
        self.report_select.bind('<<ComboboxSelected>>',lambda event:self.select_report(self.report_select.current()))
        self._label(left,'Fiziksel kanıt kayıtları',11,CYAN).pack(anchor='w',pady=(12,0))
        self.findings_list=tk.Listbox(left,bg=NAV,fg=FG,selectbackground=BLUE,
                                       exportselection=False)
        self.findings_list.pack(fill='both',expand=True,pady=7)
        self.findings_list.bind('<<ListboxSelect>>',self._finding_chosen)
        self._button(left,'Seçili Bulgu ↔ Görüntü Bağla',self._bind_image).pack(fill='x',pady=8)
        self._label(left,'Bağlantı kullanıcı beyanıdır;\nözgün görüntü kanıtı değildir.',10,GREY).pack(anchor='w')
        right=tk.Frame(self.finding_tab,bg=PANEL,padx=12,pady=10)
        right.pack(side='left',fill='both',expand=True)
        self._label(right,'Seçili ölçüm · E01 + E02 bağımlılık açıklaması',12,CYAN).pack(anchor='w')
        self.finding_text=tk.Text(right,wrap='word',bg=NAV,fg=FG,relief='flat',
                                  font=('Consolas',10),padx=12,pady=12)
        self.finding_text.pack(fill='both',expand=True,pady=8)
        self.finding_text.configure(state='disabled')

    def select_report(self,index):
        if not 0<=index<len(self.reports):return
        self.report_index=index
        self.report_select.current(index)
        try:
            item=self.reports[index];self.report=read_report(self.project,item['id'])
            self.findings=self.report.get('findings',[])
            self.findings_list.delete(0,'end')
            for f in self.findings:
                self.findings_list.insert('end',str(f.get('record_id','?')))
            self.record_id=None
            self._draw_graph()
            self._list_reports()
            self.status.set('Rapor: '+item['id']+' · Gerçek kamera kökeni doğrulanmadı')
        except (ReviewError,ValueError,OSError) as exc:self._error(exc)

    def _finding_chosen(self,event):
        sel=self.findings_list.curselection()
        if sel:
            self.record_id=self.findings[sel[0]]['record_id']
            self._show_finding(self.findings[sel[0]])

    def _show_finding(self,f):
        info={'record_id':f.get('record_id'), 'physical_claim':f.get('physical_claim'),
              'measurement':f.get('measurement'),'uncertainty':f.get('uncertainty'),
              'assumptions':f.get('assumptions'),'provenance':f.get('provenance'),
              'single_test':f.get('single_test'),'dependency':f.get('dependency'),
              'explanation':f.get('explanation'),
              'linked_images':linked_images(self.project,self.reports[self.report_index]['id'],f['record_id']),
              'origin': 'NO_AI_ORIGIN_CONCLUSION'}
        self.finding_text.configure(state='normal');self.finding_text.delete('1.0','end')
        self.finding_text.insert('1.0',json.dumps(info,indent=2,ensure_ascii=False))
        self.finding_text.configure(state='disabled')

    def _bind_image(self):
        if self.report_index is None or self.record_id is None or not self.images:
            return self._error(ReviewError('Önce E03 bulgusu ve proje görüntüsü seçin'))
        if self.image_index is None:return self._error(ReviewError('Görsel Katmanlar sayfasından görüntü seçin'))
        if not messagebox.askyesno('Kaynak bağlantısı',
            'Seçilen bulguyu görüntüye kullanıcı beyanıyla bağla?\n'
            'Bu işlem bağımsız kanıt doğrulaması değildir.',parent=self):return
        try:
            bind_finding_to_image(self.project,self.reports[self.report_index]['id'],
                                  self.record_id,self.images[self.image_index]['sha256'])
            f=next(f for f in self.findings if f['record_id']==self.record_id)
            self._show_finding(f)
        except (ReviewError,OSError,ValueError) as exc:self._error(exc)

    def _make_graph_tab(self):
        upper=tk.Frame(self.graph_tab,bg=PANEL,padx=8,pady=8);upper.pack(fill='x')
        self._label(upper,'Yalnız E03 raporundaki gerçek lineage ve bildirilen bağımlılıklar',11,GREY).pack(side='left')
        self._button(upper,'Grafiği Yenile',self._draw_graph).pack(side='right')
        self.graph=tk.Canvas(self.graph_tab,bg=NAV,highlightthickness=0)
        self.graph.pack(fill='both',expand=True,padx=8,pady=8)
        self.graph.bind('<Configure>',lambda event:self._draw_graph())

    def _draw_graph(self):
        if not hasattr(self,'graph'):return
        self.graph.delete('all')
        if not getattr(self,'report',None) or self.report.get('schema_version')!='p8.e03.v1':
            self.graph.create_text(300,150,text='Bağımlılık grafiği için E03 raporunu seçin',fill=FG)
            return
        try: data=dependency_graph(self.report)
        except ReviewError as exc:return self._error(exc)
        nodes=data['nodes'][:120]
        if not nodes:return
        positions={}
        width=max(450,self.graph.winfo_width())
        cols=max(1,min(5,int(width/250)))
        for ix,node in enumerate(nodes):
            col,row=ix%cols,ix//cols
            x,y=32+col*(width/cols),38+row*95
            positions[node['id']]=(x,y)
        for edge in data['edges'][:300]:
            if edge['from'] in positions and edge['to'] in positions:
                a,b=positions[edge['from']],positions[edge['to']]
                self.graph.create_line(a[0]+85,a[1]+28,b[0]+85,b[1]+28,
                                       fill='#d2a83a',width=2,arrow='last')
        for node in nodes:
            x,y=positions[node['id']]
            self.graph.create_rectangle(x,y,x+190,y+56,outline=CYAN,fill=PANEL,width=2)
            self.graph.create_text(x+9,y+14,anchor='w',text=node['id'][:27],fill=FG)
            self.graph.create_text(x+9,y+37,anchor='w',text=str(node['group'])[:28],fill=GREY)
        if len(data['nodes'])>120 or len(data['edges'])>300:
            self.status.set('Grafik sınırlandı; tüm düğümler/kenarlar JSON raporunda')

    def _make_report_tab(self):
        p=tk.Frame(self.report_tab,bg=PANEL,padx=12,pady=12);p.pack(fill='both',expand=True)
        self._label(p,'Gerçek P8-E01 / E02 / E03 rapor dosyaları',13,CYAN).pack(anchor='w')
        self.report_tree=ttk.Treeview(p,columns=('type','state','sha'),show='tree headings')
        self.report_tree.heading('#0',text='Rapor dosyası');self.report_tree.column('#0',width=460)
        for col,label in [('type','Şema'),('state','Durum'),('sha','SHA-256')]:
            self.report_tree.heading(col,text=label);self.report_tree.column(col,width=180)
        self.report_tree.pack(fill='both',expand=True,pady=8)
        self.report_tree.bind('<Double-1>',lambda event:self._open_selected_report())
        actions=tk.Frame(p,bg=PANEL);actions.pack(fill='x')
        self._button(actions,'Seçileni Aç',self._open_selected_report).pack(side='left',padx=4)
        self._button(actions,'E03 HTML Raporunu Tarayıcıda Aç',self._open_html).pack(side='left',padx=4)
        self._label(p,'PDF/dijital imza üretimi yok. JSON/HTML ve ZIP mevcut.',10,GREY).pack(anchor='w',pady=10)
        self._list_reports()

    def _list_reports(self):
        if not hasattr(self,'report_tree'):return
        for row in self.report_tree.get_children():self.report_tree.delete(row)
        for i,r in enumerate(self.reports):
            self.report_tree.insert('', 'end', iid=str(i), text=r['id'],
                                    values=(r['schema_version'],r['overall_state'],r['sha256'][:20]))

    def _selected_report(self):
        sel=self.report_tree.selection()
        if sel:return self.reports[int(sel[0])]
        if self.report_index is not None:return self.reports[self.report_index]
        raise ReviewError('Önce rapor seçin')

    def _open_selected_report(self):
        try:
            item=self._selected_report()
            self.select_report(self.reports.index(item));self.tabs.select(self.finding_tab)
        except (ReviewError,OSError) as exc:self._error(exc)

    def _open_html(self):
        try:
            item=self._selected_report()
            if item['schema_version']!='p8.e03.v1':
                raise ReviewError('HTML inceleyici için E03 raporu seçin')
            candidate=item['path'].with_suffix('.html')
            if not candidate.is_file():raise ReviewError('HTML raporu üretilmemiş')
            webbrowser.open(candidate.resolve().as_uri())
        except (ReviewError,OSError) as exc:self._error(exc)

    def _error(self,exc):
        self.status.set(str(exc))
        messagebox.showerror('FakeProofImageAI',str(exc),parent=self)
