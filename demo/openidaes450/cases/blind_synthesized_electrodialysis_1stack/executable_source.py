#!/usr/bin/env python3
"""Run the WaterTAP one-stack electrodialysis simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/latest/technical_reference/flowsheets/electrodialysis_1stack.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    fs = model.fs
    return {
        "feed_flow_m3_s": _value(fs.feed.properties[0].flow_vol_phase["Liq"]),
        "product_flow_m3_s": _value(fs.product.properties[0].flow_vol_phase["Liq"]),
        "disposal_flow_m3_s": _value(fs.disposal.properties[0].flow_vol_phase["Liq"]),
        "product_salinity_kg_m3": _value(fs.product_salinity),
        "disposal_salinity_kg_m3": _value(fs.disposal_salinity),
        "water_recovery_mass": _value(fs.EDstack.recovery_mass_H2O[0]),
        "membrane_area_m2": _value(fs.mem_area),
        "cell_pair_num": _value(fs.EDstack.cell_pair_num),
        "voltage_applied_v": _value(fs.EDstack.voltage_applied[0]),
        "specific_energy_kwh_m3": _value(fs.costing.specific_energy_consumption),
        "levelized_cost_of_water": _value(fs.costing.LCOW),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.electrodialysis import electrodialysis_1stack  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = electrodialysis_1stack.build()
            electrodialysis_1stack.set_operating_conditions(model)
            initial_dof = degrees_of_freedom(model)
            electrodialysis_1stack.initialize_system(model, solver=solver)
            results = electrodialysis_1stack.solve(model, solver=solver, tee=False, fail_flag=False)

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model)
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and metrics["product_flow_m3_s"] is not None
            and metrics["product_flow_m3_s"] > 0
            and metrics["product_salinity_kg_m3"] is not None
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_electrodialysis_1stack",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "ed_1stack_simulation_optimal", "pass": optimal},
                {"name": "ed_1stack_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "ed_1stack_final_dof_zero", "pass": final_dof == 0},
                {"name": "ed_1stack_product_flow_positive", "pass": metrics["product_flow_m3_s"] is not None and metrics["product_flow_m3_s"] > 0},
                {"name": "ed_1stack_streams_available", "pass": bool(stream_values)},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.electrodialysis.electrodialysis_1stack",
                "configuration": "single ED stack without concentrate recirculation",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP ED one-stack simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_electrodialysis_1stack",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ed_1stack_simulation_runner_exception", "pass": False}],
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
