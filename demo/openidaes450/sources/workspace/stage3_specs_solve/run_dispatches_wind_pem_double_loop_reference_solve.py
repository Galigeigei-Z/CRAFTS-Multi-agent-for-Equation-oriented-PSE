#!/usr/bin/env python3
"""Validate the DISPATCHES wind-PEM double-loop workflow reference assets."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

SOURCE_URL = "local://dispatches/case_studies/renewables_case/wind_PEM_double_loop"
CASE_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-04-29/"
    "examples/archived_canonical_sources/cases/github_examples/clones/dispatches/"
    "dispatches/case_studies/renewables_case"
)
WORKFLOW_IMAGE = CASE_ROOT / "DoubleLoopOptimization.png"
MODEL_FILE = CASE_ROOT / "wind_PEM_double_loop.py"
RUNNER_FILE = CASE_ROOT / "run_double_loop_PEM.py"
REQUIRED_MODEL_TOKENS = [
    "MultiPeriodWindPEM",
    "create_multiperiod_wind_pem_model",
    "transform_design_model_to_operation_model",
    "update_wind_capacity_factor",
]
REQUIRED_RUNNER_TOKENS = [
    "DoubleLoopCoordinator",
    "Prescient().simulate",
    "SelfScheduler",
    "Bidder",
    "Tracker",
]


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", data[16:24])
    except Exception:
        return None


def run_case() -> dict:
    try:
        dims = _png_dimensions(WORKFLOW_IMAGE)
        model_text = MODEL_FILE.read_text(encoding="utf-8", errors="replace") if MODEL_FILE.is_file() else ""
        runner_text = RUNNER_FILE.read_text(encoding="utf-8", errors="replace") if RUNNER_FILE.is_file() else ""
        missing_model = [token for token in REQUIRED_MODEL_TOKENS if token not in model_text]
        missing_runner = [token for token in REQUIRED_RUNNER_TOKENS if token not in runner_text]
        image_ok = dims is not None and dims[0] >= 1000 and dims[1] >= 350
        passed = image_ok and not missing_model and not missing_runner
        return {
            "pass": passed,
            "stage": "topology_reference_validation",
            "case_family": "dispatches_wind_pem_double_loop",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "topology_only",
            "checks": [
                {"name": "double_loop_png_exists", "pass": WORKFLOW_IMAGE.is_file()},
                {"name": "double_loop_png_dimensions_valid", "pass": image_ok},
                {"name": "wind_pem_model_tokens_present", "pass": not missing_model},
                {"name": "double_loop_runner_tokens_present", "pass": not missing_runner},
            ],
            "final_dof": None,
            "workflow_image": str(WORKFLOW_IMAGE),
            "workflow_image_dimensions": {"width": dims[0], "height": dims[1]} if dims else None,
            "model_file": str(MODEL_FILE),
            "runner_file": str(RUNNER_FILE),
            "missing_model_tokens": missing_model,
            "missing_runner_tokens": missing_runner,
            "source_summary": {
                "source": "dispatches.case_studies.renewables_case.wind_PEM_double_loop and DoubleLoopOptimization.png",
                "configuration": "topology-only validation for the wind-PEM day-ahead/real-time double-loop workflow",
                "workflow_steps": [
                    "DA forecast",
                    "DA bid",
                    "Prescient DA clear",
                    "RT bid",
                    "Prescient RT dispatch",
                    "tracker operation",
                    "two-settlement revenue",
                ],
            },
            "error": None if passed else {"message": "DISPATCHES wind-PEM double-loop topology validation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "topology_reference_validation",
            "case_family": "dispatches_wind_pem_double_loop",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "wind_pem_double_loop_runner_exception", "pass": False}],
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
