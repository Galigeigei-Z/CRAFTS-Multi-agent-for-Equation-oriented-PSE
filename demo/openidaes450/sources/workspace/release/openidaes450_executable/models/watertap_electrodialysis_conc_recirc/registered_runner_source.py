#!/usr/bin/env python3
"""Run the WaterTAP one-stack electrodialysis concentrate-recirculation simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/electrodialysis_1stack_conc_recirc.html"
ARC_ALIASES = {
    "arc0": "feed_to_separator",
    "arc1b": "separator_to_diluate_pump",
    "arc1f": "diluate_pump_to_edstack",
    "arc2": "separator_to_concentrate_mixer",
    "arc3b": "mixer_to_concentrate_pump",
    "arc3f": "concentrate_pump_to_edstack",
    "arc4": "edstack_diluate_to_product",
    "arc5": "edstack_concentrate_to_recycle_separator",
    "arc6": "recycle_separator_to_disposal",
    "arc7": "recycle_separator_to_mixer",
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _set_simulation_conditions(model: Any, ed: Any) -> None:
    init_arg = {
        ("flow_vol_phase", "Liq"): 5.2e-4,
        ("conc_mol_phase_comp", ("Liq", "Na_+")): 34.188,
        ("conc_mol_phase_comp", ("Liq", "Cl_-")): 34.188,
    }
    model.fs.feed.properties.calculate_state(init_arg, hold_state=True)
    model.fs.EDstack.voltage_applied[0].fix(10)
    model.fs.recovery_vol_H2O.fix(0.7)
    ed._condition_base(model)


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.electrodialysis import electrodialysis_1stack_conc_recirc as ed  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ed.build()
            _set_simulation_conditions(model, ed)
            ed.initialize_system(model)
            results = ed.solve(model, tee=False)

        termination = str(results.solver.termination_condition)
        optimal = bool(check_optimal_termination(results))
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.recovery_vol_H2O)
        product_salinity = _value(model.fs.product_salinity)
        disposal_salinity = _value(model.fs.disposal_salinity)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = optimal and lcow is not None and lcow > 0 and sec is not None and recovery is not None
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_electrodialysis_conc_recirc",
            "official_reference_url": SOURCE_URL,
            "termination_condition": termination,
            "checks": [
                {"name": "ed_conc_recirc_simulation_optimal", "pass": optimal},
                {"name": "ed_conc_recirc_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "ed_conc_recirc_recovery_available", "pass": recovery is not None},
            ],
            "final_dof": degrees_of_freedom(model),
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "product_salinity_kg_m3": product_salinity,
            "disposal_salinity_kg_m3": disposal_salinity,
            "membrane_area_m2": _value(model.fs.mem_area),
            "cell_pair_number": _value(model.fs.EDstack.cell_pair_num),
            "cell_length_m": _value(model.fs.EDstack.cell_length),
            "stack_voltage_v": _value(model.fs.EDstack.voltage_applied[0]),
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.electrodialysis.electrodialysis_1stack_conc_recirc",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP ED concentrate recirculation simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_electrodialysis_conc_recirc",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ed_conc_recirc_simulation_runner_exception", "pass": False}],
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
