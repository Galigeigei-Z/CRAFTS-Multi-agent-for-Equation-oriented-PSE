"""Execute a fresh candidate-bound NC v5 native optimization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback
from typing import Any

from orchestrator.nc_v5.state import canonical_json_sha256
from stage3_specs_solve.nc_v5.generic_conservation import solve_generic_candidate_conservation


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(
    topology_path: Path,
    spec_path: Path,
    build_plan_path: Path,
    solve_report_path: Path,
    optimization_plan_path: Path,
    adapter_contract_path: Path,
) -> dict[str, Any]:
    topology = _read(topology_path)
    spec = _read(spec_path)
    build_plan = _read(build_plan_path)
    solve_report = _read(solve_report_path)
    plan = _read(optimization_plan_path)
    adapter = _read(adapter_contract_path)
    if adapter.get("adapter") != "generic_che_conservation_v1":
        raise ValueError("the full-450 native optimizer requires the generic conservation adapter")
    if solve_report.get("pass") is not True:
        raise ValueError("native optimization requires a passing fresh native solve")
    binding = solve_report.get("candidate_binding")
    binding = binding if isinstance(binding, dict) else {}
    if binding.get("topology_sha256") != canonical_json_sha256(topology):
        raise ValueError("native solve is not bound to the promoted topology")
    if binding.get("spec_sha256") != canonical_json_sha256(spec):
        raise ValueError("native solve is not bound to the promoted specification")
    selected = plan.get("variables_to_unfix")
    target_dof = plan.get("target_dof")
    if not isinstance(selected, list) or not isinstance(target_dof, int):
        raise ValueError("invalid OptimizationPlanIR variable or DoF contract")
    if target_dof != len(selected):
        raise ValueError("OptimizationPlanIR target DoF differs from selected variables")
    stable = solve_generic_candidate_conservation(
        topology, spec, build_plan, optimize=True, optimization_plan=plan
    )
    passed = (
        stable.get("pass") is True
        and stable.get("optimization_requested") is True
        and stable.get("optimization_degrees_of_freedom") == target_dof
        and str(stable.get("termination_condition") or "").casefold() == "optimal"
    )
    return {
        "schema_version": "native-optimization-report/v5",
        "pass": passed,
        "execution_protocol": "manuscript-full-workflow/v5",
        "optimization_plan_sha256": canonical_json_sha256(plan),
        "source_native_solve_sha256": canonical_json_sha256(solve_report),
        "candidate_topology_sha256": canonical_json_sha256(topology),
        "candidate_spec_sha256": canonical_json_sha256(spec),
        "optimization_degrees_of_freedom": target_dof,
        "termination_condition": stable.get("termination_condition"),
        "objective": stable.get("objective"),
        "objective_value": stable.get("objective_value"),
        "decision_variables": stable.get("decision_variables"),
        "candidate_binding": stable.get("candidate_binding"),
        "stable_native_optimization_report": stable,
        "error": None if passed else "candidate-bound native optimization checks failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "topology-ir", "spec-ir", "build-plan", "solve-report",
        "optimization-plan", "adapter-contract", "report",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(
            args.topology_ir.resolve(), args.spec_ir.resolve(), args.build_plan.resolve(),
            args.solve_report.resolve(), args.optimization_plan.resolve(),
            args.adapter_contract.resolve(),
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "native-optimization-report/v5",
            "pass": False,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }
    _write(args.report.resolve(), report)
    print(json.dumps({"passed": report.get("pass") is True, "report": str(args.report)}))
    return 0 if report.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
