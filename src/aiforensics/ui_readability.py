"""P9-I10 bounded, source-preserving human review helpers.

All decisions and calibrated values originate in P8 E01/E02/E03 reports;
this module only filters, pages, formats and positions presentation data.
"""
from __future__ import annotations
import json
import math

PAGE_SIZE = 40
MAX_PREVIEW_CHARS = 48_000


def filter_findings(findings, query="", state="TÜMÜ"):
    if not isinstance(findings,list):
        return []
    needle = str(query).casefold().strip()
    allowed = {"TÜMÜ", "INDETERMINATE", "CONSISTENT_UNDER_ASSUMPTIONS",
               "INCONSISTENT_UNDER_ASSUMPTIONS", "NOT_EVALUATED"}
    if state not in allowed:
        raise ValueError("Unrecognized review status filter")
    result=[]
    for finding in findings:
        if not isinstance(finding,dict):
            continue
        single=finding.get("single_test") or {}
        if state!="TÜMÜ" and single.get("state")!=state:
            continue
        target=" ".join(str(finding.get(k,"")) for k in
                        ("record_id","module_id","physical_claim","observation_id"))
        if needle and needle not in target.casefold():
            continue
        result.append(finding)
    return result


def finding_page(findings, page=0, page_size=PAGE_SIZE):
    if not isinstance(page,int) or page<0 or not isinstance(page_size,int) or not 1<=page_size<=100:
        raise ValueError("Invalid evidence pagination")
    total=len(findings)
    pages=max(1,(total+page_size-1)//page_size)
    current=min(page,pages-1)
    return {"items":findings[current*page_size:(current+1)*page_size],
            "page":current,"pages":pages,"total":total}


def format_finding(finding, linked=()):
    """Human-readable, bounded E03 explanation, with raw source values preserved."""
    if not isinstance(finding,dict):
        raise ValueError("E03 finding is required")
    measurement=finding.get("measurement") or {}
    uncertainty=finding.get("uncertainty") or {}
    single=finding.get("single_test") or {}
    group=finding.get("dependency") or {}
    parts=[
        "FİZİKSEL KANIT — E03 KAYIT ÖZETİ",
        "Kayıt: "+str(finding.get("record_id","—")),
        "Modül: "+str(finding.get("module_id","—")),
        "Sıfır hipotezi: "+str(finding.get("physical_claim","—")),
        "",
        "ÖLÇÜM (özgün birim)",
        "Ölçülen: "+str(measurement.get("measured","—")),
        "Beklenen: "+str(measurement.get("predicted","—")),
        "Artık: "+str(measurement.get("signed_residual","—"))+" "+str(measurement.get("unit","")),
        "Artık standart sapması: "+str(uncertainty.get("residual_std","—")),
        "%95 artık aralığı (yalnız kaynakta varsa): "+str(measurement.get("confidence_interval_95_for_residual","—")),
        "",
        "İSTATİSTİKSEL KARAR (yalnız kaynaklı, koşullu)",
        "E01 durum: "+str(single.get("state","—")),
        "E01 p-değeri: "+str(single.get("p_value_two_sided","—")),
        "E02 grup: "+str(group.get("component_id","—")),
        "E02 grup durumu: "+str(group.get("component_state","—")),
        "E02 Holm p-değeri: "+str(group.get("holm_adjusted_p_value","—")),
        "",
        "VARSAYIMLAR / KÖKEN / GEREKÇELER",
    ]
    for item in (finding.get("assumptions") or [])[:50]:
        if isinstance(item,dict):
            parts.append("• "+str(item.get("name",""))+" · "+str(item.get("status",""))+
                         " · "+str(item.get("source","")))
    parts.append("Kaynak: "+str(finding.get("provenance") or {}))
    for reason in (finding.get("explanation") or [])[:100]:
        parts.append("• "+str(reason))
    parts += ["", "GÖRÜNTÜ BAĞLANTISI (kullanıcı beyanı, bağımsız doğrulama değil)"]
    for item in list(linked)[:50]:
        parts.append("• "+str(item.get("image",""))+" — "+str(item.get("provenance","")))
    if not linked:
        parts.append("Bağlanmış görüntü yok.")
    parts += ["", "AI kökeni kararı: NO_AI_ORIGIN_CONCLUSION",
              "Sentetik/koşullu kanıt gerçek kamera kabulü değildir."]
    content="\n".join(parts)
    return content[:MAX_PREVIEW_CHARS]+("\n[Uzun açıklama kesildi; kaynak E03 JSON'unda mevcut.]" if len(content)>MAX_PREVIEW_CHARS else "")


def graph_point(x, y, zoom=1.0, pan_x=0.0, pan_y=0.0):
    values=(x,y,zoom,pan_x,pan_y)
    if not all(isinstance(a,(int,float)) and not isinstance(a,bool) and math.isfinite(a)
               for a in values) or not 0.45<=zoom<=3.0:
        raise ValueError("Invalid graph viewport")
    return (x*zoom+pan_x,y*zoom+pan_y)


def clamp_zoom(value):
    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
        raise ValueError("Invalid zoom")
    return min(3.0,max(0.45,float(value)))
