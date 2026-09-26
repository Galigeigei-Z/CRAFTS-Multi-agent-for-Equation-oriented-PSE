#!/usr/bin/env python3
"""Run the WaterTAP ASM2d activated sludge simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/ASM2d.html"


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
        "r4_volume_m3": _value(fs.R4.volume),
        "r5_volume_m3": _value(fs.R5.volume),
        "r6_volume_m3": _value(fs.R6.volume),
        "r7_volume_m3": _value(fs.R7.volume),
        "treated_phosphate_kg_m3": _value(fs.Treated.properties[0].conc_mass_comp["S_PO4"]),
        "treated_ammonium_kg_m3": _value(fs.Treated.properties[0].conc_mass_comp["S_NH4"]),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.activated_sludge import ASM2D_flowsheet  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model, results = ASM2D_flowsheet.build_flowsheet()

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model)
        passed = (
            optimal
            and final_dof == 0
            and metrics["treated_flow_m3_s"] is not None
            and metrics["treated_flow_m3_s"] > 0
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_asm2d",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "asm2d_simulation_optimal", "pass": optimal},
                {"name": "asm2d_final_dof_zero", "pass": final_dof == 0},
                {"name": "asm2d_treated_flow_positive", "pass": metrics["treated_flow_m3_s"] is not None and metrics["treated_flow_m3_s"] > 0},
                {"name": "asm2d_streams_available", "pass": bool(stream_values)},
            ],
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.activated_sludge.ASM2D_flowsheet",
                "configuration": "ASM2d biological phosphorus removal activated sludge process",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP ASM2d simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_asm2d",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "asm2d_simulation_runner_exception", "pass": False}],
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
