"""Offline, Windows-first FakeProofImageAI desktop GUI.

Nine pages; the buttons call the actual project store and existing module CLI.
A screenshot or an uploaded image cannot by itself authorize P2–P8 inference.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import webbrowser

from .desktop_core import DesktopIntegrationError, Project, module_catalog, sha256
from .journey_core import available_projects, journey_snapshot
from .journey_ui import render_home_dashboard, render_workflow_strip

BG="#0a1420"
NAV="#0d1e30"
PANEL="#142639"
CARD="#20384e"
BLUE="#1976d2"
INK="#e7f2fa"
MUTED="#abbfd1"
CYAN="#19c5ff"
PAGES=("Genel Bakış","Görüntü Yükleme","Analiz Planı","Kalibrasyon",
       "Fiziksel Ölçümler","Kanıt İnceleme","Bağımlılık Grafiği",
       "Rapor Dışa Aktarma","Ayarlar")


def workspace_path():
    root=os.environ.get("LOCALAPPDATA")
    return (Path(root) if root else Path.home()/".local"/"share")/"FakeProofImageAI"/"projects"


class DesktopApp(tk.Tk):
    def __init__(self,workspace=None):
        super().__init__()
        self.title("FakeProofImageAI | Fizik Tabanlı Adli Görüntü Analizi")
        self.geometry("1400x870")
        self.minsize(1090,680)
        self.configure(bg=BG)
        self.workspace=Path(workspace or workspace_path())
        self.project=Project(self.workspace,"Ornek_Proje")
        self.module=tk.StringVar(value="P1-G01")
        self.source=tk.StringVar()
        self.status=tk.StringVar(value="Yerel çalışma · Gerçek kamera ve Windows kabulü yapılmadı")
        self.run_id=None
        self.busy=False
        self.preview_photo=None
        self.selected_asset_sha=None
        self.active_page=PAGES[0]
        self._style()
        self._layout()
        self.go(PAGES[0])

    def _style(self):
        style=ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",background=NAV,foreground=INK,fieldbackground=NAV,
                        rowheight=33,font=("Segoe UI",10))
        style.configure("Treeview.Heading",background=PANEL,foreground=CYAN,
                        font=("Segoe UI",10,"bold"))
        style.map("Treeview",background=[("selected","#285c86")],
                  foreground=[("selected","#ffffff")])

    def label(self,parent,value,size=11,color=INK,bold=False):
        return tk.Label(parent,text=value,bg=parent.cget("bg"),fg=color,
                        font=("Segoe UI",size,"bold" if bold else "normal"),
                        anchor="w",justify="left")

    def button(self,parent,title,action,primary=False):
        return tk.Button(parent,text=title,command=action,
                         bg=BLUE if primary else CARD,fg="white",
                         activebackground="#268adb",activeforeground="white",
                         relief="flat",padx=15,pady=8,cursor="hand2",
                         font=("Segoe UI",10))

    def box(self,title):
        container=tk.Frame(self.page,bg=PANEL,padx=16,pady=13)
        container.pack(fill="x",pady=9)
        self.label(container,title,13,CYAN,True).pack(anchor="w",pady=(0,9))
        return container

    def table(self,parent,cols,values,height=11):
        view=ttk.Treeview(parent,columns=cols,show="headings",height=height)
        for c in cols:
            view.heading(c,text=c)
            view.column(c,width=max(110,len(c)*13),stretch=True)
        for row in values:
            view.insert("","end",values=row)
        view.pack(fill="both",expand=True)
        return view

    def _layout(self):
        header=tk.Frame(self,bg=NAV,height=55)
        header.pack(fill="x")
        self.label(header,"⬡ FakeProofImageAI",16,INK,True).pack(side="left",padx=20,pady=13)
        self.project_tag=self.label(header,"Proje: Ornek_Proje",11,MUTED)
        self.project_tag.pack(side="left",padx=12)
        self.project_choice=tk.StringVar(value=self.project.name)
        self.project_picker=ttk.Combobox(header,textvariable=self.project_choice,
                values=available_projects(self.workspace),state="readonly",width=23)
        self.project_picker.pack(side="left",padx=8)
        self.project_picker.bind("<<ComboboxSelected>>",self.switch_project)
        self.button(header,"+ Yeni Proje",self.new_project,True).pack(side="right",padx=14)
        middle=tk.Frame(self,bg=BG)
        middle.pack(fill="both",expand=True)
        sidebar=tk.Frame(middle,bg=NAV,width=223)
        sidebar.pack(side="left",fill="y")
        sidebar.pack_propagate(False)
        self.nav={}
        for title in PAGES:
            b=tk.Button(sidebar,text="  "+title,anchor="w",relief="flat",
                        bg=NAV,fg=INK,activebackground=BLUE,activeforeground="white",
                        command=lambda page=title:self.go(page),
                        font=("Segoe UI",11),pady=12)
            b.pack(fill="x",padx=6,pady=2)
            self.nav[title]=b
        tk.Frame(sidebar,bg=NAV).pack(expand=True)
        self.label(sidebar,"P1–P8 · Koşullu kanıt",9,MUTED).pack(pady=14)
        # P9-I07: small screens retain every page section via a scrollable workspace.
        self.page_shell=tk.Frame(middle,bg=BG)
        self.page_shell.pack(side="left",fill="both",expand=True)
        self.page_scrollbar=ttk.Scrollbar(self.page_shell,orient="vertical")
        self.page_scrollbar.pack(side="right",fill="y")
        self.page_canvas=tk.Canvas(self.page_shell,bg=BG,bd=0,highlightthickness=0,
                                   yscrollcommand=self.page_scrollbar.set)
        self.page_canvas.pack(side="left",fill="both",expand=True)
        self.page_scrollbar.configure(command=self.page_canvas.yview)
        self.page=tk.Frame(self.page_canvas,bg=BG,padx=18,pady=12)
        self.page_window=self.page_canvas.create_window((0,0),window=self.page,anchor="nw")
        self.page.bind("<Configure>",lambda event:
                       self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all")))
        self.page_canvas.bind("<Configure>",lambda event:
                              self.page_canvas.itemconfigure(self.page_window,width=event.width))
        self.page_canvas.bind("<MouseWheel>",self._scroll_page)
        self.page_canvas.bind("<Button-4>",lambda e:self.page_canvas.yview_scroll(-3,"units"))
        self.page_canvas.bind("<Button-5>",lambda e:self.page_canvas.yview_scroll(3,"units"))
        self.bind("<Control-Key-n>",lambda event:self.new_project())
        self.bind("<Control-Key-o>",lambda event:(self.go(PAGES[1]),self.import_images()))
        self.bind("<F5>",lambda event:self.go(self.active_page))
        for position,page in enumerate(PAGES,1):
            self.bind(f"<Control-Key-{position}>",lambda event,p=page:self.go(p))
        self.bind("<Prior>",lambda event:self.page_canvas.yview_scroll(-1,"pages"))
        self.bind("<Next>",lambda event:self.page_canvas.yview_scroll(1,"pages"))
        tk.Label(self,textvariable=self.status,bg=NAV,fg=MUTED,
                 anchor="w",padx=22,pady=7).pack(fill="x")

    def _scroll_page(self,event):
        delta=getattr(event,"delta",0)
        if delta:
            self.page_canvas.yview_scroll(-3 if delta>0 else 3,"units")

    def go(self,title):
        if title not in PAGES:
            raise ValueError("Kayıtlı olmayan masaüstü sayfası")
        self.active_page=title
        for child in self.page.winfo_children():
            child.destroy()
        for name,button in self.nav.items():
            button.configure(bg=BLUE if name==title else NAV)
        self.label(self.page,title,21,INK,True).pack(anchor="w",pady=(0,8))
        render_workflow_strip(self)
        getattr(self,"screen_"+str(PAGES.index(title)))()
        self.page_canvas.yview_moveto(0)

    def err(self,error):
        self.status.set(str(error))
        messagebox.showerror("FakeProofImageAI",str(error),parent=self)

    def switch_project(self,event=None):
        choice=self.project_choice.get()
        if self.busy:
            self.project_choice.set(self.project.name)
            self.status.set("Analiz çalışırken proje değiştirilemez")
            return
        if choice==self.project.name:return
        if choice not in available_projects(self.workspace):
            self.project_choice.set(self.project.name)
            self.err("Seçili proje yerel envanterde bulunmadı")
            return
        try:
            self.project=Project(self.workspace,choice)
            self.project_tag.config(text="Proje: "+choice)
            self.run_id=None;self.source.set("");self.selected_asset_sha=None
            self.status.set("Yerel proje açıldı: "+choice+"; kamera doğrulaması yapılmadı")
            self.go(PAGES[0])
        except (OSError,ValueError) as exc:
            self.project_choice.set(self.project.name)
            self.err(exc)

    def new_project(self):
        name=simpledialog.askstring("Yeni proje","Proje adı (ASCII / _ / -)",parent=self)
        if name:
            if self.busy:
                self.status.set("Analiz sürerken yeni projeye geçilemez")
                return
            try:
                self.project=Project(self.workspace,name)
                self.project_tag.config(text="Proje: "+name)
                self.project_picker.configure(values=available_projects(self.workspace))
                self.project_choice.set(name)
                self.source.set("");self.selected_asset_sha=None
                self.run_id=None
                self.go(PAGES[0])
            except (OSError,ValueError) as e:
                self.err(e)

    def screen_0(self):
        from .integration_ui import render_unified_home
        render_unified_home(self)

    def screen_1(self):
        p=self.box("Görüntü Yükleme ve SHA-256 Envanteri")
        self.label(p,"İçe aktarılan dosya kökeni doğrulanmış sayılmaz.",10,MUTED).pack(anchor="w")
        self.button(p,"Dosya Seç",self.import_images,True).pack(anchor="w",pady=8)
        assets=self.project.data["images"]
        t=self.table(p,("Dosya","Boyut (B)","SHA-256","Köken"),
                     [(x["name"],x["bytes"],x["sha256"][:20]+"…","Doğrulanmadı")
                      for x in assets],11)
        self.preview=self.label(p,"Önizleme için görüntü satırı seçin",11,MUTED)
        self.preview.pack(anchor="w",pady=10)
        def select(event):
            if not t.selection():
                return
            item=assets[t.index(t.selection()[0])]
            self.selected_asset_sha=item["sha256"]
            try:
                from PIL import Image, ImageTk
                img=Image.open(self.project.root/"images"/item["file"])
                img.thumbnail((500,210))
                self.preview_photo=ImageTk.PhotoImage(img)
                self.preview.configure(image=self.preview_photo,text="")
            except (ImportError,OSError):
                self.preview.configure(image="",text=item["name"]+" · Pillow önizlemesi yok")
        t.bind("<<TreeviewSelect>>",select)
        self.button(p,"Seçilen Görüntüyü Anote Et",self.open_annotation_editor).pack(anchor="w",pady=4)
        self.button(p,"Görsel Katman Gezgini",lambda:self.open_review("Görsel Katmanlar")).pack(anchor="w",pady=4)

    def import_images(self):
        paths=filedialog.askopenfilenames(parent=self,
                          filetypes=[("Görüntüler","*.png *.jpg *.jpeg *.bmp *.tif *.tiff")])
        try:
            for path in paths:
                self.project.import_image(path)
            if paths:
                self.go(PAGES[1])
        except (OSError,ValueError) as e:
            self.err(e)

    def screen_2(self):
        self.label(self.page,"G01 görüntüden çalışır; diğer modüller bağımsız ölçüm JSON'u ister.",
                   10,MUTED).pack(anchor="w")
        p=self.box("P1–P8 · 27 Modül Sözleşmesi")
        entries=module_catalog()
        t=self.table(p,("Kimlik","Fiziksel İddia","CLI","Girdi"),
                     [(m["id"],m["name"],m["command"],m["input"])
                      for m in entries],15)
        t.bind("<<TreeviewSelect>>",
               lambda event: self.module.set(entries[t.index(t.selection()[0])]["id"])
               if t.selection() else None)
        p=self.box("Analiz Çalıştırma")
        self.label(p,"Seçilen modül:",10,MUTED).pack(side="left")
        tk.Label(p,textvariable=self.module,bg=PANEL,fg=CYAN,
                 font=("Segoe UI",12,"bold")).pack(side="left",padx=10)
        self.button(p,"Girdi Seç",self.select_manifest).pack(side="left",padx=8)
        self.button(p,"Çalıştır",self.run_module,True).pack(side="left",padx=8)
        self.button(self.page,"Modül Formları ve Planlayıcıyı Aç",
                    self.open_workflow,True).pack(anchor="w",pady=10)

    def open_workflow(self):
        """P9-I03 independent typed module forms + conservative execution planner."""
        try:
            from .workflow_ui import open_workflow_window
            open_workflow_window(self,self.project,initial_module=self.module.get())
        except (ValueError,OSError,ImportError) as exc:
            self.err(exc)

    def select_manifest(self):
        image=self.module.get()=="P1-G01"
        path=filedialog.askopenfilename(
            parent=self,filetypes=[("Görüntüler","*.png *.jpg *.jpeg *.bmp *.tif *.tiff")]
            if image else [("Ölçüm JSON'u","*.json")])
        if path:
            self.source.set(path)
            self.status.set(self.module.get()+" girdisi: "+path)

    def run_module(self):
        if self.busy:
            return
        if not self.source.get():
            self.select_manifest()
        if not self.source.get():
            return
        self.busy=True
        module,source=self.module.get(),self.source.get()
        self.status.set(module+" çalışıyor (yerel CLI)")
        def work():
            try:
                result,out=self.project.run(module,source)
                self.after(0,lambda:self.completed(result,out,None))
            except Exception as e:
                self.after(0,lambda msg=str(e):self.completed(None,None,msg))
        threading.Thread(target=work,daemon=True).start()

    def completed(self,result,out,error):
        self.busy=False
        if error:
            self.err(error)
            return
        self.run_id=result["run_id"]
        self.status.set(result["module_id"]+" · "+result["state"]+" · "+str(out))
        if result["returncode"]!=0:
            self.err("Modül çalışmadı; çalışma dizininde stderr.txt inceleyin")
        else:
            self.go(PAGES[5] if result["module_id"].startswith("P8-") else PAGES[4])

    def choose_module(self,module):
        self.module.set(module)
        self.source.set("")
        self.go(PAGES[2])

    def screen_3(self):
        p=self.box("Kalibrasyon Yönetimi")
        self.label(p,"G02, G04 ve O01 bağımsız geometrik veri gerektirir.",
                   11,MUTED).pack(anchor="w",pady=8)
        self.button(p,"Görüntü Üzerinde Kalibrasyon Çiz",self.open_annotation_editor,True).pack(anchor="w",pady=6)
        self.button(p,"Kalibrasyon JSON Ekle",self.add_calibration).pack(anchor="w",pady=6)
        self.button(p,"Modüle Özel Kalibrasyon Formları",
                    self.open_workflow).pack(anchor="w",pady=6)
        self.label(p,"Seçili kalibrasyon: "+str(self.project.data.get("calibration") or "YOK"),
                   10,MUTED).pack(anchor="w")
        for module,label in [("P1-G02","Kaçış noktaları"),("P1-G04","Homografi"),
                             ("P4-O01","Lens bozulması")]:
            self.button(p,label,lambda m=module:self.choose_module(m)).pack(anchor="w",pady=5)
        self.label(self.page,"Bir JSON kaydı bağımsız kalibrasyon doğrulaması değildir.",
                   10,MUTED).pack(anchor="w")

    def open_annotation_editor(self):
        """P9-I02 native-image coordinate editor; annotations are not 3D truth."""
        images=self.project.data["images"]
        if not images:
            messagebox.showinfo("Görüntü gerekli","Önce Görüntü Yükleme sayfasından görüntü ekleyin.",parent=self)
            return
        index=next((i+1 for i,x in enumerate(images)
                    if x.get("sha256")==self.selected_asset_sha),None)
        if index is None and len(images)==1:index=1
        if index is None and len(images)>1:
            names="\\n".join(str(i+1)+": "+x["name"] for i,x in enumerate(images[:30]))
            index=simpledialog.askinteger("Görüntü seç",names+"\\nGörüntü sıra numarası:",
                        minvalue=1,maxvalue=len(images),parent=self)
            if index is None:return
        asset=images[index-1]
        self.selected_asset_sha=asset["sha256"]
        try:
            from .annotation_editor import AnnotationEditor
            from .annotation_model import AnnotationError
            image_file=(self.project.root/"images"/asset["file"]).resolve(strict=True)
            image_dir=(self.project.root/"images").resolve()
            if image_file.parent!=image_dir or sha256(image_file)!=asset["sha256"]:
                raise DesktopIntegrationError("Görüntü yolu / SHA-256 doğrulaması başarısız")
            annotation_file=self.project.root/"manifests"/("annotations_"+asset["sha256"]+".json")
            AnnotationEditor(self,image_file,annotation_file,
                expected_sha256=asset["sha256"],
                on_saved=lambda document,path:self.status.set(
                    "Piksel anotasyonları kaydedildi: "+str(path)+
                    " · gerçek ölçek / kamera doğrulaması yapılmadı"))
        except (OSError,ValueError,DesktopIntegrationError) as e:
            self.err(e)

    def add_calibration(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[("JSON","*.json")])
        if path:
            try:
                self.project.set_calibration(path)
                self.go(PAGES[3])
            except (OSError,ValueError) as e:
                self.err(e)

    def artifact_table(self,p,only_evidence=False):
        files=self.project.artifacts()
        if only_evidence:
            files=[f for f in files if any(x in f.name for x in
                          ("evidence","fusion","explainable"))]
        rows=[(x.parent.name,x.name,x.suffix.lower()) for x in files[-120:]]
        t=self.table(p,("Çalışma","Kanıt Dosyası","Tür"),rows)
        def open_record(event):
            if not t.selection():
                return
            row=t.item(t.selection()[0],"values")
            file=self.project.root/"runs"/row[0]/row[1]
            if file.suffix.lower()==".html" and file.is_file():
                webbrowser.open(file.as_uri())
            else:
                self.status.set("Dosya: "+str(file))
        t.bind("<Double-1>",open_record)

    def open_review(self, tab='Görsel Katmanlar'):
        from .review_ui import ReviewWindow
        ReviewWindow(self, self.project, tab=tab,
                     initial_image_sha=self.selected_asset_sha)

    def screen_4(self):
        p=self.box("Fiziksel Ölçümler")
        self.button(p,"P9-I04 Görsel Katmanlar ve Ölçüm Gezgini",
                    lambda:self.open_review("Görsel Katmanlar"),True).pack(anchor="w",pady=6)
        self.label(p,"P1 Geometri · P2 Gölge · P3 Yansıma · P4 Optik · P5 3B · P6 Malzeme · P7 Sensör",
                   11,MUTED).pack(anchor="w",pady=9)
        self.button(p,"Görüntü Üzerinde Fiziksel Ölçüm Yap",self.open_annotation_editor,True).pack(anchor="w",pady=8)
        self.button(p,"Modül Formları ve Ölçüm Planlayıcısı",
                    self.open_workflow,True).pack(anchor="w",pady=6)
        self.button(p,"Modül Seç",lambda:self.go(PAGES[2])).pack(anchor="w")
        p=self.box("Gerçek CLI Çıktıları")
        self.artifact_table(p)

    def screen_5(self):
        p=self.box("E01 Tekil Kanıt · E02 Bağımlı Birleşim · E03 Açıklanabilir Rapor")
        self.button(p,"P9-I04 Bulgu–Görüntü ve Kanıt Gezgini",
                    lambda:self.open_review("Kanıt İnceleme"),True).pack(anchor="w",pady=6)
        b=tk.Frame(p,bg=PANEL)
        b.pack(anchor="w",pady=12)
        for module in ("P8-E01","P8-E02","P8-E03"):
            self.button(b,module,lambda m=module:self.choose_module(m)).pack(side="left",padx=8)
        self.label(p,"P-değeri AI-köken olasılığı değildir; ret özgünlük kararı üretmez.",
                   10,MUTED).pack(anchor="w")
        p=self.box("Çalışılmış Kanıt Kayıtları")
        self.artifact_table(p,True)

    def screen_6(self):
        p=self.box("E02 / E03 Bağımlılık Grafiği (gerçek lineage grupları)")
        self.button(p,"P9-I04 Gerçek Kaynak Bağımlılıklarını Aç",
                    lambda:self.open_review("Bağımlılık Grafiği"),True).pack(anchor="w",pady=6)
        self.label(p,"Bağımlılık çıkarılmadıysa örnek bağlantılar icat edilmez.",
                   10,MUTED).pack(anchor="w")
        canvas=tk.Canvas(p,bg=NAV,height=460,highlightthickness=0)
        canvas.pack(fill="both",expand=True,pady=8)
        reports=sorted(self.project.root.glob("runs/*/p8_e02_fusion_report.json"))
        reports+=sorted(self.project.root.glob("runs/*/p8_e03_explainable_report.json"))
        if not reports:
            canvas.create_text(480,190,text="E02 / E03 raporu henüz bulunmuyor",
                               fill=MUTED,font=("Segoe UI",16))
            return
        data=json.loads(reports[-1].read_text(encoding="utf-8"))
        groups=data.get("dependency_components",data.get("dependency_groups",[]))
        for i,g in enumerate(groups[:18]):
            row,col=divmod(i,3)
            x,y=22+col*315,18+row*72
            canvas.create_rectangle(x,y,x+290,y+60,fill=CARD,outline=CYAN)
            canvas.create_text(x+12,y+16,anchor="w",text=g["component_id"],
                               fill=INK,font=("Segoe UI",11,"bold"))
            canvas.create_text(x+12,y+41,anchor="w",
                               text=", ".join(g["members"][:3])[:43],fill=MUTED)
        if len(groups)>18:
            self.label(p,"Diğer gruplar JSON raporunda: "+str(len(groups)-18),
                       10,MUTED).pack(anchor="w")

    def screen_7(self):
        p=self.box("Rapor Dışa Aktarma · ZIP ve SHA-256")
        self.button(p,"P9-I04 Ayrıntılı Rapor Gezgini",
                    lambda:self.open_review("Rapor Gezgini"),True).pack(anchor="w",pady=6)
        rows=[(x["run_id"],x["module_id"],x["state"]) for x in self.project.data["runs"]]
        tree=self.table(p,("Çalışma","Modül","Durum"),rows,11)
        tree.bind("<<TreeviewSelect>>",
                  lambda e:self.select_run(tree) if tree.selection() else None)
        self.button(p,"Seçili Çalışmayı ZIP Olarak Kaydet",
                    self.export_selected,True).pack(anchor="w",pady=12)
        self.label(p,"E03 raporu JSON/HTML verir. PDF ve dijital imza henüz uygulanmadı.",
                   10,MUTED).pack(anchor="w")

    def select_run(self,tree):
        self.run_id=tree.item(tree.selection()[0],"values")[0]

    def export_selected(self):
        if not self.run_id:
            self.err("Önce çalışmayı seçin")
            return
        destination=filedialog.asksaveasfilename(
            parent=self,defaultextension=".zip",filetypes=[("ZIP","*.zip")])
        if destination:
            try:
                saved=self.project.export_run(self.run_id,destination)
                self.status.set("Arşiv: "+str(saved))
            except (OSError,ValueError) as e:
                self.err(e)

    def screen_8(self):
        p=self.box("Çalışma Ortamı")
        for title,value in [
            ("Yerel çalışma dizini",str(self.workspace)),
            ("Güncel proje",self.project.name),
            ("Bulut/API bağlantısı","YOK"),
            ("Gerçek fotoğraf performansı","ÖLÇÜLMEDİ"),
            ("Windows son kullanıcı kabulü","SON AŞAMA"),
            ("AI kökeni kararı","HESAPLANMIYOR"),
            ("Klavye kısayolları","Ctrl+1–9: sayfa · Ctrl+N: proje · Ctrl+O: görüntü · F5: yenile · PgUp/PgDn: kaydır")]:
            self.label(p,title+": "+value,11).pack(anchor="w",pady=9)


def main():
    import sys
    # Frozen PyInstaller app can dispatch the allowlisted CLI in a child process.
    if getattr(sys,'frozen',False) and len(sys.argv)>1 and sys.argv[1]=='--cli':
        from .cli import main as cli_main
        cli_main(sys.argv[2:])
        return
    app=DesktopApp()
    app.mainloop()


if __name__=="__main__":
    main()
