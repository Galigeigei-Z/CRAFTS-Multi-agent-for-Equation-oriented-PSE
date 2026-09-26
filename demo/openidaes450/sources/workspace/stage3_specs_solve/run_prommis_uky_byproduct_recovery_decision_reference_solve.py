#!/usr/bin/env python3
"""Run official PrOMMiS UKy byproduct recovery decision validation."""

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

from pyomo.environ import ConcreteModel, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.uky.costing.determine_byproduct_recovery.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"
UKY_COSTING_ROOT = SOURCE_ROOT / "prommis" / "uky" / "costing"


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))


def approx(actual: float | None, expected: float, *, rel: float = 1e-5, abs_tol: float = 1e-6) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def _run_custom_decision() -> dict[str, Any]:
    from prommis.uky.costing.determine_byproduct_recovery import ByproductRecovery  # noqa: PLC0415

    model = ConcreteModel()
    model.recovery = ByproductRecovery(materials=["Lithium", "Cobalt"])
    data = {
        "Lithium": {
            "production": 1000.0,
            "market_value": 20.0,
            "waste_disposal": 1.0,
            "conversion": 0.0,
            "conversion_cost": 0.0,
            "process_steps": 1.0,
            "process_cost": 5000.0,
        },
        "Cobalt": {
            "production": 500.0,
            "market_value": 35.0,
            "waste_disposal": 2.0,
            "conversion": 1.0,
            "conversion_cost": 2000.0,
            "process_steps": 0.0,
            "process_cost": 0.0,
        },
    }
    for material, values in data.items():
        model.recovery.material_production[material].set_value(values["production"])
        model.recovery.market_value[material].set_value(values["market_value"])
        model.recovery.waste_disposal_cost[material].set_value(values["waste_disposal"])
        model.recovery.conversion_possible[material].set_value(values["conversion"])
        model.recovery.conversion_cost[material].set_value(values["conversion_cost"])
        model.recovery.added_process_steps[material].set_value(values["process_steps"])
        model.recovery.added_process_cost[material].set_value(values["process_cost"])
    net_benefit = float(value(model.recovery.net_benefit))
    return {
        "message": model.recovery.determine_financial_viability(),
        "potential_revenue": float(value(model.recovery.potential_revenue)),
        "total_recovery_cost": float(value(model.recovery.total_recovery_cost)),
        "net_benefit": net_benefit,
    }


def _empty_material_error() -> str:
    from prommis.uky.costing.determine_byproduct_recovery import ByproductRecovery  # noqa: PLC0415

    try:
        model = ConcreteModel()
        model.recovery = ByproductRecovery(materials=[])
    except ValueError as exc:
        return str(exc)
    return ""


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from prommis.uky.costing.determine_byproduct_recovery import determine_example_usage  # noqa: PLC0415

        example_message, example_net_benefit = determine_example_usage()
        custom = _run_custom_decision()
        empty_error = _empty_material_error()
        outputs = {
            "example_message": example_message,
            "example_net_benefit": float(example_net_benefit),
            "custom_message": custom["message"],
            "custom_potential_revenue": custom["potential_revenue"],
            "custom_total_recovery_cost": custom["total_recovery_cost"],
            "custom_net_benefit": custom["net_benefit"],
            "empty_material_error": empty_error,
        }
        checks = [
            {"name": "byproduct_recovery_example_net_benefit_matches_official_test", "pass": approx(outputs["example_net_benefit"], 4920.0, rel=1e-4), "actual": outputs["example_net_benefit"]},
            {"name": "byproduct_recovery_example_message_financially_viable", "pass": outputs["example_message"].startswith("✅ Byproduct recovery is financially viable."), "actual": outputs["example_message"]},
            {"name": "byproduct_recovery_custom_revenue_expected", "pass": approx(outputs["custom_potential_revenue"], 39500.0), "actual": outputs["custom_potential_revenue"]},
            {"name": "byproduct_recovery_custom_cost_expected", "pass": approx(outputs["custom_total_recovery_cost"], 7000.0), "actual": outputs["custom_total_recovery_cost"]},
            {"name": "byproduct_recovery_custom_net_benefit_expected", "pass": approx(outputs["custom_net_benefit"], 32500.0), "actual": outputs["custom_net_benefit"]},
            {"name": "byproduct_recovery_empty_material_guard_matches_official_test", "pass": "Material list cannot be empty" in outputs["empty_material_error"], "actual": outputs["empty_material_error"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "decision_framework",
            "case_family": "prommis_uky_byproduct_recovery_decision",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "evaluated",
            "final_dof": 0,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(UKY_COSTING_ROOT / "determine_byproduct_recovery.py"),
                "official_test_source": str(UKY_COSTING_ROOT / "tests" / "test_determine_byproduct_recovery.py"),
                "official_reference_figure": str(UKY_COSTING_ROOT / "byproduct_recovery_determination_tree.png"),
                "official_module": "prommis.uky.costing.determine_byproduct_recovery",
            },
            "error": None if passed else {"message": "PrOMMiS UKy byproduct recovery decision checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "decision_framework",
            "case_family": "prommis_uky_byproduct_recovery_decision",
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
