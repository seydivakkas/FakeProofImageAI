"""P9-I06 dark desktop dashboard and explicit synthetic E01-E03 entrypoint."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from .journey_core import journey_snapshot
from .journey_ui import stage_caption
from .integration_flow import run_evidence_chain, save_example
from .desktop_core import sha256

BG="#0a1420"; PANEL="#142639"; CARD="#20384e"; BLUE="#1976d2"
CYAN="#19c5ff"; INK="#e7f2fa"; MUTED="#abbfd1"


def selected_asset(project, digest):
    if not isinstance(digest, str):
        return None
    for item in project.data.get("images", []):
        if item.get("sha256") != digest:
            continue
        root = (project.root / "images").resolve()
        try:
            path = (root / item["file"]).resolve(strict=True)
            if path.parent != root or not path.is_file() or sha256(path) != digest:
                return None
            return item, path
        except (KeyError, OSError, ValueError):
            return None
    return None


def stage_action(app, key):
    if key == "image":
        app.go("Görüntü Yükleme")
    elif key == "calibration":
        app.go("Kalibrasyon")
    elif key == "analysis":
        app.open_workflow()
    elif key == "evidence":
        app.open_review("Kanıt İnceleme")
    elif key == "export":
        app.open_review("Rapor Gezgini")


def run_synthetic_from_ui(app):
    if app.busy:
        return
    if not messagebox.askyesno(
        "SENTETİK DEMO", "Yalnız sentetik örnekten E01→E02→E03 çalışacak. "
        "Gerçek kamera veya AI köken kararı verilmez. Devam?", parent=app
    ):
        return
    project = app.project
    app.busy = True
    app.status.set("Sentetik E01→E02→E03 çalışıyor")

    def finish(result, error):
        app.busy = False
        if error is not None:
            app.err(error)
            return
        app.run_id = result["steps"][-1]["run_id"]
        app.status.set("Sentetik kanıt zinciri kaydedildi; gerçek doğrulama yapılmadı")
        app.go("Kanıt İnceleme")

    def worker():
        try:
            result = run_evidence_chain(project, save_example(project))
            app.after(0, lambda: finish(result, None))
        except Exception as exc:
            detail = str(exc)
            app.after(0, lambda: finish(None, detail))
    threading.Thread(target=worker, daemon=True).start()


def render_unified_home(app):
    snap = journey_snapshot(app.project)
    head = tk.Frame(app.page, bg=PANEL, padx=16, pady=11)
    head.pack(fill="x", pady=(0, 10))
    tk.Label(head, text="PROJE ÇALIŞMA ALANI · " + app.project.name,
             bg=PANEL, fg=CYAN, font=("Segoe UI", 14, "bold"),
             anchor="w").pack(fill="x")
    tk.Label(head, text="P1–P7 Ölçümler  →  P8-E01  →  E02  →  E03 Açıklanabilir Rapor",
             bg=PANEL, fg=INK, font=("Segoe UI", 10),
             anchor="w").pack(fill="x", pady=6)
    tk.Label(head, text="Yerel kayıtlar ≠ fiziksel doğrulama. AI kökeni hesaplanmaz.",
             bg=PANEL, fg=MUTED, font=("Segoe UI", 9),
             anchor="w").pack(fill="x")

    body = tk.Frame(app.page, bg=BG)
    body.pack(fill="both", expand=True)
    left = tk.Frame(body, bg=BG)
    left.pack(side="left", fill="both", expand=True, padx=(0, 7))
    right = tk.Frame(body, bg=BG, width=345)
    right.pack(side="right", fill="y", padx=(7, 0))
    right.pack_propagate(False)

    metrics = tk.Frame(left, bg=BG)
    metrics.pack(fill="x", pady=(0, 8))
    for title, number in (
        ("Görüntü", snap["image_count"]),
        ("P1–P7 Koşumu", snap["physics_success_count"]),
        ("P8 Kanıt Koşumu", snap["evidence_success_count"]),
        ("Hatalı Koşum", snap["failed_run_count"]),
    ):
        tile = tk.Frame(metrics, bg=CARD, padx=10, pady=9)
        tile.pack(side="left", expand=True, fill="x", padx=3)
        tk.Label(tile, text=str(number), bg=CARD, fg=CYAN,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(tile, text=title, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")

    steps = tk.Frame(left, bg=PANEL, padx=13, pady=10)
    steps.pack(fill="both", expand=True)
    tk.Label(steps, text="İŞ AKIŞI", bg=PANEL, fg=CYAN,
             font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 7))
    buttons = {
        "image": "Görüntü Ekle",
        "calibration": "Çizim ve Kalibrasyon",
        "analysis": "Modül Formları",
        "evidence": "Kanıt İnceleme",
        "export": "Rapor Gezgini",
    }
    for index, step in enumerate(snap["steps"], 1):
        row = tk.Frame(steps, bg=CARD, padx=10, pady=7)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=f"{index:02d}", bg=CARD, fg=CYAN,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 10))
        content = tk.Frame(row, bg=CARD)
        content.pack(side="left", fill="x", expand=True)
        tk.Label(content, text=step.label + " · " + stage_caption(step),
                 bg=CARD, fg=INK, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(content, text=step.detail, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=390,
                 justify="left", anchor="w").pack(fill="x")
        tk.Button(row, text=buttons[step.key], bg=BLUE, fg="white",
                  activebackground=BLUE, relief="flat", padx=8, pady=5,
                  command=lambda k=step.key: stage_action(app, k)).pack(side="right")

    selected = tk.Frame(right, bg=PANEL, padx=11, pady=11)
    selected.pack(fill="x", pady=(0, 9))
    tk.Label(selected, text="SEÇİLİ GÖRÜNTÜ", bg=PANEL, fg=CYAN,
             font=("Segoe UI", 12, "bold")).pack(anchor="w")
    images = app.project.data.get("images", [])
    item = selected_asset(app.project, getattr(app, "selected_asset_sha", None))
    if item is None and images:
        item = selected_asset(app.project, images[0].get("sha256"))
    if item:
        meta, path = item
        tk.Label(selected, text=meta["name"], bg=PANEL, fg=INK,
                 wraplength=310).pack(anchor="w", pady=6)
        try:
            from PIL import Image, ImageTk
            with Image.open(path) as original:
                original.thumbnail((305, 175))
                photo = ImageTk.PhotoImage(original.copy())
            app.preview_photo = photo
            tk.Label(selected, image=photo, bg=PANEL).pack(pady=4)
        except (OSError, ImportError, ValueError):
            tk.Label(selected, text="Önizleme mevcut değil",
                     bg=PANEL, fg=MUTED).pack()
        tk.Label(selected, text="SHA-256: " + meta["sha256"][:18] +
                 "…  ·  kaynak doğrulanmadı", bg=PANEL, fg=MUTED,
                 wraplength=310).pack(anchor="w")
    else:
        tk.Label(selected, text="Görüntü yok veya SHA-256 eşleşmedi",
                 bg=PANEL, fg=MUTED, wraplength=310).pack(pady=12)
    app.button(selected, "Görüntü ve Katmanları Aç",
               lambda: app.open_review("Görsel Katmanlar")).pack(fill="x", pady=6)

    actions = tk.Frame(right, bg=PANEL, padx=12, pady=12)
    actions.pack(fill="x")
    tk.Label(actions, text="SENTETİK ENTEGRASYON", bg=PANEL, fg=CYAN,
             font=("Segoe UI", 12, "bold")).pack(anchor="w")
    tk.Label(actions, text="Yalnız kontrollü sentetik E01→E02→E03; "
             "gerçek kamera veya AI köken kararı yok.",
             bg=PANEL, fg=MUTED, wraplength=310,
             justify="left").pack(anchor="w", pady=9)
    app.button(actions, "E01 → E02 → E03 Çalıştır",
               lambda: run_synthetic_from_ui(app), True).pack(fill="x", pady=6)
    app.button(actions, "Modül Formları ve Planlayıcı",
               app.open_workflow).pack(fill="x", pady=4)
    app.button(actions, "Kanıt ve Rapor Gezgini",
               lambda: app.open_review("Kanıt İnceleme")).pack(fill="x", pady=4)
