"""Synthetic, safety and integration checks for E03."""
import json
import subprocess
import sys

import pytest
from aiforensics.evidence_contract import EvidenceContractError, analyze_evidence_manifest
from aiforensics.evidence_fusion import analyze_fusion_manifest
from aiforensics.evidence_explain import (
    EXPLAIN_SCHEMA_VERSION, build_explainable_report, render_html_report,
    run_explainable_manifest,
)


def record(module="P1-G01", obs="a", residual=4, asset="a", supported=True):
    return {
        "module_id": module, "observation_id": obs,
        "measured": 20 + residual, "predicted": 20, "unit": "px",
        "assumptions": [{"name": "physical plane", "status":
                         "supported" if supported else "unknown", "source": "synthetic truth"}],
        "provenance": {"source_id": asset, "calibration_id": "cal-"+asset,
                       "split": "holdout", "independent_of_training": True,
                       "external_reference_verified": True},
        "uncertainty": {"measurement_std": 1, "prediction_std": 0,
                        "error_correlation": 0},
        "test": {"null_distribution": "normal_zero_mean_residual", "alpha": .01,
                 "pre_registered": True, "distribution_independently_checked": True},
        "lineage": {"raw_asset_id": asset, "calibration_asset_id": "cal-"+asset,
                    "reference_id": "ref-"+asset, "holdout_batch_id": "holdout-"+asset,
                    "feature_family_id": "feature-"+asset, "model_family_id": "model-"+module},
    }


def fixture(*records, **options):
    conf = {"familywise_alpha": .01, "plan_pre_registered": True,
            "dependency_audit_verified": True, "dependence_unknown": False,
            "declared_edges": []}
    conf.update(options)
    return {"schema_version": "p8.e01.v1", "dataset_scope": "synthetic_controlled",
            "records": list(records), "fusion": conf}


def report(m):
    return build_explainable_report(m, analyze_evidence_manifest(m),
                                    analyze_fusion_manifest(m))


def test_conditional_not_origin_verdict():
    r = report(fixture(record()))
    assert r["schema_version"] == EXPLAIN_SCHEMA_VERSION
    assert r["origin_probability"] is None
    assert r["decision"] == "NO_AI_ORIGIN_CONCLUSION"
    assert r["summary"]["conditional_rejected_group_ids"]


def test_shared_source_is_single_group():
    r = report(fixture(record(), record("P7-S01", "b", asset="a")))
    assert r["summary"]["dependency_group_count"] == 1
    group = r["dependency_groups"][0]
    assert group["member_count"] == 2
    assert any(x["field"] == "lineage.raw_asset_id"
               for x in group["shared_evidence"]["shared_references"])
    assert r["findings"][0]["dependency"]["other_member_ids"]


def test_explicit_dependency_reason_visible():
    edge = {"left": "P1-G01/a", "right": "P7-S01/b",
            "reason": "shared latent illumination"}
    r = report(fixture(record(), record("P7-S01", "b", asset="b"),
                       declared_edges=[edge]))
    assert r["dependency_groups"][0]["explicit_edges"] == [edge]
    assert "shared latent illumination" in render_html_report(r)


def test_bad_assumptions_block_group():
    r = report(fixture(record(), record("P7-S01", "b", supported=False)))
    assert r["summary"]["overall_state"] == "INDETERMINATE"
    assert r["dependency_groups"][0]["state"] == "NOT_TESTED"
    assert r["findings"][1]["single_test"]["p_value_two_sided"] is None


def test_audit_gate_blocks():
    r = report(fixture(record(), dependency_audit_verified=False))
    assert r["summary"]["fusion_state"] == "NOT_PERFORMED"


def test_html_has_no_unescaped_injection():
    r = report(fixture(record(obs="<script>alert(1)</script>",
                              asset='"><img src=x onerror=evil()>')))
    page = render_html_report(r)
    assert "<script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page
    assert "script-src" in page


def test_html_limit_is_disclosed():
    r = report(fixture(record(), record("P7-S01", "b", asset="b")))
    page = render_html_report(r, max_findings=1)
    assert "1/2" in page
    assert page.count("<article><h3>") >= 2
    with pytest.raises(ValueError):
        render_html_report(r, max_findings=0)


def test_mismatched_component_membership_rejected():
    m = fixture(record())
    e01, e02 = analyze_evidence_manifest(m), analyze_fusion_manifest(m)
    e02["dependency_components"][0]["members"] = ["bad"]
    with pytest.raises(EvidenceContractError):
        build_explainable_report(m, e01, e02)


def test_output_roundtrip_and_hash(tmp_path):
    source = tmp_path/"in.json"
    source.write_text(json.dumps(fixture(record())))
    saved = run_explainable_manifest(source, tmp_path/"out")
    assert json.loads((tmp_path/"out"/"p8_e03_explainable_report.json").read_text()) == saved
    assert (tmp_path/"out"/"p8_e03_explainable_report.html").exists()


def test_cli_explain_evidence(tmp_path):
    src = tmp_path/"in.json"
    src.write_text(json.dumps(fixture(record())))
    out = tmp_path/"out"
    result = subprocess.run(
        [sys.executable, "-m", "aiforensics", "explain-evidence",
         "--input", str(src), "--out", str(out)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "NO_AI_ORIGIN_CONCLUSION"
    assert (out/"p8_e03_explainable_report.html").exists()
