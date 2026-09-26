#!/usr/bin/env python3
"""Run the official IDAES reactor unit-model suite smoke benchmark."""

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
from idaes.core.util.testing import PhysicalParameterTestBlock  # noqa: E402
from idaes.models.properties.examples.saponification_reactions import SaponificationReactionParameterBlock  # noqa: E402
from idaes.models.properties.examples.saponification_thermo import SaponificationParameterBlock  # noqa: E402
from idaes.models.unit_models import CSTR, GibbsReactor, PFR, StoichiometricReactor  # noqa: E402


SOURCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/UnitModels/Reactors/plug_flow_reactor_doc.html"
SAPON_COMPONENTS = ("H2O", "NaOH", "EthylAcetate", "SodiumAcetate", "Ethanol")


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def fix_sapon_inlet(unit: Any, flow_vol: float) -> None:
    unit.inlet.flow_vol.fix(flow_vol)
    unit.inlet.conc_mol_comp[0, "H2O"].fix(55388.0)
    unit.inlet.conc_mol_comp[0, "NaOH"].fix(100.0)
    unit.inlet.conc_mol_comp[0, "EthylAcetate"].fix(100.0)
    unit.inlet.conc_mol_comp[0, "SodiumAcetate"].fix(1e-8)
    unit.inlet.conc_mol_comp[0, "Ethanol"].fix(1e-8)
    unit.inlet.temperature.fix(303.15)
    unit.inlet.pressure.fix(101325.0)


def sapon_port_values(port: Any) -> dict[str, Any]:
    return {
        "flow_vol": scalar(port.flow_vol, 0),
        "temperature": scalar(port.temperature, 0),
        "pressure": scalar(port.pressure, 0),
        "conc_mol_comp": {
            component: scalar(port.conc_mol_comp, 0, component)
            for component in SAPON_COMPONENTS
        },
    }


def build_cstr() -> Any:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = SaponificationParameterBlock()
    model.fs.reactions = SaponificationReactionParameterBlock(property_package=model.fs.properties)
    model.fs.unit = CSTR(
        property_package=model.fs.properties,
        reaction_package=model.fs.reactions,
        has_equilibrium_reactions=False,
        has_heat_transfer=True,
        has_heat_of_reaction=True,
        has_pressure_change=True,
    )
    fix_sapon_inlet(model.fs.unit, 1.0e-3)
    model.fs.unit.volume[0].fix(1.5e-3)
    model.fs.unit.heat_duty[0].fix(0)
    model.fs.unit.deltaP[0].fix(0)
    return model


def build_pfr() -> Any:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = SaponificationParameterBlock()
    model.fs.reactions = SaponificationReactionParameterBlock(property_package=model.fs.properties)
    model.fs.unit = PFR(
        property_package=model.fs.properties,
        reaction_package=model.fs.reactions,
        has_equilibrium_reactions=False,
        has_heat_transfer=True,
        has_heat_of_reaction=True,
        has_pressure_change=True,
    )
    fix_sapon_inlet(model.fs.unit, 1.0)
    model.fs.unit.length.fix(0.5)
    model.fs.unit.area.fix(0.1)
    model.fs.unit.heat_duty.fix(0)
    model.fs.unit.deltaP.fix(0)
    return model


def solve_unit(label: str, model: Any, tee: bool) -> dict[str, Any]:
    initial_dof = degrees_of_freedom(model)
    model.fs.unit.initialize()
    results = get_solver().solve(model, tee=tee)
    termination = results.solver.termination_condition
    final_dof = degrees_of_freedom(model)
    return {
        "pass": bool(termination == TerminationCondition.optimal and final_dof == 0),
        "label": label,
        "initial_dof": initial_dof,
        "final_dof": final_dof,
        "termination_condition": str(termination),
        "outlet": sapon_port_values(model.fs.unit.outlet),
    }


def construct_gibbs() -> dict[str, Any]:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = PhysicalParameterTestBlock()
    model.fs.unit = GibbsReactor(property_package=model.fs.properties)
    return {
        "pass": True,
        "label": "gibbs",
        "constructed": True,
        "constraint_count": len(model.fs.unit.gibbs_minimization),
    }


def construct_stoichiometric() -> dict[str, Any]:
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = SaponificationParameterBlock()
    model.fs.reactions = SaponificationReactionParameterBlock(property_package=model.fs.properties)
    model.fs.unit = StoichiometricReactor(
        property_package=model.fs.properties,
        reaction_package=model.fs.reactions,
        has_heat_transfer=True,
        has_heat_of_reaction=True,
        has_pressure_change=True,
    )
    return {
        "pass": True,
        "label": "stoichiometric",
        "constructed": True,
        "has_ports": bool(hasattr(model.fs.unit, "inlet") and hasattr(model.fs.unit, "outlet")),
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        checks = [
            solve_unit("cstr", build_cstr(), tee),
            solve_unit("pfr", build_pfr(), tee),
            construct_gibbs(),
            construct_stoichiometric(),
        ]
        passed = all(check.get("pass") for check in checks)
        return {
            "pass": bool(passed),
            "stage": "steady_state_solver",
            "case_family": "reactor_unit_suite",
            "source_url": SOURCE_URL,
            "checks": checks,
            "error": None if passed else {"message": "one or more reactor suite checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "reactor_unit_suite",
            "source_url": SOURCE_URL,
            "checks": [],
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
