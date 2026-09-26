#!/usr/bin/env python3
"""Run the WaterTAP RO-with-energy-recovery optimization solve."""

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
from optimization_plan_contract import plan_provenance, validate_optimization_plan  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/RO_with_energy_recovery.html"
ARC_ALIASES = {
    "s01": "feed_to_separator",
    "s02": "separator_to_p1",
    "s03": "p1_to_mixer",
    "s04": "mixer_to_ro",
    "s05": "ro_permeate_to_product",
    "s06": "ro_retentate_to_pxr",
    "s07": "pxr_brine_to_disposal",
    "s08": "separator_to_pxr",
    "s09": "pxr_feed_to_p2",
    "s10": "p2_to_mixer",
}
OPTIMIZATION_VARIABLES = (
    "fs.P1.control_volume.properties_out[0].pressure",
    "fs.RO.area",
)
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "minimize levelized cost of water",
    "variables_to_unfix": [
        "fs.P1.control_volume.properties_out[0].pressure",
        "fs.RO.area",
    ],
    "target_dof": 1,
    "constraints": [
        "product NaCl mass fraction <= 500e-6",
        "minimum terminal water flux >= 1/3600 kg/m2/s",
    ],
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case(optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        validate_optimization_plan(
            optimization_plan, OPTIMIZATION_PLAN_TEMPLATE, label="RO-with-ERD"
        )
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.RO_with_energy_recovery import RO_with_energy_recovery as ro_erd  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ro_erd.build(erd_type=ro_erd.ERDtype.pressure_exchanger)
            ro_erd.set_operating_conditions(model)
            ro_erd.initialize_system(model)
            simulation_results = ro_erd.solve(model, tee=False)
            ro_erd.optimize_set_up(model)
            optimization_results = ro_erd.solve(model, tee=False)

        sim_optimal = bool(check_optimal_termination(simulation_results))
        opt_optimal = bool(check_optimal_termination(optimization_results))
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.RO.recovery_mass_phase_comp[0, "Liq", "H2O"])
        product_salinity = _value(model.fs.product.properties[0].mass_frac_phase_comp["Liq", "NaCl"])
        pressure_pa = _value(model.fs.P1.control_volume.properties_out[0].pressure)
        membrane_area_m2 = _value(model.fs.RO.area)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = (
            sim_optimal
            and opt_optimal
            and lcow is not None
            and lcow > 0
            and sec is not None
            and recovery is not None
            and product_salinity is not None
            and product_salinity <= 500e-6
        )
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_ro_with_energy_recovery",
            "official_reference_url": SOURCE_URL,
            "simulation_termination_condition": str(simulation_results.solver.termination_condition),
            "termination_condition": str(optimization_results.solver.termination_condition),
            "checks": [
                {"name": "ro_erd_pre_optimization_simulation_optimal", "pass": sim_optimal},
                {"name": "ro_erd_optimization_optimal", "pass": opt_optimal},
                {"name": "ro_erd_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "ro_erd_product_quality_met", "pass": product_salinity is not None and product_salinity <= 500e-6},
            ],
            "final_dof": degrees_of_freedom(model),
            "erd_type": "pressure_exchanger",
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "product_salinity_mass_fraction": product_salinity,
            "ro_operating_pressure_pa": pressure_pa,
            "membrane_area_m2": membrane_area_m2,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.RO_with_energy_recovery.RO_with_energy_recovery",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            **plan_provenance(optimization_plan, OPTIMIZATION_PLAN_TEMPLATE),
            "error": None if passed else {"message": "WaterTAP RO-with-ERD optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_ro_with_energy_recovery",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ro_erd_optimization_runner_exception", "pass": False}],
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
