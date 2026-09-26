#!/usr/bin/env python3
"""Run the WaterTAP BSM2 wastewater treatment simulation solve."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))
from watertap_streams import streams_from_arcs  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/1.2.0/technical_reference/flowsheets/BSM2.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        if getattr(obj, "is_indexed", lambda: False)():
            for index in obj:
                return float(value(obj[index]))
        return float(value(obj))
    except Exception:
        return None


def _metrics(model: Any) -> dict[str, Any]:
    fs = model.fs
    return {
        "feed_flow_m3_s": _value(fs.FeedWater.properties[0].flow_vol),
        "treated_flow_m3_s": _value(fs.Treated.properties[0].flow_vol),
        "sludge_flow_m3_s": _value(fs.Sludge.properties[0].flow_vol),
        "r1_volume_m3": _value(fs.R1.volume),
        "r2_volume_m3": _value(fs.R2.volume),
        "r3_volume_m3": _value(fs.R3.volume),
        "anaerobic_digester_liquid_volume_m3": _value(fs.RADM.volume_liquid),
        "anaerobic_digester_vapor_volume_m3": _value(fs.RADM.volume_vapor),
    }


def run_case() -> dict[str, Any]:
    try:
        import pyomo.environ as pyo  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.full_water_resource_recovery_facility import BSM2  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = BSM2.build()
            BSM2.set_operating_conditions(model)
            BSM2.initialize_system(model)
            initial_dof = degrees_of_freedom(model)
            BSM2.scale_system(model)
            scaling = pyo.TransformationFactory("core.scale_model")
            scaled_model = scaling.create_using(model, rename=False)
            results = BSM2.solve(scaled_model, tee=False)
            scaling.propagate_solution(scaled_model, model)

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model)
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and metrics["treated_flow_m3_s"] is not None
            and metrics["treated_flow_m3_s"] > 0
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_bsm2",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "bsm2_simulation_optimal", "pass": optimal},
                {"name": "bsm2_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "bsm2_final_dof_zero", "pass": final_dof == 0},
                {"name": "bsm2_treated_flow_positive", "pass": metrics["treated_flow_m3_s"] is not None and metrics["treated_flow_m3_s"] > 0},
                {"name": "bsm2_streams_available", "pass": bool(stream_values)},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.full_water_resource_recovery_facility.BSM2",
                "configuration": "full WRRF simulation before optional BSM2 optimization hooks",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP BSM2 simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_bsm2",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "bsm2_simulation_runner_exception", "pass": False}],
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
