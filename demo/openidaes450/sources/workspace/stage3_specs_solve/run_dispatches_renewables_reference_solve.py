#!/usr/bin/env python3
"""Run the local DISPATCHES wind-battery-PEM-tank-turbine case."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

SOURCE_URL = "https://dispatches.readthedocs.io/en/main/examples/ConceptualDesignOptimization.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/dispatches_wind_battery_pem_tank_turbine/source_root")


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(CASE_ROOT) not in sys.path:
        sys.path.insert(0, str(CASE_ROOT))


def jsonify(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonify(item) for item in value]
    try:
        import numpy as np  # noqa: PLC0415

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from dispatches.case_studies.renewables_case.load_parameters import default_input_params  # noqa: PLC0415
        from dispatches.case_studies.renewables_case.wind_battery_PEM_tank_turbine_LMP import (  # noqa: PLC0415
            wind_battery_pem_tank_turb_optimize,
        )

        params = deepcopy(default_input_params)
        params["design_opt"] = False
        params["extant_wind"] = True
        params["wind_resource"] = {0: params["wind_resource"][0]}
        params["DA_LMPs"] = params["DA_LMPs"][:1]
        result = jsonify(
            wind_battery_pem_tank_turb_optimize(
                1,
                input_params=params,
                verbose=False,
                plot=False,
            )
        )
        passed = isinstance(result, dict) and "NPV" in result
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "dispatches_wind_battery_pem_tank_turbine",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimization_result_returned" if passed else "failed",
            "checks": [{"name": "one_period_dispatches_optimization_returned_result", "pass": passed}],
            "wind_mw": result.get("wind_mw") if isinstance(result, dict) else None,
            "battery_mw": result.get("batt_mw") if isinstance(result, dict) else None,
            "pem_mw": result.get("pem_mw") if isinstance(result, dict) else None,
            "tank_kgH2": result.get("tank_kgH2") if isinstance(result, dict) else None,
            "turbine_mw": result.get("turb_mw") if isinstance(result, dict) else None,
            "npv": result.get("NPV") if isinstance(result, dict) else None,
            "annual_revenue_h2": result.get("annual_rev_h2") if isinstance(result, dict) else None,
            "annual_revenue_electricity": result.get("annual_rev_E") if isinstance(result, dict) else None,
            "stream_values": {
                "wind_to_splitter": {"power_mw": result.get("wind_mw") if isinstance(result, dict) else None},
                "pem_hydrogen": {"pem_mw": result.get("pem_mw") if isinstance(result, dict) else None},
                "h2_storage": {"tank_kgH2": result.get("tank_kgH2") if isinstance(result, dict) else None},
                "turbine_to_grid": {"turbine_mw": result.get("turb_mw") if isinstance(result, dict) else None},
            },
            "source_summary": {"source": str(CASE_ROOT / "renewables_case" / "wind_battery_PEM_tank_turbine_LMP.py")},
            "error": None if passed else {"message": "DISPATCHES runner did not return NPV result"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "dispatches_wind_battery_pem_tank_turbine",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "one_period_dispatches_optimization_returned_result", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
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
    main()
