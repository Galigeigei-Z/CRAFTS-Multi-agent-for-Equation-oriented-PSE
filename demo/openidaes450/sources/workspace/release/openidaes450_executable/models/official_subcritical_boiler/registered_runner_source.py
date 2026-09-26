#!/usr/bin/env python3
"""Run the official subcritical boiler case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/subcritical/subcritical_boiler_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402


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


def water_port_values(port: Any) -> dict[str, Any]:
    return {
        "flow_mol": component_value(port.flow_mol, 0) if hasattr(port, "flow_mol") else None,
        "pressure": component_value(port.pressure, 0) if hasattr(port, "pressure") else None,
        "enth_mol": component_value(port.enth_mol, 0) if hasattr(port, "enth_mol") else None,
        "temperature": component_value(port.temperature, 0) if hasattr(port, "temperature") else None,
    }


def stream_values(model: Any) -> dict[str, Any]:
    fs = model.fs
    values = {
        "drum_liquid_to_downcomer": water_port_values(fs.drum.liquid_outlet),
        "downcomer_to_waterwall_01": water_port_values(fs.downcomer.outlet),
        "waterwall_10_to_drum": water_port_values(fs.Waterwalls[10].outlet),
        "drum_steam_outlet": water_port_values(fs.drum.steam_outlet),
        "drum_feedwater_inlet": water_port_values(fs.drum.feedwater_inlet),
    }
    for index in fs.ww_zones:
        values[f"waterwall_{int(index):02d}_outlet"] = water_port_values(fs.Waterwalls[index].outlet)
    return values


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        import pyomo.environ as pyo  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from idaes.models_extra.power_generation.flowsheets.subcritical_power_plant import subcritical_boiler as sub  # noqa: PLC0415
        from pyomo.opt import SolverStatus, TerminationCondition  # noqa: PLC0415

        model = sub.main()
        solver = pyo.SolverFactory("ipopt")
        results = solver.solve(model, tee=tee)
        optimal = (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )
        return {
            "pass": bool(optimal and degrees_of_freedom(model) == 0),
            "stage": "steady_state_solver",
            "case_family": "subcritical_boiler",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "final_dof": degrees_of_freedom(model),
            "stream_values": stream_values(model),
            "source_summary": {
                "source": "idaes.models_extra.power_generation.flowsheets.subcritical_power_plant.subcritical_boiler.main",
                "stream_count": len(stream_values(model)),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "subcritical_boiler",
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
