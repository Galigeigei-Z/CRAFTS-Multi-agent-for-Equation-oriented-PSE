#!/usr/bin/env python3
"""Run the upstream IDAES PlateHeatExchanger benchmark configuration."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "core"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import ConcreteModel, TerminationCondition, check_optimal_termination, units as pyunits, value  # noqa: E402
from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from idaes.core.util.testing import initialization_tester  # noqa: E402
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock  # noqa: E402
from idaes.models_extra.column_models.plate_heat_exchanger import PlateHeatExchanger  # noqa: E402
from idaes.models_extra.column_models.properties.MEA_solvent import configuration as aqueous_mea  # noqa: E402
from stage3_specs_solve.native_topology_probe import probe_native_topology  # noqa: E402


SOURCE_URL = "https://idaes-pse.readthedocs.io/en/2.7.0/reference_guides/model_libraries/models_extra/phe.html"
COMPONENTS = ("CO2", "H2O", "MEA")


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def build_model() -> Any:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.hotside_properties = GenericParameterBlock(**aqueous_mea)
    model.fs.coldside_properties = GenericParameterBlock(**aqueous_mea)
    model.fs.unit = PlateHeatExchanger(
        passes=4,
        channels_per_pass=12,
        number_of_divider_plates=2,
        hot_side={"property_package": model.fs.hotside_properties},
        cold_side={"property_package": model.fs.coldside_properties},
    )
    return model


def set_operating_conditions(model: Any) -> None:
    unit = model.fs.unit
    unit.hot_side_inlet.flow_mol[0].fix(60.54879)
    unit.hot_side_inlet.temperature[0].fix(392.23)
    unit.hot_side_inlet.pressure[0].fix(202650)
    unit.hot_side_inlet.mole_frac_comp[0, "CO2"].fix(0.0158)
    unit.hot_side_inlet.mole_frac_comp[0, "H2O"].fix(0.8747)
    unit.hot_side_inlet.mole_frac_comp[0, "MEA"].fix(0.1095)

    unit.cold_side_inlet.flow_mol[0].fix(63.01910)
    unit.cold_side_inlet.temperature[0].fix(326.36)
    unit.cold_side_inlet.pressure[0].fix(202650)
    unit.cold_side_inlet.mole_frac_comp[0, "CO2"].fix(0.0414)
    unit.cold_side_inlet.mole_frac_comp[0, "H2O"].fix(0.8509)
    unit.cold_side_inlet.mole_frac_comp[0, "MEA"].fix(0.1077)

    unit.plate_length.fix()
    unit.plate_width.fix()
    unit.plate_thickness.fix()
    unit.plate_pact_length.fix()
    unit.port_diameter.fix()
    unit.plate_therm_cond.fix()
    unit.area.fix()


def liquid_stream(port: Any) -> dict[str, Any]:
    flow_mol = scalar(port.flow_mol, 0) or 0.0
    mole_frac = {component: scalar(port.mole_frac_comp, 0, component) for component in COMPONENTS}
    return {
        "flow_mol": flow_mol,
        "temperature": scalar(port.temperature, 0),
        "pressure": scalar(port.pressure, 0),
        "mole_frac_comp": mole_frac,
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        model = build_model()
        set_operating_conditions(model)
        initial_dof = degrees_of_freedom(model)
        initialization_tester(model, duty=(245000, pyunits.W), optarg={"bound_push": 1e-8, "mu_init": 1e-8})
        results = get_solver().solve(model, tee=tee)
        termination = results.solver.termination_condition
        final_dof = degrees_of_freedom(model)
        native_topology_binding = probe_native_topology(
            model,
            units={
                "hot_feed": "fs.unit.hot_side_inlet",
                "cold_feed": "fs.unit.cold_side_inlet",
                "unit": "fs.unit",
                "hot_product": "fs.unit.hot_side_outlet",
                "cold_product": "fs.unit.cold_side_outlet",
            },
            arcs={
                "hot_feed_to_phe": ("fs.unit.hot_side_inlet", "fs.unit.hot_side_inlet"),
                "cold_feed_to_phe": ("fs.unit.cold_side_inlet", "fs.unit.cold_side_inlet"),
                "phe_hot_to_product": ("fs.unit.hot_side_outlet", "fs.unit.hot_side_outlet"),
                "phe_cold_to_product": ("fs.unit.cold_side_outlet", "fs.unit.cold_side_outlet"),
            },
        )
        passed = bool(check_optimal_termination(results) and final_dof == 0 and native_topology_binding["passed"])
        unit = model.fs.unit
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "plate_heat_exchanger",
            "source_url": SOURCE_URL,
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "termination_condition": str(termination),
            "heat_duty": scalar(unit.heat_duty, 0),
            "effectiveness": scalar(unit.effectiveness, 0),
            "ntu": scalar(unit.NTU, 0),
            "stream_values": {
                "hot_side_inlet": liquid_stream(unit.hot_side_inlet),
                "hot_side_outlet": liquid_stream(unit.hot_side_outlet),
                "cold_side_inlet": liquid_stream(unit.cold_side_inlet),
                "cold_side_outlet": liquid_stream(unit.cold_side_outlet),
            },
            "native_topology_binding": native_topology_binding,
            "error": None if passed else {"message": "PlateHeatExchanger solve did not reach optimal zero-DOF state"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "plate_heat_exchanger",
            "source_url": SOURCE_URL,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case(tee=args.tee)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
