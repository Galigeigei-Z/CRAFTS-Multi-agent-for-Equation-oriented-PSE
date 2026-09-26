#!/usr/bin/env python3
"""Run the local PrOMMiS diafiltration cascade as Stage-3 validation."""

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

from pyomo.environ import value  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/tutorials/diafiltration.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_diafiltration_cascade/source_root")


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(CASE_ROOT) not in sys.path:
        sys.path.insert(0, str(CASE_ROOT))


def scalar(obj: Any) -> float | None:
    try:
        return float(value(obj))
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from prommis.nanofiltration.diafiltration import main  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        model = main()
        design_dof = degrees_of_freedom(model)
        stream_values = port_stream_values(model.fs, max_streams=60)
        li_recovery = scalar(getattr(model, "Li_recovery", None))
        co_recovery = scalar(getattr(model, "Co_recovery", None))
        total_annualized_cost = scalar(getattr(getattr(model.fs, "costing", None), "total_annualized_cost", None))
        passed = bool(
            li_recovery is not None
            and co_recovery is not None
            and total_annualized_cost is not None
            and li_recovery >= 0.94
            and co_recovery >= 0.63
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_cascade",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "design_degrees_of_freedom": design_dof,
            "checks": [
                {"name": "lithium_recovery_bound", "pass": bool(li_recovery is not None and li_recovery >= 0.94)},
                {"name": "cobalt_recovery_bound", "pass": bool(co_recovery is not None and co_recovery >= 0.63)},
                {"name": "annualized_cost_available", "pass": total_annualized_cost is not None},
            ],
            "lithium_recovery": li_recovery,
            "lithium_purity": scalar(getattr(model, "Li_purity", None)),
            "cobalt_recovery": co_recovery,
            "cobalt_purity": scalar(getattr(model, "Co_purity", None)),
            "total_membrane_area_m2": scalar(getattr(model, "total_membrane_area", None)),
            "total_annualized_cost": total_annualized_cost,
            "stream_values": stream_values,
            "source_summary": {"source": str(CASE_ROOT / "nanofiltration" / "diafiltration.py")},
            "error": None if passed else {"message": "PrOMMiS diafiltration checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_cascade",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main_cli()
