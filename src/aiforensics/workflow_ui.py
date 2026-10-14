"""P9-I03: module-specific, typed nested-JSON forms + guarded desktop run queue.

Offline Tkinter extension to P9-I01. No implicit image-to-physics inference.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .workflow_planner import (
    FORM_CATALOG, WorkflowError, build_execution_plan, execute_plan,
    field_path_label, list_form_fields, load_form_data, load_synthetic_example,
    save_form_data, structural_checks, update_form_field,
)

BG='#0a1420'; PANEL='#142639'; NAV='#0d1e30'; FG='#eef6ff'
BLUE='#1976d2'; CYAN='#19c5ff'; GREY='#abbfd1'


class WorkflowWindow(tk.Toplevel):
    def __init__(self,master,project,*,initial_module='P1-G02'):
        super().__init__(master)
        self.title('FakeProofImageAI — P9-I03 Modül Formları ve Çalıştırma Planı')
        self.geometry('1230x790');self.minsize(1000,640);self.configure(bg=BG)
        self.project=project
        self.initial_module=initial_module if initial_module in FORM_CATALOG else 'P1-G02'
        self.paths={};self.docs={};self.selected=self.initial_module
        self.plan=None;self.busy=False;self.stop=threading.Event()
        self.state=tk.StringVar(value='Hazır · JSON alanları fiziksel kalibrasyon kanıtı değildir')
        self._build()
        self.select_module(self.initial_module)

    def button(self,frame,text,action,primary=False):
        return tk.Button(frame,text=text,command=action,relief='flat',
                         bg=BLUE if primary else '#294057',fg=FG,
                         activebackground='#307db6',activeforeground=FG,
                         cursor='hand2',padx=10,pady=6)

    def _build(self):
        header=tk.Frame(self,bg=NAV,padx=18,pady=12);header.pack(fill='x')
        tk.Label(header,text='P9-I03 | Veri Formları ve Güvenli İş Akışı',bg=NAV,fg=FG,
                 font=('Segoe UI',15,'bold')).pack(side='left')
        tk.Label(header,text='Yerel · 27 modül · Gerçek kamera kabulü SON AŞAMA',
                 bg=NAV,fg=GREY).pack(side='right')
        body=tk.PanedWindow(self,orient='horizontal',bg=BG,bd=0,sashwidth=6)
        body.pack(fill='both',expand=True,padx=12,pady=12)
        left=tk.Frame(body,bg=PANEL,padx=10,pady=10);body.add(left,minsize=265,width=295)
        tk.Label(left,text='Modül kataloğu',bg=PANEL,fg=CYAN,font=('Segoe UI',13,'bold')).pack(anchor='w')
        self.module_list=tk.Listbox(left,bg=NAV,fg=FG,selectbackground=BLUE,
                                   activestyle='none',font=('Segoe UI',10),
                                   borderwidth=0,highlightthickness=0,exportselection=False)
        self.module_list.pack(fill='both',expand=True,pady=8)
        self.module_ids=list(FORM_CATALOG)
        for mid in self.module_ids:self.module_list.insert('end',f'{mid} · {FORM_CATALOG[mid].title}')
        self.module_list.bind('<<ListboxSelect>>',self._list_click)
        tk.Label(left,text='Modül seçili iken plan sırasına ekle; her\nmodül için girdi dosyası ayrıca belirtilir.',
                 bg=PANEL,fg=GREY,justify='left',wraplength=265).pack(anchor='w')
        self.button(left,'Seçili Modülü Plana Ekle',self.add_current_to_plan,True).pack(fill='x',pady=7)
        right=tk.Frame(body,bg=BG);body.add(right,minsize=625)
        notebook=ttk.Notebook(right);notebook.pack(fill='both',expand=True)
        self.form_page=tk.Frame(notebook,bg=PANEL,padx=12,pady=10)
        self.plan_page=tk.Frame(notebook,bg=PANEL,padx=12,pady=10)
        notebook.add(self.form_page,text='Modüle Özel Form')
        notebook.add(self.plan_page,text='Önkoşullar ve Çalıştırma Planı')
        self._form_page()
        self._plan_page()
        tk.Label(self,textvariable=self.state,bg=NAV,fg=GREY,
                 anchor='w',padx=15,pady=7).pack(fill='x')

    def _form_page(self):
        self.form_title=tk.Label(self.form_page,text='',bg=PANEL,fg=CYAN,
                                 font=('Segoe UI',13,'bold'),anchor='w')
        self.form_title.pack(fill='x')
        self.form_provenance=tk.Label(self.form_page,text='',bg=PANEL,fg=GREY,
                    wraplength=800,justify='left',anchor='w')
        self.form_provenance.pack(fill='x',pady=5)
        controls=tk.Frame(self.form_page,bg=PANEL);controls.pack(fill='x',pady=6)
        self.button(controls,'Manifest Aç',self.open_manifest,True).pack(side='left',padx=2)
        self.button(controls,'Sentetik Örnek Oluştur',self.make_example).pack(side='left',padx=2)
        self.button(controls,'Alanı Düzenle',self.edit_field).pack(side='left',padx=2)
        self.button(controls,'Kaydet',self.save_manifest).pack(side='left',padx=2)
        self.form_input=tk.StringVar(value='Girdi seçilmedi')
        tk.Label(self.form_page,textvariable=self.form_input,bg=PANEL,fg=GREY,
                 anchor='w',wraplength=780).pack(fill='x',pady=(0,7))
        self.fields=ttk.Treeview(self.form_page,columns=('path','kind','value'),show='headings')
        for c,w in [('path',330),('kind',115),('value',390)]:
            self.fields.heading(c,text={'path':'JSON alanı','kind':'Veri tipi','value':'Değer / Koleksiyon'}[c]);
            self.fields.column(c,width=w,stretch=(c!='kind'))
        self.fields.pack(fill='both',expand=True)
        self.fields.bind('<Double-1>',lambda _e:self.edit_field())
        self.validation=tk.StringVar(value='Bağımsız kalibrasyon veya ölçüm doğrulaması henüz yapılmadı')
        tk.Label(self.form_page,textvariable=self.validation,bg=PANEL,fg=CYAN,
                 wraplength=820,justify='left').pack(anchor='w',pady=8)

    def _plan_page(self):
        tk.Label(self.plan_page,text='Gerçek CLI komutları · görünür girdi / bağımlılık denetimi',
                 bg=PANEL,fg=CYAN,font=('Segoe UI',13,'bold')).pack(anchor='w')
        ctl=tk.Frame(self.plan_page,bg=PANEL);ctl.pack(fill='x',pady=10)
        self.button(ctl,'Seçili Modülü Ekle',self.add_current_to_plan,True).pack(side='left',padx=3)
        self.button(ctl,'Sırayı Hesapla',self.compile_plan).pack(side='left',padx=3)
        self.button(ctl,'Planı JSON Kaydet',self.save_plan).pack(side='left',padx=3)
        self.button(ctl,'Çalıştır',self.execute,True).pack(side='left',padx=3)
        self.button(ctl,'Sonraki Adımda Durdur',self.request_stop).pack(side='left',padx=3)
        self.queue=ttk.Treeview(self.plan_page,columns=('mod','cmd','state','input','reason'),show='headings',height=11)
        for c,label,width in [('mod','Modül',90),('cmd','CLI',210),('state','Durum',125),
                              ('input','Girdi',175),('reason','Engel / Önkoşul',280)]:
            self.queue.heading(c,text=label);self.queue.column(c,width=width,stretch=True)
        self.queue.pack(fill='both',expand=True,pady=4)
        self.queue.bind('<Double-1>',lambda _e:self.choose_step_input())
        self.button(self.plan_page,'Seçili Adıma Girdi Dosyası Ata',self.choose_step_input).pack(anchor='w',pady=7)
        self.plan_info=tk.StringVar(value='Birden fazla modül seçin; diğer modüllerin verileri üretilmiş varsayılmaz.')
        tk.Label(self.plan_page,textvariable=self.plan_info,bg=PANEL,fg=GREY,
                 justify='left',wraplength=825).pack(anchor='w',pady=6)
        self.log=tk.Text(self.plan_page,bg=NAV,fg=FG,height=7,wrap='word',font=('Consolas',9))
        self.log.pack(fill='x',pady=4)
        self.queued=[]

    def _list_click(self,_event):
        index=self.module_list.curselection()
        if index:self.select_module(self.module_ids[index[0]])

    def select_module(self,mid):
        self.selected=mid
        ix=self.module_ids.index(mid)
        if self.module_list.curselection()!=(ix,):
            self.module_list.selection_clear(0,'end');self.module_list.selection_set(ix)
            self.module_list.see(ix)
        spec=FORM_CATALOG[mid]
        self.form_title.configure(text=f'{mid} — {spec.title} ({spec.input_kind.upper()})')
        self.form_provenance.configure(text=spec.provenance_rule+'\n'+spec.notes)
        self.form_input.set(str(self.paths.get(mid) or 'Girdi seçilmedi'))
        self.refresh_fields()

    def refresh_fields(self):
        for child in self.fields.get_children():self.fields.delete(child)
        doc=self.docs.get(self.selected)
        if doc is None:
            self.validation.set('Modül için ayrı JSON/görüntü girdisi seçilmelidir.')
            return
        self._field_rows=list_form_fields(doc)
        for ix,row in enumerate(self._field_rows):
            text=str(row['value']).replace('\n',' ')[:165]
            self.fields.insert('','end',iid=str(ix),values=(field_path_label(row['path']),row['kind'],text))
        problems=structural_checks(self.selected,doc)
        self.validation.set('Yapısal eksikler: '+'; '.join(problems) if problems else
                            'Yapısal üst alanlar mevcut. Bu fiziksel/istatistiksel geçerlilik onayı DEĞİLDİR.')

    def _warn(self,exc):
        self.state.set(str(exc))
        messagebox.showerror('P9-I03',str(exc),parent=self)

    def open_manifest(self):
        spec=FORM_CATALOG[self.selected]
        if spec.input_kind=='image':
            allowed=[('Görüntü','*.png *.jpg *.jpeg *.tif *.tiff *.bmp')]
        else:allowed=[('JSON','*.json')]
        chosen=filedialog.askopenfilename(parent=self,filetypes=allowed)
        if not chosen:return
        try:
            if spec.input_kind=='json':self.docs[self.selected]=load_form_data(self.selected,chosen)
            self.paths[self.selected]=chosen
            self.plan=None
            self.select_module(self.selected)
            self.state.set(self.selected+' için açık girdi: '+chosen)
        except (WorkflowError,OSError,ValueError) as e:self._warn(e)

    def make_example(self):
        if self.selected=='P1-G01':return self._warn(WorkflowError('G01 için gerçek/sentetik görüntü seçin'))
        dest=self.project.root/'manifests'/'p9_i03_synthetic'/self.selected
        try:
            path,document=load_synthetic_example(self.selected,destination=dest)
            self.docs[self.selected]=document;self.paths[self.selected]=str(path)
            self.plan=None;self.select_module(self.selected)
            self.state.set('SENTETİK örnek; gerçek kamera kalibrasyonu DEĞİLDİR: '+str(path))
        except (OSError,ValueError,WorkflowError) as exc:self._warn(exc)

    def edit_field(self):
        doc=self.docs.get(self.selected);selection=self.fields.selection()
        if doc is None or not selection:return
        row=self._field_rows[int(selection[0])];path=row['path'];old=doc
        for key in path:old=old[key]
        value=json.dumps(old,ensure_ascii=False,indent=2) if not isinstance(old,str) else old
        editor=tk.Toplevel(self);editor.title('Tür korumalı alan · '+field_path_label(path))
        editor.geometry('680x420');editor.configure(bg=PANEL)
        tk.Label(editor,text=f'{field_path_label(path)}  [{row["kind"]}]',
                 bg=PANEL,fg=CYAN,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=12,pady=8)
        entry=tk.Text(editor,wrap='none',bg=NAV,fg=FG,insertbackground=CYAN)
        entry.pack(fill='both',expand=True,padx=12,pady=8);entry.insert('1.0',value)
        def save():
            try:
                text=entry.get('1.0','end-1c')
                self.docs[self.selected]=update_form_field(doc,path,text)
                self.refresh_fields();self.plan=None;editor.destroy()
                self.state.set('Alan düzenlendi; kaydedilmemiş JSON değişiklikleri var')
            except (WorkflowError,ValueError) as exc:messagebox.showerror('Alan hatası',str(exc),parent=editor)
        self.button(editor,'Değişikliği Uygula',save,True).pack(pady=9)

    def save_manifest(self):
        doc=self.docs.get(self.selected)
        if doc is None:return self._warn(WorkflowError('Önce bir form/manifest yükleyin'))
        proposed=self.project.root/'manifests'/(self.selected.replace('-','_')+'_edited.json')
        target=filedialog.asksaveasfilename(parent=self,initialdir=str(proposed.parent),
                          initialfile=proposed.name,defaultextension='.json',filetypes=[('JSON','*.json')])
        if not target:return
        try:
            path=save_form_data(self.selected,doc,target)
            self.paths[self.selected]=str(path);self.plan=None
            self.select_module(self.selected)
            self.state.set('JSON kaydedildi: '+str(path))
        except (OSError,ValueError,WorkflowError) as exc:self._warn(exc)

    def add_current_to_plan(self):
        if self.selected not in self.queued:self.queued.append(self.selected)
        self.plan=None;self.refresh_queue()
        self.state.set(self.selected+' plan listesine eklendi; her adımda girdi zorunlu')

    def refresh_queue(self):
        for child in self.queue.get_children():self.queue.delete(child)
        steps=self.plan['steps'] if self.plan else [
            {'module_id':m,'command':FORM_CATALOG[m].command,
             'state':'PLANLANMADI','input_path':str(self.paths.get(m) or ''),'reasons':[]}
            for m in self.queued]
        for step in steps:
            m=step['module_id']
            self.queue.insert('','end',iid=m,values=(m,step['command'],step['state'],
                    Path(step['input_path']).name if step.get('input_path') else 'YOK',
                    '; '.join(step['reasons'])[:165]))

    def choose_step_input(self):
        sel=self.queue.selection()
        if not sel:return
        self.select_module(sel[0]);self.open_manifest()
        self.refresh_queue()

    def compile_plan(self):
        try:
            self.plan=build_execution_plan(self.queued,self.paths)
            self.refresh_queue()
            self.plan_info.set(f"{self.plan['ready_count']} hazır, {self.plan['blocked_count']} engelli. "
                'Sıra yalnız seçili modüllerin tercihiyle kurulur; kalibrasyon otomatik aktarılmaz.')
            return self.plan
        except (WorkflowError,OSError,ValueError) as exc:
            self._warn(exc);return None

    def save_plan(self):
        plan=self.compile_plan()
        if plan is None:return
        target=self.project.root/'manifests'/'p9_i03_execution_plan.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding='utf-8')
        self.state.set('Plan kaydedildi: '+str(target))

    def request_stop(self):
        self.stop.set();self.state.set('Güvenli durdurma istendi; çalışan modül tamamlandıktan sonra duracak')

    def execute(self):
        if self.busy:return
        plan=self.compile_plan()
        if plan is None:return
        if plan['blocked_count']:
            return self._warn(WorkflowError('Engelli adımlar var: önce eksik JSON/görüntü girdilerini tamamlayın'))
        self.stop.clear();self.busy=True
        self.log.insert('end','Plan başladı · Girdilerin SHA-256 değerleri yeniden kontrol edilecek.\n')
        def emit(entry):
            self.after(0,lambda e=dict(entry):self._log(e))
        def worker():
            try:
                result=execute_plan(self.project,plan,stop_requested=self.stop.is_set,on_step=emit)
                self.after(0,lambda:self._done(result,None))
            except Exception as e:
                self.after(0,lambda msg=str(e):self._done(None,msg))
        threading.Thread(target=worker,daemon=True).start()

    def _log(self,entry):
        self.log.insert('end',json.dumps(entry,ensure_ascii=False)+'\n')
        self.log.see('end')

    def _done(self,result,error):
        self.busy=False
        if error:return self._warn(WorkflowError(error))
        path=self.project.root/'manifests'/'p9_i03_execution_result.json'
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        self.state.set('Çalıştırma sonuçlandı · Sentetik/koşullu · '+str(path))


def open_workflow_window(master,project,initial_module='P1-G02'):
    win=WorkflowWindow(master,project,initial_module=initial_module)
    win.transient(master)
    return win
