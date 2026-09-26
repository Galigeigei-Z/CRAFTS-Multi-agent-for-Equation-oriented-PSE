#!/usr/bin/env python3
"""Build and solve the official PrOMMiS superstructure pathway NPV model."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import Objective, SolverFactory, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/superstructure/superstructure_function_documentation.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))


def _build_official_npv_model(*, piecewise_repn: str | None = None) -> Any:
    import pyomo.environ as pyo  # noqa: PLC0415
    from prommis.superstructure.tests import test_superstructure_function as ts  # noqa: PLC0415

    original_piecewise = None
    if piecewise_repn is not None:
        original_piecewise = pyo.Piecewise

        def patched_piecewise(*args: Any, **kwargs: Any) -> Any:
            if kwargs.get("pw_repn") == "SOS2":
                kwargs = dict(kwargs)
                kwargs["pw_repn"] = piecewise_repn
            return original_piecewise(*args, **kwargs)

        pyo.Piecewise = patched_piecewise

    try:
        return ts.build_model(
            obj_func=ts.obj_func,
            plant_start=ts.plant_start,
            plant_lifetime=ts.plant_lifetime,
            available_feed=ts.available_feed,
            collection_rate=ts.collection_rate,
            tracked_comps=ts.tracked_comps,
            prod_comp_mass=ts.prod_comp_mass,
            num_stages=ts.num_stages,
            options_in_stage=ts.options_in_stage,
            option_outlets=ts.option_outlets,
            option_efficiencies=ts.option_efficiencies,
            profit=ts.profit,
            opt_var_oc_params=ts.opt_var_oc_params,
            operators_per_discrete_unit=ts.operators_per_discrete_unit,
            yearly_cost_per_unit=ts.yearly_cost_per_unit,
            capital_cost_per_unit=ts.capital_cost_per_unit,
            processing_rate=ts.processing_rate,
            num_operators=ts.num_operators,
            labor_rate=ts.labor_rate,
            discretized_purchased_equipment_cost=ts.discretized_purchased_equipment_cost,
            consider_environmental_impacts=False,
            options_environmental_impacts=[],
            epsilon=[],
            consider_byproduct_valorization=False,
            byproduct_values=[],
            byproduct_opt_conversions=[],
        )
    finally:
        if original_piecewise is not None:
            pyo.Piecewise = original_piecewise


def _active_objective_value(model: Any) -> float | None:
    objectives = list(model.component_data_objects(Objective, active=True))
    if not objectives:
        return None
    return float(value(objectives[0].expr))


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        model = _build_official_npv_model()
        build_checks = {
            "stages": int(value(model.fs.num_stages)),
            "tracked_components": [str(c) for c in model.fs.tracked_comps],
            "objective_function_choice": str(value(model.fs.objective_function_choice)),
            "has_net_present_value": hasattr(model.fs.costing, "net_present_value"),
            "option_count": len(list(model.fs.all_opts_set)),
        }
        solver_attempts: list[dict[str, Any]] = []
        solved = False
        termination = None
        npv = None
        objective = None
        solver_plan = (
            ("gurobi", None),
            ("appsi_highs", "CC"),
            ("highs", "CC"),
        )
        for solver_name, piecewise_repn in solver_plan:
            try:
                opt = SolverFactory(solver_name)
                if not opt.available(False):
                    solver_attempts.append(
                        {"solver": solver_name, "available": False, "piecewise_repn": piecewise_repn or "SOS2"}
                    )
                    continue
                solve_model = _build_official_npv_model(piecewise_repn=piecewise_repn)
                results = opt.solve(solve_model, tee=False)
                termination = str(results.solver.termination_condition)
                npv = float(value(solve_model.fs.costing.net_present_value))
                objective = _active_objective_value(solve_model)
                solved = termination.lower() == "optimal"
                solver_attempts.append(
                    {
                        "solver": solver_name,
                        "available": True,
                        "piecewise_repn": piecewise_repn or "SOS2",
                        "termination_condition": termination,
                    }
                )
                if solved:
                    break
            except Exception as exc:  # noqa: BLE001
                solver_attempts.append(
                    {
                        "solver": solver_name,
                        "available": True,
                        "piecewise_repn": piecewise_repn or "SOS2",
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:500],
                    }
                )

        build_pass = bool(
            build_checks["stages"] == 3
            and build_checks["has_net_present_value"]
            and build_checks["option_count"] == 6
        )
        return {
            "pass": bool(solved and build_pass),
            "stage": "steady_state_solver" if solved else "official_build_contract",
            "case_family": "prommis_superstructure_pathway_npv",
            "official_reference_url": SOURCE_URL,
            "termination_condition": termination,
            "final_dof": None,
            "build_contract_pass": build_pass,
            "solver_attempts": solver_attempts,
            "net_present_value": npv,
            "objective_value": objective,
            "checks": [
                {"name": "superstructure_official_model_builds", "pass": build_pass, "actual": build_checks},
                {"name": "superstructure_milp_solver_available", "pass": solved, "actual": solver_attempts},
            ],
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "superstructure" / "superstructure_function.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "superstructure" / "tests" / "test_superstructure_function.py"),
                "solver_note": "The official test uses Gurobi with SOS2 piecewise constraints. This runner preserves that path first, then rebuilds with Pyomo CC piecewise linearization for HiGHS when Gurobi is unavailable.",
            },
            "error": None
            if solved
            else {"message": "Official superstructure model built, but no compatible MILP solver solved it in this environment."},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "official_build_contract",
            "case_family": "prommis_superstructure_pathway_npv",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_summary": {"source_root": str(SOURCE_ROOT)},
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main_cli()
