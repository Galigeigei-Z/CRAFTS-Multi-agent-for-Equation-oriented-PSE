#!/usr/bin/env python3
"""Solve and optimize the two-stage pervaporation recycle extension."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "examples" / "pervaporation_two_stage_recycle" / "source_root"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
from runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import SolverFactory, TerminationCondition, value  # noqa: E402
from model import add_optimization, build_model  # noqa: E402


CASE_KEY = "variant_idaes_pervaporation_two_stage_recycle"


def _v(obj: Any) -> float:
    return float(value(obj))


def run(tee: bool = False) -> dict[str, Any]:
    try:
        model = build_model()
        fs = model.fs
        solver = SolverFactory("ipopt")
        solver.options["tol"] = 1e-9
        solver.options["max_iter"] = 1000
        base = solver.solve(model, tee=tee)
        steady_dof = degrees_of_freedom(model)
        if base.solver.termination_condition != TerminationCondition.optimal or steady_dof != 0:
            raise RuntimeError(f"base solve failed: {base.solver.termination_condition}, DoF={steady_dof}")

        add_optimization(model)
        optimization_dof = degrees_of_freedom(model)
        optimized = solver.solve(model, tee=tee)
        if optimized.solver.termination_condition != TerminationCondition.optimal:
            raise RuntimeError(f"optimization failed: {optimized.solver.termination_condition}")
        decisions = {
            "stage1_membrane_area_m2": _v(fs.PV101.area),
            "stage2_membrane_area_m2": _v(fs.PV102.area),
            "stage1_retentate_recycle_fraction": _v(fs.S101.recycle_fraction),
        }
        fs.PV101.area.fix(decisions["stage1_membrane_area_m2"])
        fs.PV102.area.fix(decisions["stage2_membrane_area_m2"])
        fs.S101.recycle_fraction.fix(decisions["stage1_retentate_recycle_fraction"])
        fs.total_area.deactivate()
        final = solver.solve(model, tee=tee)
        final_dof = degrees_of_freedom(model)

        fresh_water = _v(fs.WATER.flow["water"] + fs.GLYCOL.flow["water"])
        fresh_glycol = _v(fs.WATER.flow["ethylene_glycol"] + fs.GLYCOL.flow["ethylene_glycol"])
        stage1_feed = sum(_v(fs.PV101.inlet_flow[c]) for c in ("water", "ethylene_glycol"))
        stage2_feed = sum(_v(fs.PV102.inlet_flow[c]) for c in ("water", "ethylene_glycol"))
        report = {
            "schema_version": "native_optimization_report/1",
            "case_key": CASE_KEY,
            "pass": final.solver.termination_condition == TerminationCondition.optimal and final_dof == 0,
            "stage": "steady_state_optimization_then_fixed_decision_resolve",
            "solver": "IPOPT",
            "termination_condition": str(final.solver.termination_condition),
            "steady_state_dof": steady_dof,
            "optimization_dof": optimization_dof,
            "final_dof": final_dof,
            "objective": "maximize water recovery with glycol-loss and condensation-duty penalties at fixed total membrane area",
            "objective_value": _v(fs.objective.expr),
            "decision_variables": decisions,
            "constraints": {"total_membrane_area_m2": 10.0, "maximum_glycol_loss_fraction": 0.005},
            "metrics": {
                "water_recovery_fraction": _v(fs.PERMEATE.flow["water"]) / fresh_water,
                "glycol_loss_fraction": _v(fs.PERMEATE.flow["ethylene_glycol"]) / fresh_glycol,
                "glycol_recovery_fraction": 1 - _v(fs.PERMEATE.flow["ethylene_glycol"]) / fresh_glycol,
                "stage1_stage_cut": sum(_v(fs.PV101.permeate_flow[c]) for c in ("water", "ethylene_glycol")) / stage1_feed,
                "stage2_stage_cut": sum(_v(fs.PV102.permeate_flow[c]) for c in ("water", "ethylene_glycol")) / stage2_feed,
                "permeate_water_flow_mol_s": _v(fs.PERMEATE.flow["water"]),
                "permeate_glycol_flow_mol_s": _v(fs.PERMEATE.flow["ethylene_glycol"]),
                "retentate_glycol_flow_mol_s": _v(fs.RETENTATE.flow["ethylene_glycol"]),
                "total_condensation_duty_kw": _v(fs.PV101.duty + fs.PV102.duty) / 1000,
            },
            "source_model": "examples/pervaporation_two_stage_recycle/source_root/model.py",
            "source_anchor": "official_idaes_skeleton_pervaporation",
            "chemical_change": "A second membrane stage and retentate recycle couple composition-dependent flux, water recovery, glycol loss, area allocation, and condensation duty.",
            "error": None,
        }
        return report
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "native_optimization_report/1",
            "case_key": CASE_KEY,
            "pass": False,
            "termination_condition": None,
            "final_dof": None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-6000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run(tee=args.tee)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
