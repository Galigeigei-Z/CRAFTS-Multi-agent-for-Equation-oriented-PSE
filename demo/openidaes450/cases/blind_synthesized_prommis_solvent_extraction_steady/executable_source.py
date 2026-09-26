#!/usr/bin/env python3
"""Run official PrOMMiS steady solvent extraction validation."""

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

from idaes.core.initialization import InitializationStatus  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import check_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.solvent_extraction.solvent_extraction_steady.html"
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


def approx(actual: float | None, expected: float, *, rel: float = 1e-4, abs_tol: float = 0.0) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def outlet_conc(model: Any, outlet: str, component: str) -> float | None:
    try:
        return scalar(getattr(model.fs.solex, outlet).conc_mass_comp[0.0, component])
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from prommis.solvent_extraction.solvent_extraction_steady import model_buildup_and_set_inputs  # noqa: PLC0415

        model = model_buildup_and_set_inputs(dosage=5, number_of_stages=3, has_holdup=False)
        initializer = model.fs.solex.default_initializer()
        initializer.initialize(model.fs.solex)
        init_ok = initializer.summary[model.fs.solex]["status"] == InitializationStatus.Ok

        solver = get_solver("ipopt_v2")
        results = solver.solve(model, tee=False)
        optimal = check_optimal_termination(results)
        final_dof = degrees_of_freedom(model)

        organic_kerosene = outlet_conc(model, "organic_outlet", "Kerosene")
        organic_dehpa = outlet_conc(model, "organic_outlet", "DEHPA")
        organic_sc = outlet_conc(model, "organic_outlet", "Sc_o")
        organic_nd = outlet_conc(model, "organic_outlet", "Nd_o")
        aqueous_sc = outlet_conc(model, "aqueous_outlet", "Sc")
        aqueous_nd = outlet_conc(model, "aqueous_outlet", "Nd")
        aqueous_fe = outlet_conc(model, "aqueous_outlet", "Fe")
        aqueous_h = outlet_conc(model, "aqueous_outlet", "H")

        checks = [
            {"name": "solvent_extraction_initializer_ok", "pass": bool(init_ok), "actual": str(initializer.summary[model.fs.solex]["status"])},
            {"name": "solvent_extraction_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "solvent_extraction_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "solvent_extraction_organic_kerosene_matches_official_test", "pass": approx(organic_kerosene, 8.2000e05), "actual": organic_kerosene},
            {"name": "solvent_extraction_organic_dehpa_matches_official_test", "pass": approx(organic_dehpa, 4.6087e04), "actual": organic_dehpa},
            {"name": "solvent_extraction_organic_sc_matches_official_test", "pass": approx(organic_sc, 1.7633e00), "actual": organic_sc},
            {"name": "solvent_extraction_organic_nd_matches_official_test", "pass": approx(organic_nd, 6.5178e-02), "actual": organic_nd},
            {"name": "solvent_extraction_aqueous_sc_matches_official_test", "pass": approx(aqueous_sc, 2.7415e-03), "actual": aqueous_sc},
            {"name": "solvent_extraction_aqueous_nd_matches_official_test", "pass": approx(aqueous_nd, 8.8099e-01), "actual": aqueous_nd},
            {"name": "solvent_extraction_aqueous_fe_matches_official_test", "pass": approx(aqueous_fe, 5.8559e02), "actual": aqueous_fe},
            {"name": "solvent_extraction_aqueous_h_matches_official_test", "pass": approx(aqueous_h, 3.9513e01), "actual": aqueous_h},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_solvent_extraction_steady",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "dosage_percent": 5,
            "number_of_stages": 3,
            "has_holdup": False,
            "organic_outlet_conc_mass_comp": {
                "Kerosene": organic_kerosene,
                "DEHPA": organic_dehpa,
                "Sc_o": organic_sc,
                "Nd_o": organic_nd,
            },
            "aqueous_outlet_conc_mass_comp": {
                "Sc": aqueous_sc,
                "Nd": aqueous_nd,
                "Fe": aqueous_fe,
                "H": aqueous_h,
            },
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "solvent_extraction" / "solvent_extraction_steady.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "solvent_extraction" / "tests" / "test_solvent_extraction_steady.py"),
                "official_module": "prommis.solvent_extraction.solvent_extraction_steady",
            },
            "error": None if passed else {"message": "PrOMMiS steady solvent extraction checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_solvent_extraction_steady",
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
