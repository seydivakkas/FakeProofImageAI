"""P9-I05 local dashboard and navigation. Displayed statuses are not physics verdicts."""
from __future__ import annotations
import tkinter as tk
from .journey_core import journey_snapshot

BG='#0a1420'; PANEL='#142639'; CARD='#20384e'; BLUE='#1976d2'
CYAN='#19c5ff'; GREEN='#81c7ae'; TEXT='#e7f2fa'; MUTED='#abbfd1'

def stage_caption(step):
    return {'RECORDED':'Kaydedildi','DRAFT':'Taslak','ATTEMPTED':'Denendi',
            'READY_TO_SELECT':'Seçim gerekli','ACTION_REQUIRED':'Girdi gerekli'
            }.get(step.state,'İncelenecek')

def render_workflow_strip(app):
    snap=journey_snapshot(app.project)
    frame=tk.Frame(app.page,bg=PANEL,padx=10,pady=8)
    frame.pack(fill='x',pady=(0,10))
    row=tk.Frame(frame,bg=PANEL);row.pack(fill='x')
    for index,step in enumerate(snap['steps'],1):
        selected=app.active_page==step.page
        tk.Button(row,text=f'{index}. {step.label}\n{stage_caption(step)}',
                  command=lambda p=step.page:app.go(p),anchor='w',justify='left',
                  relief='flat',bg=BLUE if selected else CARD,
                  fg=TEXT if selected else MUTED,
                  activebackground=BLUE,activeforeground=TEXT,
                  font=('Segoe UI',9),padx=9,pady=7,cursor='hand2'
                  ).pack(side='left',expand=True,fill='x',padx=3)
    tk.Label(frame,text='Yerel iş akışı · Kaydedildi = fiziksel doğrulandı değildir · AI köken kararı yok',
             bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w'
             ).pack(fill='x',pady=(8,0))

def render_home_dashboard(app):
    snap=journey_snapshot(app.project)
    intro=app.box('Projenin Gerçek Durumu')
    overview=tk.Frame(intro,bg=PANEL);overview.pack(fill='x',pady=5)
    for caption,count in [
        ('Görüntüler',snap['image_count']),
        ('Anotasyon Taslakları',snap['annotation_draft_count']),
        ('Fizik Koşumları',snap['physics_success_count']),
        ('P8 Kanıt Koşumları',snap['evidence_success_count']),
        ('Hatalı Koşumlar',snap['failed_run_count'])]:
        card=tk.Frame(overview,bg=CARD,padx=12,pady=11)
        card.pack(side='left',expand=True,fill='x',padx=4)
        tk.Label(card,text=str(count),bg=CARD,fg=CYAN,
                 font=('Segoe UI',19,'bold')).pack(anchor='w')
        tk.Label(card,text=caption,bg=CARD,fg=TEXT,
                 font=('Segoe UI',9)).pack(anchor='w')
    panel=app.box('Adım Adım Çalışma')
    for i,step in enumerate(snap['steps'],1):
        line=tk.Frame(panel,bg=PANEL);line.pack(fill='x',pady=3)
        tk.Label(line,text=f'{i:02d}  {step.label}  |  {stage_caption(step)}',
                 bg=PANEL,fg=GREEN if step.state=='RECORDED' else TEXT,
                 font=('Segoe UI',10,'bold'),width=37,anchor='w').pack(side='left')
        tk.Label(line,text=step.detail,bg=PANEL,fg=MUTED,
                 font=('Segoe UI',9),anchor='w').pack(side='left',expand=True,fill='x')
        app.button(line,'Aç',lambda p=step.page:app.go(p)).pack(side='right',padx=4)
    recent=app.box('Son Analizler (Gerçek CLI Kayıtları)')
    rows=[(r.get('run_id',''),r.get('module_id',''),r.get('state',''))
          for r in reversed(app.project.data['runs'][-8:])]
    app.table(recent,('Çalışma','Modül','Yürütme Durumu'),rows,height=5)
    actions=tk.Frame(app.page,bg=BG);actions.pack(fill='x',pady=4)
    step=next(s for s in snap['steps'] if s.key==snap['recommended_step'])
    app.button(actions,'Sıradaki: '+step.label,lambda:app.go(step.page),True).pack(side='left',padx=5)
    app.button(actions,'Modül Formları',app.open_workflow).pack(side='left',padx=5)
    app.button(actions,'Kanıt / Rapor Gezgini',lambda:app.open_review('Kanıt İnceleme')).pack(side='left',padx=5)
    app.label(app.page,'Sentetik otomatik testler gerçek kamera veya Windows son kullanıcı kabulü değildir.',
              10,MUTED).pack(anchor='w',pady=(7,0))
