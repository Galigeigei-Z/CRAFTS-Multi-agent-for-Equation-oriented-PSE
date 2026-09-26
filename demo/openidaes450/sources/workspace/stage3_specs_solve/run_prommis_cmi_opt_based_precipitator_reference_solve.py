#!/usr/bin/env python3
"""Run official PrOMMiS CMI optimization-based precipitator validation."""

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
from pyomo.environ import value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.cmi_precipitator.opt_based_precipitator.html"
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


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from idaes.core.solvers import get_solver  # noqa: PLC0415
        from pyomo.environ import assert_optimal_termination  # noqa: PLC0415
        from idaes.core.scaling.util import set_scaling_factor  # noqa: PLC0415
        from prommis.cmi_precipitator.tests import test_precipitator as official_test  # noqa: PLC0415

        test_obj = official_test.TestPrec()
        model = test_obj.prec.__wrapped__(test_obj)
        set_scaling_factor(model.fs.unit.log_k_equilibrium_rxn_eqns[0.0, "E1"], 1e-4)
        set_scaling_factor(model.fs.unit.log_k_equilibrium_rxn_eqns[0.0, "E2"], 1e-10)
        set_scaling_factor(model.fs.unit.log_q_precipitate_equilibrium_rxn_eqns[0.0, "E3"], 1e-10)
        results = get_solver().solve(model)
        assert_optimal_termination(results)

        unit = model.fs.unit
        fe_out = scalar(unit.aqueous_outlet.molality_aqueous_comp[0, "Fe^3+"])
        h_out = scalar(unit.aqueous_outlet.molality_aqueous_comp[0, "H^+"])
        feoh3 = scalar(unit.precipitate_outlet.moles_precipitate_comp[0, "FeOH3"])
        final_dof = degrees_of_freedom(model)
        passed = bool(
            final_dof == 1
            and fe_out is not None and abs(fe_out - 0.104766) < 1e-4
            and h_out is not None and h_out > 0
            and feoh3 is not None and feoh3 > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_cmi_opt_based_precipitator",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "checks": [
                {"name": "cmi_precipitator_design_dof_recorded", "pass": final_dof == 1, "actual": final_dof},
                {"name": "cmi_precipitator_fe_out_matches_official_test", "pass": bool(fe_out is not None and abs(fe_out - 0.104766) < 1e-4), "actual": fe_out},
                {"name": "cmi_precipitator_h_out_positive", "pass": bool(h_out is not None and h_out > 0), "actual": h_out},
                {"name": "cmi_precipitator_feoh3_precipitate_positive", "pass": bool(feoh3 is not None and feoh3 > 0), "actual": feoh3},
            ],
            "aqueous_fe3_molality": fe_out,
            "aqueous_h_molality": h_out,
            "feoh3_moles": feoh3,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "cmi_precipitator" / "opt_based_precipitator.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "cmi_precipitator" / "tests" / "test_precipitator.py"),
            },
            "error": None if passed else {"message": "PrOMMiS CMI precipitator checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_cmi_opt_based_precipitator",
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
