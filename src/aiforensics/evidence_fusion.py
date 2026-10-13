"""P8-E02: dependency-aware, familywise-valid conditional evidence aggregation.

Not an AI-origin classifier or posterior probability. Given calibrated E01
marginal p-values, potentially overlapping findings are clustered. Within each
connected component use a Bonferroni union bound; across components use Holm.
These procedures are valid under arbitrary dependence *when* marginal nulls
are correctly calibrated and the collection has been pre-specified.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .evidence_contract import (
    SCHEMA_VERSION, EvidenceContractError, analyze_evidence_manifest,
)

FUSION_SCHEMA_VERSION = "p8.e02.v1"
LINEAGE_FIELDS = (
    "raw_asset_id", "calibration_asset_id", "reference_id",
    "holdout_batch_id", "feature_family_id", "model_family_id",
)
MAX_RECORDS = 10000


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceContractError(f"{name} must be a nonempty string")
    if len(value) > 512:
        raise EvidenceContractError(f"{name} is too long")
    return value.strip()


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise EvidenceContractError(f"{name} must be boolean")
    return value


def _lineage(record: dict, key: str) -> tuple[dict[str, str] | None, str | None]:
    value = record.get("lineage")
    if not isinstance(value, dict):
        return None, "lineage absent or malformed; potential common data unassessed"
    if any(k not in LINEAGE_FIELDS for k in value):
        return None, "unrecognized lineage field; dependency completeness not established"
    try:
        result = {name: _text(value.get(name), f"{key}.lineage.{name}") for name in LINEAGE_FIELDS}
    except EvidenceContractError as exc:
        return None, str(exc)
    return result, None


def _config(manifest: dict) -> tuple[dict, list[str]]:
    conf = manifest.get("fusion")
    if not isinstance(conf, dict):
        raise EvidenceContractError("fusion must be a config object")
    allowed = {"familywise_alpha", "plan_pre_registered",
               "dependency_audit_verified", "declared_edges", "dependence_unknown"}
    if set(conf) - allowed:
        raise EvidenceContractError("unexpected fusion config field")
    try:
        alpha = float(conf.get("familywise_alpha"))
    except (ValueError, TypeError) as exc:
        raise EvidenceContractError("familywise_alpha required") from exc
    if isinstance(conf.get("familywise_alpha"), bool) or not math.isfinite(alpha) or not 0 < alpha < 1:
        raise EvidenceContractError("familywise_alpha must lie strictly in (0,1)")
    prereg = _bool(conf.get("plan_pre_registered"), "fusion.plan_pre_registered")
    audit = _bool(conf.get("dependency_audit_verified"), "fusion.dependency_audit_verified")
    unknown = _bool(conf.get("dependence_unknown", False), "fusion.dependence_unknown")
    edges = conf.get("declared_edges", [])
    if not isinstance(edges, list) or len(edges) > MAX_RECORDS * 2:
        raise EvidenceContractError("declared_edges must be a bounded array")
    reasons = []
    if not prereg:
        reasons.append("multiple-comparison plan not pre-registered")
    if not audit:
        reasons.append("cross-module dependency audit not independently verified")
    if unknown:
        reasons.append("unresolved dependency relationships declared")
    return {"familywise_alpha": alpha, "plan_pre_registered": prereg,
            "dependency_audit_verified": audit, "dependence_unknown": unknown,
            "declared_edges": edges}, reasons


class _DSU:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        x, y = self.find(x), self.find(y)
        if x == y:
            return
        if self.size[x] < self.size[y]:
            x, y = y, x
        self.parent[y] = x
        self.size[x] += self.size[y]


def analyze_fusion_manifest(manifest: dict) -> dict:
    """Re-evaluate E01 inputs; never accept externally supplied p-values.

    Group p = min(1,m * min(marginal p)) is valid for the intersection null
    under arbitrary within-group dependence. Holm across groups controls
    the familywise error for tested group intersection nulls.
    """
    if not isinstance(manifest, dict):
        raise EvidenceContractError("manifest must be an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceContractError("P8-E01 schema_version required for input records")
    conf, global_reasons = _config(manifest)
    evaluation = analyze_evidence_manifest(manifest)
    records = manifest["records"]
    evaluated = evaluation["records"]
    if len(records) > MAX_RECORDS:
        raise EvidenceContractError("too many records")
    keys = [(r["module_id"], r["observation_id"]) for r in evaluated]
    labels = [f"{module}/{obs}" for module, obs in keys]
    label_to_idx = {label: i for i, label in enumerate(labels)}
    if len(label_to_idx) != len(labels):
        raise EvidenceContractError("nonunique canonical record label")
    dsu = _DSU(len(records))
    first_seen: dict[tuple[str, str], int] = {}
    individual = []
    lineage_by_index = {}
    for i, (raw, measured) in enumerate(zip(records, evaluated)):
        label = labels[i]
        lineage, lineage_problem = _lineage(raw, label)
        reasons = []
        if lineage_problem:
            reasons.append(lineage_problem)
        if measured["state"] in ("INDETERMINATE", "NOT_APPLICABLE") or measured["p_value_two_sided"] is None:
            reasons.append("E01 marginal null not independently calibrated or evaluable")
        if lineage is not None:
            lineage_by_index[i] = lineage
            for name, value in lineage.items():
                token = (name, value)
                if token in first_seen:
                    dsu.union(i, first_seen[token])
                else:
                    first_seen[token] = i
        prov = measured["provenance"]
        if not prov.get("independent_of_training") or prov.get("split") != "holdout":
            reasons.append("train/holdout leakage gate")
        individual.append({
            "record_id": label, "module_id": keys[i][0],
            "observation_id": keys[i][1], "e01_state": measured["state"],
            "p_value_two_sided": measured["p_value_two_sided"],
            "eligible": not reasons, "exclusion_reasons": reasons, "lineage": lineage,
        })
    # Also union source/calibration identity provided by the E01 contract
    # even if an E02 lineage declaration spuriously claims different data.
    for name in ("source_id", "calibration_id"):
        first_provenance = {}
        for i, e in enumerate(evaluated):
            token = e["provenance"].get(name)
            if isinstance(token, str) and token.strip():
                if token in first_provenance:
                    dsu.union(i, first_provenance[token])
                else:
                    first_provenance[token] = i
    explicit_edges = []
    for edge in conf["declared_edges"]:
        if not isinstance(edge, dict) or set(edge) != {"left", "right", "reason"}:
            raise EvidenceContractError("declared_edges require left, right, reason")
        left = _text(edge["left"], "edge.left")
        right = _text(edge["right"], "edge.right")
        reason = _text(edge["reason"], "edge.reason")
        if left not in label_to_idx or right not in label_to_idx:
            raise EvidenceContractError("declared edge references unknown record")
        if left == right:
            raise EvidenceContractError("self dependency edge")
        dsu.union(label_to_idx[left], label_to_idx[right])
        explicit_edges.append({"left": left, "right": right, "reason": reason})
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(len(records)):
        clusters[dsu.find(i)].append(i)
    components = []
    for indices in sorted(clusters.values(), key=lambda v: min(v)):
        ids = [labels[i] for i in indices]
        eligible_indices = [i for i in indices if individual[i]["eligible"]]
        # Never select favorable tests from a component containing an
        # uncalibrated, unknown or nonreportable linked measurement.
        blocked = len(eligible_indices) != len(indices)
        p = None
        if not blocked:
            p = min(1.0, len(indices) * min(evaluated[i]["p_value_two_sided"] for i in indices))
        component = {
            "component_id": f"dependency_{len(components) + 1:03d}",
            "members": ids, "member_count": len(indices),
            "module_ids": sorted(set(keys[i][0] for i in indices)),
            "lineage_reuse": sorted({
                field for field in LINEAGE_FIELDS
                if len({lineage_by_index[i][field] for i in indices if i in lineage_by_index})
                   < len([i for i in indices if i in lineage_by_index])
            }),
            "p_value_union_bound": p, "eligible": not blocked,
            "holm_adjusted_p_value": None,
            "rejects_component_intersection_null": None,
            "state": "NOT_TESTED" if blocked else "AWAITING_MULTIPLICITY_CORRECTION",
            "blocking_reasons": sorted({
                reason for i in indices
                for reason in individual[i]["exclusion_reasons"]
            }),
        }
        components.append(component)
        for i in indices:
            individual[i]["component_id"] = component["component_id"]
    eligible_components = [c for c in components if c["eligible"]]
    if not global_reasons and eligible_components:
        ordered = sorted(eligible_components, key=lambda c: (c["p_value_union_bound"], c["component_id"]))
        m = len(ordered)
        floor = 0.0
        for j, comp in enumerate(ordered):
            floor = max(floor, min(1.0, (m-j) * comp["p_value_union_bound"]))
            comp["holm_adjusted_p_value"] = floor
            comp["rejects_component_intersection_null"] = floor <= conf["familywise_alpha"]
            comp["state"] = (
                "REJECTS_CONDITIONAL_COMPONENT_NULL" if floor <= conf["familywise_alpha"]
                else "DOES_NOT_REJECT_CONDITIONAL_COMPONENT_NULL"
            )
    elif global_reasons:
        for comp in eligible_components:
            comp["state"] = "BLOCKED_GLOBAL_DEPENDENCE_AUDIT"
            comp["blocking_reasons"] = global_reasons
    rejected = [c["component_id"] for c in components
                if c["rejects_component_intersection_null"] is True]
    blocked_ids = [c["component_id"] for c in components
                   if not c["eligible"] or global_reasons]
    counts = {s: sum(c["state"] == s for c in components) for s in (
        "REJECTS_CONDITIONAL_COMPONENT_NULL",
        "DOES_NOT_REJECT_CONDITIONAL_COMPONENT_NULL",
        "BLOCKED_GLOBAL_DEPENDENCE_AUDIT", "NOT_TESTED"
    )}
    return {
        "schema_version": FUSION_SCHEMA_VERSION, "input_schema_version": SCHEMA_VERSION,
        "engine": "P8-E02", "dataset_scope": evaluation["dataset_scope"],
        "record_count": len(records), "component_count": len(components),
        "lineage_fields": list(LINEAGE_FIELDS),
        "method": "within-component Bonferroni union bound; Holm across eligible components",
        "multiplicity_control": {
            "target": "familywise error for tested component intersection nulls",
            "familywise_alpha": conf["familywise_alpha"],
            "arbitrary_dependence_valid": True,
            "tested_component_count": len(eligible_components) if not global_reasons else 0,
            "plan_pre_registered": conf["plan_pre_registered"],
            "dependency_audit_verified": conf["dependency_audit_verified"],
        },
        "individual_records": individual, "dependency_components": components,
        "explicit_dependency_edges": explicit_edges,
        "summary_counts": counts, "rejected_component_ids": rejected,
        "blocked_component_ids": blocked_ids,
        "fusion_state": (
            "NOT_PERFORMED" if global_reasons or not eligible_components
            else "CONDITIONAL_FAMILYWISE_AGGREGATION"
        ),
        "overall_state": (
            "INDETERMINATE" if global_reasons or blocked_ids
            else "SOME_COMPONENT_NULLS_REJECTED" if rejected
            else "NO_COMPONENT_NULL_REJECTED"
        ),
        "decision": "NO_AI_ORIGIN_CONCLUSION",
        "warnings": [
            "Component rejection means at least one conditional physical null may fail, not AI origin.",
            "Failure to reject does not establish model correctness or image authenticity.",
            "Neither the group p-values nor adjusted p-values are posterior or AI probabilities.",
            "Undeclared shared causes and imperfect marginal null calibration invalidate nominal FWER.",
            "A union bound does not create extra information from correlated measurements.",
            "Real camera measurements and false positive calibration remain a final phase.",
        ],
    }


def run_fusion_manifest(input_path: str | Path, out_dir: str | Path) -> dict:
    source = Path(input_path)
    content = source.read_bytes()
    manifest = json.loads(content)
    report = analyze_fusion_manifest(manifest)
    report["source_manifest_sha256"] = hashlib.sha256(content).hexdigest()
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "p8_e02_fusion_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report
