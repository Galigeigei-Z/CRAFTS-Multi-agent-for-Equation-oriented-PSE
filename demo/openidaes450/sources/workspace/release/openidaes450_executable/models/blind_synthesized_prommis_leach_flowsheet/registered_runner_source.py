#!/usr/bin/env python3
"""Run official PrOMMiS cocurrent slurry leach flowsheet validation."""

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

from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import ConcreteModel, Expression, check_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.leaching.leach_flowsheet.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))


def scalar(obj: Any) -> float | None:
    try:
        return float(value(obj))
    except Exception:
        return None


def approx(actual: float | None, expected: float, *, rel: float = 1e-5, abs_tol: float = 1e-6) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from prommis.leaching.leach_flowsheet import CocurrentSlurryLeachingFlowsheet  # noqa: PLC0415

        model = ConcreteModel()
        model.fs = CocurrentSlurryLeachingFlowsheet()
        model.fs.scale_model()
        initializer = model.fs.default_initializer()
        initializer.initialize(model.fs)
        results = get_solver("ipopt_v2").solve(model, tee=False)
        optimal = check_optimal_termination(results)
        final_dof = degrees_of_freedom(model)

        @model.Expression(model.fs.coal.component_list)
        def recovery(b, j):
            f_in = b.fs.leach.solid_inlet.flow_mass[0]
            f_out = b.fs.leach.solid_outlet.flow_mass[0]
            x_in = b.fs.leach.solid_inlet.mass_frac_comp[0, j]
            x_out = b.fs.leach.solid_outlet.mass_frac_comp[0, j]
            return (1 - f_out * x_out / (f_in * x_in)) * 100

        outputs = {
            "recovery_sc2o3": scalar(model.recovery["Sc2O3"]),
            "recovery_nd2o3": scalar(model.recovery["Nd2O3"]),
            "recovery_la2o3": scalar(model.recovery["La2O3"]),
            "recovery_gd2o3": scalar(model.recovery["Gd2O3"]),
            "conversion_sc2o3": scalar(model.fs.leach.mscontactor.solid[0, 1].conversion_comp["Sc2O3"]),
            "conversion_nd2o3": scalar(model.fs.leach.mscontactor.solid[0, 1].conversion_comp["Nd2O3"]),
            "conversion_cao": scalar(model.fs.leach.mscontactor.solid[0, 1].conversion_comp["CaO"]),
        }
        init_status = str(initializer.summary.get(model.fs, {}).get("status", "unknown"))
        checks = [
            {"name": "leach_flowsheet_initializer_ok", "pass": "Ok" in init_status, "actual": init_status},
            {"name": "leach_flowsheet_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "leach_flowsheet_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "leach_flowsheet_recovery_sc2o3_matches_official_test", "pass": approx(outputs["recovery_sc2o3"], 5.486783341761903), "actual": outputs["recovery_sc2o3"]},
            {"name": "leach_flowsheet_recovery_nd2o3_matches_official_test", "pass": approx(outputs["recovery_nd2o3"], 45.79540997369025), "actual": outputs["recovery_nd2o3"]},
            {"name": "leach_flowsheet_recovery_la2o3_matches_official_test", "pass": approx(outputs["recovery_la2o3"], 38.342494088335066), "actual": outputs["recovery_la2o3"]},
            {"name": "leach_flowsheet_conversion_cao_matches_official_test", "pass": approx(outputs["conversion_cao"], 0.5145052459223426), "actual": outputs["conversion_cao"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_leach_flowsheet",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "leaching" / "leach_flowsheet.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "leaching" / "tests" / "test_leach_flowsheet.py"),
                "official_module": "prommis.leaching.leach_flowsheet",
            },
            "error": None if passed else {"message": "PrOMMiS leach flowsheet checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_leach_flowsheet",
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
