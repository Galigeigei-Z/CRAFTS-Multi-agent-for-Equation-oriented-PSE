"""Audit the exact NC v5 native runtime import and solver surface."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from stage3_specs_solve.nc_v5.runner_registry import resolve_runner


ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    "compiler.nc_v5.topology_to_buildplan",
    "compiler.nc_v5.spec_binding",
    "stage2_topology.idaes_prebuilder",
    "stage3_specs_solve.che_executable_contract",
    "stage3_specs_solve.spec_ir_builder",
    "stage3_specs_solve.nc_v5.native_runner",
    "stage3_specs_solve.nc_v5.generic_conservation",
    "highspy",
    "sandbox_solver.solve_build_plan",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_preflight() -> dict[str, Any]:
    errors: list[str] = []
    imported = []
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            path = Path(str(module.__file__ or "")).resolve()
            imported.append({"module": name, "path": str(path), "sha256": _sha(path) if path.is_file() else None})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    ledger = []
    forbidden = []
    for name, module in sorted(sys.modules.items()):
        text = str(getattr(module, "__file__", "") or "")
        if not text:
            continue
        path = Path(text).resolve()
        row = {"module": name, "path": str(path), "sha256": _sha(path) if path.is_file() else None}
        ledger.append(row)
        lowered = str(path).lower()
        if "2026-05-31/langgraph_idaes_pipeline" in lowered or "evaluator_gold" in lowered:
            forbidden.append(row)
    runner = resolve_runner("native_candidate_runner_v5")
    ipopt = shutil.which("ipopt")
    try:
        from pyomo.environ import SolverFactory  # noqa: PLC0415

        highs_available = bool(
            SolverFactory("appsi_highs").available(exception_flag=False)
        )
    except Exception as exc:  # noqa: BLE001
        highs_available = False
        errors.append(f"appsi_highs: {type(exc).__name__}: {exc}")
    checks = {
        "all_registered_modules_imported": not errors,
        "runner_contract_v5": runner.contract_version == "native-candidate-runner/v5",
        "runtime_python_exact": Path(sys.executable).absolute().is_file(),
        "ipopt_executable_available": bool(ipopt),
        "highs_python_solver_available": highs_available,
        "legacy_runtime_imports_absent": not forbidden,
        "evaluator_imports_absent": not any(row["module"].startswith("experiment.standardized_workflow.artifacts") for row in ledger),
    }
    return {
        "schema_version": "nc-v5-environment-preflight/1",
        "runtime_python": str(Path(sys.executable).absolute()),
        "runner": {"runner_id": runner.runner_id, "entrypoint": runner.entrypoint, "contract_version": runner.contract_version},
        "required_imports": imported,
        "loaded_module_ledger": ledger,
        "solver_executables": {
            "ipopt": ipopt,
            "appsi_highs_available": highs_available,
        },
        "forbidden_imports": forbidden,
        "errors": errors,
        "checks": checks,
        "passed": all(checks.values()),
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_preflight()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "failed_checks": report["failed_checks"], "module_count": len(report["loaded_module_ledger"])}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
