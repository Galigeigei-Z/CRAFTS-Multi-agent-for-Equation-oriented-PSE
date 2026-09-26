#!/usr/bin/env python3
"""Optimize the official NGFC autothermal reformer subsystem."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/"
    "langgraph_idaes_pipeline"
)
SOURCE_RELATIVE_PATH = Path(
    "examples/archived_canonical_sources/cases/sources/official_examples_power_gen"
)
SOURCE_ROOT = LEGACY_ARTIFACT_ROOT / SOURCE_RELATIVE_PATH
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/ngfc/NGFC_flowsheet_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

import pyomo.environ as pyo  # noqa: E402
from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import Constraint, Objective, TerminationCondition, value  # noqa: E402

from stage3_specs_solve.run_ngfc_atr_reference_solve import (  # noqa: E402
    scale_reformer_subsystem,
    stream_values,
)


OPTIMIZATION_VARIABLES = (
    "fs.reformer_bypass.split_fraction[0, 'bypass_outlet']",
)
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "maximize syngas H2 mole fraction",
    "variables_to_unfix": ["fs.reformer_bypass.split_fraction[0, 'bypass_outlet']"],
    "target_dof": 1,
    "constraints": ["syngas N2 mole fraction <= 0.34"],
}


def validate_optimization_plan(path: Path | None) -> None:
    if path is None:
        return
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if candidate != OPTIMIZATION_PLAN_TEMPLATE:
        raise ValueError("OptimizationPlanIR does not match the registered NGFC ATR template")


def register_local_sofc_rom() -> None:
    for name in ("idaes_examples", "idaes_examples.mod", "idaes_examples.mod.power_gen"):
        sys.modules.setdefault(name, types.ModuleType(name))
    spec = importlib.util.spec_from_file_location(
        "idaes_examples.mod.power_gen.SOFC_ROM", SOURCE_ROOT / "SOFC_ROM.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)


def component_value(obj: Any, *index: Any) -> float | None:
    if index:
        try:
            return float(value(obj[index]))
        except Exception:
            pass
    try:
        if hasattr(obj, "is_indexed") and obj.is_indexed():
            return float(value(obj[next(iter(obj))]))
    except Exception:
        pass
    try:
        return float(value(obj))
    except Exception:
        return None


def build_initialized_model() -> Any:
    register_local_sofc_rom()
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    import NGFC_flowsheet as ngfc  # noqa: PLC0415

    model = pyo.ConcreteModel(name="NGFC ATR optimization")
    model.fs = FlowsheetBlock(dynamic=False)
    ngfc.build_properties(model)
    ngfc.build_reformer(model)
    ngfc.set_reformer_inputs(model)
    scale_reformer_subsystem(model)
    ngfc.initialize_reformer(model, outlvl=50)
    pyo.SolverFactory("ipopt").solve(model, tee=False)
    return model


def configure_optimization(model: Any) -> None:
    fs = model.fs
    fs.reformer_bypass.split_fraction[0, "bypass_outlet"].unfix()
    fs.reformer_bypass.split_fraction[0, "bypass_outlet"].setlb(0.1)
    fs.reformer_bypass.split_fraction[0, "bypass_outlet"].setub(0.8)

    if not hasattr(fs, "atr_n2_product_limit"):
        fs.atr_n2_product_limit = Constraint(
            expr=fs.bypass_rejoin.outlet.mole_frac_comp[0, "N2"] <= 0.34
        )
    if not hasattr(fs, "atr_h2_max_objective"):
        fs.atr_h2_max_objective = Objective(
            expr=-fs.bypass_rejoin.outlet.mole_frac_comp[0, "H2"]
        )


def optimization_summary(
    model: Any,
    termination: str,
    steady_state_dof: int | None,
    optimization_dof: int | None,
) -> dict[str, Any]:
    fs = model.fs
    h2 = component_value(fs.bypass_rejoin.outlet.mole_frac_comp, 0, "H2")
    n2 = component_value(fs.bypass_rejoin.outlet.mole_frac_comp, 0, "N2")
    return {
        "pass": termination == str(TerminationCondition.optimal),
        "stage": "steady_state_optimization",
        "case_family": "ngfc_atr",
        "official_reference_url": OFFICIAL_REFERENCE_URL,
        "optimization_form": "rigorous_ngfc_reformer_subsystem_ipopt",
        "optimization_basis": {
            "decision_variables": ["bypass_frac"],
            "objective": "maximize syngas H2 mole fraction",
            "constraint": "syngas N2 mole fraction <= 0.34",
            "note": "This runner uses the rigorous local IDAES NGFC reformer subsystem with Ipopt.",
        },
        "optimization_plan_variables": list(OPTIMIZATION_VARIABLES),
        "termination_condition": termination,
        "steady_state_dof_before_optimization": steady_state_dof,
        "optimization_degrees_of_freedom": optimization_dof,
        "final_dof": optimization_dof,
        "objective_max_h2_mole_fraction": h2,
        "decision_variables": {
            "bypass_frac": component_value(fs.reformer_bypass.split_fraction, 0, "bypass_outlet"),
            "steam_to_ng_ratio_effective": component_value(fs.reformer_mix.steam_inlet.flow_mol, 0)
            / ((1 - component_value(fs.reformer_bypass.split_fraction, 0, "bypass_outlet")) * component_value(fs.reformer_recuperator.tube_inlet.flow_mol, 0)),
        },
        "constraints": {
            "bypass_frac_bounds": [0.1, 0.8],
            "max_product_n2_mole_fraction": 0.34,
            "product_n2_mole_fraction": n2,
        },
        "product": {
            "atr_syngas_h2_mole_fraction": h2,
            "atr_syngas_n2_mole_fraction": n2,
            "atr_syngas_flow_mol": component_value(fs.bypass_rejoin.outlet.flow_mol, 0),
            "atr_syngas_temperature": component_value(fs.bypass_rejoin.outlet.temperature, 0),
            "atr_syngas_pressure": component_value(fs.bypass_rejoin.outlet.pressure, 0),
        },
        "stream_values": stream_values(model),
        "source_binding": {
            "kind": "explicit_legacy_artifact_root",
            "artifact_root": str(LEGACY_ARTIFACT_ROOT),
            "relative_path": str(SOURCE_RELATIVE_PATH),
        },
        "error": None,
    }


def run_optimization(
    tee: bool = False, optimization_plan: Path | None = None
) -> dict[str, Any]:
    try:
        validate_optimization_plan(optimization_plan)
        model = build_initialized_model()
        steady_state_dof = degrees_of_freedom(model)
        configure_optimization(model)
        optimization_dof = degrees_of_freedom(model)
        solver = pyo.SolverFactory("ipopt")
        solver.options["max_iter"] = 500
        solver.options["tol"] = 1e-6
        results = solver.solve(model, tee=tee)
        termination = str(results.solver.termination_condition)
        summary = optimization_summary(model, termination, steady_state_dof, optimization_dof)
        summary["optimization_plan_file"] = (
            str(optimization_plan) if optimization_plan else None
        )
        return summary
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_optimization",
            "case_family": "ngfc_atr",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_binding": {
                "kind": "explicit_legacy_artifact_root",
                "artifact_root": str(LEGACY_ARTIFACT_ROOT),
                "relative_path": str(SOURCE_RELATIVE_PATH),
            },
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--optimization-plan", type=Path)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_optimization(tee=args.tee, optimization_plan=args.optimization_plan)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
