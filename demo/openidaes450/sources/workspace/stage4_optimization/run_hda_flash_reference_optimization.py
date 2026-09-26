#!/usr/bin/env python3
"""Optimize the converged local HDA flash reference case."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "examples" / "hda_flash"
SOURCE_ROOT = CASE_PATH / "source_root"
OFFICIAL_REFERENCE_URL = "https://idaes-examples.readthedocs.io/en/2.4.0/docs/tut/core/hda_flowsheet_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import Constraint, Expression, Objective, SolverFactory, TerminationCondition, value  # noqa: E402


OPTIMIZATION_VARIABLES = (
    "fs.H101.outlet.temperature",
    "fs.R101.conversion",
    "fs.F101.vap_outlet.temperature",
    "fs.F102.vap_outlet.temperature",
    "fs.S101.split_fraction[0,purge]",
)


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


def add_hda_flash_costing(model: Any) -> None:
    fs = model.fs
    if not hasattr(fs, "product_purity"):
        fs.product_purity = Expression(
            expr=fs.F102.vap_outlet.flow_mol_phase_comp[0, "Vap", "benzene"]
            / (
                fs.F102.vap_outlet.flow_mol_phase_comp[0, "Vap", "benzene"]
                + fs.F102.vap_outlet.flow_mol_phase_comp[0, "Vap", "toluene"]
            )
        )
    if not hasattr(fs, "cooling_cost"):
        fs.cooling_cost = Expression(
            expr=0.25e-7 * (-fs.F101.heat_duty[0])
            + 0.25e-7 * (-fs.F102.heat_duty[0])
        )
    if not hasattr(fs, "heating_cost"):
        fs.heating_cost = Expression(expr=2.2e-7 * fs.H101.heat_duty[0])
    if not hasattr(fs, "operating_cost"):
        fs.operating_cost = Expression(expr=3600 * 24 * 365 * (fs.heating_cost + fs.cooling_cost))
    if not hasattr(fs, "capital_cost"):
        fs.capital_cost = Expression(expr=0)


def configure_hda_flash_optimization(model: Any, variables_to_unfix: list[str] | None = None) -> list[str]:
    fs = model.fs
    add_hda_flash_costing(model)
    if not hasattr(fs, "objective"):
        fs.objective = Objective(expr=fs.operating_cost + fs.capital_cost)

    variable_map = {
        "fs.H101.outlet.temperature": fs.H101.outlet.temperature,
        "fs.R101.conversion": fs.R101.conversion,
        "fs.F101.vap_outlet.temperature": fs.F101.vap_outlet.temperature,
        "fs.F102.vap_outlet.temperature": fs.F102.vap_outlet.temperature,
        "fs.S101.split_fraction[0,purge]": fs.S101.split_fraction[0, "purge"],
    }
    selected = list(OPTIMIZATION_VARIABLES) if variables_to_unfix is None else variables_to_unfix
    unknown = [name for name in selected if name not in variable_map]
    if unknown:
        raise ValueError(f"OptimizationPlanIR contains unsupported HDA flash variables: {unknown}")
    for name in selected:
        variable_map[name].unfix()

    fs.H101.outlet.temperature[0].setlb(500)
    fs.H101.outlet.temperature[0].setub(650)
    fs.R101.outlet.temperature[0].setlb(600)
    fs.R101.outlet.temperature[0].setub(900)
    fs.R101.conversion.setlb(0.55)
    fs.R101.conversion.setub(0.95)
    fs.F101.vap_outlet.temperature[0].setlb(300)
    fs.F101.vap_outlet.temperature[0].setub(365)
    fs.F102.vap_outlet.temperature[0].setlb(330)
    fs.F102.vap_outlet.temperature[0].setub(430)
    fs.S101.split_fraction[0, "purge"].setlb(0.05)
    fs.S101.split_fraction[0, "purge"].setub(0.5)

    if not hasattr(fs, "f102_vapor_product_purity"):
        fs.f102_vapor_product_purity = Constraint(expr=fs.product_purity >= 0.82)
    if not hasattr(fs, "f102_vapor_benzene_product_flow"):
        fs.f102_vapor_benzene_product_flow = Constraint(
            expr=fs.F102.vap_outlet.flow_mol_phase_comp[0, "Vap", "benzene"] >= 0.13
        )
    if not hasattr(fs, "f101_overhead_benzene_loss"):
        fs.f101_overhead_benzene_loss = Constraint(
            expr=fs.F101.vap_outlet.flow_mol_phase_comp[0, "Vap", "benzene"]
            <= 0.45 * fs.R101.outlet.flow_mol_phase_comp[0, "Vap", "benzene"]
        )
    return selected


def optimization_summary(
    model: Any,
    termination: str,
    steady_state_dof: int | None,
    optimization_dof: int | None,
    selected_variables: list[str],
) -> dict[str, Any]:
    fs = model.fs
    reactor_benzene = component_value(fs.R101.outlet.flow_mol_phase_comp, 0, "Vap", "benzene") or 0.0
    flash_benzene = component_value(fs.F101.vap_outlet.flow_mol_phase_comp, 0, "Vap", "benzene") or 0.0
    overhead_loss_fraction = flash_benzene / reactor_benzene if reactor_benzene else None
    return {
        "pass": termination == str(TerminationCondition.optimal),
        "stage": "steady_state_optimization",
        "case_family": "hda_flash",
        "official_reference_url": OFFICIAL_REFERENCE_URL,
        "termination_condition": termination,
        "steady_state_dof_before_optimization": steady_state_dof,
        "optimization_degrees_of_freedom": optimization_dof,
        "final_dof": optimization_dof,
        "optimization_plan_variables": selected_variables,
        "objective_total_cost_per_year": component_value(fs.operating_cost + fs.capital_cost),
        "operating_cost_per_year": component_value(fs.operating_cost),
        "capital_cost": None,
        "decision_variables": {
            "H101_outlet_temperature": component_value(fs.H101.outlet.temperature, 0),
            "R101_outlet_temperature": component_value(fs.R101.outlet.temperature, 0),
            "R101_conversion": component_value(fs.R101.conversion),
            "F101_vap_outlet_temperature": component_value(fs.F101.vap_outlet.temperature, 0),
            "F102_vap_outlet_temperature": component_value(fs.F102.vap_outlet.temperature, 0),
            "S101_purge_split_fraction": component_value(fs.S101.split_fraction, 0, "purge"),
        },
        "constraints": {
            "min_f102_vapor_benzene_mole_frac": 0.82,
            "min_f102_vapor_benzene_flow_mol": 0.13,
            "max_f101_overhead_benzene_loss_fraction": 0.45,
        },
        "product": {
            "f102_vapor_benzene_flow_mol": component_value(fs.F102.vap_outlet.flow_mol_phase_comp, 0, "Vap", "benzene"),
            "f102_vapor_toluene_flow_mol": component_value(fs.F102.vap_outlet.flow_mol_phase_comp, 0, "Vap", "toluene"),
            "f102_vapor_benzene_mole_frac": component_value(fs.product_purity),
            "f102_liquid_benzene_flow_mol": component_value(fs.F102.liq_outlet.flow_mol_phase_comp, 0, "Liq", "benzene"),
            "f102_liquid_toluene_flow_mol": component_value(fs.F102.liq_outlet.flow_mol_phase_comp, 0, "Liq", "toluene"),
            "f101_overhead_benzene_loss_fraction": overhead_loss_fraction,
        },
        "error": None,
    }


def run_optimization(tee: bool = False, optimization_plan: Path | None = None) -> dict[str, Any]:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from notebook_build import (  # noqa: PLC0415
            build_model,
            initialize_model,
            set_operating_conditions,
            solve_model,
        )

        model = build_model()
        set_operating_conditions(model)
        initialize_model(model)
        solve_model(model, tee=tee)
        steady_state_dof = degrees_of_freedom(model)
        plan = json.loads(optimization_plan.read_text(encoding="utf-8")) if optimization_plan else {}
        requested_variables = plan.get("variables_to_unfix") if isinstance(plan, dict) else None
        selected_variables = configure_hda_flash_optimization(model, requested_variables)
        optimization_dof = degrees_of_freedom(model)
        results = SolverFactory("ipopt").solve(model, tee=tee)
        termination = str(results.solver.termination_condition)
        summary = optimization_summary(model, termination, steady_state_dof, optimization_dof, selected_variables)
        summary["optimization_plan_file"] = str(optimization_plan) if optimization_plan else None
        return summary
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_optimization",
            "case_family": "hda_flash",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
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
