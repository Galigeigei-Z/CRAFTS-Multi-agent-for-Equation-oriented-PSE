#!/usr/bin/env python3
"""Solve the native MeOH-H2O NRTL staged partial-condensation variant."""

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
from stage3_specs_solve.methanol_water_nrtl_purification_model import (  # noqa: E402
    build_model,
    initialize_model,
    metrics,
    set_operating_conditions,
    solve_model,
)


CASE_ID = "variant_methanol_water_nrtl_partial_condensation"
THERMO_URL = "https://github.com/CalebBell/thermo/tree/0.6.0"
THERMO_VERSION = "0.6.0"
NRTL_DATABASE_SHA256 = "14db0a06d3a4fd988b6e49e4eb8eac4ea9bc007a550149451c3ac36cc8774f7b"


def run_case(tee=False):
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = build_model()
            set_operating_conditions(model)
            initial_dof = degrees_of_freedom(model)
            initialize_model(model)
            results = solve_model(model, tee=tee)
        final_dof = degrees_of_freedom(model)
        optimal = bool(check_optimal_termination(results))
        case_metrics = metrics(model)
        checks = [
            {"name": "native_idaes_solve_optimal", "pass": optimal},
            {"name": "initial_dof_zero", "pass": initial_dof == 0},
            {"name": "final_dof_zero", "pass": final_dof == 0},
            {
                "name": "methanol_product_purity_at_least_95_mol_pct",
                "pass": case_metrics["purified_product_methanol_mole_fraction"] >= 0.95,
            },
            {
                "name": "staged_vle_enriches_methanol",
                "pass": case_metrics["purified_product_methanol_mole_fraction"]
                > case_metrics["feed_methanol_mole_fraction"],
            },
            {
                "name": "methanol_recovery_above_30_pct",
                "pass": case_metrics["overall_methanol_recovery"] >= 0.30,
            },
            {
                "name": "polisher_requires_cooling",
                "pass": case_metrics["polisher_cooling_duty_kW"] < -1000,
            },
            {
                "name": "feed_flash_is_vapor_state",
                "pass": case_metrics["flash_vapor_flow_mol_s"]
                / case_metrics["feed_flow_mol_s"]
                >= 0.999,
            },
            {
                "name": "partial_condenser_rejects_water",
                "pass": case_metrics["polisher_condensate_water_mole_fraction"]
                > 1 - case_metrics["feed_methanol_mole_fraction"],
            },
            {
                "name": "flash_molar_balance_closes",
                "pass": abs(case_metrics["flash_total_molar_closure"] - 1) <= 1e-6,
            },
            {
                "name": "polisher_molar_balance_closes",
                "pass": abs(case_metrics["polisher_total_molar_closure"] - 1) <= 1e-6,
            },
        ]
        passed = all(item["pass"] for item in checks)
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "methanol_water_nrtl_partial_condensation",
            "termination_condition": str(results.solver.termination_condition),
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "checks": checks,
            "variant_metrics": case_metrics,
            "source_summary": {
                "property_model": "ideal vapor + temperature-dependent liquid NRTL (tau_ij=b_ij/T)",
                "binary_system": "methanol (CAS 67-56-1) / water (CAS 7732-18-5)",
                "parameter_source": "thermo 0.6.0 ChemSep NRTL interaction-parameter database",
                "source_url": THERMO_URL,
                "source_version": THERMO_VERSION,
                "license": "MIT",
                "database_sha256": NRTL_DATABASE_SHA256,
                "nrtl_b_K": {
                    "methanol_to_water": -95.13209282738782,
                    "water_to_methanol": 398.95345259688855,
                },
                "nrtl_alpha": 0.2999,
                "evidence_boundary": (
                    "Steady-state binary MeOH-H2O equilibrium stages at 1 atm. "
                    "Dissolved synthesis gases, higher alcohols, salts, pressure drop, "
                    "equipment sizing, and downstream total condensation are not represented."
                ),
                "stdout_tail": stdout.getvalue()[-5000:],
            },
            "error": None if passed else {"message": "One or more validation checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "methanol_water_nrtl_partial_condensation",
            "termination_condition": None,
            "checks": [{"name": "runner_exception", "pass": False}],
            "source_summary": {
                "source_url": THERMO_URL,
                "source_version": THERMO_VERSION,
                "license": "MIT",
                "database_sha256": NRTL_DATABASE_SHA256,
                "stdout_tail": stdout.getvalue()[-5000:],
            },
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
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
