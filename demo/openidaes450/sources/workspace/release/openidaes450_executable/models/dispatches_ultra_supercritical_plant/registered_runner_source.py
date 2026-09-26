#!/usr/bin/env python3
"""Validate the DISPATCHES ultra-supercritical plant reference topology asset."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402
from stage1_reference.reference_topology_ir import extract_svg_labels  # noqa: E402

configure_py310_runtime()

SOURCE_URL = "local://dispatches/case_studies/fossil_case/ultra_supercritical_plant"
SVG_PATH = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-04-29/"
    "examples/archived_canonical_sources/cases/github_examples/clones/dispatches/"
    "dispatches/case_studies/fossil_case/ultra_supercritical_plant/pfd_ultra_supercritical_pc.svg"
)
REQUIRED_LABELS = {
    "Ultra Supercritical Pulverized Coal Power Plant",
    "Boiler",
    "Reheater 1",
    "Reheater 2",
    "FWH1",
    "FWH9",
    "condenser",
    "BFW Pump",
    "Power out (MWe)",
}


def run_case() -> dict:
    try:
        labels = extract_svg_labels(SVG_PATH, max_labels=250) if SVG_PATH.is_file() else []
        label_set = set(labels)
        missing = sorted(label for label in REQUIRED_LABELS if label not in label_set)
        turbine_count = sum(1 for label in labels if label.startswith("Turbine "))
        fwh_count = sum(1 for label in labels if label.startswith("FWH"))
        passed = SVG_PATH.is_file() and not missing and turbine_count >= 11 and fwh_count >= 9
        return {
            "pass": passed,
            "stage": "topology_reference_validation",
            "case_family": "dispatches_ultra_supercritical_plant",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "topology_only",
            "checks": [
                {"name": "usc_pfd_svg_exists", "pass": SVG_PATH.is_file()},
                {"name": "usc_required_labels_present", "pass": not missing},
                {"name": "usc_turbine_train_labels_present", "pass": turbine_count >= 11},
                {"name": "usc_feedwater_heater_labels_present", "pass": fwh_count >= 9},
            ],
            "final_dof": None,
            "pfd_svg": str(SVG_PATH),
            "label_count": len(labels),
            "turbine_label_count": turbine_count,
            "feedwater_heater_label_count": fwh_count,
            "missing_labels": missing,
            "source_summary": {
                "source": "dispatches.case_studies.fossil_case.ultra_supercritical_plant.pfd_ultra_supercritical_pc.svg",
                "configuration": "topology-only validation for the official USC pulverized coal plant PFD",
                "labels": labels[:80],
            },
            "error": None if passed else {"message": "DISPATCHES USC PFD topology validation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "topology_reference_validation",
            "case_family": "dispatches_ultra_supercritical_plant",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "usc_topology_reference_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
