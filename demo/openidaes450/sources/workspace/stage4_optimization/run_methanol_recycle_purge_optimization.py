#!/usr/bin/env python3
"""Optimize methanol-loop purge against methane buildup and recycle work."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/"
    "langgraph_idaes_pipeline"
)
SOURCE_RELATIVE = Path("examples/methanol_recycle/source_root/notebook_build.py")
SOURCE = LEGACY_ARTIFACT_ROOT / SOURCE_RELATIVE
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import (  # noqa: E402
    Constraint,
    Expression,
    Objective,
    SolverFactory,
    TerminationCondition,
    maximize,
    value,
)


CASE_KEY = "variant_methanol_recycle_purge_optimized"
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "maximize liquid methanol value minus recycle-compressor penalty",
    "variables_to_unfix": ["purge_fraction"],
    "target_dof": 1,
    "constraints": ["recycle_methane_limit"],
}


def _validate_plan(path: Path | None) -> None:
    if path is None:
        return
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if candidate != OPTIMIZATION_PLAN_TEMPLATE:
        raise ValueError("OptimizationPlanIR does not match the registered methanol template")


def _load_source() -> Any:
    spec = importlib.util.spec_from_file_location("methanol_recycle_parent", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v(obj: Any) -> float:
    return float(value(obj))


def _set_inert_feed(fs: Any) -> None:
    compositions = {
        fs.H2: {"H2": 0.979998, "CO": 1e-6, "CH3OH": 1e-6, "CH4": 0.02},
        fs.CO: {"H2": 1e-6, "CO": 0.949998, "CH3OH": 1e-6, "CH4": 0.05},
    }
    for feed, composition in compositions.items():
        for component, fraction in composition.items():
            feed.outlet.mole_frac_comp[0, component].fix(fraction)


def run(tee: bool = False, optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        _validate_plan(optimization_plan)
        parent = _load_source()
        model = parent.build_model()
        parent.set_operating_conditions(model)
        fs = model.fs
        parent.initialize_model(model)
        parent.solve_model(model, tee=tee)
        target_compositions = {
            fs.H2: {"H2": 0.989998, "CO": 1e-6, "CH3OH": 1e-6, "CH4": 0.01},
            fs.CO: {"H2": 1e-6, "CO": 0.979998, "CH3OH": 1e-6, "CH4": 0.02},
        }
        original_compositions = {
            feed: {component: _v(feed.outlet.mole_frac_comp[0, component]) for component in composition}
            for feed, composition in target_compositions.items()
        }
        continuation_solver = SolverFactory("ipopt")
        continuation_solver.options["tol"] = 1e-7
        continuation_solver.options["max_iter"] = 1000
        for alpha in (0.25, 0.50, 0.75, 1.0):
            for feed, composition in target_compositions.items():
                for component, target in composition.items():
                    start = original_compositions[feed][component]
                    feed.outlet.mole_frac_comp[0, component].fix(start + alpha * (target - start))
            fs.S101.split_fraction[0, "purge"].fix(0.9999 + alpha * (0.20 - 0.9999))
            continuation = continuation_solver.solve(model, tee=tee)
            if continuation.solver.termination_condition != TerminationCondition.optimal:
                raise RuntimeError(f"inert-feed continuation failed at alpha={alpha}: {continuation.solver.termination_condition}")
        steady_dof = degrees_of_freedom(model)

        fs.S101.split_fraction[0, "purge"].unfix()
        fs.S101.split_fraction[0, "purge"].setlb(0.02)
        fs.S101.split_fraction[0, "purge"].setub(0.95)
        fs.recycle_methane_limit = Constraint(
            expr=fs.S101.recycle.mole_frac_comp[0, "CH4"] <= 0.15
        )
        fs.methanol_product_rate = Expression(
            expr=fs.CH3OH.inlet.flow_mol[0] * fs.CH3OH.inlet.mole_frac_comp[0, "CH3OH"]
        )
        fs.purge_value_objective = Objective(
            expr=fs.methanol_product_rate - 1e-7 * fs.C101.work_mechanical[0],
            sense=maximize,
        )
        optimization_dof = degrees_of_freedom(model)
        solver = SolverFactory("ipopt")
        solver.options["tol"] = 1e-7
        solver.options["max_iter"] = 1000
        result = solver.solve(model, tee=tee)
        termination = str(result.solver.termination_condition)
        if result.solver.termination_condition != TerminationCondition.optimal:
            raise RuntimeError(f"optimization terminated with {termination}")

        optimum_purge = _v(fs.S101.split_fraction[0, "purge"])
        fs.S101.split_fraction[0, "purge"].fix(optimum_purge)
        final_result = solver.solve(model, tee=tee)
        final_dof = degrees_of_freedom(model)

        fresh_co = _v(fs.CO.outlet.flow_mol[0] * fs.CO.outlet.mole_frac_comp[0, "CO"])
        product_methanol = _v(fs.methanol_product_rate)
        purge_methanol = _v(fs.S101.purge.flow_mol[0] * fs.S101.purge.mole_frac_comp[0, "CH3OH"])
        report = {
            "schema_version": "native_optimization_report/1",
            "case_key": CASE_KEY,
            "pass": final_result.solver.termination_condition == TerminationCondition.optimal and final_dof == 0,
            "stage": "steady_state_optimization_then_fixed_decision_resolve",
            "solver": "IPOPT",
            "termination_condition": str(final_result.solver.termination_condition),
            "steady_state_dof": steady_dof,
            "optimization_dof": optimization_dof,
            "final_dof": final_dof,
            "objective": "maximize liquid methanol production minus recycle-compressor penalty subject to recycle methane <= 0.15",
            "objective_value": _v(fs.purge_value_objective.expr),
            "decision_variables": {"purge_fraction": optimum_purge},
            "constraints": {"maximum_recycle_methane_mole_fraction": 0.15},
            "metrics": {
                "recycle_methane_mole_fraction": _v(fs.S101.recycle.mole_frac_comp[0, "CH4"]),
                "reactor_co_conversion": _v(fs.R101.co_conversion),
                "fresh_co_flow_mol_s": fresh_co,
                "methanol_product_flow_mol_s": product_methanol,
                "purge_methanol_flow_mol_s": purge_methanol,
                "apparent_fresh_co_to_liquid_methanol_fraction": product_methanol / fresh_co,
                "compressor_work_w": _v(fs.C101.work_mechanical[0]),
                "recycle_flow_mol_s": _v(fs.S101.recycle.flow_mol[0]),
            },
            "source_binding": {
                "kind": "explicit_legacy_artifact_root",
                "legacy_artifact_root": str(LEGACY_ARTIFACT_ROOT),
                "relative_path": str(SOURCE_RELATIVE),
            },
            "chemical_change": "Explicit methane impurities make purge selection a reactant-loss versus inert-accumulation and compression tradeoff.",
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
