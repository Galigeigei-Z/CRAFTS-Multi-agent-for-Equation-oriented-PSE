#!/usr/bin/env python3
"""Run the WaterTAP full seawater RO desalination simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/seawater_RO_desalination.html"

ARC_ALIASES = {
    "fs.pretreatment.s01": "pretreatment_train__01",
    "fs.pretreatment.s02": "pretreatment_train__02",
    "fs.pretreatment.s03": "pretreatment_train__03",
    "fs.pretreatment.s04": "pretreatment_train__04",
    "fs.pretreatment.s05": "pretreatment_train__05",
    "fs.pretreatment.s07": "pretreatment_train__06",
    "fs.pretreatment.s08": "pretreatment_train__07",
    "fs.pretreatment.s06": "pretreatment_backwash",
    "fs.desalination.s01": "desal_s01",
    "fs.desalination.s02": "desal_s02",
    "fs.desalination.s03": "desal_s03",
    "fs.desalination.s04": "desal_s04",
    "fs.desalination.s05": "desal_s05",
    "fs.desalination.s06": "desal_s06",
    "fs.desalination.s07": "desal_s07",
    "fs.s_tb_psttrt": "posttreatment_train__01",
    "fs.posttreatment.s01": "posttreatment_train__02",
    "fs.posttreatment.s02": "posttreatment_train__03",
    "fs.posttreatment.s03": "posttreatment_train__04",
    "fs.posttreatment.s04": "posttreatment_train__05",
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    fs = model.fs
    metrics = {
        "feed_flow_m3_s": _value(fs.feed.properties[0].flow_vol),
        "ro_area_m2": _value(fs.desalination.RO.area),
        "ro_recovery_mass_h2o": _value(fs.desalination.RO.recovery_mass_phase_comp[0, "Liq", "H2O"]),
        "ro_pump_work_w": _value(fs.desalination.P1.control_volume.work[0]),
        "product_flow_m3_s": _value(fs.municipal.properties[0].flow_vol),
        "disposal_flow_m3_s": _value(fs.disposal.properties[0].flow_vol_phase["Liq"]),
    }
    if hasattr(fs, "zo_costing"):
        metrics.update(
            {
                "zo_total_capital_cost": _value(fs.zo_costing.total_capital_cost),
                "zo_total_operating_cost": _value(fs.zo_costing.total_operating_cost),
            }
        )
    if hasattr(fs, "ro_costing"):
        metrics.update(
            {
                "ro_total_capital_cost": _value(fs.ro_costing.total_capital_cost),
                "ro_total_operating_cost": _value(fs.ro_costing.total_operating_cost),
            }
        )
    return metrics


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.seawater_RO_desalination import seawater_RO_desalination  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = seawater_RO_desalination.build_flowsheet(erd_type="pressure_exchanger")
            initial_dof = degrees_of_freedom(model)
            seawater_RO_desalination.initialize_system(model)
            sim_results = seawater_RO_desalination.solve(model, tee=False, checkpoint="solve pressure_exchanger seawater RO simulation", fail_flag=False)
            seawater_RO_desalination.add_costing(model)
            seawater_RO_desalination.initialize_costing(model)
            costing_dof = degrees_of_freedom(model)
            costing_results = seawater_RO_desalination.solve(model, tee=False, checkpoint="solve pressure_exchanger seawater RO costing", fail_flag=False)

        sim_optimal = bool(check_optimal_termination(sim_results))
        costing_optimal = bool(check_optimal_termination(costing_results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = (
            sim_optimal
            and costing_optimal
            and initial_dof == 0
            and costing_dof == 0
            and final_dof == 0
            and metrics["product_flow_m3_s"] is not None
            and metrics["product_flow_m3_s"] > 0
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_seawater_ro_desalination",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(costing_results.solver.termination_condition),
            "checks": [
                {"name": "seawater_ro_simulation_optimal", "pass": sim_optimal},
                {"name": "seawater_ro_costing_optimal", "pass": costing_optimal},
                {"name": "seawater_ro_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "seawater_ro_costing_dof_zero", "pass": costing_dof == 0},
                {"name": "seawater_ro_final_dof_zero", "pass": final_dof == 0},
                {"name": "seawater_ro_product_flow_positive", "pass": metrics["product_flow_m3_s"] is not None and metrics["product_flow_m3_s"] > 0},
                {"name": "seawater_ro_streams_available", "pass": bool(stream_values)},
            ],
            "initial_dof": initial_dof,
            "costing_dof": costing_dof,
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.seawater_RO_desalination.seawater_RO_desalination",
                "erd_type": "pressure_exchanger",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP seawater RO simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_seawater_ro_desalination",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "seawater_ro_simulation_runner_exception", "pass": False}],
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
