#!/usr/bin/env python3
"""Run official PrOMMiS multicomponent ion-exchange validation."""

from __future__ import annotations

import argparse
import contextlib
import io
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
from pyomo.environ import value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.ion_exchange.ix_freundlich_multicomponent_example.html"
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


def run_case() -> dict[str, Any]:
    stdout = io.StringIO()
    try:
        _prepare_imports()
        from pyomo.environ import assert_optimal_termination  # noqa: PLC0415
        from idaes.core.solvers import get_solver  # noqa: PLC0415
        from prommis.ion_exchange.tests import test_ion_exchange_multicomponent as official_test  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            model = official_test.create_model(regenerant="single_use", hazardous_waste=False)
            solver = get_solver(solver="ipopt_v2")
            init_results = solver.solve(model, tee=False)
            assert_optimal_termination(init_results)
            official_test.build_clark_with_costing(model, regenerant="single_use", target_component="La")
            costing_results = solver.solve(model, tee=False)
            assert_optimal_termination(costing_results)
            official_test.run_optimization(model, target_component="La")
            results = solver.solve(model, tee=False)
            assert_optimal_termination(results)

        ix = model.fs.unit_ix
        final_dof = degrees_of_freedom(model)
        bed_depth = scalar(ix.bed_depth)
        bed_diameter = scalar(ix.bed_diameter)
        target_breakthrough_time = scalar(ix.target_breakthrough_time)
        total_capital_cost = scalar(model.fs.costing.total_capital_cost)
        fixed_operating_cost = scalar(ix.costing.fixed_operating_cost)
        stream_values = port_stream_values(model.fs, max_streams=100)
        passed = bool(
            final_dof is not None
            and bed_depth is not None and abs(bed_depth - 2.249999764670581) < 1e-4
            and bed_diameter is not None and bed_diameter > 0
            and target_breakthrough_time is not None and target_breakthrough_time > 0
            and total_capital_cost is not None and total_capital_cost > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_ion_exchange_multicomponent",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "checks": [
                {"name": "ix_multicomponent_design_dof_recorded", "pass": final_dof is not None, "actual": final_dof},
                {"name": "ix_multicomponent_bed_depth_matches_official_test", "pass": bool(bed_depth is not None and abs(bed_depth - 2.249999764670581) < 1e-4), "actual": bed_depth},
                {"name": "ix_multicomponent_bed_diameter_positive", "pass": bool(bed_diameter is not None and bed_diameter > 0), "actual": bed_diameter},
                {"name": "ix_multicomponent_breakthrough_time_positive", "pass": bool(target_breakthrough_time is not None and target_breakthrough_time > 0), "actual": target_breakthrough_time},
                {"name": "ix_multicomponent_capital_cost_positive", "pass": bool(total_capital_cost is not None and total_capital_cost > 0), "actual": total_capital_cost},
            ],
            "bed_depth_m": bed_depth,
            "bed_diameter_m": bed_diameter,
            "target_breakthrough_time_s": target_breakthrough_time,
            "total_capital_cost": total_capital_cost,
            "fixed_operating_cost": fixed_operating_cost,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "ion_exchange" / "ix_freundlich_multicomponent_example.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "ion_exchange" / "tests" / "test_ion_exchange_multicomponent.py"),
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS multicomponent ion-exchange checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_ion_exchange_multicomponent",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_summary": {"source_root": str(SOURCE_ROOT), "stdout_tail": stdout.getvalue()[-4000:]},
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
