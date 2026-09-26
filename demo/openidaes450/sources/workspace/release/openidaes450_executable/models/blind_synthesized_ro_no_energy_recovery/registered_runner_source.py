#!/usr/bin/env python3
"""Run the WaterTAP RO no-energy-recovery simulation solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/RO_with_energy_recovery.html"
SOURCE_VARIANT_URL = f"{SOURCE_URL}#no_ERD"
ARC_ALIASES = {
    "s01": "feed_to_p1",
    "s02": "p1_to_ro",
    "s03": "ro_permeate_to_product",
    "s04": "ro_retentate_to_disposal",
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
        from watertap.flowsheets.RO_with_energy_recovery import RO_with_energy_recovery as ro_erd  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ro_erd.build(erd_type=ro_erd.ERDtype.no_ERD)
            ro_erd.set_operating_conditions(model)
            ro_erd.initialize_system(model)
            results = ro_erd.solve(model, tee=False)

        termination = str(results.solver.termination_condition)
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.RO.recovery_mass_phase_comp[0, "Liq", "H2O"])
        product_salinity = _value(model.fs.product.properties[0].mass_frac_phase_comp["Liq", "NaCl"])
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = optimal and final_dof == 0 and lcow is not None and lcow > 0 and sec is not None and recovery is not None
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_ro_no_energy_recovery",
            "official_reference_url": SOURCE_URL,
            "source_variant_url": SOURCE_VARIANT_URL,
            "termination_condition": termination,
            "checks": [
                {"name": "ro_no_erd_simulation_optimal", "pass": optimal},
                {"name": "ro_no_erd_final_dof_zero", "pass": final_dof == 0},
                {"name": "ro_no_erd_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "ro_no_erd_recovery_available", "pass": recovery is not None},
            ],
            "final_dof": final_dof,
            "erd_type": "no_ERD",
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "product_salinity_mass_fraction": product_salinity,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.RO_with_energy_recovery.RO_with_energy_recovery",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP RO no-ERD simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_ro_no_energy_recovery",
            "official_reference_url": SOURCE_URL,
            "source_variant_url": SOURCE_VARIANT_URL,
            "termination_condition": None,
            "checks": [{"name": "ro_no_erd_simulation_runner_exception", "pass": False}],
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
