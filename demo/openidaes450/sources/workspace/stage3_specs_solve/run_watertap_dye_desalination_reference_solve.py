#!/usr/bin/env python3
"""Run the WaterTAP dye desalination GAC + RO reference simulation solve."""

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
from watertap_streams import merge_named_streams, streams_from_arcs  # noqa: E402

SOURCE_URL = "local://watertap/flowsheets/dye_desalination/dye_desalination_gac_ro"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _flow_vol(properties: Any) -> float | None:
    if hasattr(properties, "flow_vol"):
        return _value(properties.flow_vol)
    return _value(properties.flow_vol_phase["Liq"])


def _conc(properties: Any, component: str) -> float | None:
    flow = _flow_vol(properties)
    if flow:
        component_key = "TDS" if component == "tds_as_tds" else component
        if hasattr(properties, "flow_mass_phase_comp"):
            try:
                mass_flow = _value(properties.flow_mass_phase_comp["Liq", component_key])
                if mass_flow is not None:
                    return mass_flow / flow
            except Exception:
                pass
        if hasattr(properties, "flow_mass_comp"):
            try:
                mass_flow = _value(properties.flow_mass_comp[component_key])
                if mass_flow is not None:
                    return mass_flow / flow
            except Exception:
                pass
    if hasattr(properties, "conc_mass_comp"):
        return _value(properties.conc_mass_comp[component])
    if hasattr(properties, "conc_mass_phase_comp"):
        phase_component = ("Liq", "TDS" if component == "tds_as_tds" else component)
        try:
            return _value(properties.conc_mass_phase_comp[phase_component])
        except Exception:
            return None
    return None


def _metrics(model: Any) -> dict[str, Any]:
    feed = model.fs.feed.properties[0]
    treated = model.fs.treated.properties[0]
    dye_product = model.fs.concentrated_dye.properties[0]
    permeate = model.fs.permeate.properties[0]
    brine = model.fs.brine.properties[0]
    return {
        "feed_flow_m3_s": _flow_vol(feed),
        "treated_gac_flow_m3_s": _flow_vol(treated),
        "concentrated_dye_flow_m3_s": _flow_vol(dye_product),
        "permeate_flow_m3_s": _flow_vol(permeate),
        "brine_flow_m3_s": _flow_vol(brine),
        "feed_dye_conc_kg_m3": _conc(feed, "dye"),
        "treated_dye_conc_kg_m3": _conc(treated, "dye"),
        "permeate_tds_conc_kg_m3": _conc(permeate, "tds_as_tds"),
        "brine_tds_conc_kg_m3": _conc(brine, "tds_as_tds"),
        "gac_bed_volume_m3": _value(model.fs.gac.bed_volume),
        "gac_bed_mass_kg": _value(model.fs.gac.bed_mass_gac),
        "ro_area_m2": _value(model.fs.desalination.RO.area),
        "ro_recovery_vol_liq": _value(model.fs.desalination.RO.recovery_vol_phase[0, "Liq"]),
        "levelized_cost_of_treatment": _value(model.fs.LCOT),
        "levelized_cost_of_water": _value(model.fs.LCOW),
        "specific_energy_intensity": _value(model.fs.specific_energy_intensity),
        "total_capital_cost": _value(model.fs.total_capital_cost),
        "total_operating_cost": _value(model.fs.total_operating_cost),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from pyomo.util.check_units import assert_units_consistent  # noqa: PLC0415
        from watertap.core.util.initialization import assert_degrees_of_freedom  # noqa: PLC0415
        from watertap.flowsheets.dye_desalination import dye_desalination  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = dye_desalination.build(
                RO_1D=False,
                include_RO=True,
                include_pretreatment=False,
                include_dewatering=False,
                include_gac=True,
            )
            dye_desalination.set_operating_conditions(model)
            assert_units_consistent(model)
            dye_desalination.initialize_system(model)
            assert_degrees_of_freedom(model, 0)
            initial_results = dye_desalination.solve(model, checkpoint="solve initialized dye desalination flowsheet")
            dye_desalination.add_costing(model, dye_revenue=False, brine_revenue=False)
            dye_desalination.initialize_costing(model)
            final_dof_before_solve = degrees_of_freedom(model)
            results = dye_desalination.solve(model, checkpoint="solve dye desalination flowsheet with costing")

        optimal = bool(check_optimal_termination(results))
        initial_optimal = bool(check_optimal_termination(initial_results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = merge_named_streams(
            streams_from_arcs(model),
            {
                "feed": model.fs.feed.outlet,
                "treated_gac_product": model.fs.treated.inlet,
                "concentrated_dye_product": model.fs.concentrated_dye.inlet,
                "ro_permeate_product": model.fs.permeate.inlet,
                "ro_brine_product": model.fs.brine.inlet,
            },
        )
        passed = (
            initial_optimal
            and optimal
            and final_dof_before_solve == 0
            and final_dof == 0
            and metrics["permeate_flow_m3_s"] is not None
            and metrics["permeate_flow_m3_s"] > 0
            and metrics["levelized_cost_of_water"] is not None
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_dye_desalination",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "dye_desalination_initial_solve_optimal", "pass": initial_optimal},
                {"name": "dye_desalination_final_solve_optimal", "pass": optimal},
                {"name": "dye_desalination_final_dof_zero", "pass": final_dof == 0},
                {"name": "dye_desalination_permeate_flow_positive", "pass": metrics["permeate_flow_m3_s"] is not None and metrics["permeate_flow_m3_s"] > 0},
                {"name": "dye_desalination_lcow_available", "pass": metrics["levelized_cost_of_water"] is not None},
                {"name": "dye_desalination_streams_available", "pass": bool(stream_values)},
            ],
            "final_dof": final_dof,
            "final_dof_before_solve": final_dof_before_solve,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.dye_desalination.dye_desalination",
                "configuration": "RO_1D=False, include_RO=True, include_gac=True, no operation optimization",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP dye desalination simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_dye_desalination",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "dye_desalination_runner_exception", "pass": False}],
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
