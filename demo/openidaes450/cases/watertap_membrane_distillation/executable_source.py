#!/usr/bin/env python3
"""Run the WaterTAP membrane distillation simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/membrane_distillation.html"
ARC_ALIASES = {
    "s01": "feed_to_feed_pump",
    "s02": "feed_pump_to_mixer",
    "s03": "mixer_to_heat_exchanger_cold_side",
    "s04": "heat_exchanger_cold_out_to_brine_pump",
    "s05": "brine_pump_to_heater",
    "s06": "heater_to_md_hot_inlet",
    "s07": "md_hot_outlet_to_concentrate_separator",
    "s08": "concentrate_separator_to_reject",
    "s09": "concentrate_separator_recycle_to_mixer",
    "s10": "chiller_to_md_cold_inlet",
    "s11": "md_cold_outlet_to_heat_exchanger_hot_side",
    "s12": "heat_exchanger_hot_out_to_permeate_separator",
    "s13": "permeate_separator_to_product",
    "s14": "permeate_separator_cold_loop_to_pump",
    "s15": "permeate_pump_to_chiller",
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.MD import MD_single_stage_continuous_recirculation as md  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = md.build()
            md.set_operating_conditions(model)
            md.initialize_system(model, verbose=False)
            results = md.solve(model, tee=False)

        termination = str(results.solver.termination_condition)
        optimal = bool(check_optimal_termination(results))
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.overall_recovery)
        recycle_ratio = _value(model.fs.recycle_ratio[0])
        thermal_efficiency = _value(model.fs.MD.thermal_efficiency[0])
        effectiveness = _value(model.fs.MD.effectiveness[0])
        permeate_tds = _value(model.fs.permeate.properties[0].mass_frac_phase_comp["Liq", "TDS"])
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = optimal and lcow is not None and lcow > 0 and sec is not None and recovery is not None
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_membrane_distillation",
            "official_reference_url": SOURCE_URL,
            "termination_condition": termination,
            "checks": [
                {"name": "md_simulation_optimal", "pass": optimal},
                {"name": "md_simulation_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "md_simulation_recovery_available", "pass": recovery is not None},
            ],
            "final_dof": degrees_of_freedom(model),
            "water_recovery": recovery,
            "recycle_ratio": recycle_ratio,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "thermal_efficiency": thermal_efficiency,
            "effectiveness": effectiveness,
            "permeate_tds_mass_fraction": permeate_tds,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.MD.MD_single_stage_continuous_recirculation",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP MD simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_membrane_distillation",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "md_simulation_runner_exception", "pass": False}],
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
