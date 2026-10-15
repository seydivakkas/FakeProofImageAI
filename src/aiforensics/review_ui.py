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
from .ui_readability import (
    filter_findings, finding_page, format_finding, graph_point, clamp_zoom,
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
        self.title('FakeProofImageAI — P9-I10 Açıklanabilir Kanıt Gezgini')
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
        self.finding_query = tk.StringVar(value="")
        self.finding_filter = tk.StringVar(value="TÜMÜ")
        self.detail_mode = tk.StringVar(value="Açıklama")
        self.finding_page_no = 0
        self.visible_findings = []
        self.page_findings = []
        self.graph_zoom = 1.0
        self.graph_pan_x = 0.0
        self.graph_pan_y = 0.0
        self.graph_node_positions = {}
        self.graph_selected = None
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
        self._label(left,'Fiziksel kanıt kayıtları · kaynaklı E03',11,CYAN).pack(anchor='w',pady=(12,0))
        search=tk.Frame(left,bg=PANEL);search.pack(fill='x',pady=(6,3))
        self._label(search,'Ara (Ctrl+F)',10,GREY).pack(anchor='w')
        self.search_entry=ttk.Entry(search,textvariable=self.finding_query)
        self.search_entry.pack(fill='x')
        self.search_entry.bind('<Escape>',lambda event:self.finding_query.set(""))
        self.state_picker=ttk.Combobox(left,textvariable=self.finding_filter,state='readonly',
            values=('TÜMÜ','INDETERMINATE','CONSISTENT_UNDER_ASSUMPTIONS',
                    'INCONSISTENT_UNDER_ASSUMPTIONS','NOT_EVALUATED'))
        self.state_picker.pack(fill='x',pady=(0,4))
        self.finding_counter=tk.StringVar(value='0 bulgu')
        self._label(left,'Görünür kayıtlar (sayfalı)',10,GREY).pack(anchor='w')
        tk.Label(left,textvariable=self.finding_counter,bg=PANEL,fg=GREY,
                 font=('Segoe UI',9),anchor='w').pack(fill='x')
        self.findings_list=tk.Listbox(left,bg=NAV,fg=FG,selectbackground=BLUE,
                                       exportselection=False)
        self.findings_list.pack(fill='both',expand=True,pady=7)
        self.findings_list.bind('<<ListboxSelect>>',self._finding_chosen)
        pager=tk.Frame(left,bg=PANEL);pager.pack(fill='x')
        self._button(pager,'◀ Önceki',lambda:self._change_page(-1)).pack(side='left',padx=3)
        self._button(pager,'Sonraki ▶',lambda:self._change_page(1)).pack(side='left',padx=3)
        self.finding_query.trace_add('write',lambda *_:self._update_findings())
        self.finding_filter.trace_add('write',lambda *_:self._update_findings())
        self._button(left,'Seçili Bulgu ↔ Görüntü Bağla',self._bind_image).pack(fill='x',pady=8)
        self._button(left,'Seçili Bulguda Görüntü Bölgesine Git',self._focus_finding).pack(fill='x',pady=8)
        self._label(left,'Bağlantı kullanıcı beyanıdır;\nözgün görüntü kanıtı değildir.',10,GREY).pack(anchor='w')
        right=tk.Frame(self.finding_tab,bg=PANEL,padx=12,pady=10)
        right.pack(side='left',fill='both',expand=True)
        self._label(right,'Ölçüm / belirsizlik / varsayım / kaynak',12,CYAN).pack(anchor='w')
        options=tk.Frame(right,bg=PANEL);options.pack(fill='x',pady=3)
        for kind in ('Açıklama','Ham JSON'):
            tk.Radiobutton(options,text=kind,value=kind,variable=self.detail_mode,
                command=self._render_selected_finding,bg=PANEL,fg=FG,
                selectcolor=NAV,activebackground=PANEL).pack(side='left',padx=5)
        tk.Button(options,text='Ctrl+F: Ara · F3: Sonraki',bg=PANEL,fg=GREY,
                  relief='flat',takefocus=False).pack(side='right')
        detail=tk.Frame(right,bg=NAV);detail.pack(fill='both',expand=True,pady=8)
        scrollbar=ttk.Scrollbar(detail,orient='vertical')
        scrollbar.pack(side='right',fill='y')
        self.finding_text=tk.Text(detail,wrap='word',bg=NAV,fg=FG,relief='flat',
                                  font=('Consolas',10),padx=12,pady=12,
                                  yscrollcommand=scrollbar.set)
        self.finding_text.pack(side='left',fill='both',expand=True)
        scrollbar.configure(command=self.finding_text.yview)
        self.finding_text.configure(state='disabled')
        self.bind('<Control-f>',lambda event:(self.tabs.select(self.finding_tab),
                                             self.search_entry.focus_set()))
        self.bind('<F3>',lambda event:self._navigate_finding(1))
        self.bind('<Shift-F3>',lambda event:self._navigate_finding(-1))

    def select_report(self,index):
        if not 0<=index<len(self.reports):return
        self.report_index=index
        self.report_select.current(index)
        try:
            item=self.reports[index];self.report=read_report(self.project,item['id'])
            self.findings=self.report.get('findings',[])
            self.record_id=None
            self.finding_page_no=0
            self._update_findings()
            self._set_finding_text("Bir bulgu seçin. Sayfalama ve filtreleme bilimsel kararları değiştirmez.")
            self._draw_graph()
            self._list_reports()
            self.status.set('Rapor: '+item['id']+' · Gerçek kamera kökeni doğrulanmadı')
        except (ReviewError,ValueError,OSError) as exc:self._error(exc)

    def _set_finding_text(self,value):
        self.finding_text.configure(state='normal')
        self.finding_text.delete('1.0','end')
        self.finding_text.insert('1.0',value)
        self.finding_text.configure(state='disabled')

    def _update_findings(self):
        items=filter_findings(getattr(self,'findings',[]),
                               self.finding_query.get(),self.finding_filter.get())
        page=finding_page(items,self.finding_page_no)
        self.finding_page_no=page['page']
        self.visible_findings=items
        self.page_findings=page['items']
        self.findings_list.delete(0,'end')
        for finding in self.page_findings:
            self.findings_list.insert('end',str(finding.get('record_id','?')))
        self.finding_counter.set(
            f"{page['total']} kayıt · sayfa {page['page']+1}/{page['pages']} · "
            "ilk 40 kayıt gösterilir")

    def _change_page(self,direction):
        target=self.finding_page_no+direction
        if target<0 or target*40>=len(self.visible_findings):return
        self.finding_page_no=target
        self._update_findings()

    def _navigate_finding(self,step):
        if not self.page_findings:return
        selected=self.findings_list.curselection()
        i=(selected[0] if selected else (-1 if step>0 else 0))+step
        if i>=len(self.page_findings):
            self._change_page(1);i=0
        elif i<0:
            self._change_page(-1);i=len(self.page_findings)-1
        if not self.page_findings:return
        i=min(max(0,i),len(self.page_findings)-1)
        self.findings_list.selection_clear(0,'end')
        self.findings_list.selection_set(i)
        self.findings_list.see(i)
        self._finding_chosen(None)

    def _finding_chosen(self,event):
        selected=self.findings_list.curselection()
        if selected and selected[0]<len(self.page_findings):
            self.record_id=self.page_findings[selected[0]]['record_id']
            self._show_finding(self.page_findings[selected[0]])

    def _render_selected_finding(self):
        if self.record_id is None:return
        finding=next((x for x in getattr(self,'findings',[])
                      if x.get('record_id')==self.record_id),None)
        if finding:self._show_finding(finding)

    def _show_finding(self,f):
        linked=linked_images(self.project,self.reports[self.report_index]['id'],
                             f['record_id'])
        if self.detail_mode.get()=='Ham JSON':
            info=dict(f)
            info['linked_images']=linked
            content=json.dumps(info,indent=2,ensure_ascii=False,allow_nan=False)
            if len(content)>48000:
                content=content[:48000]+'\n[Önizleme sınırı. Tam kayıt E03 JSON raporunda.]'
        else:
            content=format_finding(f,linked)
        self._set_finding_text(content)

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

    def _focus_finding(self):
        """Open only an explicitly linked user-provenance ROI, no automatic localization."""
        if self.report_index is None or self.record_id is None or self.image_index is None:
            return self._error(ReviewError('E03 kaydı ve proje görüntüsü seçilmeli'))
        report_id=self.reports[self.report_index]['id']
        digest=self.images[self.image_index]['sha256']
        from .review_workspace import linked_images
        links=linked_images(self.project,report_id,self.record_id)
        if not any(x.get('sha256')==digest and
                   x.get('provenance')=='user_asserted_not_verified' for x in links):
            return self._error(ReviewError('Önce bu bulguyu seçili görüntüye elle bağlayın'))
        try:
            from .focus_view_ui import FindingFocusWindow
            FindingFocusWindow(self,self.project,report_id,self.record_id,digest)
        except (ReviewError,ValueError,OSError,TypeError,ImportError) as exc:
            self._error(exc)

    def _make_graph_tab(self):
        upper=tk.Frame(self.graph_tab,bg=PANEL,padx=8,pady=8);upper.pack(fill='x')
        self._label(upper,'Kaynaklı E03 grafiği · +/- yakınlaştır · oklar kaydır · Home sıfırla',
                    10,GREY).pack(side='left')
        for caption,fn in (('−',lambda:self._zoom_graph(1/1.2)),
                           ('+',lambda:self._zoom_graph(1.2)),
                           ('Sıfırla',self._reset_graph)):
            self._button(upper,caption,fn).pack(side='right',padx=3)
        self.graph=tk.Canvas(self.graph_tab,bg=NAV,highlightthickness=0,
                             takefocus=True,cursor='fleur')
        self.graph.pack(fill='both',expand=True,padx=8,pady=8)
        self.graph.bind('<Configure>',lambda event:self._draw_graph())
        self.graph.bind('<MouseWheel>',lambda e:self._zoom_graph(1.12 if e.delta>0 else 1/1.12))
        self.graph.bind('<Button-4>',lambda e:self._zoom_graph(1.12))
        self.graph.bind('<Button-5>',lambda e:self._zoom_graph(1/1.12))
        self.graph.bind('<Key-plus>',lambda e:self._zoom_graph(1.2))
        self.graph.bind('<Key-equal>',lambda e:self._zoom_graph(1.2))
        self.graph.bind('<Key-minus>',lambda e:self._zoom_graph(1/1.2))
        self.graph.bind('<Home>',lambda e:self._reset_graph())
        for key,dx,dy in (('<Left>',-35,0),('<Right>',35,0),
                          ('<Up>',0,-35),('<Down>',0,35)):
            self.graph.bind(key,lambda e,dx=dx,dy=dy:self._pan_graph(dx,dy))
        self.graph.bind('<ButtonPress-1>',self._graph_press)
        self.graph.bind('<B1-Motion>',self._graph_drag)
        self.graph.bind('<ButtonRelease-1>',self._graph_pick)

    def _reset_graph(self):
        self.graph_zoom=1.0
        self.graph_pan_x=self.graph_pan_y=0.0
        self._draw_graph()

    def _zoom_graph(self,factor):
        self.graph_zoom=clamp_zoom(self.graph_zoom*factor)
        self._draw_graph()

    def _pan_graph(self,dx,dy):
        self.graph_pan_x=max(-6000,min(6000,self.graph_pan_x+dx))
        self.graph_pan_y=max(-6000,min(6000,self.graph_pan_y+dy))
        self._draw_graph()

    def _graph_press(self,event):
        self.graph.focus_set()
        self._drag_start=(event.x,event.y,self.graph_pan_x,self.graph_pan_y)

    def _graph_drag(self,event):
        if not hasattr(self,'_drag_start'):return
        x,y,old_x,old_y=self._drag_start
        self.graph_pan_x=max(-6000,min(6000,old_x+event.x-x))
        self.graph_pan_y=max(-6000,min(6000,old_y+event.y-y))
        self._draw_graph()

    def _graph_pick(self,event):
        if not hasattr(self,'_drag_start'):return
        x,y,_,_=self._drag_start
        del self._drag_start
        if abs(event.x-x)+abs(event.y-y)>8:return
        for rid,(left,top,w,h) in self.graph_node_positions.items():
            if left<=event.x<=left+w and top<=event.y<=top+h:
                self.graph_selected=rid
                self.status.set("Seçili kaynak E03 kaydı: "+rid+
                                " · ayrıntı için Kanıt İnceleme sekmesi")
                self._draw_graph()
                self.finding_query.set(rid)
                self.tabs.select(self.finding_tab)
                if self.page_findings:
                    self.findings_list.selection_clear(0,'end')
                    self.findings_list.selection_set(0)
                    self._finding_chosen(None)
                break

    def _draw_graph(self):
        if not hasattr(self,'graph'):return
        self.graph.delete('all')
        self.graph_node_positions={}
        if not getattr(self,'report',None) or self.report.get('schema_version')!='p8.e03.v1':
            self.graph.create_text(300,150,text='Bağımlılık grafiği için E03 raporunu seçin',fill=FG)
            return
        try:data=dependency_graph(self.report)
        except ReviewError as exc:return self._error(exc)
        nodes=data['nodes'][:120]
        if not nodes:return
        width=max(450,self.graph.winfo_width())
        cols=max(1,min(5,int(width/250)))
        positions={}
        for ix,node in enumerate(nodes):
            col,row=ix%cols,ix//cols
            base_x,base_y=32+col*(width/cols),38+row*95
            x,y=graph_point(base_x,base_y,self.graph_zoom,
                            self.graph_pan_x,self.graph_pan_y)
            positions[node['id']]=(x,y)
        for edge in data['edges'][:300]:
            if edge['from'] in positions and edge['to'] in positions:
                a,b=positions[edge['from']],positions[edge['to']]
                dx,dy=85*self.graph_zoom,28*self.graph_zoom
                self.graph.create_line(a[0]+dx,a[1]+dy,b[0]+dx,b[1]+dy,
                                       fill='#d2a83a',width=2,arrow='last')
        for node in nodes:
            rid=node['id']
            x,y=positions[rid]
            w,h=190*self.graph_zoom,56*self.graph_zoom
            self.graph_node_positions[rid]=(x,y,w,h)
            self.graph.create_rectangle(x,y,x+w,y+h,
                   outline='#f3bf66' if rid==self.graph_selected else CYAN,
                   fill=PANEL,width=3 if rid==self.graph_selected else 2)
            self.graph.create_text(x+9*self.graph_zoom,y+14*self.graph_zoom,
                                   anchor='w',text=rid[:27],fill=FG)
            self.graph.create_text(x+9*self.graph_zoom,y+37*self.graph_zoom,
                                   anchor='w',text=str(node['group'])[:28],fill=GREY)
        if len(data['nodes'])>120 or len(data['edges'])>300:
            self.status.set('Grafik yalnız ilk 120 düğüm/300 kenarı gösterir; tümü JSON raporunda')

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
