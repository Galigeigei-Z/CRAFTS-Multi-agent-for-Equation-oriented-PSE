#!/usr/bin/env python3
"""Run the WaterTAP ion exchange demonstration simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/1.4.0rc0/technical_reference/flowsheets/ion_exchange.html"
ARC_ALIASES = {
    "feed_to_ix": "feed_to_ion_exchange",
    "ix_to_product": "ion_exchange_to_product",
    "ix_to_regen": "ion_exchange_to_regeneration",
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
        "breakthrough_time_s": _value(ix.t_breakthru),
        "bed_volumes_until_regeneration": _value(ix.vel_bed * ix.t_breakthru / ix.bed_depth),
        "column_volume_m3": _value(ix.col_vol_per),
        "capital_cost": _value(ix.costing.capital_cost),
        "total_capital_cost": _value(model.fs.costing.total_capital_cost),
        "total_operating_cost": _value(model.fs.costing.total_operating_cost),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.ion_exchange import ion_exchange_demo as ix_demo  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ix_demo.ix_build(["Ca_2+"])
            ix_demo.set_operating_conditions(model)
            ix_demo.initialize_system(model)
            results = get_solver().solve(model)

        optimal = bool(check_optimal_termination(results))
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = (
            optimal
            and degrees_of_freedom(model) == 0
            and metrics["levelized_cost_of_water"] is not None
            and metrics["levelized_cost_of_water"] > 0
            and metrics["product_target_ion_conc_kg_m3"] is not None
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_ion_exchange",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "ix_simulation_optimal", "pass": optimal},
                {"name": "ix_simulation_dof_zero", "pass": degrees_of_freedom(model) == 0},
                {"name": "ix_simulation_lcow_positive", "pass": metrics["levelized_cost_of_water"] is not None and metrics["levelized_cost_of_water"] > 0},
                {"name": "ix_simulation_streams_available", "pass": bool(stream_values)},
            ],
            "final_dof": degrees_of_freedom(model),
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.ion_exchange.ion_exchange_demo",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP IX simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_ion_exchange",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ix_simulation_runner_exception", "pass": False}],
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
