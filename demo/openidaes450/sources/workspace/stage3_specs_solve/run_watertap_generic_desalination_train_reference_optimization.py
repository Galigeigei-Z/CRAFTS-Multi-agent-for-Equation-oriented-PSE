#!/usr/bin/env python3
"""Run the WaterTAP generic desalination treatment train optimization solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/1.5.0/technical_reference/flowsheets/generic_desalination_train.html"
ARC_ALIASES = {
    "Feed_to_separator": "feed_to_pretreatment",
    "Pretreatment_to_desalter": "pretreatment_to_desal_1",
    "Desal_1_to_desalter": "desal_1_brine_to_desal_2",
    "Desal_2_to_desalter": "desal_2_brine_to_desal_3",
    "Desal_3_to_valorizer": "desal_3_brine_to_valorizer",
    "Desal_1_to_product_mixer": "desal_1_product_to_product_mixer",
    "Desal_2_to_product_mixer": "desal_2_product_to_product_mixer",
    "Desal_3_to_product_mixer": "desal_3_product_to_product_mixer",
    "product_mixer_to_product": "product_mixer_to_product",
    "Pretreatment_to_disposal_mixer": "pretreatment_disposal_to_disposal_mixer",
    "Valorizer_to_disposal_mixer": "valorizer_disposal_to_disposal_mixer",
    "disposal_mixer_to_disposal": "disposal_mixer_to_disposal",
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    fs = model.fs
    return {
        "levelized_cost_of_water": _value(fs.costing.LCOW),
        "water_recovery_percent": _value(fs.water_recovery),
        "feed_h2o_flow_kg_s": _value(fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"]),
        "product_h2o_flow_kg_s": _value(fs.product.properties[0].flow_mass_phase_comp["Liq", "H2O"]),
        "disposal_h2o_flow_kg_s": _value(fs.disposal.properties[0].flow_mass_phase_comp["Liq", "H2O"]),
        "feed_tds_conc_kg_m3": _value(fs.feed.properties[0].conc_mass_phase_comp["Liq", "TDS"]),
        "feed_x_conc_kg_m3": _value(fs.feed.properties[0].conc_mass_phase_comp["Liq", "X"]),
        "desal_1_water_recovery_percent": _value(fs.Desal_1.desalter.water_recovery),
        "desal_2_water_recovery_percent": _value(fs.Desal_2.desalter.water_recovery),
        "desal_3_water_recovery_percent": _value(fs.Desal_3.desalter.water_recovery),
        "annual_feed_cost": _value(fs.feed.annual_cost),
        "annual_product_cost": _value(fs.product.annual_cost),
        "annual_disposal_cost": _value(fs.disposal.annual_cost),
        "pretreatment_x_removal_percent": _value(fs.Pretreatment.separator.component_removal_percent["X"]),
        "valorizer_x_value": _value(fs.Valorizer.separator.product_value["X"]),
    }


def _apply_official_optimization_specs(model: Any) -> None:
    fs = model.fs
    fs.Pretreatment.separator.component_removal_percent["X"].fix(50)
    fs.Pretreatment.separator.separation_cost["X"].fix(0.5)
    fs.Valorizer.separator.product_value["X"].fix(1)
    fs.Valorizer.separator.component_removal_percent["X"].fix(50)
    fs.Desal_1.desalter.water_recovery.fix(80)
    fs.Desal_2.desalter.water_recovery.fix(50)
    fs.Desal_2.desalter.recovery_cost.fix(0.01)
    fs.Desal_2.desalter.recovery_cost_offset.fix(35)
    fs.Desal_3.desalter.water_recovery.unfix()
    fs.Desal_3.desalter.brine_water_mass_percent.fix(80)


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.generic_desalination_train import generic_train  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = generic_train.build()
            initial_dof = degrees_of_freedom(model)
            generic_train.initialize(model, solver)
            post_initialize_dof = degrees_of_freedom(model)
            _apply_official_optimization_specs(model)
            pre_final_solve_dof = degrees_of_freedom(model)
            results = generic_train.solve(model, solver)

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = (
            optimal
            and initial_dof == 0
            and pre_final_solve_dof == 0
            and final_dof == 0
            and metrics["levelized_cost_of_water"] is not None
            and metrics["levelized_cost_of_water"] > 0
            and metrics["water_recovery_percent"] is not None
            and metrics["water_recovery_percent"] > 90
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_generic_desalination_train",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "generic_train_optimization_optimal", "pass": optimal},
                {"name": "generic_train_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "generic_train_pre_final_solve_dof_zero", "pass": pre_final_solve_dof == 0},
                {"name": "generic_train_final_dof_zero", "pass": final_dof == 0},
                {"name": "generic_train_lcow_positive", "pass": metrics["levelized_cost_of_water"] is not None and metrics["levelized_cost_of_water"] > 0},
                {"name": "generic_train_recovery_high", "pass": metrics["water_recovery_percent"] is not None and metrics["water_recovery_percent"] > 90},
            ],
            "initial_dof": initial_dof,
            "post_initialize_dof": post_initialize_dof,
            "pre_final_solve_dof": pre_final_solve_dof,
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.generic_desalination_train.generic_train",
                "train_type": "Pretreatment>Desal1>Desal2>Crystalizer>Valorizer",
                "optimization_note": "Matches the official main() post-initialization specs: fix Pretreatment/Valorizer X parameters, fix Desal_1 and Desal_2 recoveries, and optimize Desal_3 recovery against brine water mass percent.",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP generic desalination train optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_generic_desalination_train",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "generic_train_optimization_runner_exception", "pass": False}],
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
