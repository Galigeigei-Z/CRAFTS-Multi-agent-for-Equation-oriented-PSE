#!/usr/bin/env python3
"""Solve the native WaterTAP mother-liquor recycle crystallization variant."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import check_optimal_termination  # noqa: E402
from stage3_specs_solve.watertap_mother_liquor_recycle_crystallization_model import (  # noqa: E402
    build_model,
    initialize_model,
    metrics,
    set_operating_conditions,
    solve_model,
)


SOURCE_URL = "https://watertap.readthedocs.io/en/latest/technical_reference/flowsheets/crystallization.html"


def run_case(tee=False):
    try:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = build_model()
            set_operating_conditions(model)
            initial_dof = degrees_of_freedom(model)
            initialize_model(model)
            results = solve_model(model, tee=tee)
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        variant_metrics = metrics(model)
        checks = [
            {"name": "mother_liquor_recycle_optimal", "pass": optimal},
            {"name": "mother_liquor_recycle_initial_dof_zero", "pass": initial_dof == 0},
            {"name": "mother_liquor_recycle_final_dof_zero", "pass": final_dof == 0},
            {"name": "recycle_raises_overall_recovery", "pass": variant_metrics["overall_fresh_feed_nacl_recovery"] > variant_metrics["single_pass_nacl_recovery"]},
            {"name": "purge_is_nonzero", "pass": 0 < variant_metrics["mother_liquor_purge_fraction"] < 1},
            {"name": "steady_state_nacl_balance_closes", "pass": abs(variant_metrics["steady_state_nacl_balance_error_kg_s"]) < 1e-5},
        ]
        passed = all(check["pass"] for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_mother_liquor_recycle_crystallization",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "checks": checks,
            "variant_metrics": variant_metrics,
            "source_summary": {
                "source": "WaterTAP Crystallization with explicit steady-state liquid mother-liquor recycle and purge equations",
                "evidence_boundary": "Steady-state pure NaCl-water recycle with fixed purge; recycle conditioning pressure is represented as a boundary, but pump work, impurity species, fouling, dynamic accumulation, and purge optimization are not represented.",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "Recycle crystallization checks did not all pass"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_mother_liquor_recycle_crystallization",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "mother_liquor_recycle_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-6000:]},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case(tee=args.tee)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
