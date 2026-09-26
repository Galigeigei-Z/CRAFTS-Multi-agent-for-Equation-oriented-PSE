#!/usr/bin/env python3
"""Solve the methanol two-bed/interstage-cooling engineering variant."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "examples" / "methanol_two_bed" / "source_root"
for path in (ROOT, SOURCE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import value  # noqa: E402


def component_flow(port: Any, component: str) -> float:
    return float(value(port.flow_mol[0] * port.mole_frac_comp[0, component]))


def port_values(port: Any) -> dict[str, Any]:
    data = {
        "flow_mol_s": float(value(port.flow_mol[0])),
        "pressure_Pa": float(value(port.pressure[0])),
        "mole_frac_comp": {
            component: float(value(port.mole_frac_comp[0, component]))
            for component in ("H2", "CO", "CH3OH", "CH4")
        },
    }
    if hasattr(port, "temperature"):
        data["temperature_K"] = float(value(port.temperature[0]))
    if hasattr(port, "enth_mol"):
        data["enth_mol_J_mol"] = float(value(port.enth_mol[0]))
    return data


def run_case(*, tee: bool = False) -> dict[str, Any]:
    try:
        from notebook_build import main  # noqa: PLC0415

        model, result = main(tee=tee)
        fs = model.fs
        fresh_co = component_flow(fs.CO.outlet, "CO")
        final_co = component_flow(fs.R102.outlet, "CO")
        flash_methanol = component_flow(fs.F101.inlet, "CH3OH")
        liquid_methanol = component_flow(fs.F101.liq_outlet, "CH3OH")
        bed1_duty = float(value(fs.R101.heat_duty[0]))
        bed2_duty = float(value(fs.R102.heat_duty[0]))
        intercooler_duty = float(value(fs.H103.heat_duty[0]))
        return {
            "pass": True,
            "stage": "steady_state_solver",
            "case_family": "methanol_two_bed_intercooled",
            "variant_basis": "topology_distinct_reaction_staging",
            "termination_condition": str(result.solver.termination_condition),
            "final_dof": degrees_of_freedom(model),
            "variant_metrics": {
                "bed1_co_conversion": float(value(fs.R101.co_conversion)),
                "bed2_co_conversion": float(value(fs.R102.co_conversion)),
                "overall_fresh_co_conversion": (fresh_co - final_co) / fresh_co,
                "interstage_cooler_duty_W": intercooler_duty,
                "bed1_heat_duty_W": bed1_duty,
                "bed2_heat_duty_W": bed2_duty,
                "peak_bed_heat_removal_W": max(abs(bed1_duty), abs(bed2_duty)),
                "total_reactor_heat_removal_W": abs(bed1_duty) + abs(bed2_duty),
                "total_reaction_section_heat_removal_W": abs(bed1_duty)
                + abs(bed2_duty)
                + abs(intercooler_duty),
                "flash_methanol_recovery": liquid_methanol / flash_methanol,
            },
            "streams": {
                "bed1_feed": port_values(fs.R101.inlet),
                "bed1_outlet": port_values(fs.R101.outlet),
                "bed2_feed": port_values(fs.R102.inlet),
                "bed2_outlet": port_values(fs.R102.outlet),
                "methanol_product": port_values(fs.F101.liq_outlet),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "methanol_two_bed_intercooled",
            "variant_basis": "topology_distinct_reaction_staging",
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case(tee=args.tee)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main_cli()
