"""P9-I08 high-fidelity Tk desktop panels backed only by recorded local evidence.

These are human-interface views, not camera authentication or AI-origin scoring.
The eight module cards show execution records, never inferred physical validity.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from .desktop_core import sha256
from .integration_ui import selected_asset
from .review_workspace import report_catalog, read_report

BG = "#0a1420"
NAV = "#0d1e30"
PANEL = "#142639"
CARD = "#20384e"
BLUE = "#1976d2"
CYAN = "#19c5ff"
INK = "#e7f2fa"
MUTED = "#abbfd1"
GREEN = "#85d5b8"
AMBER = "#f3bf66"
RED = "#f19d9b"

MODULE_GROUPS = (
    ("P1", "Geometri", "P1-G01"),
    ("P2", "Gölge", "P2-S01"),
    ("P3", "Yansıma", "P3-R01"),
    ("P4", "Optik", "P4-O01"),
    ("P5", "Derinlik", "P5-D01"),
    ("P6", "Malzeme", "P6-M01"),
    ("P7", "Sensör", "P7-S01"),
    ("P8", "Kanıt", "P8-E01"),
)


def module_cards(project):
    """Module status from execution records; records do not verify camera physics."""
    runs = [x for x in project.data.get("runs", []) if isinstance(x, dict)]
    items = []
    for prefix, title, entry in MODULE_GROUPS:
        matching = [x for x in runs if str(x.get("module_id", "")).startswith(prefix + "-")]
        succeeded = sum(x.get("state") == "SUCCEEDED" for x in matching)
        failed = sum(x.get("state") in ("FAILED", "TIMEOUT") for x in matching)
        state = ("Kayıt yok" if not matching else
                 "Çalışma hatası" if failed and not succeeded else
                 "Koşum kaydı" if succeeded else "Yalnız deneme")
        items.append({"prefix": prefix, "title": title, "entry": entry,
                      "state": state, "succeeded": succeeded, "failed": failed,
                      "run_count": len(matching), "validated": False})
    return items


def latest_e03(project):
    """Read only E03 reports accepted by the existing local report registry."""
    try:
        candidates = [x for x in report_catalog(project)
                      if x.get("schema_version") == "p8.e03.v1"]
    except (ValueError, OSError, KeyError, TypeError):
        return None
    for item in reversed(candidates):
        try:
            report = read_report(project, item["id"])
            if (report.get("decision") == "NO_AI_ORIGIN_CONCLUSION"
                    and isinstance(report.get("findings"), list)):
                return {"id": item["id"], "report": report,
                        "report_sha256": item["sha256"]}
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return None


def dashboard_stats(project):
    cards = module_cards(project)
    recent = [x for x in project.data.get("runs", []) if isinstance(x, dict)]
    return {"image_count": len(project.data.get("images", [])),
            "run_count": len(recent),
            "successful_runs": sum(x.get("state") == "SUCCEEDED" for x in recent),
            "failed_runs": sum(x.get("state") in ("FAILED", "TIMEOUT") for x in recent),
            "module_cards": cards, "camera_validation": "NOT_PERFORMED",
            "origin_decision": "NO_AI_ORIGIN_CONCLUSION"}


def _label(parent, content, size=10, color=INK, *, strong=False, wrap=0):
    return tk.Label(parent, text=str(content), bg=parent.cget("bg"), fg=color,
                    font=("Segoe UI", size, "bold" if strong else "normal"),
                    anchor="w", justify="left",
                    wraplength=wrap or 0)


def _surface(parent, heading, *, side=None, grow=False):
    frame = tk.Frame(parent, bg=PANEL, padx=12, pady=10,
                     highlightthickness=1, highlightbackground="#2a455d")
    if side:
        frame.pack(side=side, fill="both" if grow else "y",
                   expand=grow, padx=5, pady=5)
    else:
        frame.pack(fill="x", pady=5)
    _label(frame, heading, 12, CYAN, strong=True).pack(anchor="w", pady=(0,8))
    return frame


def _action(app, parent, label, command, *, primary=False, side=None):
    button = app.button(parent, label, command, primary)
    button.pack(side=side, padx=4, pady=4) if side else button.pack(anchor="w", pady=4)
    return button


def _source_image(app, parent, width=490, height=256):
    """Render a SHA-confirmed original photograph; no invented overlay or scores."""
    record = selected_asset(app.project, getattr(app, "selected_asset_sha", None))
    if record is None:
        images = app.project.data.get("images", [])
        if images and not getattr(app, "selected_asset_sha", None):
            record = selected_asset(app.project, images[0].get("sha256"))
    surface = tk.Frame(parent, bg=NAV, width=width, height=height)
    surface.pack(fill="x", pady=7)
    surface.pack_propagate(False)
    if record is None:
        _label(surface, "Görüntü yok veya dosya bütünlüğü doğrulanamadı.",
               11, MUTED, wrap=width-30).pack(anchor="center", expand=True, padx=14)
        return False
    meta, path = record
    try:
        from PIL import Image, ImageTk
        with Image.open(path) as image:
            image.thumbnail((width-24, height-14))
            photo = ImageTk.PhotoImage(image.copy())
        if not hasattr(app, "_fidelity_photos"):
            app._fidelity_photos = []
        app._fidelity_photos.append(photo)
        tk.Label(surface, image=photo, bg=NAV).pack(expand=True)
    except (OSError, ValueError, ImportError):
        _label(surface, "Önizleme gösterilemiyor; görüntü hash'i kayıtlı.",
               10, MUTED).pack(anchor="center", expand=True)
    _label(parent, meta.get("name", "Görüntü") + "  ·  SHA-256: " +
           meta["sha256"][:18] + "…  ·  kamera kökeni doğrulanmadı",
           9, MUTED, wrap=width+40).pack(anchor="w")
    return True


def _recent_table(app, parent, *, limit=6):
    rows = []
    for run in reversed(app.project.data.get("runs", [])[-limit:]):
        rows.append((run.get("module_id", "—"), run.get("state", "—"),
                     run.get("run_id", "—")))
    if not rows:
        _label(parent, "Bu projede henüz analiz koşumu yok.", 10, MUTED).pack(anchor="w", pady=7)
    else:
        app.table(parent, ("Modül", "Yürütme", "Kayıt"), rows,
                  height=min(max(len(rows), 2), 7))


def render_overview(app):
    """Mockup-like 8-module status dashboard, responsive vertically."""
    app._fidelity_photos = []
    stats = dashboard_stats(app.project)
    head = _surface(app.page, "FAKEPROOFIMAGEAI   /   PROJE ÇALIŞMA ALANI")
    _label(head, app.project.name + "  ·  P1–P8 fiziksel kanıt inceleme",
           13, INK, strong=True).pack(anchor="w")
    _label(head, "Kayıt durumu ≠ fiziksel doğrulama. Gerçek kamera / Windows kabulü yapılmadı.",
           9, MUTED).pack(anchor="w", pady=(4,0))
    module_frame = _surface(app.page, "FİZİK MODÜLLERİ  ·  KAYNAKLI KOŞUM DURUMU")
    for half in (stats["module_cards"][:4], stats["module_cards"][4:]):
        row = tk.Frame(module_frame, bg=PANEL)
        row.pack(fill="x", pady=3)
        for item in half:
            tile = tk.Frame(row, bg=CARD, padx=9, pady=9,
                            highlightthickness=1, highlightbackground="#35536c")
            tile.pack(side="left", expand=True, fill="x", padx=3)
            tk.Label(tile, text=item["prefix"], bg=CARD, fg=CYAN,
                     font=("Segoe UI",14,"bold")).pack(anchor="w")
            _label(tile, item["title"], 10, INK, strong=True).pack(anchor="w")
            color = (GREEN if item["succeeded"] else
                     RED if item["failed"] else MUTED)
            _label(tile, item["state"], 9, color).pack(anchor="w", pady=(2,0))
            _label(tile, str(item["succeeded"]) + " başarılı / " +
                   str(item["run_count"]) + " koşum", 8, MUTED).pack(anchor="w")
            target = item["entry"]
            _action(app, tile, "Modülü aç",
                    (lambda m=target: app.choose_module(m)) if item["prefix"]!="P8"
                    else (lambda: app.open_review("Kanıt İnceleme")))

    columns = tk.Frame(app.page, bg=BG)
    columns.pack(fill="x", pady=(3,0))
    left = tk.Frame(columns, bg=BG)
    left.pack(side="left", fill="both", expand=True)
    right = tk.Frame(columns, bg=BG)
    right.pack(side="left", fill="both", expand=True)
    image_panel = _surface(left, "SEÇİLİ GÖRÜNTÜ  /  ANALİZ ÖNİZLEMESİ")
    _source_image(app, image_panel, width=450, height=214)
    actionrow=tk.Frame(image_panel,bg=PANEL)
    actionrow.pack(fill="x",pady=(5,0))
    _action(app,actionrow,"Görüntü yükle",lambda:app.go("Görüntü Yükleme"),side="left")
    _action(app,actionrow,"Çizim editörü",app.open_annotation_editor,side="left")
    _action(app,actionrow,"Katmanları aç",
            lambda:app.open_review("Görsel Katmanlar"),side="left")
    recent=_surface(right,"SON ÇALIŞTIRILAN ANALİZLER")
    _recent_table(app,recent,limit=5)
    _action(app,recent,"Analiz planlayıcısı",app.open_workflow)
    bottom = tk.Frame(app.page,bg=BG)
    bottom.pack(fill="x")
    evidence=_surface(bottom,"KANIT DURUMU  /  P8-E01–E03")
    latest=latest_e03(app.project)
    if latest is None:
        _label(evidence,"Kaynaklı E03 raporu bulunamadı. Bilinmeyen sonuçlar hesaplanmaz.",
               10,MUTED).pack(anchor="w")
    else:
        report=latest["report"]
        total=len(report["findings"])
        _label(evidence,f"E03 raporu: {total} kayıt · SHA: {latest['report_sha256'][:18]}…",
               10,INK).pack(anchor="w")
        _label(evidence,"Koşullu hipotez sonuçları; AI kökeni kararı YOK.",
               9,MUTED).pack(anchor="w")
    row=tk.Frame(evidence,bg=PANEL);row.pack(fill="x",pady=5)
    _action(app,row,"Kanıt gezgini",lambda:app.open_review("Kanıt İnceleme"),side="left")
    _action(app,row,"Bağımlılıklar",lambda:app.open_review("Bağımlılık Grafiği"),side="left")
    _action(app,row,"Rapor dışa aktar",lambda:app.go("Rapor Dışa Aktarma"),side="left")


def render_calibration(app):
    app._fidelity_photos=[]
    columns=tk.Frame(app.page,bg=BG)
    columns.pack(fill="x")
    left=tk.Frame(columns,bg=BG);left.pack(side="left",fill="both",expand=True)
    right=tk.Frame(columns,bg=BG,width=300);right.pack(side="right",fill="y")
    viewer=_surface(left,"KALİBRASYON GÖRÜNTÜSÜ")
    _source_image(app,viewer,width=620,height=345)
    _label(viewer,"Çizgiler ve ROI piksel düzeyindedir; ölçek veya kamera parametresi kanıtı değildir.",
           10,MUTED,wrap=600).pack(anchor="w")
    _action(app,viewer,"Görüntü üzerinde çizim yap",app.open_annotation_editor,primary=True)
    box=_surface(right,"KAMERA / KALİBRASYON GİRDİLERİ")
    calibration=app.project.data.get("calibration")
    _label(box,"Seçili kayıt: "+str(calibration or "YOK"),10,INK,wrap=270).pack(anchor="w")
    _label(box,"Bağımsız doğrulama: YAPILMADI",9,AMBER).pack(anchor="w",pady=5)
    _action(app,box,"Kalibrasyon JSON ekle",app.add_calibration)
    for mid,caption in (("P1-G02","Kaçış noktası çizgileri"),
                        ("P1-G04","Homografi"),("P4-O01","Lens bozulması")):
        _action(app,box,caption,lambda m=mid:app.choose_module(m))
    _label(box,"Özgün görüntü ve kalibrasyon ölçümleri ayrı kayıtlar olarak tutulur.",
           9,MUTED,wrap=270).pack(anchor="w",pady=6)


def render_measurements(app):
    app._fidelity_photos=[]
    columns=tk.Frame(app.page,bg=BG);columns.pack(fill="x")
    left=tk.Frame(columns,bg=BG);left.pack(side="left",fill="both",expand=True)
    right=tk.Frame(columns,bg=BG,width=300);right.pack(side="right",fill="y")
    viewer=_surface(left,"FİZİKSEL GÖRÜNTÜ VE KATMANLAR")
    _source_image(app,viewer,width=620,height=300)
    _action(app,viewer,"Piksel ölçüm editörü",app.open_annotation_editor,primary=True)
    _action(app,viewer,"Görüntü katmanlarını incele",
            lambda:app.open_review("Görsel Katmanlar"))
    tools=_surface(right,"FİZİK MODÜLÜ ARAÇLARI")
    for mid,title in (("P1-G01","P1 Geometri"),("P2-S01","P2 Gölge"),
                      ("P3-R01","P3 Yansıma"),("P4-O01","P4 Optik"),
                      ("P5-D01","P5 Derinlik"),("P6-M01","P6 Malzeme"),
                      ("P7-S01","P7 Sensör")):
        _action(app,tools,title,lambda m=mid:app.choose_module(m))
    history=_surface(app.page,"ÖLÇÜMLER  /  GERÇEK MODÜL ÇIKTILARI")
    _recent_table(app,history,limit=7)
    latest=latest_e03(app.project)
    if latest:
        _label(history,"E03 belirsizlik ve artıkları için Kanıt İnceleme sayfasına geçin.",
               10,MUTED).pack(anchor="w")
        _action(app,history,"Belirsizlikleri incele",
                lambda:app.open_review("Kanıt İnceleme"))
    else:
        _label(history,"Henüz E03 ölçüm özeti yok. Grafik/veri noktası uydurulmaz.",
               10,MUTED).pack(anchor="w")


def render_evidence(app):
    data=latest_e03(app.project)
    intro=_surface(app.page,"AÇIKLANABİLİR KANIT  /  E01 → E02 → E03")
    _label(intro,"Koşullu testin reddi tek başına AI kökeni veya fotoğrafın gerçekliği değildir.",
           10,AMBER).pack(anchor="w")
    nav=tk.Frame(intro,bg=PANEL);nav.pack(fill="x",pady=5)
    for mid in ("P8-E01","P8-E02","P8-E03"):
        _action(app,nav,mid,lambda m=mid:app.choose_module(m),side="left")
    if data is None:
        blank=_surface(app.page,"KANIT BULGULARI")
        _label(blank,"Doğrulanmış biçimli E03 raporu bulunmadı. Sonuç ve p-değeri gösterilmiyor.",
               10,MUTED).pack(anchor="w",pady=4)
    else:
        report=data["report"]
        box=_surface(app.page,"E03 BULGULARI  ·  "+str(len(report["findings"]))+" KAYIT")
        rows=[]
        for finding in report["findings"][:60]:
            one=finding.get("single_test") or {}
            dependency=finding.get("dependency") or {}
            rows.append((str(finding.get("record_id","—"))[:32],
                         str(finding.get("module_id","—")),
                         str(one.get("state","NOT_EVALUATED")),
                         str(dependency.get("component_id","—"))))
        app.table(box,("Kanıt ID","Modül","Tekil durum","Bağımlılık grubu"),
                  rows,height=min(max(3,len(rows)),12))
        if len(report["findings"])>60:
            _label(box,"İlk 60 kayıt gösteriliyor; tamamı E03 JSON raporunda.",
                   9,MUTED).pack(anchor="w")
        _label(box,"Rapordaki ölçümler, belirsizlikler ve gerekçeler bağımsız kaynak kabulü değildir.",
               9,MUTED).pack(anchor="w",pady=6)
    choices=_surface(app.page,"KANIT GEZGİNİ VE RAPOR")
    buttons=tk.Frame(choices,bg=PANEL);buttons.pack(fill="x")
    _action(app,buttons,"Bulgu ve görüntü",
            lambda:app.open_review("Kanıt İnceleme"),primary=True,side="left")
    _action(app,buttons,"Bağımlılık grafiği",
            lambda:app.open_review("Bağımlılık Grafiği"),side="left")
    _action(app,buttons,"Rapor gezgini",
            lambda:app.open_review("Rapor Gezgini"),side="left")
