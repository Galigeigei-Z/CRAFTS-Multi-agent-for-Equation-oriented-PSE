#!/usr/bin/env python3
"""Run the official supercritical power-plant case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/supercritical/supercritical_power_plant_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402
from stream_extract import port_stream_values  # noqa: E402


def component_value(obj: Any, *index: Any) -> float | None:
    if index:
        try:
            return float(value(obj[index]))
        except Exception:
            pass
    try:
        if hasattr(obj, "is_indexed") and obj.is_indexed():
            return float(value(obj[next(iter(obj))]))
    except Exception:
        pass
    try:
        return float(value(obj))
    except Exception:
        return None


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from idaes.models_extra.power_generation.flowsheets.supercritical_power_plant.SCPC_full_plant import (  # noqa: PLC0415
            main as run_official_scpc_full_plant,
        )
        from pyomo.opt import SolverStatus, TerminationCondition  # noqa: PLC0415

        model, results = run_official_scpc_full_plant()
        optimal = (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )
        fs = model.fs
        metrics = {
            "gross_power_mw": -component_value(fs.turb.power, 0) * 1e-6 if component_value(fs.turb.power, 0) is not None else None,
            "main_steam_pressure_pa": component_value(fs.turb.inlet_split.inlet.pressure, 0),
            "attemperator_enth_mol": component_value(fs.ATMP1.outlet.enth_mol, 0),
            "platen_superheater_heat_w": component_value(fs.PlSH.heat_duty, 0),
            "reheater_outlet_pressure_pa": component_value(fs.RH.cold_side_outlet.pressure, 0),
        }
        return {
            "pass": bool(optimal and degrees_of_freedom(model) == 0),
            "stage": "steady_state_solver",
            "case_family": "supercritical_power_plant",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "final_dof": degrees_of_freedom(model),
            "stream_values": port_stream_values(model),
            **metrics,
            "source_summary": {
                "source": "idaes.models_extra.power_generation.flowsheets.supercritical_power_plant.SCPC_full_plant.main",
                "note": "Official full SCPC plant runner: steam cycle + boiler network + connected final solve.",
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "supercritical_power_plant",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case(tee=args.tee)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
