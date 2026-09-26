#!/usr/bin/env python3
"""Build, solve, and validate the native WaterTAP ASM1 dewatering unit case."""

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
from stage3_specs_solve.watertap_asm1_dewatering_unit_model import (  # noqa: E402
    build_model,
    initialize_model,
    metrics,
    set_operating_conditions,
    solve_model,
)


SOURCE_URL = "https://github.com/watertap-org/watertap/blob/main/watertap/unit_models/dewatering.py"


def run_case(tee=False):
    try:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = build_model()
            set_operating_conditions(model)
            initial_dof = degrees_of_freedom(model)
            initialize_model(model)
            results = solve_model(model, tee=tee)
        final_dof = degrees_of_freedom(model)
        optimal = bool(check_optimal_termination(results))
        result_metrics = metrics(model)
        checks = [
            {"name": "asm1_dewaterer_optimal", "pass": optimal},
            {"name": "asm1_dewaterer_initial_dof_zero", "pass": initial_dof == 0},
            {"name": "asm1_dewaterer_final_dof_zero", "pass": final_dof == 0},
            {"name": "tss_capture_matches_native_correlation", "pass": abs(result_metrics["tss_capture_fraction"] - 0.98) < 1e-7},
            {"name": "cake_dry_solids_near_native_28wtpct_correlation", "pass": 0.275 < result_metrics["cake_dry_solids_mass_fraction"] < 0.29},
            {"name": "filtrate_hydraulic_recovery_physical", "pass": 0.90 < result_metrics["filtrate_hydraulic_recovery"] < 1.0},
            {"name": "hydraulic_balance_closed", "pass": abs(result_metrics["hydraulic_balance_residual_m3_s"]) < 1e-10},
            {"name": "particulate_balance_closed", "pass": abs(result_metrics["particulate_balance_residual_kg_s"]) < 1e-10},
            {"name": "electricity_consumption_positive", "pass": result_metrics["electricity_consumption_kw"] > 0},
        ]
        passed = all(check["pass"] for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_asm1_dewatering_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "checks": checks,
            "variant_metrics": result_metrics,
            "source_summary": {
                "source": "Official WaterTAP DewateringUnit with the official ASM1 property package and BSM2 benchmark feed",
                "configuration": "One separator-based dewaterer producing clarified overflow and a concentrated sludge cake; native correlations specify 98% TSS capture and 28 wt% cake dry solids.",
                "evidence_boundary": "Steady-state empirical BSM2 dewatering correlation. Polymer dose, particle-size effects, compressibility, cycle dynamics, equipment redundancy, and detailed centrifuge or belt-press mechanics are not represented.",
                "stdout_tail": stdout.getvalue()[-5000:],
            },
            "error": None if passed else {"message": "ASM1 dewatering checks did not all pass"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_asm1_dewatering_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "asm1_dewaterer_runner_exception", "pass": False}],
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
