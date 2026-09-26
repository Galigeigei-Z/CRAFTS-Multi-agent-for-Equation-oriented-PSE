#!/usr/bin/env python3
"""Run the WaterTAP granular activated carbon demonstration simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/1.0.0/technical_reference/flowsheets/gac.html"
ARC_ALIASES = {
    "s01": "feed_to_gac",
    "s02": "gac_to_product",
    "s03": "gac_to_adsorbed_removed",
}
GAC_BUILD_OPTIONS = {
    "material_flow_basis": "molar",
    "film_transfer_coefficient_type": "calculated",
    "surface_diffusion_coefficient_type": "calculated",
    "diffusivity_calculation": "HaydukLaudie",
    "cost_contactor_type": "pressure",
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    gac_unit = model.fs.gac
    feed = model.fs.feed.properties[0]
    product = model.fs.product.properties[0]
    adsorbed = model.fs.adsorbed_removed.properties[0]
    return {
        "levelized_cost_of_water": _value(model.fs.costing.LCOW),
        "specific_energy_consumption": _value(model.fs.costing.specific_energy_consumption),
        "feed_flow_m3_s": _value(feed.flow_vol_phase["Liq"]),
        "product_flow_m3_s": _value(product.flow_vol_phase["Liq"]),
        "feed_solute_flow_mol_s": _value(feed.flow_mol_phase_comp["Liq", "solute"]),
        "product_solute_flow_mol_s": _value(product.flow_mol_phase_comp["Liq", "solute"]),
        "adsorbed_solute_flow_mol_s": _value(adsorbed.flow_mol_phase_comp["Liq", "solute"]),
        "bed_length_m": _value(gac_unit.bed_length),
        "bed_volume_m3": _value(gac_unit.bed_volume),
        "bed_mass_gac_kg": _value(gac_unit.bed_mass_gac),
        "operational_time_s": _value(gac_unit.operational_time),
        "gac_usage_rate_kg_s": _value(gac_unit.gac_usage_rate),
        "bed_volumes_treated": _value(gac_unit.bed_volumes_treated),
        "capital_cost": _value(gac_unit.costing.capital_cost),
        "total_capital_cost": _value(model.fs.costing.total_capital_cost),
        "total_operating_cost": _value(model.fs.costing.total_operating_cost),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.gac import gac as gac_flowsheet  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = gac_flowsheet.build(**GAC_BUILD_OPTIONS)
            initial_dof = degrees_of_freedom(model)
            gac_flowsheet.initialize(model, solver)
            results = solver.solve(model)

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and metrics["levelized_cost_of_water"] is not None
            and metrics["levelized_cost_of_water"] > 0
            and metrics["bed_mass_gac_kg"] is not None
            and metrics["bed_mass_gac_kg"] > 0
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_gac",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "gac_simulation_optimal", "pass": optimal},
                {"name": "gac_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "gac_final_dof_zero", "pass": final_dof == 0},
                {"name": "gac_lcow_positive", "pass": metrics["levelized_cost_of_water"] is not None and metrics["levelized_cost_of_water"] > 0},
                {"name": "gac_streams_available", "pass": bool(stream_values)},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.gac.gac",
                "build_options": GAC_BUILD_OPTIONS,
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP GAC simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_gac",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "gac_simulation_runner_exception", "pass": False}],
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
