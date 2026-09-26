#!/usr/bin/env python3
"""Run the local WaterTAP MVC single-stage optimization solve."""

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
            simulation_results = mvc.solve(model, tee=False)
            model.fs.Q_ext[0].fix(0)
            del model.fs.objective
            mvc.set_up_optimization(model)
            optimization_results = mvc.solve(model, tee=False)

        sim_optimal = bool(check_optimal_termination(simulation_results))
        opt_optimal = bool(check_optimal_termination(optimization_results))
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.recovery[0])
        q_ext = _value(model.fs.Q_ext[0])
        stream_values = streams_from_arcs(model)
        passed = sim_optimal and opt_optimal and lcow is not None and lcow > 0 and sec is not None and recovery is not None
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_mvc_single_stage",
            "official_reference_url": SOURCE_URL,
            "simulation_termination_condition": str(simulation_results.solver.termination_condition),
            "termination_condition": str(optimization_results.solver.termination_condition),
            "checks": [
                {"name": "mvc_pre_optimization_simulation_optimal", "pass": sim_optimal},
                {"name": "mvc_optimization_optimal", "pass": opt_optimal},
                {"name": "mvc_lcow_positive", "pass": lcow is not None and lcow > 0},
            ],
            "final_dof": degrees_of_freedom(model),
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "external_heat_w": q_ext,
            "stream_values": stream_values,
            "source_summary": {"source": str(CASE_ROOT / "mvc" / "mvc_single_stage.py"), "stdout_tail": stdout.getvalue()[-4000:]},
            "error": None if passed else {"message": "WaterTAP MVC optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_mvc_single_stage",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "mvc_optimization_runner_exception", "pass": False}],
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
