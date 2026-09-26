#!/usr/bin/env python3
"""Run the WaterTAP ion exchange demonstration optimization solve."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
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
from optimization_plan_contract import plan_provenance, validate_optimization_plan  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/1.4.0rc0/technical_reference/flowsheets/ion_exchange.html"
ARC_ALIASES = {
    "feed_to_ix": "feed_to_ion_exchange",
    "ix_to_product": "ion_exchange_to_product",
    "ix_to_regen": "ion_exchange_to_regeneration",
}
OPTIMIZATION_VARIABLES = (
    "fs.ion_exchange.dimensionless_time",
    "fs.ion_exchange.number_columns",
    "fs.ion_exchange.bed_depth",
)
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "minimize levelized cost of water",
    "variables_to_unfix": [
        "fs.ion_exchange.dimensionless_time",
        "fs.ion_exchange.number_columns",
        "fs.ion_exchange.bed_depth",
    ],
    "target_dof": 0,
    "constraints": ["treated product calcium concentration = 0.025 kg/m3"],
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    ix = model.fs.ion_exchange
    target = str(ix.config.target_ion)
    feed = model.fs.feed.properties[0]
    product = model.fs.product.properties[0]
    feed_conc = _value(feed.conc_mass_phase_comp["Liq", target])
    product_conc = _value(product.conc_mass_phase_comp["Liq", target])
    removal = None
    if feed_conc:
        removal = 1 - (product_conc or 0.0) / feed_conc
    return {
        "target_ion": target,
        "levelized_cost_of_water": _value(model.fs.costing.LCOW),
        "specific_energy_consumption": _value(model.fs.costing.specific_energy_consumption),
        "feed_flow_m3_s": _value(feed.flow_vol_phase["Liq"]),
        "product_flow_m3_s": _value(product.flow_vol_phase["Liq"]),
        "feed_target_ion_conc_kg_m3": feed_conc,
        "product_target_ion_conc_kg_m3": product_conc,
        "target_ion_removal_fraction": removal,
        "number_columns": _value(ix.number_columns),
        "bed_depth_m": _value(ix.bed_depth),
        "dimensionless_time": _value(ix.dimensionless_time),
        "breakthrough_time_s": _value(ix.t_breakthru),
        "bed_volumes_until_regeneration": _value(ix.vel_bed * ix.t_breakthru / ix.bed_depth),
        "column_volume_m3": _value(ix.col_vol_per),
        "capital_cost": _value(ix.costing.capital_cost),
        "total_capital_cost": _value(model.fs.costing.total_capital_cost),
        "total_operating_cost": _value(model.fs.costing.total_operating_cost),
    }


def run_case(optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        validate_optimization_plan(
            optimization_plan, OPTIMIZATION_PLAN_TEMPLATE, label="ion-exchange"
        )
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.ion_exchange import ion_exchange_demo as ix_demo  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ix_demo.ix_build(["Ca_2+"])
            ix_demo.set_operating_conditions(model)
            ix_demo.initialize_system(model)
            simulation_results = solver.solve(model)
            ix_demo.optimize_system(model)
            ix = model.fs.ion_exchange
            number_columns_before_rounding = _value(ix.number_columns)
            bed_depth = _value(ix.bed_depth)
            ix.bed_depth.fix(bed_depth)
            ix.number_columns.fix(math.ceil(ix.number_columns()))
            rounded_results = solver.solve(model)

        sim_optimal = bool(check_optimal_termination(simulation_results))
        rounded_optimal = bool(check_optimal_termination(rounded_results))
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        final_dof = degrees_of_freedom(model)
        passed = (
            sim_optimal
            and rounded_optimal
            and final_dof == 0
            and metrics["levelized_cost_of_water"] is not None
            and metrics["levelized_cost_of_water"] > 0
            and metrics["product_target_ion_conc_kg_m3"] is not None
            and metrics["product_target_ion_conc_kg_m3"] <= 0.026
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_ion_exchange",
            "official_reference_url": SOURCE_URL,
            "simulation_termination_condition": str(simulation_results.solver.termination_condition),
            "termination_condition": str(rounded_results.solver.termination_condition),
            "checks": [
                {"name": "ix_pre_optimization_simulation_optimal", "pass": sim_optimal},
                {"name": "ix_rounded_integer_column_optimization_optimal", "pass": rounded_optimal},
                {"name": "ix_final_dof_zero", "pass": final_dof == 0},
                {"name": "ix_lcow_positive", "pass": metrics["levelized_cost_of_water"] is not None and metrics["levelized_cost_of_water"] > 0},
                {"name": "ix_product_quality_met", "pass": metrics["product_target_ion_conc_kg_m3"] is not None and metrics["product_target_ion_conc_kg_m3"] <= 0.026},
            ],
            "final_dof": final_dof,
            "number_columns_before_integer_rounding": number_columns_before_rounding,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.ion_exchange.ion_exchange_demo",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            **plan_provenance(optimization_plan, OPTIMIZATION_PLAN_TEMPLATE),
            "error": None if passed else {"message": "WaterTAP IX optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_ion_exchange",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ix_optimization_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--optimization-plan", type=Path)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case(optimization_plan=args.optimization_plan)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
