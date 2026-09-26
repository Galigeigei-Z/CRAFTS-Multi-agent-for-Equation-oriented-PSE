#!/usr/bin/env python3
"""Run official PrOMMiS membrane cascade flowsheet validation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import check_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://github.com/prommis/prommis/tree/main/src/prommis/nanofiltration/membrane_cascade_flowsheet"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"
FLOWSHEET_ROOT = SOURCE_ROOT / "prommis" / "nanofiltration" / "membrane_cascade_flowsheet"


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))


def scalar(obj: Any) -> float | None:
    try:
        return float(value(obj))
    except Exception:
        return None


def approx(actual: float | None, expected: float, *, rel: float = 1e-5, abs_tol: float = 1e-6) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from prommis.nanofiltration.membrane_cascade_flowsheet.diafiltration_flowsheet_model import (  # noqa: PLC0415
            DiafiltrationModel,
        )

        solutes = ["Li", "Co"]
        precipitate_yield = {
            "permeate": {"Li": 0.81, "Co": 0.01},
            "retentate": {"Li": 0.20, "Co": 0.89},
        }
        feed = {"solvent": 100, "Li": 170, "Co": 1700}
        diafiltrate = {"solvent": 30, "Li": 3, "Co": 6}
        flowsheet = DiafiltrationModel(
            NS=1,
            NT=3,
            solutes=solutes,
            flux=0.1,
            sieving_coefficient={"Li": 1.3, "Co": 0.5},
            feed=feed,
            diafiltrate=diafiltrate,
            precipitate=True,
            precipitate_yield=precipitate_yield,
        )
        flowsheet.ns = 2
        flowsheet.nt = 5
        mixing = "stage"
        model = flowsheet.build_flowsheet(mixing=mixing)
        flowsheet.initialize(model, mixing=mixing, precipitate=True, info=False)
        flowsheet.unfix_dof(model, mixing=mixing, precipitate=True)
        model.fs.split_diafiltrate.mixed_state[0].flow_vol.fix(30)
        model.fs.precipitator["retentate"].volume.fix(500)
        model.fs.precipitator["permeate"].volume.fix(500)
        model.recovery_li = 0.8

        optimization_dof = degrees_of_freedom(model)
        results = get_solver().solve(model, tee=False)
        optimal = check_optimal_termination(results)

        outputs = {
            "optimization_dof": optimization_dof,
            "final_dof": degrees_of_freedom(model),
            "membrane_recovery_li": scalar(model.rec_perc_li),
            "membrane_recovery_co": scalar(model.rec_perc_co),
            "overall_recovery_li": scalar(model.prec_perc_li),
            "overall_recovery_co": scalar(model.prec_perc_co),
            "stage_1_length": scalar(model.fs.stage[1].length),
            "retentate_solid_co": scalar(model.fs.precipitator["retentate"].solid.flow_mass_solute[0, "Co"]),
            "retentate_solid_li": scalar(model.fs.precipitator["retentate"].solid.flow_mass_solute[0, "Li"]),
            "permeate_solid_co": scalar(model.fs.precipitator["permeate"].solid.flow_mass_solute[0, "Co"]),
            "permeate_solid_li": scalar(model.fs.precipitator["permeate"].solid.flow_mass_solute[0, "Li"]),
            "waste_solvent_flow_vol": scalar(model.fs.split_precipitate_recycle.waste.flow_vol[0]),
            "waste_co": scalar(model.fs.split_precipitate_recycle.waste.flow_mass_solute[0, "Co"]),
            "waste_li": scalar(model.fs.split_precipitate_recycle.waste.flow_mass_solute[0, "Li"]),
        }
        checks = [
            {"name": "membrane_cascade_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "membrane_cascade_optimization_dof_13", "pass": optimization_dof == 13, "actual": optimization_dof},
            {"name": "membrane_cascade_overall_li_recovery_matches_official_test", "pass": approx(outputs["overall_recovery_li"], 0.799, abs_tol=1e-3), "actual": outputs["overall_recovery_li"]},
            {"name": "membrane_cascade_overall_co_recovery_matches_official_test", "pass": approx(outputs["overall_recovery_co"], 0.525, abs_tol=1e-3), "actual": outputs["overall_recovery_co"]},
            {"name": "membrane_cascade_membrane_li_recovery_matches_official_test", "pass": approx(outputs["membrane_recovery_li"], 0.9353, abs_tol=1e-4), "actual": outputs["membrane_recovery_li"]},
            {"name": "membrane_cascade_membrane_co_recovery_matches_official_test", "pass": approx(outputs["membrane_recovery_co"], 0.5178, abs_tol=1e-4), "actual": outputs["membrane_recovery_co"]},
            {"name": "membrane_cascade_stage_1_length_matches_official_test", "pass": approx(outputs["stage_1_length"], 1105.388, abs_tol=1e-3), "actual": outputs["stage_1_length"]},
            {"name": "membrane_cascade_retentate_solid_co_matches_official_test", "pass": approx(outputs["retentate_solid_co"], 893.679, abs_tol=1e-3), "actual": outputs["retentate_solid_co"]},
            {"name": "membrane_cascade_permeate_solid_li_matches_official_test", "pass": approx(outputs["permeate_solid_li"], 135.999, abs_tol=1e-3), "actual": outputs["permeate_solid_li"]},
            {"name": "membrane_cascade_waste_solvent_matches_official_test", "pass": approx(outputs["waste_solvent_flow_vol"], 100.0, abs_tol=1e-6), "actual": outputs["waste_solvent_flow_vol"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "optimization_solver",
            "case_family": "prommis_membrane_cascade_flowsheet",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": optimization_dof,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(FLOWSHEET_ROOT / "diafiltration_flowsheet_model.py"),
                "official_test_source": str(FLOWSHEET_ROOT / "tests" / "test_flowsheet.py"),
                "official_reference_figure": str(FLOWSHEET_ROOT / "flowsheet.png"),
                "official_module": "prommis.nanofiltration.membrane_cascade_flowsheet.diafiltration_flowsheet_model",
            },
            "error": None if passed else {"message": "PrOMMiS membrane cascade flowsheet checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "optimization_solver",
            "case_family": "prommis_membrane_cascade_flowsheet",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_summary": {"source_root": str(SOURCE_ROOT)},
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main_cli()
