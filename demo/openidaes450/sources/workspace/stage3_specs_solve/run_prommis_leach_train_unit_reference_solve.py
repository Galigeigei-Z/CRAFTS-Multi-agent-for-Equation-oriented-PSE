#!/usr/bin/env python3
"""Run official PrOMMiS leach-train unit validation."""

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

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import SolverFactory, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.leaching.leach_train.html"
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


def _recovery(model: Any, component: str) -> float | None:
    try:
        f_in = model.fs.leach.solid_inlet.flow_mass[0]
        f_out = model.fs.leach.solid_outlet.flow_mass[0]
        x_in = model.fs.leach.solid_inlet.mass_frac_comp[0, component]
        x_out = model.fs.leach.solid_outlet.mass_frac_comp[0, component]
        return float(value(1 - f_out * x_out / (f_in * x_in)) * 100)
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from pyomo.environ import assert_optimal_termination  # noqa: PLC0415
        from prommis.leaching.tests import test_leach_train as official_test  # noqa: PLC0415

        model = official_test.model_lb.__wrapped__()
        initializer = model.fs.leach.default_initializer()
        initializer.initialize(model.fs.leach)
        results = SolverFactory("ipopt_v2").solve(model, tee=False)
        assert_optimal_termination(results)

        final_dof = degrees_of_freedom(model)
        la_recovery = _recovery(model, "La2O3")
        ce_recovery = _recovery(model, "Ce2O3")
        nd_recovery = _recovery(model, "Nd2O3")
        liquid_flow = scalar(model.fs.leach.liquid_outlet.flow_vol[0])
        solid_flow = scalar(model.fs.leach.solid_outlet.flow_mass[0])
        passed = bool(
            final_dof == 0
            and la_recovery is not None and abs(la_recovery - 31.26929380118505) < 1e-4
            and ce_recovery is not None and ce_recovery > 0
            and nd_recovery is not None and nd_recovery > 0
            and liquid_flow is not None and liquid_flow > 0
            and solid_flow is not None and solid_flow > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_leach_train_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "checks": [
                {"name": "leach_train_dof_zero", "pass": final_dof == 0, "actual": final_dof},
                {"name": "leach_train_la_recovery_matches_official_test", "pass": bool(la_recovery is not None and abs(la_recovery - 31.26929380118505) < 1e-4), "actual": la_recovery},
                {"name": "leach_train_ce_recovery_positive", "pass": bool(ce_recovery is not None and ce_recovery > 0), "actual": ce_recovery},
                {"name": "leach_train_nd_recovery_positive", "pass": bool(nd_recovery is not None and nd_recovery > 0), "actual": nd_recovery},
                {"name": "leach_train_outlet_flows_positive", "pass": bool(liquid_flow is not None and liquid_flow > 0 and solid_flow is not None and solid_flow > 0), "actual": [liquid_flow, solid_flow]},
            ],
            "la_recovery_percent": la_recovery,
            "ce_recovery_percent": ce_recovery,
            "nd_recovery_percent": nd_recovery,
            "liquid_outlet_flow": liquid_flow,
            "solid_outlet_flow": solid_flow,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "leaching" / "leach_train.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "leaching" / "tests" / "test_leach_train.py"),
            },
            "error": None if passed else {"message": "PrOMMiS leach train checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_leach_train_unit",
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
