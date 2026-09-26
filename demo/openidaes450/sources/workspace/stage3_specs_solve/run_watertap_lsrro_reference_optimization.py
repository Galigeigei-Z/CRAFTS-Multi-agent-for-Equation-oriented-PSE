#!/usr/bin/env python3
"""Run the local WaterTAP LSRRO optimization solve."""

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
from optimization_plan_contract import plan_provenance, validate_optimization_plan  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/lsrro.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/watertap_lsrro/source_root")
OPTIMIZATION_VARIABLES = (
    "fs.PrimaryPumps[1].control_volume.properties_out[0].pressure",
    "fs.PrimaryPumps[2].control_volume.properties_out[0].pressure",
    "fs.PrimaryPumps[3].control_volume.properties_out[0].pressure",
    "fs.EnergyRecoveryDevices[1].control_volume.properties_out[0].pressure",
    "fs.ROUnits[1].area",
    "fs.ROUnits[2].area",
    "fs.ROUnits[3].area",
    "fs.ROUnits[2].A_comp[0, 'H2O']",
    "fs.ROUnits[3].A_comp[0, 'H2O']",
    "fs.ROUnits[2].B_comp[0, 'NaCl']",
    "fs.ROUnits[3].B_comp[0, 'NaCl']",
)
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "minimize levelized cost of water for the three-stage LSRRO train",
    "variables_to_unfix": [
        "fs.PrimaryPumps[1].control_volume.properties_out[0].pressure",
        "fs.PrimaryPumps[2].control_volume.properties_out[0].pressure",
        "fs.PrimaryPumps[3].control_volume.properties_out[0].pressure",
        "fs.EnergyRecoveryDevices[1].control_volume.properties_out[0].pressure",
        "fs.ROUnits[1].area",
        "fs.ROUnits[2].area",
        "fs.ROUnits[3].area",
        "fs.ROUnits[2].A_comp[0, 'H2O']",
        "fs.ROUnits[3].A_comp[0, 'H2O']",
        "fs.ROUnits[2].B_comp[0, 'NaCl']",
        "fs.ROUnits[3].B_comp[0, 'NaCl']",
    ],
    "target_dof": 11,
    "constraints": [
        "water recovery = 0.50",
        "permeate NaCl mass fraction <= 500e-6",
        "NaCl solubility limit",
        "stage A/B permeability equality tradeoff",
    ],
}


def _prepare_imports() -> None:
    if str(CASE_ROOT) not in sys.path:
        sys.path.insert(0, str(CASE_ROOT))


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case(optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        validate_optimization_plan(
            optimization_plan, OPTIMIZATION_PLAN_TEMPLATE, label="LSRRO"
        )
        _prepare_imports()
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from lsrro import lsrro  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model, results = lsrro.run_lsrro_case(
                number_of_stages=3,
                water_recovery=0.50,
                Cin=70,
                Qin=1e-3,
                Cbrine=None,
                A_case=lsrro.ACase.optimize,
                B_case=lsrro.BCase.optimize,
                AB_tradeoff=lsrro.ABTradeoff.equality_constraint,
                has_NaCl_solubility_limit=True,
                has_calculated_concentration_polarization=True,
                has_calculated_ro_pressure_drop=True,
                permeate_quality_limit=500e-6,
                quick_start=False,
            )

        termination = str(results.solver.termination_condition)
        optimal = bool(check_optimal_termination(results))
        lcow = _value(model.fs.costing.LCOW)
        recovery = _value(model.fs.water_recovery)
        sec = _value(model.fs.costing.specific_energy_consumption)
        stream_values = streams_from_arcs(model)
        passed = optimal and lcow is not None and lcow > 0 and recovery is not None and recovery >= 0.49
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_lsrro",
            "official_reference_url": SOURCE_URL,
            "termination_condition": termination,
            "checks": [
                {"name": "lsrro_optimization_optimal", "pass": optimal},
                {"name": "lsrro_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "lsrro_water_recovery_target_met", "pass": recovery is not None and recovery >= 0.49},
            ],
            "final_dof": degrees_of_freedom(model),
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "number_of_stages": int(_value(model.fs.NumberOfStages) or 3),
            "stream_values": stream_values,
            "source_summary": {"source": str(CASE_ROOT / "lsrro" / "lsrro.py"), "stdout_tail": stdout.getvalue()[-4000:]},
            **plan_provenance(optimization_plan, OPTIMIZATION_PLAN_TEMPLATE),
            "error": None if passed else {"message": "WaterTAP LSRRO optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_lsrro",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "lsrro_optimization_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--optimization-plan", type=Path)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case(optimization_plan=args.optimization_plan)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
