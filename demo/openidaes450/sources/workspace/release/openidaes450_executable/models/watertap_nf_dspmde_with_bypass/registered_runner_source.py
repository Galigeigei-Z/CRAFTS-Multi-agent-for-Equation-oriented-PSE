#!/usr/bin/env python3
"""Run the WaterTAP NF-DSPM-DE with bypass reference simulation solve."""

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

SOURCE_URL = "local://watertap/flowsheets/nf_dspmde/nf_with_bypass"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    feed = model.fs.feed.properties[0]
    product = model.fs.product.properties[0]
    disposal = model.fs.disposal.properties[0]
    nf_unit = model.fs.NF.nfUnit
    return {
        "feed_flow_m3_s": _value(feed.flow_vol_phase["Liq"]),
        "product_flow_m3_s": _value(product.flow_vol_phase["Liq"]),
        "disposal_flow_m3_s": _value(disposal.flow_vol_phase["Liq"]),
        "feed_total_hardness_mg_l_as_caco3": _value(feed.total_hardness),
        "product_total_hardness_mg_l_as_caco3": _value(product.total_hardness),
        "disposal_total_hardness_mg_l_as_caco3": _value(disposal.total_hardness),
        "bypass_split_fraction": _value(model.fs.by_pass_splitter.split_fraction[0, "bypass"]),
        "nf_area_m2": _value(nf_unit.area),
        "nf_recovery_vol_liq": _value(nf_unit.recovery_vol_phase[0, "Liq"]),
        "nf_feed_pressure_pa": _value(model.fs.NF.pump.outlet.pressure[0]),
        "levelized_cost_of_water": _value(model.fs.costing.LCOW),
        "specific_energy_consumption": _value(model.fs.costing.specific_energy_consumption),
        "total_capital_cost": _value(model.fs.costing.total_capital_cost),
        "total_operating_cost": _value(model.fs.costing.total_operating_cost),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.nf_dspmde import nf_with_bypass  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = nf_with_bypass.build()
            nf_with_bypass.initialize(model, solver)
            results = solver.solve(model)

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model)
        passed = (
            optimal
            and final_dof == 0
            and metrics["product_flow_m3_s"] is not None
            and metrics["product_flow_m3_s"] > 0
            and metrics["product_total_hardness_mg_l_as_caco3"] is not None
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_nf_dspmde_with_bypass",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "nf_bypass_simulation_optimal", "pass": optimal},
                {"name": "nf_bypass_final_dof_zero", "pass": final_dof == 0},
                {"name": "nf_bypass_product_flow_positive", "pass": metrics["product_flow_m3_s"] is not None and metrics["product_flow_m3_s"] > 0},
                {"name": "nf_bypass_product_hardness_available", "pass": metrics["product_total_hardness_mg_l_as_caco3"] is not None},
                {"name": "nf_bypass_streams_available", "pass": bool(stream_values)},
            ],
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.nf_dspmde.nf_with_bypass",
                "configuration": "DSPM-DE nanofiltration with feed bypass and product hardness constraint",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP NF-DSPM-DE bypass simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_nf_dspmde_with_bypass",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "nf_bypass_simulation_runner_exception", "pass": False}],
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
