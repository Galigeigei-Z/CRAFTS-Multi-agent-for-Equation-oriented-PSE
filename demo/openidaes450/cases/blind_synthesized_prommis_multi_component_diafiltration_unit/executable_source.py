#!/usr/bin/env python3
"""Run official PrOMMiS MultiComponentDiafiltration unit validation."""

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

from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import ConcreteModel, SolverFactory, TransformationFactory, check_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.nanofiltration.multi_component_diafiltration.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"
NANOFILTRATION_ROOT = SOURCE_ROOT / "prommis" / "nanofiltration"


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
        from prommis.nanofiltration.multi_component_diafiltration import MultiComponentDiafiltration  # noqa: PLC0415
        from prommis.nanofiltration.multi_component_diafiltration_solute_properties import (  # noqa: PLC0415
            MultiComponentDiafiltrationSoluteParameter,
        )

        cation_list = ["Li", "Co"]
        anion_list = ["Cl"]
        inlet_flow_volume = {"feed": 12.5, "diafiltrate": 3.75}
        inlet_concentration = {
            "feed": {"Li": 245, "Co": 288, "Cl": 821},
            "diafiltrate": {"Li": 14, "Co": 3, "Cl": 20},
        }

        model = ConcreteModel()
        model.fs = FlowsheetBlock(dynamic=False)
        model.fs.properties = MultiComponentDiafiltrationSoluteParameter(
            cation_list=cation_list,
            anion_list=anion_list,
        )
        model.fs.unit = MultiComponentDiafiltration(
            property_package=model.fs.properties,
            cation_list=cation_list,
            anion_list=anion_list,
            include_boundary_layer=True,
            NFE_module_length=10,
            NFE_boundary_layer_thickness=5,
            NFE_membrane_thickness=5,
        )

        initial_dof = degrees_of_freedom(model.fs.unit)
        model.fs.unit.total_module_length.fix()
        model.fs.unit.total_membrane_length.fix()
        model.fs.unit.applied_pressure.fix()
        model.fs.unit.feed_flow_volume.fix(inlet_flow_volume["feed"])
        model.fs.unit.diafiltrate_flow_volume.fix(inlet_flow_volume["diafiltrate"])
        for t in model.fs.unit.time:
            for j in model.fs.unit.solutes:
                model.fs.unit.feed_conc_mol_comp[t, j].fix(inlet_concentration["feed"][j])
                model.fs.unit.diafiltrate_conc_mol_comp[t, j].fix(inlet_concentration["diafiltrate"][j])

        initializer = model.fs.unit.default_initializer()
        initializer.initialize(model.fs.unit)
        final_dof = degrees_of_freedom(model.fs.unit)

        scaling = TransformationFactory("core.scale_model")
        scaled_model = scaling.create_using(model, rename=False)
        results = SolverFactory("ipopt").solve(scaled_model, tee=False)
        scaling.propagate_solution(scaled_model, model)
        optimal = check_optimal_termination(results)

        outputs = {
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "membrane_fixed_charge": scalar(model.fs.unit.membrane_fixed_charge),
            "retentate_flow_volume": scalar(model.fs.unit.retentate_flow_volume[0, 1]),
            "retentate_li": scalar(model.fs.unit.retentate_conc_mol_comp[0, 1, "Li"]),
            "retentate_co": scalar(model.fs.unit.retentate_conc_mol_comp[0, 1, "Co"]),
            "retentate_cl": scalar(model.fs.unit.retentate_conc_mol_comp[0, 1, "Cl"]),
            "permeate_flow_volume": scalar(model.fs.unit.permeate_flow_volume[0, 1]),
            "permeate_li": scalar(model.fs.unit.permeate_conc_mol_comp[0, 1, "Li"]),
            "permeate_co": scalar(model.fs.unit.permeate_conc_mol_comp[0, 1, "Co"]),
            "permeate_cl": scalar(model.fs.unit.permeate_conc_mol_comp[0, 1, "Cl"]),
        }
        checks = [
            {"name": "multi_component_diafiltration_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "multi_component_diafiltration_initial_dof_9", "pass": initial_dof == 9, "actual": initial_dof},
            {"name": "multi_component_diafiltration_final_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "multi_component_diafiltration_fixed_charge_matches_official_test", "pass": approx(outputs["membrane_fixed_charge"], -44.0), "actual": outputs["membrane_fixed_charge"]},
            {"name": "multi_component_diafiltration_retentate_flow_matches_official_test", "pass": approx(outputs["retentate_flow_volume"], 6.0854, abs_tol=1e-4), "actual": outputs["retentate_flow_volume"]},
            {"name": "multi_component_diafiltration_retentate_li_matches_official_test", "pass": approx(outputs["retentate_li"], 190.89, abs_tol=1e-2), "actual": outputs["retentate_li"]},
            {"name": "multi_component_diafiltration_retentate_co_matches_official_test", "pass": approx(outputs["retentate_co"], 239.83, abs_tol=1e-2), "actual": outputs["retentate_co"]},
            {"name": "multi_component_diafiltration_retentate_cl_matches_official_test", "pass": approx(outputs["retentate_cl"], 670.55, abs_tol=1e-2), "actual": outputs["retentate_cl"]},
            {"name": "multi_component_diafiltration_permeate_flow_matches_official_test", "pass": approx(outputs["permeate_flow_volume"], 10.035, abs_tol=1e-3), "actual": outputs["permeate_flow_volume"]},
            {"name": "multi_component_diafiltration_permeate_li_matches_official_test", "pass": approx(outputs["permeate_li"], 191.70, abs_tol=1e-2), "actual": outputs["permeate_li"]},
            {"name": "multi_component_diafiltration_permeate_co_matches_official_test", "pass": approx(outputs["permeate_co"], 222.48, abs_tol=1e-2), "actual": outputs["permeate_co"]},
            {"name": "multi_component_diafiltration_permeate_cl_matches_official_test", "pass": approx(outputs["permeate_cl"], 636.67, abs_tol=1e-2), "actual": outputs["permeate_cl"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_multi_component_diafiltration_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(NANOFILTRATION_ROOT / "multi_component_diafiltration.py"),
                "official_test_source": str(NANOFILTRATION_ROOT / "tests" / "test_multi_component_diafiltration.py"),
                "official_reference_figure": str(NANOFILTRATION_ROOT / "membrane_schematic.png"),
                "official_module": "prommis.nanofiltration.multi_component_diafiltration",
            },
            "error": None if passed else {"message": "PrOMMiS MultiComponentDiafiltration checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_multi_component_diafiltration_unit",
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
