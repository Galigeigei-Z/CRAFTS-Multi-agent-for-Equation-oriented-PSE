#!/usr/bin/env python3
"""Solve a two-stage LSRRO engineering variant at the common feed basis."""

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
from watertap_streams import merge_named_streams, streams_from_arcs  # noqa: E402

CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/watertap_lsrro/source_root")
SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/lsrro.html"
NUMBER_OF_STAGES = 2
FEED_SALINITY_KG_M3 = 70
FEED_FLOW_M3_S = 1e-3


def scalar(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        if str(CASE_ROOT) not in sys.path:
            sys.path.insert(0, str(CASE_ROOT))
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from lsrro import lsrro  # noqa: PLC0415

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            model = lsrro.build(
                number_of_stages=NUMBER_OF_STAGES,
                has_NaCl_solubility_limit=True,
                has_calculated_concentration_polarization=True,
                has_calculated_ro_pressure_drop=True,
            )
            lsrro.set_operating_conditions(model, Cin=FEED_SALINITY_KG_M3, Qin=FEED_FLOW_M3_S)
            lsrro.initialize(model, verbose=False)
            results = lsrro.solve(model)

        fs = model.fs
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = {
            "water_recovery": scalar(fs.water_recovery),
            "levelized_cost_of_water": scalar(fs.costing.LCOW),
            "specific_energy_consumption": scalar(fs.costing.specific_energy_consumption),
            "total_pump_work_kW": scalar(fs.total_pump_work),
            "recovered_pump_work_kW": scalar(fs.recovered_pump_work),
            "net_pump_work_kW": scalar(fs.net_pump_work),
            "product_nacl_mass_fraction": scalar(fs.product.properties[0].mass_frac_phase_comp["Liq", "NaCl"]),
            "disposal_nacl_mass_fraction": scalar(fs.disposal.properties[0].mass_frac_phase_comp["Liq", "NaCl"]),
            "total_membrane_area_m2": sum(scalar(unit.area) or 0.0 for unit in fs.ROUnits.values()),
        }
        streams = merge_named_streams(
            streams_from_arcs(model),
            {"feed": fs.feed.outlet, "product": fs.product.inlet, "disposal": fs.disposal.inlet},
        )
        passed = (
            optimal
            and final_dof == 0
            and metrics["water_recovery"] is not None
            and metrics["specific_energy_consumption"] is not None
            and metrics["levelized_cost_of_water"] is not None
            and bool(streams)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_lsrro_two_stage",
            "variant_basis": "topology_distinct_stage_count",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "number_of_stages": NUMBER_OF_STAGES,
            "feed_salinity_kg_m3": FEED_SALINITY_KG_M3,
            "feed_flow_m3_s": FEED_FLOW_M3_S,
            "variant_metrics": metrics,
            "stream_values": streams,
            "checks": [
                {"name": "two_stage_lsrro_optimal", "pass": optimal},
                {"name": "two_stage_lsrro_dof_zero", "pass": final_dof == 0},
                {"name": "two_stage_lsrro_metrics_available", "pass": passed},
            ],
            "source_summary": {
                "source": str(CASE_ROOT / "lsrro" / "lsrro.py"),
                "configuration": "two stages; 70 kg/m3 NaCl; 1e-3 m3/s feed",
                "stdout_tail": output.getvalue()[-5000:],
            },
            "error": None if passed else {"message": "Two-stage LSRRO failed one or more promotion checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_lsrro_two_stage",
            "variant_basis": "topology_distinct_stage_count",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = run_case()
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
