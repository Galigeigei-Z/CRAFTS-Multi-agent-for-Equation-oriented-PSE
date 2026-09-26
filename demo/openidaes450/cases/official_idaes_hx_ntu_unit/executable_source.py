#!/usr/bin/env python3
"""Run the official IDAES HeatExchangerNTU unit-model benchmark."""

from __future__ import annotations

import argparse
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

from pyomo.environ import ConcreteModel, TerminationCondition, value  # noqa: E402
from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock  # noqa: E402
from idaes.models.unit_models.heat_exchanger_ntu import HeatExchangerNTU  # noqa: E402
from idaes.models_extra.column_models.properties.MEA_solvent import configuration as aqueous_mea  # noqa: E402
from stage3_specs_solve.native_topology_probe import probe_native_topology  # noqa: E402


SOURCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/UnitModels/Operations/heat_exchanger_NTU.html"
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
    model.fs.heat_exchanger = HeatExchangerNTU(
        hot_side={
            "property_package": model.fs.hotside_properties,
            "has_pressure_change": True,
        },
        cold_side={
            "property_package": model.fs.coldside_properties,
            "has_pressure_change": True,
        },
    )
    hx = model.fs.heat_exchanger
    hx.hot_side_inlet.flow_mol[0].fix(60.54879)
    hx.hot_side_inlet.temperature[0].fix(392.23)
    hx.hot_side_inlet.pressure[0].fix(202650)
    hx.hot_side_inlet.mole_frac_comp[0, "CO2"].fix(0.0158)
    hx.hot_side_inlet.mole_frac_comp[0, "H2O"].fix(0.8747)
    hx.hot_side_inlet.mole_frac_comp[0, "MEA"].fix(0.1095)
    hx.cold_side_inlet.flow_mol[0].fix(63.01910)
    hx.cold_side_inlet.temperature[0].fix(326.36)
    hx.cold_side_inlet.pressure[0].fix(202650)
    hx.cold_side_inlet.mole_frac_comp[0, "CO2"].fix(0.0414)
    hx.cold_side_inlet.mole_frac_comp[0, "H2O"].fix(0.8509)
    hx.cold_side_inlet.mole_frac_comp[0, "MEA"].fix(0.1077)
    hx.area.fix(100)
    hx.heat_transfer_coefficient.fix(200)
    hx.effectiveness.fix(0.7)
    hx.hot_side.deltaP.fix(-2000)
    hx.cold_side.deltaP.fix(-2000)
    return model


def port_values(port: Any) -> dict[str, Any]:
    return {
        "flow_mol": scalar(port.flow_mol, 0),
        "temperature": scalar(port.temperature, 0),
        "pressure": scalar(port.pressure, 0),
        "mole_frac_comp": {
            component: scalar(port.mole_frac_comp, 0, component)
            for component in COMPONENTS
        },
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        model = build_model()
        initial_dof = degrees_of_freedom(model)
        model.fs.heat_exchanger.initialize()
        results = get_solver().solve(model, tee=tee)
        termination = results.solver.termination_condition
        final_dof = degrees_of_freedom(model)
        native_topology_binding = probe_native_topology(
            model, units={"heat_exchanger": "fs.heat_exchanger"}, arcs={}
        )
        passed = termination == TerminationCondition.optimal and final_dof == 0 and native_topology_binding["passed"]
        return {
            "pass": bool(passed),
            "stage": "steady_state_solver",
            "case_family": "hx_ntu_unit",
            "source_url": SOURCE_URL,
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "termination_condition": str(termination),
            "stream_values": {
                "hot_side_outlet": port_values(model.fs.heat_exchanger.hot_side_outlet),
                "cold_side_outlet": port_values(model.fs.heat_exchanger.cold_side_outlet),
            },
            "native_topology_binding": native_topology_binding,
            "error": None if passed else {"message": "HX-NTU solve did not reach optimal termination with DOF 0"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "hx_ntu_unit",
            "source_url": SOURCE_URL,
            "initial_dof": None,
            "final_dof": None,
            "termination_condition": None,
            "stream_values": {},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case(tee=args.tee)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
