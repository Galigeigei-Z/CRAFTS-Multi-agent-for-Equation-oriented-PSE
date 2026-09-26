#!/usr/bin/env python3
"""Build and solve the clarifier-only RAS WaterTAP ASM1 topology variant."""

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
from stage3_specs_solve.watertap_asm1_clarifier_only_ras_model import (  # noqa: E402
    build_initialized_model,
    solve_clarifier_only_ras,
    variant_metrics,
)


SOURCE_URL = "https://github.com/watertap-org/watertap/blob/main/watertap/flowsheets/activated_sludge/ASM1_flowsheet.py"


def run_case(tee=False):
    try:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model, baseline_results, baseline_metrics = build_initialized_model()
            initial_dof = degrees_of_freedom(model)
            results, continuation = solve_clarifier_only_ras(model, tee=tee)
        final_dof = degrees_of_freedom(model)
        optimal = bool(check_optimal_termination(results))
        baseline_optimal = bool(check_optimal_termination(baseline_results))
        metrics = variant_metrics(model, baseline_metrics)
        continuation_optimal = all(step["termination_condition"] == "optimal" for step in continuation)
        checks = [
            {"name": "official_asm1_baseline_optimal", "pass": baseline_optimal},
            {"name": "clarifier_only_ras_continuation_optimal", "pass": continuation_optimal},
            {"name": "clarifier_only_ras_final_solve_optimal", "pass": optimal},
            {"name": "clarifier_only_ras_initial_dof_zero", "pass": initial_dof == 0},
            {"name": "clarifier_only_ras_final_dof_zero", "pass": final_dof == 0},
            {"name": "direct_reactor_recycle_closed", "pass": abs(metrics["variant_direct_reactor_recycle_fraction"]) < 1e-12},
            {"name": "clarifier_ras_positive", "pass": metrics["clarifier_ras_flow_m3_s"] > 0},
            {"name": "treated_flow_positive", "pass": metrics["treated_flow_m3_s"] > 0},
            {"name": "hydraulic_flow_balance_closed", "pass": abs(metrics["hydraulic_balance_residual_m3_s"]) < 1e-8},
            {"name": "effluent_and_energy_metrics_finite", "pass": metrics["effluent_soluble_inorganic_n_mg_l"] > 0 and metrics["estimated_aeration_power_kw"] > 0},
        ]
        passed = all(check["pass"] for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_asm1_clarifier_only_ras",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "checks": checks,
            "continuation_path": continuation,
            "variant_metrics": metrics,
            "source_summary": {
                "source": "Official WaterTAP ASM1 flowsheet and property/reaction packages",
                "configuration": "All R5 effluent passes through CL1; only CL1 underflow RAS is returned, with the existing waste-sludge purge retained.",
                "evidence_boundary": "Steady-state ASM1 surrogate with ideal component-split clarifier. Aeration electricity is an explicit post-processing estimate from native oxygen transfer using 1.8 kg O2/kWh; it is not a blower model. No phosphorus, settling dynamics, or equipment costing is represented.",
                "stdout_tail": stdout.getvalue()[-5000:],
            },
            "error": None if passed else {"message": "Clarifier-only RAS ASM1 checks did not all pass"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_asm1_clarifier_only_ras",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "clarifier_only_ras_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
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
