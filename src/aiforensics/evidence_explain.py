"""P8-E03: explain E01/E02 conditional physical evidence; never infer AI origin."""
from __future__ import annotations

from collections import defaultdict
import hashlib
from html import escape
import json
import math
from pathlib import Path

from .evidence_contract import (
    SCHEMA_VERSION, MODULES, EvidenceContractError, analyze_evidence_manifest,
)
from .evidence_fusion import analyze_fusion_manifest, FUSION_SCHEMA_VERSION

EXPLAIN_SCHEMA_VERSION = "p8.e03.v1"
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_HTML_FINDINGS = 250


def _label(item):
    return str(item["module_id"]) + "/" + str(item["observation_id"])


def _num(value):
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and math.isfinite(value):
        return format(value, ".8g")
    return str(value)


def _h(value):
    return escape(str(value), quote=True)


def _validate_alignment(manifest, individual, fusion):
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceContractError("invalid input schema")
    if individual.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceContractError("invalid individual schema")
    if fusion.get("schema_version") != FUSION_SCHEMA_VERSION:
        raise EvidenceContractError("invalid fusion schema")
    raw = manifest.get("records")
    evaluated = individual.get("records")
    linked = fusion.get("individual_records")
    groups = fusion.get("dependency_components")
    if not all(isinstance(x, list) for x in (raw, evaluated, linked, groups)):
        raise EvidenceContractError("required arrays are missing")
    if len(raw) != len(evaluated) or len(evaluated) != len(linked):
        raise EvidenceContractError("E01/E02 cardinality mismatch")
    labels = [_label(x) for x in evaluated]
    if labels != [x.get("record_id") for x in linked] or len(labels) != len(set(labels)):
        raise EvidenceContractError("E01/E02 record identity mismatch")
    if labels != [_label(x) for x in raw]:
        raise EvidenceContractError("input/E01 order mismatch")
    members = [name for group in groups for name in group.get("members", [])]
    if len(members) != len(labels) or set(members) != set(labels) or len(members) != len(set(members)):
        raise EvidenceContractError("group membership does not partition records")
    if individual.get("dataset_scope") != fusion.get("dataset_scope"):
        raise EvidenceContractError("dataset scope mismatch")
    if fusion.get("decision") != "NO_AI_ORIGIN_CONCLUSION":
        raise EvidenceContractError("unsupported origin verdict")


def _shared_references(members, limit=250):
    values = defaultdict(list)
    for item in members:
        rid = item["record_id"]
        for name in ("source_id", "calibration_id"):
            value = item.get("provenance", {}).get(name)
            if isinstance(value, str) and value:
                values[("provenance." + name, value)].append(rid)
        for name, value in (item.get("lineage") or {}).items():
            if isinstance(value, str) and value:
                values[("lineage." + name, value)].append(rid)
    shared = sorted((key, value, sorted(set(ids))) for (key, value), ids in values.items()
                    if len(set(ids)) > 1)
    return {"shared_reference_count": len(shared),
            "shared_references": [
                {"field": key, "identifier": value, "members": ids}
                for key, value, ids in shared[:limit]],
            "omitted_shared_reference_count": max(0, len(shared)-limit)}


def build_explainable_report(manifest, e01_report, e02_report, *, input_sha256=None):
    """Formatting API; only the run entry point guarantees E01/E02 recomputation."""
    _validate_alignment(manifest, e01_report, e02_report)
    by_group = {group["component_id"]: group for group in e02_report["dependency_components"]}
    if len(by_group) != len(e02_report["dependency_components"]):
        raise EvidenceContractError("duplicate dependency group")
    measured = {_label(item): item for item in e01_report["records"]}
    persons = {}
    for item in e02_report["individual_records"]:
        group = by_group.get(item.get("component_id"))
        if group is None or item["record_id"] not in group["members"]:
            raise EvidenceContractError("broken individual/group association")
        persons[item["record_id"]] = dict(item, provenance=measured[item["record_id"]]["provenance"])
    findings = []
    for raw, individual, person in zip(manifest["records"], e01_report["records"],
                                       e02_report["individual_records"]):
        rid = _label(individual)
        group = by_group[person["component_id"]]
        reasons = list(individual["reasons"])
        reasons.extend(person["exclusion_reasons"])
        reasons.extend(group["blocking_reasons"])
        if group["state"] == "REJECTS_CONDITIONAL_COMPONENT_NULL":
            reasons.append("Grup intersection-null reddedildi; hangi üyenin bağımsız kanıt olduğu çıkarılamaz.")
        elif group["state"] == "DOES_NOT_REJECT_CONDITIONAL_COMPONENT_NULL":
            reasons.append("Grup hipotezi reddedilmedi; bu özgünlük veya fiziksel doğruluk kanıtı değildir.")
        else:
            reasons.append("Bağımlılık grubu test edilmedi veya denetim nedeniyle engellendi.")
        findings.append({
            "record_id": rid, "module_id": individual["module_id"],
            "module_label": MODULES[individual["module_id"]],
            "observation_id": individual["observation_id"],
            "physical_claim": individual["test"]["null_hypothesis"],
            "measurement": {key: individual.get(key) for key in (
                "unit", "measured", "predicted", "signed_residual",
                "effect_size_absolute", "standardized_effect",
                "confidence_interval_95_for_residual")},
            "uncertainty": individual["uncertainty"],
            "assumptions": individual["assumptions"],
            "provenance": individual["provenance"],
            "lineage": person["lineage"],
            "single_test": {
                "state": individual["state"], "reasons": individual["reasons"],
                "p_value_two_sided": individual["p_value_two_sided"],
                "alpha": individual["test"]["alpha"],
                "eligible_for_fusion": person["eligible"],
                "exclusion_reasons": person["exclusion_reasons"]},
            "dependency": {
                "component_id": group["component_id"], "component_state": group["state"],
                "other_member_ids": [x for x in group["members"] if x != rid],
                "p_value_union_bound": group["p_value_union_bound"],
                "holm_adjusted_p_value": group["holm_adjusted_p_value"],
                "blocking_reasons": group["blocking_reasons"]},
            "explanation": reasons, "image_origin_conclusion": "NOT_EVALUATED"})
    groups = []
    for group in e02_report["dependency_components"]:
        linked = [persons[rid] for rid in group["members"]]
        edges = [e for e in e02_report["explicit_dependency_edges"]
                 if e["left"] in group["members"] and e["right"] in group["members"]]
        groups.append({
            "component_id": group["component_id"], "members": group["members"],
            "member_count": group["member_count"], "module_ids": group["module_ids"],
            "state": group["state"], "blocking_reasons": group["blocking_reasons"],
            "lineage_reuse": group["lineage_reuse"],
            "shared_evidence": _shared_references(linked),
            "explicit_edges": edges,
            "p_value_union_bound": group["p_value_union_bound"],
            "holm_adjusted_p_value": group["holm_adjusted_p_value"],
            "rejects_component_intersection_null":
                group["rejects_component_intersection_null"]})
    return {
        "schema_version": EXPLAIN_SCHEMA_VERSION, "engine": "P8-E03",
        "dataset_scope": e02_report["dataset_scope"],
        "source_manifest_sha256": input_sha256,
        "source_analysis_schemas": {"individual": SCHEMA_VERSION, "fusion": FUSION_SCHEMA_VERSION},
        "summary": {
            "record_count": len(findings), "dependency_group_count": len(groups),
            "module_ids": sorted({x["module_id"] for x in findings}),
            "individual_state_counts": e01_report["summary_counts"],
            "group_state_counts": e02_report["summary_counts"],
            "fusion_state": e02_report["fusion_state"],
            "overall_state": e02_report["overall_state"],
            "conditional_rejected_group_ids": e02_report["rejected_component_ids"],
            "blocked_group_ids": e02_report["blocked_component_ids"],
            "method": e02_report["method"],
            "multiplicity_control": e02_report["multiplicity_control"]},
        "findings": findings, "dependency_groups": groups,
        "explicit_dependency_edges": e02_report["explicit_dependency_edges"],
        "decision": "NO_AI_ORIGIN_CONCLUSION", "origin_probability": None,
        "explanation_policy": {
            "p_values_recalculated_here": False,
            "statistical_inference_delegated_to": ["P8-E01", "P8-E02"],
            "single_test_significance_is_not_familywise_significance": True,
            "report_generation_is_not_source_authentication": True,
            "real_world_calibration_completed": False},
        "warnings": list(e02_report["warnings"]) + [
            "Report formatting does not create additional independent evidence.",
            "Identifiers may be sensitive; exports are local until explicitly shared."]}


def render_html_report(report, *, max_findings=MAX_HTML_FINDINGS):
    """Script-free, HTML-escaped standalone report; no external resources."""
    if type(max_findings) is not int or not 1 <= max_findings <= 10000:
        raise ValueError("max_findings must be in 1..10000")
    result = ['<!doctype html><html lang="tr"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; script-src &#39;none&#39;; img-src &#39;none&#39;; object-src &#39;none&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">',
        '<title>FakeProofImageAI — P8-E03</title>',
        '<style>body{font:15px/1.55 system-ui,sans-serif;color:#142138;max-width:1100px;padding:24px;margin:auto;background:#f6f8fb}section,article{background:white;padding:16px;margin:12px 0;border:1px solid #d7dfe9;border-radius:10px;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e0e5eb;padding:8px}summary{cursor:pointer;font-weight:bold}small{color:#516074}p{overflow-wrap:anywhere}</style></head><body>',
        '<h1>FakeProofImageAI · P8-E03</h1>',
        '<section><strong>AI kökeni belirlenmez.</strong> Koşullu fiziksel hipotezlerin değerlendirmesi, fotoğrafın gerçekliğine veya AI kökenine ilişkin bir olasılık değildir.</section>',
        '<section><h2>Birleşik sonuç</h2>']
    summary = report["summary"]
    for title, value in (
        ("Kapsam", report["dataset_scope"]), ("Ölçüm", summary["record_count"]),
        ("Bağımlılık grubu", summary["dependency_group_count"]),
        ("Grup durumu", summary["overall_state"]), ("Birleşim", summary["fusion_state"]),
        ("İstatistiksel yöntem", summary["method"]),
        ("Karar", report["decision"]), ("Kaynak SHA-256",
                                         report.get("source_manifest_sha256") or "yok")):
        result.append("<p><strong>" + _h(title) + ":</strong> " + _h(value) + "</p>")
    result.append("</section><section><h2>Bağımlılık grafiği</h2>")
    for group in report["dependency_groups"]:
        result.append("<article><h3>" + _h(group["component_id"]) + "</h3><p>" +
                      _h(group["state"]) + " · " + _h(group["member_count"]) +
                      " ölçüm</p><p><strong>Üyeler:</strong> " +
                      _h(", ".join(group["members"])) + "</p><p>Grup p = " +
                      _h(_num(group["p_value_union_bound"])) + ", Holm p = " +
                      _h(_num(group["holm_adjusted_p_value"])) + "</p>")
        refs = group["shared_evidence"]
        if refs["shared_references"]:
            result.append("<details><summary>Ortak kaynak ve kalibrasyonlar</summary><ul>")
            for ref in refs["shared_references"]:
                result.append("<li>" + _h(ref["field"]) + " = " + _h(ref["identifier"]) +
                              " [" + _h(", ".join(ref["members"])) + "]</li>")
            result.append("</ul></details>")
        for edge in group["explicit_edges"]:
            result.append("<p>Açık bağımlılık: " + _h(edge["left"]) + " ↔ " +
                          _h(edge["right"]) + ": " + _h(edge["reason"]) + "</p>")
        for reason in group["blocking_reasons"]:
            result.append("<p>Engelleme: " + _h(reason) + "</p>")
        if refs["omitted_shared_reference_count"]:
            result.append("<p>Gösterilmeyen referans: " +
                          _h(refs["omitted_shared_reference_count"]) + "</p>")
        result.append("</article>")
    result.append("</section><section><h2>Tekil ölçümler ve gerekçeleri</h2>")
    for finding in report["findings"][:max_findings]:
        measured = finding["measurement"]
        result.append("<article><h3>" + _h(finding["record_id"]) + "</h3><p>" +
                      _h(finding["module_label"]) + " · " +
                      _h(finding["single_test"]["state"]) + "</p>")
        result.append("<table><tr><th>Ölçülen</th><th>Beklenen</th><th>Artık</th><th>Artık σ</th><th>p</th></tr><tr><td>" +
                      _h(_num(measured["measured"])) + " " + _h(measured["unit"]) +
                      "</td><td>" + _h(_num(measured["predicted"])) +
                      "</td><td>" + _h(_num(measured["signed_residual"])) +
                      "</td><td>" + _h(_num(finding["uncertainty"]["residual_std"])) +
                      "</td><td>" + _h(_num(finding["single_test"]["p_value_two_sided"])) +
                      "</td></tr></table><p>Hipotez: " + _h(finding["physical_claim"]) + "</p>")
        result.append("<details><summary>Varsayımlar, kaynaklar, karara etki</summary><ul>")
        for assumption in finding["assumptions"]:
            result.append("<li>" + _h(assumption.get("name")) + ": " +
                          _h(assumption.get("status")) + " · kaynak: " +
                          _h(assumption.get("source")) + "</li>")
        for reason in finding["explanation"]:
            result.append("<li>" + _h(reason) + "</li>")
        result.append("</ul><p>Kaynak: " + _h(finding["provenance"].get("source_id")) +
                      " · Kalibrasyon: " + _h(finding["provenance"].get("calibration_id")) +
                      "</p><p>İlişkili kayıtlar: " +
                      _h(", ".join(finding["dependency"]["other_member_ids"])) +
                      "</p></details></article>")
    if len(report["findings"]) > max_findings:
        result.append("<p>HTML görüntüleme sınırı: " + _h(max_findings) + "/" +
                      _h(len(report["findings"])) +
                      ". Tüm bulgular JSON raporunda yer alır.</p>")
    result.append("</section><section><h2>Bilimsel sınırlamalar</h2><ul>")
    for warning in report["warnings"]:
        result.append("<li>" + _h(warning) + "</li>")
    result.append("</ul></section></body></html>")
    return "".join(result)


def _reject_constant(value):
    raise EvidenceContractError("non-finite JSON numeric constant: " + value)


def run_explainable_manifest(input_path, out_dir, *, max_html_findings=MAX_HTML_FINDINGS):
    source = Path(input_path)
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise EvidenceContractError("input file exceeds report size limit")
    payload = source.read_bytes()
    manifest = json.loads(payload, parse_constant=_reject_constant)
    e01 = analyze_evidence_manifest(manifest)
    e02 = analyze_fusion_manifest(manifest)
    report = build_explainable_report(
        manifest, e01, e02, input_sha256=hashlib.sha256(payload).hexdigest())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "p8_e03_explainable_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8")
    (out / "p8_e03_explainable_report.html").write_text(
        render_html_report(report, max_findings=max_html_findings),
        encoding="utf-8")
    return report
