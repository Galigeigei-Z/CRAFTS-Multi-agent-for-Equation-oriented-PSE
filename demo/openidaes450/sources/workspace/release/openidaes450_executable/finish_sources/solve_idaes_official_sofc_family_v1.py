#!/usr/bin/env python3
"""Run and record native solves for the pinned official IDAES SOFC family."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
COMMIT = "b9606eeddf24ddcb24b27eabe84a911d148abc93"
SOURCE_ROOT = ROOT / ".external_sources" / "idaes_examples_power_generation" / COMMIT
REGISTRY_PATH = ROOT / "experiment" / "case_registry" / "registry.json"

CASES = {
    "official_idaes_sofc_power_plant": {
        "source_dir": "sofc",
        "module": "sofc",
        "checkpoint": "sofc_init.json.gz",
        "model_root": "fs",
        "mode": "checkpoint_feasibility",
        "metrics": ("gross_power", "net_power", "HHV_efficiency", "CO2_emissions"),
    },
    "official_idaes_sofc_soec_coproduction": {
        "source_dir": "sofc_soec",
        "module": "sofc_with_soec",
        "checkpoint": "sofc_soec_init.json.gz",
        "model_root": "fs",
        "mode": "checkpoint_feasibility",
        "metrics": ("gross_power", "net_power", "hydrogen_product_rate", "soec_load"),
    },
    "official_idaes_rsofc_soec_mode": {
        "source_dir": "rsofc",
        "module": "rsofc_soec_flowsheet",
        "checkpoint": "rsofc_soec_surrogate_init.json.gz",
        "model_root": "soec_fs",
        "mode": "official_base_case_simulation",
        "metrics": ("net_power", "hydrogen_product_rate", "h2_product_rate_mass", "CO2_capture_efficiency"),
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scalar_value(component: Any, pyo: Any) -> float | None:
    candidates = []
    try:
        candidates.append(component[0])
    except (KeyError, TypeError):
        pass
    candidates.append(component)
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return float(pyo.value(candidate))
        except (TypeError, ValueError):
            continue
    return None


def maximum_constraint_violation(model: Any, pyo: Any) -> float:
    maximum = 0.0
    for constraint in model.component_data_objects(pyo.Constraint, active=True, descend_into=True):
        try:
            body = float(pyo.value(constraint.body))
            if constraint.equality:
                violation = abs(body - float(pyo.value(constraint.lower)))
            else:
                violation = 0.0
                if constraint.has_lb():
                    violation = max(violation, float(pyo.value(constraint.lower)) - body)
                if constraint.has_ub():
                    violation = max(violation, body - float(pyo.value(constraint.upper)))
            maximum = max(maximum, violation)
        except (TypeError, ValueError):
            continue
    return maximum


def solve_case(case_key: str) -> dict[str, Any]:
    config = CASES[case_key]
    source_dir = SOURCE_ROOT / config["source_dir"]
    os.chdir(source_dir)
    sys.path.insert(0, str(source_dir))

    import importlib
    import idaes
    from idaes.core.util import model_serializer as ms
    from idaes.core.util.model_statistics import (
        degrees_of_freedom,
        number_total_constraints,
        number_variables,
    )
    import pyomo
    import pyomo.environ as pyo

    started = time.time()
    source = importlib.import_module(config["module"])
    if case_key == "official_idaes_rsofc_soec_mode":
        model = pyo.ConcreteModel()
        model, _solver = source.get_model(model)
        flowsheet = model.soec_fs
        flowsheet.hydrogen_product_rate.fix(2500)
        flowsheet.aux_boiler_feed_pump.inlet.flow_mol.unfix()
        linear_solver = "ma27"
    else:
        model = source.get_model()
        ms.from_json(model, fname=str(source_dir / config["checkpoint"]))
        flowsheet = model.fs
        linear_solver = "mumps"

    initial_dof = degrees_of_freedom(model)
    solver_options = {
        "nlp_scaling_method": "user-scaling",
        "linear_solver": linear_solver,
        "tol": 1e-7,
        "max_iter": 500,
        "bound_push": 1e-12,
    }
    result = pyo.SolverFactory("ipopt").solve(
        flowsheet,
        tee=False,
        options=solver_options,
        symbolic_solver_labels=case_key == "official_idaes_rsofc_soec_mode",
    )
    termination = str(result.solver.termination_condition)
    final_dof = degrees_of_freedom(model)
    max_violation = maximum_constraint_violation(flowsheet, pyo)
    passed = termination == "optimal" and final_dof == 0 and max_violation <= 1e-5
    metrics = {}
    for name in config["metrics"]:
        component = getattr(flowsheet, name, None)
        if component is not None:
            value = scalar_value(component, pyo)
            if value is not None:
                metrics[name] = value
    return {
        "pass": passed,
        "case_key": case_key,
        "stage": "native_official_checkpoint_solve",
        "execution_mode": config["mode"],
        "source_commit": COMMIT,
        "source_file": str((source_dir / f"{config['module']}.py").relative_to(ROOT)),
        "checkpoint_file": str((source_dir / config["checkpoint"]).relative_to(ROOT)),
        "environment": {
            "idaes_version": idaes.__version__,
            "pyomo_version": pyomo.__version__,
            "solver": "ipopt",
            "linear_solver": linear_solver,
            "solver_options": solver_options,
        },
        "solver_status": str(result.solver.status),
        "termination_condition": termination,
        "initial_dof": initial_dof,
        "final_dof": final_dof,
        "variable_count": number_variables(model),
        "constraint_count": number_total_constraints(model),
        "maximum_unscaled_constraint_violation": max_violation,
        "solver_time_seconds": float(getattr(result.solver, "time", 0.0) or 0.0),
        "wall_time_seconds": time.time() - started,
        "metrics": metrics,
        "checks": [
            {"name": "ipopt_optimal_termination", "pass": termination == "optimal"},
            {"name": "final_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {
                "name": "maximum_constraint_violation_le_1e-5",
                "pass": max_violation <= 1e-5,
                "actual": max_violation,
            },
        ],
        "generated_at": utc_now(),
        "claim_boundary": (
            "Native current-environment checkpoint reconstruction and Ipopt solve."
            if passed
            else "Native execution attempted but did not satisfy the solved acceptance gate."
        ),
    }


def write_report_and_update_registry(case_key: str, report: dict[str, Any]) -> Path:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    record = next(record for record in registry["cases"] if record["case_key"] == case_key)
    selection = record["selection"]
    report_path = ROOT / selection["selected_validation_dir"] / "native_solve_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    selection["solve_report_file"] = str(report_path.relative_to(ROOT))
    if report["pass"]:
        selection.update(
            {
                "status": "solved",
                "selected_status": "solved",
                "execution_status": "native_solve_complete",
                "evidence_maturity": "official_source_native_solved",
                "claim_boundary": "Official pinned code and PFD with a current-environment DOF-zero optimal native solve.",
            }
        )
        if "solved" not in record["tags"]:
            record["tags"].append("solved")
    else:
        selection.update(
            {
                "status": "source_verified",
                "selected_status": "source_verified",
                "execution_status": "native_solve_failed",
                "evidence_maturity": "official_code_pfd_and_native_failure_diagnostic",
                "claim_boundary": "Official code and PFD topology verified; native solve attempted but not converged.",
            }
        )
    meta_path = report_path.parent / "source_verified_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(
        {
            "status": selection["status"],
            "execution_status": selection["execution_status"],
            "evidence_maturity": selection["evidence_maturity"],
            "claim_boundary": selection["claim_boundary"],
            "solve_report_file": str(report_path.relative_to(ROOT)),
            "updated_at": utc_now(),
        }
    )
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    registry["updated_at"] = utc_now()
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), required=True)
    args = parser.parse_args()
    report = solve_case(args.case)
    report_path = write_report_and_update_registry(args.case, report)
    print(json.dumps({"case_key": args.case, "pass": report["pass"], "report": str(report_path)}, indent=2))
    if not report["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
