#!/usr/bin/env python3
"""Run the official PrOMMiS UKy rare-earth flowsheet as Stage-3 validation."""

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


SOURCE_URL = "https://prommis.readthedocs.io/en/stable/tutorials/uky_flowsheet-solution.html"
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
        from prommis.uky import uky_flowsheet as uky  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            model, results = uky.main()

        final_dof = degrees_of_freedom(model)
        ree_recovery = scalar(model.fs.overall_ree_recovery_percentage[0])
        ree_product_flow = scalar(model.fs.ree_product_flow[0])
        product_purity = scalar(model.fs.ree_product_purity_percentage[0])
        stream_values = port_stream_values(model.fs, max_streams=250)
        passed = bool(
            final_dof == 0
            and ree_recovery is not None
            and ree_recovery > 0
            and ree_product_flow is not None
            and ree_product_flow > 0
            and product_purity is not None
            and product_purity > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_uky_flowsheet",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": [
                {"name": "uky_degrees_of_freedom_zero", "pass": final_dof == 0, "actual": final_dof},
                {"name": "uky_ree_recovery_positive", "pass": bool(ree_recovery is not None and ree_recovery > 0), "actual": ree_recovery},
                {"name": "uky_ree_product_flow_positive", "pass": bool(ree_product_flow is not None and ree_product_flow > 0), "actual": ree_product_flow},
                {"name": "uky_product_purity_positive", "pass": bool(product_purity is not None and product_purity > 0), "actual": product_purity},
                {"name": "uky_stream_values_available", "pass": bool(stream_values), "actual": len(stream_values)},
            ],
            "overall_ree_recovery_percent": ree_recovery,
            "ree_product_flow_kg_h": ree_product_flow,
            "ree_product_purity_percent": product_purity,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "uky" / "uky_flowsheet.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/stable/_images/uky_flowsheet.png",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS UKy flowsheet checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_uky_flowsheet",
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
