#!/usr/bin/env python3
"""Run the WaterTAP simple crystallizer official specification sweep."""

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
from watertap_streams import stream_from_port  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/latest/technical_reference/flowsheets/crystallization.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _snapshot(model: Any, name: str, results: Any) -> dict[str, Any]:
    crystallizer = model.fs.crystallizer
    return {
        "case": name,
        "termination_condition": str(results.solver.termination_condition),
        "temperature_operating_k": _value(crystallizer.temperature_operating),
        "pressure_operating_pa": _value(crystallizer.pressure_operating),
        "crystallization_yield_nacl": _value(crystallizer.crystallization_yield["NaCl"]),
        "product_volumetric_solids_fraction": _value(crystallizer.product_volumetric_solids_fraction),
        "magma_density_kg_m3": _value(crystallizer.dens_mass_magma),
        "work_mechanical_w": _value(crystallizer.work_mechanical[0]),
        "solid_nacl_flow_kg_s": _value(crystallizer.solids.flow_mass_phase_comp[0, "Sol", "NaCl"]),
        "vapor_h2o_flow_kg_s": _value(crystallizer.vapor.flow_mass_phase_comp[0, "Vap", "H2O"]),
        "liquid_out_h2o_flow_kg_s": _value(crystallizer.outlet.flow_mass_phase_comp[0, "Liq", "H2O"]),
        "liquid_out_nacl_flow_kg_s": _value(crystallizer.outlet.flow_mass_phase_comp[0, "Liq", "NaCl"]),
        "capital_cost": _value(crystallizer.costing.capital_cost),
        "total_capital_cost": _value(model.fs.costing.total_capital_cost),
        "total_operating_cost": _value(model.fs.costing.total_operating_cost),
    }


def _stream_values(model: Any) -> dict[str, dict[str, Any]]:
    crystallizer = model.fs.crystallizer
    ports = {
        "feed_to_crystallizer": crystallizer.inlet,
        "crystallizer_liquid_outlet": crystallizer.outlet,
        "crystallizer_vapor_outlet": crystallizer.vapor,
        "crystallizer_solids_outlet": crystallizer.solids,
    }
    streams: dict[str, dict[str, Any]] = {}
    for name, port in ports.items():
        record = stream_from_port(port)
        if record:
            record["source_port"] = port.getname(fully_qualified=True)
            streams[name] = record
    return streams


def run_case() -> dict[str, Any]:
    try:
        from idaes.core import FlowsheetBlock, UnitModelCostingBlock  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        import idaes.core.util.scaling as iscale  # noqa: PLC0415
        import idaes.logger as idaeslog  # noqa: PLC0415
        from pyomo.environ import ConcreteModel, TerminationCondition  # noqa: PLC0415
        from pyomo.util.check_units import assert_units_consistent  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.costing import CrystallizerCostType, WaterTAPCosting  # noqa: PLC0415
        from watertap.property_models.unit_specific import cryst_prop_pack as props  # noqa: PLC0415
        from watertap.unit_models.crystallizer import Crystallization  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ConcreteModel()
            model.fs = FlowsheetBlock(dynamic=False)
            model.fs.properties = props.NaClParameterBlock()
            model.fs.costing = WaterTAPCosting()
            model.fs.crystallizer = Crystallization(property_package=model.fs.properties)
            crystallizer = model.fs.crystallizer

            crystallizer.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"].fix(10.5119)
            crystallizer.inlet.flow_mass_phase_comp[0, "Liq", "H2O"].fix(38.9326)
            crystallizer.inlet.flow_mass_phase_comp[0, "Sol", "NaCl"].fix(1e-6)
            crystallizer.inlet.flow_mass_phase_comp[0, "Vap", "H2O"].fix(1e-6)
            crystallizer.inlet.pressure[0].fix(101325)
            crystallizer.inlet.temperature[0].fix(293.15)

            crystallizer.temperature_operating.fix(328.15)
            crystallizer.solids.flow_mass_phase_comp[0, "Sol", "NaCl"].fix(5.556)
            crystallizer.crystal_growth_rate.fix()
            crystallizer.souders_brown_constant.fix()
            crystallizer.crystal_median_length.fix()

            model.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Liq", "H2O"))
            model.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Liq", "NaCl"))
            model.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e0, index=("Vap", "H2O"))
            model.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Sol", "NaCl"))
            iscale.calculate_scaling_factors(model.fs)
            crystallizer.costing = UnitModelCostingBlock(
                flowsheet_costing_block=model.fs.costing,
                costing_method_arguments={"cost_type": CrystallizerCostType.mass_basis},
            )
            model.fs.costing.cost_process()

            crystallizer.initialize(outlvl=idaeslog.WARNING)
            assert_units_consistent(model)
            solver = get_solver()

            case_results = []
            results = solver.solve(model, tee=False, symbolic_solver_labels=True)
            case_results.append(_snapshot(model, "case_1_fixed_temperature_and_solids_flow", results))

            crystallizer.solids.flow_mass_phase_comp[0, "Sol", "NaCl"].unfix()
            crystallizer.crystallization_yield["NaCl"].fix(0.7)
            results = solver.solve(model, tee=False)
            case_results.append(_snapshot(model, "case_2_fixed_crystallization_yield", results))

            crystallizer.crystallization_yield["NaCl"].unfix()
            crystallizer.product_volumetric_solids_fraction.fix(0.1182)
            results = solver.solve(model, tee=False)
            case_results.append(_snapshot(model, "case_3_fixed_product_solids_fraction", results))

            crystallizer.product_volumetric_solids_fraction.unfix()
            crystallizer.dens_mass_magma.fix(250)
            results = solver.solve(model, tee=False)
            case_results.append(_snapshot(model, "case_4_fixed_magma_density", results))

            crystallizer.dens_mass_magma.unfix()
            crystallizer.work_mechanical[0].fix(55000)
            results = solver.solve(model, tee=False)
            case_results.append(_snapshot(model, "case_5_fixed_heat_addition", results))

        final_dof = degrees_of_freedom(model)
        optimal = all(item["termination_condition"] == str(TerminationCondition.optimal) for item in case_results)
        final_case = case_results[-1]
        stream_values = _stream_values(model)
        passed = (
            optimal
            and final_dof == 0
            and final_case["vapor_h2o_flow_kg_s"] is not None
            and final_case["solid_nacl_flow_kg_s"] is not None
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_specification_sweep",
            "case_family": "watertap_crystallization",
            "official_reference_url": SOURCE_URL,
            "termination_condition": final_case["termination_condition"],
            "checks": [
                {"name": "crystallization_all_official_cases_optimal", "pass": optimal},
                {"name": "crystallization_final_dof_zero", "pass": final_dof == 0},
                {"name": "crystallization_streams_available", "pass": bool(stream_values)},
            ],
            "final_dof": final_dof,
            "case_results": case_results,
            "temperature_operating_k": final_case["temperature_operating_k"],
            "pressure_operating_pa": final_case["pressure_operating_pa"],
            "crystallization_yield_nacl": final_case["crystallization_yield_nacl"],
            "product_volumetric_solids_fraction": final_case["product_volumetric_solids_fraction"],
            "magma_density_kg_m3": final_case["magma_density_kg_m3"],
            "work_mechanical_w": final_case["work_mechanical_w"],
            "solid_nacl_flow_kg_s": final_case["solid_nacl_flow_kg_s"],
            "vapor_h2o_flow_kg_s": final_case["vapor_h2o_flow_kg_s"],
            "capital_cost": final_case["capital_cost"],
            "total_capital_cost": final_case["total_capital_cost"],
            "total_operating_cost": final_case["total_operating_cost"],
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.crystallization.sim_simple_crystallizer",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP crystallization specification sweep did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_specification_sweep",
            "case_family": "watertap_crystallization",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "crystallization_runner_exception", "pass": False}],
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
