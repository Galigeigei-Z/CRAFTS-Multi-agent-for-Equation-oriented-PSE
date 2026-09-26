#!/usr/bin/env python3
"""Build and solve the native two-bed WaterTAP GAC lead-lag variant."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import check_optimal_termination  # noqa: E402
from stage3_specs_solve.watertap_gac_lead_lag_model import (  # noqa: E402
    build_model,
    initialize_model,
    metrics,
    set_operating_conditions,
    solve_model,
)


SOURCE_URL = "https://watertap.readthedocs.io/en/1.0.0/technical_reference/flowsheets/gac.html"


def run_case(tee=False):
    try:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = build_model()
            set_operating_conditions(model)
            initial_dof = degrees_of_freedom(model)
            initialize_model(model)
            results = solve_model(model, tee=tee)
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        variant_metrics = metrics(model)
        checks = [
            {"name": "gac_lead_lag_optimal", "pass": optimal},
            {"name": "gac_lead_lag_initial_dof_zero", "pass": initial_dof == 0},
            {"name": "gac_lead_lag_final_dof_zero", "pass": final_dof == 0},
            {"name": "lag_bed_removes_additional_solute", "pass": variant_metrics["lag_bed_incremental_solute_removal_mol_s"] > 0},
            {"name": "lag_bed_provides_breakthrough_protection", "pass": variant_metrics["breakthrough_protection_factor"] > 1.5},
            {"name": "final_product_below_five_percent_feed_concentration", "pass": variant_metrics["final_to_feed_solute_ratio"] < 0.05},
        ]
        passed = all(check["pass"] for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_gac_lead_lag",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "checks": checks,
            "variant_metrics": variant_metrics,
            "source_summary": {
                "source": "Two serial WaterTAP GAC units using the official MCAS property package and CPHSDM performance relationships",
                "evidence_boundary": "Steady-state average-bed design model. It quantifies serial polishing and bed capacity, but does not simulate transient breakthrough fronts, valve sequencing, or cyclic bed rotation.",
                "stdout_tail": stdout.getvalue()[-5000:],
            },
            "error": None if passed else {"message": "Lead-lag GAC checks did not all pass"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_gac_lead_lag",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "gac_lead_lag_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main():
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
    main()
