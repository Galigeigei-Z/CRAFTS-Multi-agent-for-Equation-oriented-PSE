#!/usr/bin/env python3
"""Run the official IDAES HeatExchanger1D unit-model benchmark."""

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

from pyomo.environ import TerminationCondition, units as pyunits, value  # noqa: E402
from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from idaes.models.properties import iapws95  # noqa: E402
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock  # noqa: E402
from idaes.models.properties.modular_properties.examples.BT_ideal import configuration as bt_ideal  # noqa: E402
from idaes.models.unit_models.heat_exchanger import HeatExchangerFlowPattern  # noqa: E402
from idaes.models.unit_models.heat_exchanger_1D import HeatExchanger1D  # noqa: E402
from pyomo.environ import ConcreteModel  # noqa: E402
from stage3_specs_solve.native_topology_probe import probe_native_topology  # noqa: E402


SOURCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/UnitModels/Operations/heat_exchanger_1D.html"


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def build_model() -> Any:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties_shell = iapws95.Iapws95ParameterBlock()
    model.fs.properties_tube = GenericParameterBlock(**bt_ideal)
    model.fs.heat_exchanger = HeatExchanger1D(
        hot_side={"property_package": model.fs.properties_shell},
        cold_side={"property_package": model.fs.properties_tube},
        hot_side_name="shell",
        cold_side_name="tube",
        finite_elements=20,
        flow_type=HeatExchangerFlowPattern.cocurrent,
    )
    hx = model.fs.heat_exchanger
    hx.area.fix(0.5)
    hx.length.fix(4.85)
    hx.heat_transfer_coefficient.fix(500)
    hx.shell_inlet.flow_mol[0].fix(100)
    hx.shell_inlet.enth_mol[0].fix(
        iapws95.htpx(450 * pyunits.K, P=101325 * pyunits.Pa)
    )
    hx.shell_inlet.pressure[0].fix(101325)
    hx.tube_inlet.flow_mol[0].fix(250)
    hx.tube_inlet.temperature[0].fix(350)
    hx.tube_inlet.pressure[0].fix(101325)
    hx.tube_inlet.mole_frac_comp[0, "benzene"].fix(0.4)
    hx.tube_inlet.mole_frac_comp[0, "toluene"].fix(0.6)
    return model


def stream_values(model: Any) -> dict[str, Any]:
    hx = model.fs.heat_exchanger
    return {
        "shell_outlet": {
            "flow_mol": scalar(hx.shell_outlet.flow_mol, 0),
            "enth_mol": scalar(hx.shell_outlet.enth_mol, 0),
            "pressure": scalar(hx.shell_outlet.pressure, 0),
        },
        "tube_outlet": {
            "flow_mol": scalar(hx.tube_outlet.flow_mol, 0),
            "temperature": scalar(hx.tube_outlet.temperature, 0),
            "pressure": scalar(hx.tube_outlet.pressure, 0),
            "mole_frac_comp": {
                "benzene": scalar(hx.tube_outlet.mole_frac_comp, 0, "benzene"),
                "toluene": scalar(hx.tube_outlet.mole_frac_comp, 0, "toluene"),
            },
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
            "case_family": "hx1d_unit",
            "source_url": SOURCE_URL,
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "termination_condition": str(termination),
            "stream_values": stream_values(model),
            "native_topology_binding": native_topology_binding,
            "error": None if passed else {"message": "HX1D solve did not reach optimal termination with DOF 0"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "hx1d_unit",
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
