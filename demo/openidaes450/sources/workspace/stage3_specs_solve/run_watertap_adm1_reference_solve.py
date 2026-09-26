#!/usr/bin/env python3
"""Run the WaterTAP ADM1 anaerobic digestion simulation solve."""

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
from watertap_streams import stream_from_port  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/ADM1.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        if getattr(obj, "is_indexed", lambda: False)():
            for index in obj:
                return float(value(obj[index]))
        return float(value(obj))
    except Exception:
        return None


def _stream_values(model: Any) -> dict[str, dict[str, Any]]:
    fs = model.fs
    ports = {
        "sludge_feed": fs.R1.inlet,
        "liquid_digestate": fs.R1.liquid_outlet,
        "biogas": fs.R1.vapor_outlet,
    }
    streams: dict[str, dict[str, Any]] = {}
    for name, port in ports.items():
        record = stream_from_port(port)
        if record:
            record["source_port"] = port.getname(fully_qualified=True)
            streams[name] = record
    return streams


def _metrics(model: Any) -> dict[str, Any]:
    fs = model.fs
    return {
        "feed_flow_m3_s": _value(fs.R1.inlet.flow_vol),
        "liquid_digestate_flow_m3_s": _value(fs.R1.liquid_outlet.flow_vol),
        "biogas_flow_m3_s": _value(fs.R1.vapor_outlet.flow_vol),
        "liquid_volume_m3": _value(fs.R1.volume_liquid),
        "vapor_volume_m3": _value(fs.R1.volume_vapor),
        "liquid_outlet_temperature_k": _value(fs.R1.liquid_outlet.temperature),
    }


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.anaerobic_digester import ADM1_flowsheet  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model, results = ADM1_flowsheet.build_flowsheet()

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = _stream_values(model)
        passed = (
            optimal
            and final_dof == 0
            and metrics["liquid_digestate_flow_m3_s"] is not None
            and metrics["liquid_digestate_flow_m3_s"] > 0
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_adm1",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "adm1_simulation_optimal", "pass": optimal},
                {"name": "adm1_final_dof_zero", "pass": final_dof == 0},
                {"name": "adm1_liquid_digestate_flow_positive", "pass": metrics["liquid_digestate_flow_m3_s"] is not None and metrics["liquid_digestate_flow_m3_s"] > 0},
                {"name": "adm1_streams_available", "pass": bool(stream_values)},
            ],
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.anaerobic_digester.ADM1_flowsheet",
                "configuration": "single ADM1 anaerobic digester with liquid and vapor outlets",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP ADM1 simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_adm1",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "adm1_simulation_runner_exception", "pass": False}],
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
