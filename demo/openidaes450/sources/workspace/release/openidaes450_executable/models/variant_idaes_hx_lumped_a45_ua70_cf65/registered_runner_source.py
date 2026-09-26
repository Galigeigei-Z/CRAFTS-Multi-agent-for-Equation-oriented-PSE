#!/usr/bin/env python3
"""Run the official IDAES HeatExchangerLumpedCapacitance benchmark."""

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

from pyomo.environ import ConcreteModel, TerminationCondition, units as pyunits, value  # noqa: E402
from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from idaes.models.properties import iapws95  # noqa: E402
from idaes.models.properties.iapws95 import htpx  # noqa: E402
from idaes.models.properties.modular_properties import GenericParameterBlock  # noqa: E402
from idaes.models.properties.modular_properties.examples.BT_ideal import configuration  # noqa: E402
from idaes.models.unit_models import HeatExchangerFlowPattern, HeatExchangerLumpedCapacitance  # noqa: E402
from stage3_specs_solve.native_topology_probe import probe_native_topology  # noqa: E402


SOURCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/UnitModels/Operations/heat_exchanger_lc.html"


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def build_model() -> Any:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties_shell = iapws95.Iapws95ParameterBlock()
    model.fs.properties_tube = GenericParameterBlock(**configuration)
    model.fs.heat_exchanger = HeatExchangerLumpedCapacitance(
        hot_side_name="shell",
        cold_side_name="tube",
        shell={"property_package": model.fs.properties_shell},
        tube={"property_package": model.fs.properties_tube},
        flow_pattern=HeatExchangerFlowPattern.crossflow,
        dynamic_heat_balance=False,
    )
    return model


def set_operating_conditions(model: Any) -> None:
    hx = model.fs.heat_exchanger
    hx.shell_inlet.flow_mol.fix(100)
    hx.shell_inlet.enth_mol.fix(htpx(400 * pyunits.K, 101325 * pyunits.Pa))
    hx.shell_inlet.pressure.fix(101325)
    hx.tube_inlet.flow_mol.fix(250)
    hx.tube_inlet.mole_frac_comp[0, "benzene"].fix(0.4)
    hx.tube_inlet.mole_frac_comp[0, "toluene"].fix(0.6)
    hx.tube_inlet.temperature.fix(380)
    hx.tube_inlet.pressure.fix(101325)
    hx.area.fix(50)
    hx.ua_hot_side.fix(200 * 1000)
    hx.ua_cold_side.fix(200 * 1000)
    hx.crossflow_factor.fix(0.6)


def shell_stream(state_block: Any) -> dict[str, Any]:
    state = state_block[0] if hasattr(state_block, "__getitem__") else state_block
    return {
        "flow_mol": scalar(state.flow_mol),
        "temperature": scalar(state.temperature),
        "pressure": scalar(state.pressure),
    }


def tube_stream(port: Any) -> dict[str, Any]:
    flow_mol = scalar(port.flow_mol, 0) or 0.0
    mole_frac = {component: scalar(port.mole_frac_comp, 0, component) for component in ("benzene", "toluene")}
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
        hx = model.fs.heat_exchanger
        hx.initialize()
        results = get_solver().solve(model, tee=tee)
        termination = results.solver.termination_condition
        final_dof = degrees_of_freedom(model)
        native_topology_binding = probe_native_topology(
            model,
            units={
                "shell_inlet": "fs.heat_exchanger.shell_inlet",
                "tube_inlet": "fs.heat_exchanger.tube_inlet",
                "heat_exchanger": "fs.heat_exchanger",
                "shell_outlet": "fs.heat_exchanger.shell_outlet",
                "tube_outlet": "fs.heat_exchanger.tube_outlet",
            },
            arcs={
                "shell_feed_to_hx": ("fs.heat_exchanger.shell_inlet", "fs.heat_exchanger.shell_inlet"),
                "tube_feed_to_hx": ("fs.heat_exchanger.tube_inlet", "fs.heat_exchanger.tube_inlet"),
                "hx_shell_to_product": ("fs.heat_exchanger.shell_outlet", "fs.heat_exchanger.shell_outlet"),
                "hx_tube_to_product": ("fs.heat_exchanger.tube_outlet", "fs.heat_exchanger.tube_outlet"),
            },
        )
        passed = bool(termination == TerminationCondition.optimal and final_dof == 0 and native_topology_binding["passed"])
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "hx_lumped_capacitance",
            "source_url": SOURCE_URL,
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "termination_condition": str(termination),
            "heat_duty": scalar(hx.heat_duty, 0),
            "stream_values": {
                "shell_inlet": shell_stream(hx.hot_side.properties_in),
                "shell_outlet": shell_stream(hx.hot_side.properties_out),
                "tube_inlet": tube_stream(hx.tube_inlet),
                "tube_outlet": tube_stream(hx.tube_outlet),
            },
            "native_topology_binding": native_topology_binding,
            "error": None if passed else {"message": "HX lumped-capacitance solve did not reach optimal zero-DOF state"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "hx_lumped_capacitance",
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
