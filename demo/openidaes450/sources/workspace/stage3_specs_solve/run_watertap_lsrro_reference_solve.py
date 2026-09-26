#!/usr/bin/env python3
"""Run the local WaterTAP LSRRO simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/lsrro.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/watertap_lsrro/source_root")


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
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from lsrro import lsrro  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = lsrro.build(
                number_of_stages=3,
                has_NaCl_solubility_limit=True,
                has_calculated_concentration_polarization=True,
                has_calculated_ro_pressure_drop=True,
            )
            lsrro.set_operating_conditions(model, Cin=70, Qin=1e-3)
            lsrro.initialize(model)
            results = lsrro.solve(model)

        termination = str(results.solver.termination_condition)
        optimal = bool(check_optimal_termination(results))
        lcow = _value(model.fs.costing.LCOW)
        recovery = _value(model.fs.water_recovery)
        sec = _value(model.fs.costing.specific_energy_consumption)
        stream_values = streams_from_arcs(model)
        passed = optimal and lcow is not None and lcow > 0 and recovery is not None
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_lsrro",
            "official_reference_url": SOURCE_URL,
            "termination_condition": termination,
            "checks": [
                {"name": "lsrro_simulation_optimal", "pass": optimal},
                {"name": "lsrro_simulation_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "lsrro_simulation_recovery_available", "pass": recovery is not None},
            ],
            "final_dof": degrees_of_freedom(model),
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "number_of_stages": int(_value(model.fs.NumberOfStages) or 3),
            "stream_values": stream_values,
            "source_summary": {"source": str(CASE_ROOT / "lsrro" / "lsrro.py"), "stdout_tail": stdout.getvalue()[-4000:]},
            "error": None if passed else {"message": "WaterTAP LSRRO solve did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "watertap_lsrro",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "lsrro_runner_exception", "pass": False}],
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
