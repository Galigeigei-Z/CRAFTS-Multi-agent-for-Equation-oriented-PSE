#!/usr/bin/env python3
"""Solve and validate the native steady-state IDAES closed feedwater heater."""

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

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import TerminationCondition, value  # noqa: E402
from pyomo.util.check_units import assert_units_consistent  # noqa: E402

from stage3_specs_solve.idaes_steady_feedwater_heater_model import (  # noqa: E402
    SOURCE_URL,
    VERIFICATION_URL,
    build_model,
    initialize_and_solve,
)


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def state_values(port: Any) -> dict[str, float | None]:
    return {
        "flow_mol_mol_s": scalar(port.flow_mol, 0),
        "pressure_Pa": scalar(port.pressure, 0),
        "enthalpy_mol_J_mol": scalar(port.enth_mol, 0),
    }


def _heat_duty(section: Any) -> float | None:
    for candidate in ("heat_duty", "cold_side_heat", "hot_side_heat"):
        obj = getattr(section, candidate, None)
        if obj is not None:
            result = scalar(obj, 0)
            if result is not None:
                return result
    return None


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = build_model()
            initial_dof = degrees_of_freedom(model)
            assert_units_consistent(model)
            results = initialize_and_solve(model, tee=tee)
        fwh = model.fs.fwh
        final_dof = degrees_of_freedom(model)
        termination = results.solver.termination_condition

        steam_in = state_values(fwh.desuperheat.hot_side_inlet)
        feedwater_in = state_values(fwh.cooling.cold_side_inlet)
        feedwater_out = state_values(fwh.desuperheat.cold_side_outlet)
        drain_in = state_values(fwh.drain_mix.drain)
        drain_out = state_values(fwh.cooling.hot_side_outlet)

        steam_flow = steam_in["flow_mol_mol_s"]
        fw_flow = feedwater_in["flow_mol_mol_s"]
        fw_h_in = feedwater_in["enthalpy_mol_J_mol"]
        fw_h_out = feedwater_out["enthalpy_mol_J_mol"]
        feedwater_duty = (
            fw_flow * (fw_h_out - fw_h_in)
            if None not in (fw_flow, fw_h_in, fw_h_out)
            else None
        )
        extraction_ratio = steam_flow / fw_flow if steam_flow and fw_flow else None
        zone_duties = {
            "desuperheating_W": _heat_duty(fwh.desuperheat),
            "condensing_W": _heat_duty(fwh.condense),
            "drain_cooling_W": _heat_duty(fwh.cooling),
        }
        summed_zone_duty = (
            sum(zone_duties.values())
            if all(v is not None for v in zone_duties.values())
            else None
        )
        relative_duty_residual = (
            abs(summed_zone_duty - feedwater_duty) / max(abs(feedwater_duty), 1.0)
            if summed_zone_duty is not None and feedwater_duty is not None
            else None
        )

        checks = [
            {"name": "optimal_termination", "pass": termination == TerminationCondition.optimal},
            {"name": "initial_dof_zero", "pass": initial_dof == 0},
            {"name": "final_dof_zero", "pass": final_dof == 0},
            {"name": "units_consistent", "pass": True},
            {
                "name": "official_extraction_flow_reproduced",
                "pass": steam_flow is not None and abs(steam_flow - 98.335) < 0.02,
            },
            {
                "name": "feedwater_is_heated",
                "pass": fw_h_out is not None and fw_h_in is not None and fw_h_out > fw_h_in,
            },
            {
                "name": "three_zone_duty_closes",
                "pass": relative_duty_residual is not None and relative_duty_residual < 1e-6,
            },
        ]
        passed = all(check["pass"] for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "idaes_steady_feedwater_heater",
            "source_url": SOURCE_URL,
            "verification_url": VERIFICATION_URL,
            "termination_condition": str(termination),
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "checks": checks,
            "metrics": {
                "extraction_steam_flow_mol_s": steam_flow,
                "feedwater_flow_mol_s": fw_flow,
                "extraction_to_feedwater_molar_ratio": extraction_ratio,
                "feedwater_heat_gain_W": feedwater_duty,
                "zone_heat_duties": zone_duties,
                "zone_duty_sum_W": summed_zone_duty,
                "relative_duty_residual": relative_duty_residual,
                "feedwater_enthalpy_rise_J_mol": (
                    fw_h_out - fw_h_in if fw_h_out is not None and fw_h_in is not None else None
                ),
            },
            "stream_values": {
                "extraction_steam_inlet": steam_in,
                "cascade_drain_inlet": drain_in,
                "feedwater_inlet": feedwater_in,
                "heated_feedwater_outlet": feedwater_out,
                "cooled_drain_outlet": drain_out,
            },
            "evidence_boundary": (
                "Native steady-state FWH0D solve with IAPWS95, three heat-transfer zones, "
                "and drain mixing. Dynamic holdup and control response are outside this case."
            ),
            "stdout_tail": stdout.getvalue()[-4000:],
            "error": None if passed else {"message": "Feedwater-heater validation checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "idaes_steady_feedwater_heater",
            "source_url": SOURCE_URL,
            "termination_condition": None,
            "initial_dof": None,
            "final_dof": None,
            "checks": [{"name": "runner_exception", "pass": False}],
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
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
