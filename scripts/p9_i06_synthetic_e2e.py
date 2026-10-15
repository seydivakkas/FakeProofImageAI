"""CLI-level controlled software journey; does not use real images."""
import argparse
import json
import tempfile
from pathlib import Path
from aiforensics.desktop_core import Project
from aiforensics.integration_flow import run_evidence_chain, save_example


def main(argv=None):
    p = argparse.ArgumentParser(description="Synthetic E01 E02 E03 software workflow")
    p.add_argument("--workspace", type=Path)
    args = p.parse_args(argv)
    if args.workspace:
        workspace = args.workspace
        workspace.mkdir(parents=True, exist_ok=True)
        project = Project(workspace, "SentetikEntegrasyon")
        report = run_evidence_chain(project, save_example(project))
    else:
        with tempfile.TemporaryDirectory(prefix="fakeproof-p9-i06-") as tmp:
            project = Project(tmp, "SentetikEntegrasyon")
            report = run_evidence_chain(project, save_example(project))
    print(json.dumps({
        "stages": [x["module_id"] for x in report["steps"]],
        "scope": report["scope"], "decision": report["decision"],
        "camera_validation": report["camera_validation"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
