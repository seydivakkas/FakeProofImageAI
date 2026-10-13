"""P8-E02 deterministic synthetic stress: no real-camera or AI detection claims."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from aiforensics.evidence_fusion import analyze_fusion_manifest


def scenario_record(module, obs, value, trial):
    asset=f"synthetic-scene-{trial}"
    return {
        "module_id":module, "observation_id":obs, "measured":float(value),
        "predicted":0.0, "unit":"px",
        "assumptions":[{"name":"physical model","status":"supported",
                        "source":"controlled synthetic truth"}],
        "provenance":{"source_id":asset,"calibration_id":f"cal-{trial}",
                      "split":"holdout","independent_of_training":True,
                      "external_reference_verified":True},
        "test":{"null_distribution":"normal_zero_mean_residual",
                "alpha":0.01,"pre_registered":True,
                "distribution_independently_checked":True},
        "uncertainty":{"measurement_std":1.0,"prediction_std":0.0,
                       "error_correlation":0.0},
        "lineage":{"raw_asset_id":asset,"calibration_asset_id":f"cal-{trial}",
                   "reference_id":f"world-{trial}",
                   "holdout_batch_id":f"holdout-{trial}",
                   "feature_family_id":f"feature-{module}",
                   "model_family_id":f"model-{module}"},
    }


def benchmark(trials=80, seed=2208):
    if not 1 <= trials <= 2000:
        raise ValueError("trials outside safe range")
    rng=np.random.default_rng(seed)
    results={"seed":seed,"trials":trials,"synthetic_null_trials":0,
             "synthetic_shifted_trials":0,"false_conditional_rejections_null":0,
             "detection_shifted":0,"missing_lineage_blocks":0}
    for trial in range(trials):
        # All four observations share one synthetic camera; strong correlation.
        z=float(rng.normal())
        shift=4.7 if trial%2 else 0.0
        records=[
            scenario_record(module, f"obs-{i}", z+shift, trial)
            for i,module in enumerate(["P1-G01","P1-G02","P4-O01","P7-S01"])
        ]
        if trial%10==0:
            del records[-1]["lineage"]
        manifest={
            "schema_version":"p8.e01.v1","dataset_scope":"synthetic_controlled",
            "records":records,
            "fusion":{"familywise_alpha":0.01,"plan_pre_registered":True,
                      "dependency_audit_verified":True,
                      "dependence_unknown":False,"declared_edges":[]},
        }
        output=analyze_fusion_manifest(manifest)
        rejected=bool(output["rejected_component_ids"])
        if trial%10==0:
            assert output["overall_state"]=="INDETERMINATE"
            results["missing_lineage_blocks"]+=1
        elif trial%2:
            results["synthetic_shifted_trials"]+=1
            results["detection_shifted"]+=rejected
        else:
            results["synthetic_null_trials"]+=1
            results["false_conditional_rejections_null"]+=rejected
    results["scope"]="correlated-normal synthetic stress, not AI-origin or real-camera performance"
    return results


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--trials",type=int,default=80)
    parser.add_argument("--seed",type=int,default=2208)
    parser.add_argument("--out",type=Path,default=Path("outputs/p8_e02_benchmark.json"))
    args=parser.parse_args()
    report=benchmark(args.trials,args.seed)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
