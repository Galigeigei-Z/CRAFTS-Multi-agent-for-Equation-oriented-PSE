#!/usr/bin/env python3
"""Run the local DISPATCHES nuclear double-loop flowsheet smoke."""

from __future__ import annotations

import argparse
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

SOURCE_URL = "https://dispatches.readthedocs.io/en/main/examples/nuclear_flowsheet_double_loop.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/dispatches_nuclear_double_loop_notebook/source_root")


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
        from idaes.core.solvers import get_solver  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import ConcreteModel, check_optimal_termination  # noqa: PLC0415
        import nuclear_flowsheet as nuclear  # noqa: PLC0415

        model = ConcreteModel()
        nuclear.build_ne_flowsheet(model)
        nuclear.fix_dof_and_initialize(model)
        final_dof = degrees_of_freedom(model)
        results = get_solver().solve(model, tee=False)
        optimal = bool(check_optimal_termination(results))
        passed = optimal and final_dof == 0
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "dispatches_nuclear_double_loop",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "nuclear_flowsheet_dof_zero", "pass": final_dof == 0},
                {"name": "nuclear_flowsheet_solve_optimal", "pass": optimal},
            ],
            "final_dof": final_dof,
            "nuclear_power_kw": _value(model.fs.np_power_split.electricity[0]),
            "grid_split_fraction": _value(model.fs.np_power_split.split_fraction["np_to_grid", 0]),
            "pem_electricity_kw": _value(model.fs.pem.electricity[0]),
            "tank_holdup_mol": _value(model.fs.h2_tank.tank_holdup[0]),
            "turbine_work_w": _value(model.fs.h2_turbine.work_mechanical[0]),
            "stream_values": {
                "nuclear_to_splitter": {"electricity_kw": _value(model.fs.np_power_split.electricity[0])},
                "splitter_to_pem": {"electricity_kw": _value(model.fs.pem.electricity[0])},
                "h2_tank": {"holdup_mol": _value(model.fs.h2_tank.tank_holdup[0])},
                "h2_turbine": {"work_w": _value(model.fs.h2_turbine.work_mechanical[0])},
            },
            "source_summary": {"source": str(CASE_ROOT / "nuclear_flowsheet.py")},
            "error": None if passed else {"message": "DISPATCHES nuclear flowsheet smoke did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "dispatches_nuclear_double_loop",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "nuclear_runner_exception", "pass": False}],
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
