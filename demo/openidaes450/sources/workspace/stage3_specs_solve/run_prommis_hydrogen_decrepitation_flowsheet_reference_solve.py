#!/usr/bin/env python3
"""Run official PrOMMiS hydrogen decrepitation flowsheet validation."""

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

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import SolverFactory, assert_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.hydrogen_decrepitation.hydrogen_decrepitation_flowsheet.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"


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


def approx(actual: float | None, expected: float, *, rel: float = 1e-5, abs_tol: float = 0.0) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from idaes.core.initialization import BlockTriangularizationInitializer, InitializationStatus  # noqa: PLC0415
        from idaes.core.util.initialization import propagate_state  # noqa: PLC0415
        from prommis.hydrogen_decrepitation.hydrogen_decrepitation_flowsheet import build_flowsheet  # noqa: PLC0415

        model = build_flowsheet()
        initializer = BlockTriangularizationInitializer()
        initializer.initialize(model.fs.shredder)
        propagate_state(model.fs.shredded_REPM)

        furnace = model.fs.hydrogen_decrepitation_furnace
        furnace.flow_mol_gas_constraint.deactivate()
        initializer.initialize(furnace)
        furnace.flow_mol_gas_constraint.activate()
        init_ok = initializer.summary[furnace]["status"] == InitializationStatus.Ok

        results = SolverFactory("ipopt").solve(model, tee=False)
        assert_optimal_termination(results)

        final_dof = degrees_of_freedom(model)
        solid_flow = scalar(furnace.solid_out[0].flow_mass)
        nd_frac = scalar(furnace.solid_out[0].mass_frac_comp["Nd"])
        nd2fe14b_frac = scalar(furnace.solid_out[0].mass_frac_comp["Nd2Fe14B"])
        gas_flow = scalar(furnace.gas_out[0].flow_mol)
        h2_frac = scalar(furnace.gas_out[0].mole_frac_comp["H2"])
        gas_temperature = scalar(furnace.gas_out[0].temperature)
        gas_pressure = scalar(furnace.gas_out[0].pressure)

        checks = [
            {"name": "hydrogen_decrepitation_initializer_ok", "pass": bool(init_ok), "actual": str(initializer.summary[furnace]["status"])},
            {"name": "hydrogen_decrepitation_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "hydrogen_decrepitation_solid_flow_matches_official_test", "pass": approx(solid_flow, 0.0057367), "actual": solid_flow},
            {"name": "hydrogen_decrepitation_nd_mass_frac_matches_official_test", "pass": approx(nd_frac, 0.0100001), "actual": nd_frac},
            {"name": "hydrogen_decrepitation_nd2fe14b_mass_frac_matches_official_test", "pass": approx(nd2fe14b_frac, 0.99), "actual": nd2fe14b_frac},
            {"name": "hydrogen_decrepitation_gas_flow_matches_official_test", "pass": approx(gas_flow, 0.0056509), "actual": gas_flow},
            {"name": "hydrogen_decrepitation_h2_pure", "pass": approx(h2_frac, 1.0), "actual": h2_frac},
            {"name": "hydrogen_decrepitation_gas_state_matches_official_test", "pass": bool(approx(gas_temperature, 443.15) and approx(gas_pressure, 101325.0)), "actual": {"temperature": gas_temperature, "pressure": gas_pressure}},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_hydrogen_decrepitation_flowsheet",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "solid_product_flow_mass_kg_s": solid_flow,
            "solid_product_mass_frac": {"Nd": nd_frac, "Nd2Fe14B": nd2fe14b_frac},
            "gas_out_flow_mol_s": gas_flow,
            "gas_out_mole_frac_h2": h2_frac,
            "gas_out_temperature_K": gas_temperature,
            "gas_out_pressure_Pa": gas_pressure,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "hydrogen_decrepitation" / "hydrogen_decrepitation_flowsheet.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "hydrogen_decrepitation" / "tests" / "test_hydrogen_decrepitation_flowsheet.py"),
                "official_module": "prommis.hydrogen_decrepitation.hydrogen_decrepitation_flowsheet",
            },
            "error": None if passed else {"message": "PrOMMiS hydrogen decrepitation checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_hydrogen_decrepitation_flowsheet",
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
