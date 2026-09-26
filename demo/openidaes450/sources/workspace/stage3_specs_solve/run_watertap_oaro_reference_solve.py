#!/usr/bin/env python3
"""Run the WaterTAP OARO simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/oaro.html"
ARC_ALIASES = {
    "s01": "feed_to_p1",
    "s02": "p1_to_oaro_feed",
    "s03": "oaro_feed_out_to_erd1",
    "s04": "erd1_to_disposal",
    "s05": "oaro_permeate_out_to_p2",
    "s06": "p2_to_ro",
    "s07": "ro_permeate_to_product",
    "s08": "ro_retentate_to_erd2",
    "s09": "erd2_to_p3",
    "s10": "p3_to_oaro_permeate_in",
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.oaro import oaro  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = oaro.build()
            oaro.set_operating_conditions(model)
            oaro.initialize_system(model, verbose=False)
            results = oaro.solve(model, tee=False)

        termination = str(results.solver.termination_condition)
        optimal = bool(check_optimal_termination(results))
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.water_recovery)
        volumetric_recovery = _value(model.fs.volumetric_recovery)
        product_salinity = _value(model.fs.product.properties[0].mass_frac_phase_comp["Liq", "NaCl"])
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = optimal and lcow is not None and lcow > 0 and recovery is not None and sec is not None
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_oaro",
            "official_reference_url": SOURCE_URL,
            "termination_condition": termination,
            "checks": [
                {"name": "oaro_simulation_optimal", "pass": optimal},
                {"name": "oaro_simulation_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "oaro_simulation_recovery_available", "pass": recovery is not None},
            ],
            "final_dof": degrees_of_freedom(model),
            "erd_type": "pump_as_turbine",
            "water_recovery": recovery,
            "volumetric_recovery": volumetric_recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "product_salinity_mass_fraction": product_salinity,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.oaro.oaro",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP OARO simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_oaro",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "oaro_simulation_runner_exception", "pass": False}],
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
