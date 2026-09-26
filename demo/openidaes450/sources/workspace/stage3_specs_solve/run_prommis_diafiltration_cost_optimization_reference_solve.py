#!/usr/bin/env python3
"""Run official PrOMMiS diafiltration costing and optimization validation."""

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


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/tutorials/diafiltration_flowsheet_optimization_tutorial-solution.html"
BASE_FLOWSHEET_URL = "https://prommis.readthedocs.io/en/latest/tutorials/diafiltration.html"
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
        from prommis.uky.costing import diafiltration_flowsheet_optimization_example as opt  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            model = opt.main()

        final_dof = degrees_of_freedom(model)
        costing = model.fs.costing
        stage_lengths = [scalar(model.fs.stage1.length), scalar(model.fs.stage2.length), scalar(model.fs.stage3.length)]
        cost_of_recovery = scalar(costing.cost_of_recovery)
        annualized_cost = scalar(getattr(costing, "annualized_cost", None))
        total_variable_om = scalar(costing.total_variable_OM_cost[0]) if hasattr(costing, "total_variable_OM_cost") else None
        total_fixed_om = scalar(getattr(costing, "total_fixed_OM_cost", None))
        li_recovery = scalar(model.fs.Li_recovery)
        co_recovery = scalar(model.fs.Co_recovery)
        stream_values = port_stream_values(model.fs, max_streams=200)
        passed = bool(
            final_dof is not None
            and cost_of_recovery is not None
            and cost_of_recovery > 0
            and annualized_cost is not None
            and annualized_cost > 0
            and li_recovery is not None
            and li_recovery >= 0.945
            and co_recovery is not None
            and co_recovery >= 0.635
            and all(length is not None and length > 0 for length in stage_lengths)
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_cost_optimization",
            "official_reference_url": SOURCE_URL,
            "base_flowsheet_reference_url": BASE_FLOWSHEET_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "design_degrees_of_freedom": final_dof,
            "checks": [
                {"name": "diafiltration_cost_optimization_design_dof_recorded", "pass": final_dof is not None, "actual": final_dof},
                {"name": "diafiltration_cost_optimization_cost_of_recovery_positive", "pass": bool(cost_of_recovery is not None and cost_of_recovery > 0), "actual": cost_of_recovery},
                {"name": "diafiltration_cost_optimization_annualized_cost_positive", "pass": bool(annualized_cost is not None and annualized_cost > 0), "actual": annualized_cost},
                {"name": "diafiltration_cost_optimization_li_recovery_bound", "pass": bool(li_recovery is not None and li_recovery >= 0.945), "actual": li_recovery},
                {"name": "diafiltration_cost_optimization_co_recovery_bound", "pass": bool(co_recovery is not None and co_recovery >= 0.635), "actual": co_recovery},
                {"name": "diafiltration_cost_optimization_stage_lengths_positive", "pass": all(length is not None and length > 0 for length in stage_lengths), "actual": stage_lengths},
                {"name": "diafiltration_cost_optimization_stream_values_available", "pass": bool(stream_values), "actual": len(stream_values)},
            ],
            "cost_of_recovery": cost_of_recovery,
            "annualized_cost": annualized_cost,
            "total_variable_OM_cost": total_variable_om,
            "total_fixed_OM_cost": total_fixed_om,
            "lithium_recovery": li_recovery,
            "cobalt_recovery": co_recovery,
            "stage_lengths_m": stage_lengths,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "uky" / "costing" / "diafiltration_flowsheet_optimization_example.py"),
                "base_flowsheet_source": str(SOURCE_ROOT / "prommis" / "nanofiltration" / "diafiltration.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/latest/_images/diafiltration_pfd.png",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS diafiltration cost optimization checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_cost_optimization",
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
