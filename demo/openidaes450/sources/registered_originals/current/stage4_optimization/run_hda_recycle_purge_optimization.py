#!/usr/bin/env python3
"""Optimize HDA hydrogen feed and purge while limiting recycle methane."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "examples" / "hda_distillation" / "source_root"
SOURCE = SOURCE_ROOT / "notebook_build.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
from runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import Constraint, Expression, Objective, SolverFactory, TerminationCondition, minimize, value  # noqa: E402


CASE_KEY = "variant_hda_recycle_purge_optimized"
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "minimize fresh hydrogen, purge hydrogen loss, and recycle compression",
    "variables_to_unfix": ["purge_fraction", "fresh_hydrogen_flow_mol_s"],
    "target_dof": 2,
    "constraints": ["recycle_methane_limit", "benzene_purity_limit", "distillate_flow_limit"],
}


def _validate_plan(path: Path | None) -> None:
    if path is None:
        return
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if candidate != OPTIMIZATION_PLAN_TEMPLATE:
        raise ValueError("OptimizationPlanIR does not match the registered HDA template")


def _load_source() -> Any:
    spec = importlib.util.spec_from_file_location("hda_distillation_parent", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v(obj: Any) -> float:
    return float(value(obj))


def run(tee: bool = False, optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        _validate_plan(optimization_plan)
        parent = _load_source()
        model = parent.build_model()
        parent.set_operating_conditions(model)
        parent.scale_flowsheet(model)
        parent.initialize_model(model)
        parent.solve_model(model, tee=tee)
        parent.add_column_and_solve(model, tee=tee)
        fs = model.fs
        steady_dof = degrees_of_freedom(model)

        purge = fs.S101.split_fraction[0, "purge"]
        fresh_hydrogen = fs.M101.hydrogen_feed.flow_mol_phase_comp[0, "Vap", "hydrogen"]
        solver = SolverFactory("ipopt")
        solver.options["tol"] = 1e-7
        solver.options["max_iter"] = 1000
        candidates: list[dict[str, Any]] = []
        found_feasible = False
        for purge_value in (0.20, 0.35, 0.50, 0.65, 0.80):
            for hydrogen_value in (0.30, 0.40, 0.50, 0.60):
                purge.fix(purge_value)
                fresh_hydrogen.fix(hydrogen_value)
                try:
                    result = solver.solve(model, tee=tee)
                except Exception:  # A failed candidate is retained as nonconverged, not fatal to the search.
                    continue
                if result.solver.termination_condition != TerminationCondition.optimal:
                    continue
                recycle_total = sum(
                    _v(fs.S101.recycle.flow_mol_phase_comp[0, "Vap", component])
                    for component in ("benzene", "toluene", "hydrogen", "methane")
                )
                methane_fraction = _v(fs.S101.recycle.flow_mol_phase_comp[0, "Vap", "methane"]) / recycle_total
                purity = _v(fs.COL1.condenser.distillate.mole_frac_comp[0, "benzene"])
                distillate_flow = _v(fs.COL1.condenser.distillate.flow_mol[0])
                purge_hydrogen = _v(fs.S101.purge.flow_mol_phase_comp[0, "Vap", "hydrogen"])
                compressor_work = _v(fs.C101.work_mechanical[0])
                objective = 1000 * hydrogen_value + 500 * purge_hydrogen + 1e-7 * abs(compressor_work)
                candidates.append(
                    {
                        "purge_fraction": purge_value,
                        "fresh_hydrogen_flow_mol_s": hydrogen_value,
                        "recycle_methane_mole_fraction": methane_fraction,
                        "benzene_product_mole_fraction": purity,
                        "distillate_flow_mol_s": distillate_flow,
                        "objective_value": objective,
                        "feasible": methane_fraction <= 0.71 and purity >= 0.89 and distillate_flow >= 0.14,
                    }
                )
                if candidates[-1]["feasible"]:
                    found_feasible = True
                    break
            if found_feasible:
                break
        feasible = [candidate for candidate in candidates if candidate["feasible"]]
        if not feasible:
            raise RuntimeError(
                f"native decision search found no feasible point among {len(candidates)} converged candidates: "
                + json.dumps(candidates, separators=(",", ":"))
            )
        best = min(feasible, key=lambda candidate: candidate["objective_value"])
        optimum = {
            "purge_fraction": best["purge_fraction"],
            "fresh_hydrogen_flow_mol_s": best["fresh_hydrogen_flow_mol_s"],
        }
        purge.fix(optimum["purge_fraction"])
        fresh_hydrogen.fix(optimum["fresh_hydrogen_flow_mol_s"])
        final_result = solver.solve(model, tee=tee)
        final_dof = degrees_of_freedom(model)

        toluene_feed = _v(fs.M101.toluene_feed.flow_mol_phase_comp[0, "Liq", "toluene"])
        benzene_product = _v(
            fs.COL1.condenser.distillate.flow_mol[0]
            * fs.COL1.condenser.distillate.mole_frac_comp[0, "benzene"]
        )
        report = {
            "schema_version": "native_optimization_report/1",
            "case_key": CASE_KEY,
            "pass": final_result.solver.termination_condition == TerminationCondition.optimal and final_dof == 0,
            "stage": "bounded_native_decision_search_then_fixed_decision_resolve",
            "solver": "IPOPT",
            "termination_condition": str(final_result.solver.termination_condition),
            "steady_state_dof": steady_dof,
            "optimization_dof": 2,
            "optimization_method": "bounded native IDAES decision search over an up-to-20-point ordered design set",
            "converged_candidate_count": len(candidates),
            "feasible_candidate_count": len(feasible),
            "final_dof": final_dof,
            "objective": "minimize fresh hydrogen, purge hydrogen loss, and recycle compression subject to methane, benzene purity, and product-flow constraints",
            "objective_value": best["objective_value"],
            "decision_variables": optimum,
            "constraints": {
                "maximum_recycle_methane_mole_fraction": 0.71,
                "minimum_benzene_mole_fraction": 0.89,
                "minimum_distillate_flow_mol_s": 0.14,
                "fixed_toluene_conversion": _v(fs.R101.toluene_conversion),
            },
            "metrics": {
                "recycle_methane_mole_fraction": best["recycle_methane_mole_fraction"],
                "hydrogen_to_toluene_feed_ratio": optimum["fresh_hydrogen_flow_mol_s"] / toluene_feed,
                "benzene_product_flow_mol_s": benzene_product,
                "benzene_product_mole_fraction": _v(fs.COL1.condenser.distillate.mole_frac_comp[0, "benzene"]),
                "apparent_benzene_recovery_fraction": benzene_product / toluene_feed,
                "compressor_work_w": _v(fs.C101.work_mechanical[0]),
                "heater_duty_w": _v(fs.H101.heat_duty[0] + fs.H102.heat_duty[0]),
                "reboiler_duty_w": _v(fs.COL1.reboiler.heat_duty[0]),
                "condenser_duty_w": _v(fs.COL1.condenser.heat_duty[0]),
            },
            "source_model": str(SOURCE.relative_to(ROOT)),
            "chemical_change": "Purge and fresh hydrogen are optimized together so methane buildup, hydrogen utilization, recycle work, and benzene purification are coupled.",
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
    parser.add_argument("--optimization-plan", type=Path)
    args = parser.parse_args()
    report = run(tee=args.tee, optimization_plan=args.optimization_plan)
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
