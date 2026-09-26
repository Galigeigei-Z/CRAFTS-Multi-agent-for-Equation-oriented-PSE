#!/usr/bin/env python3
"""Run the local WaterTAP MVC single-stage simulation solve."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))
from watertap_streams import streams_from_arcs  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/latest/technical_reference/flowsheets/mvc.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/watertap_mvc_single_stage/source_root")


def _prepare_imports() -> None:
    if str(CASE_ROOT) not in sys.path:
        sys.path.insert(0, str(CASE_ROOT))


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _maximum_constraint_residual(model: Any) -> float:
    """Return the largest active equality/inequality violation at the loaded solution."""

    from pyomo.environ import Constraint, value  # noqa: PLC0415

    maximum = 0.0
    for constraint in model.component_data_objects(Constraint, active=True, descend_into=True):
        body = float(value(constraint.body))
        if constraint.equality:
            residual = abs(body - float(value(constraint.lower)))
        else:
            residual = 0.0
            if constraint.has_lb():
                residual = max(residual, float(value(constraint.lower)) - body)
            if constraint.has_ub():
                residual = max(residual, body - float(value(constraint.upper)))
        maximum = max(maximum, residual)
    return maximum


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import Objective, check_optimal_termination  # noqa: PLC0415
        from mvc import mvc_single_stage as mvc  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = mvc.build()
            mvc.set_operating_conditions(model)
            mvc.add_Q_ext(model, time_point=model.fs.config.time)
            mvc.initialize_system(model)
            mvc.scale_costs(model)
            mvc.fix_outlet_pressures(model)
            model.fs.objective = Objective(expr=model.fs.Q_ext[0])
            optimization_results = mvc.solve(model, tee=False)
            optimization_dof = degrees_of_freedom(model)
            optimized_external_heat = _value(model.fs.Q_ext[0])
            model.fs.Q_ext[0].fix(optimized_external_heat)
            model.fs.objective.deactivate()

        optimization_optimal = bool(check_optimal_termination(optimization_results))
        termination = str(optimization_results.solver.termination_condition)
        maximum_constraint_residual = _maximum_constraint_residual(model)
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.recovery[0])
        q_ext = _value(model.fs.Q_ext[0])
        stream_values = streams_from_arcs(model)
        final_dof = degrees_of_freedom(model)
        passed = (
            optimization_optimal
            and final_dof == 0
            and maximum_constraint_residual <= 1e-4
            and lcow is not None
            and lcow > 0
            and sec is not None
            and recovery is not None
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_mvc_single_stage",
            "official_reference_url": SOURCE_URL,
            "optimization_termination_condition": str(
                optimization_results.solver.termination_condition
            ),
            "termination_condition": termination,
            "checks": [
                {"name": "mvc_external_heat_minimization_optimal", "pass": optimization_optimal},
                {"name": "mvc_terminal_solution_loaded", "pass": optimization_optimal},
                {"name": "mvc_terminal_design_dof_zero", "pass": final_dof == 0},
                {"name": "mvc_terminal_constraint_residual", "pass": maximum_constraint_residual <= 1e-4},
                {"name": "mvc_simulation_lcow_available", "pass": lcow is not None and lcow > 0},
                {"name": "mvc_simulation_recovery_available", "pass": recovery is not None},
            ],
            "optimization_dof_before_terminal_freeze": optimization_dof,
            "frozen_design_variables": {"fs.Q_ext[0]": optimized_external_heat},
            "final_dof": final_dof,
            "maximum_constraint_residual": maximum_constraint_residual,
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "external_heat_w": q_ext,
            "stream_values": stream_values,
            "source_summary": {"source": str(CASE_ROOT / "mvc" / "mvc_single_stage.py"), "stdout_tail": stdout.getvalue()[-4000:]},
            "error": None if passed else {"message": "WaterTAP MVC solve did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "watertap_mvc_single_stage",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "mvc_runner_exception", "pass": False}],
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
