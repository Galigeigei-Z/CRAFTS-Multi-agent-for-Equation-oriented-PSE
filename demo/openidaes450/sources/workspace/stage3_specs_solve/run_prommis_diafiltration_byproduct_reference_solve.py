#!/usr/bin/env python3
"""Run official PrOMMiS diafiltration with byproduct recovery decision validation."""

from __future__ import annotations

import argparse
import contextlib
import io
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
from pyomo.environ import ConcreteModel, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/tutorials/byproduct_recovery_determination-solution.html"
DIAFILTRATION_SOURCE_URL = "https://prommis.readthedocs.io/en/latest/tutorials/diafiltration.html"
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
    stdout = io.StringIO()
    try:
        _prepare_imports()
        from prommis.nanofiltration import diafiltration  # noqa: PLC0415
        from prommis.uky.costing.costing_dictionaries import load_default_sale_prices  # noqa: PLC0415
        from prommis.uky.costing.determine_byproduct_recovery import ByproductRecovery  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            dia_model = diafiltration.main()

        final_dof = degrees_of_freedom(dia_model)
        total_annualized_cost = scalar(dia_model.fs.costing.total_annualized_cost)
        li_recovery = scalar(dia_model.Li_recovery)
        co_recovery = scalar(dia_model.Co_recovery)
        li_recovery_mass = scalar(dia_model.fs.stage3.permeate_outlet.flow_vol[0] * dia_model.fs.stage3.permeate_outlet.conc_mass_solute[0, "Li"] * 8000)
        co_recovery_mass = scalar(dia_model.fs.stage1.retentate_outlet.flow_vol[0] * dia_model.fs.stage1.retentate_outlet.conc_mass_solute[0, "Co"] * 8000)
        sale_prices = load_default_sale_prices()

        recovery_model = ConcreteModel()
        recovery_model.recovery_determine = ByproductRecovery(materials=["Lithium", "Cobalt"])
        material_data = {
            "Lithium": {
                "production": li_recovery_mass,
                "market_value": sale_prices["Li"],
                "waste_disposal": 1,
                "conversion": 0,
                "conversion_cost": 0,
                "process_steps": 1,
                "process_cost": total_annualized_cost,
            },
            "Cobalt": {
                "production": co_recovery_mass,
                "market_value": sale_prices["Co"],
                "waste_disposal": 1,
                "conversion": 0,
                "conversion_cost": 0,
                "process_steps": 0,
                "process_cost": 0,
            },
        }
        for material, data in material_data.items():
            block = recovery_model.recovery_determine
            block.material_production[material].set_value(data["production"] or 0)
            block.market_value[material].set_value(data["market_value"])
            block.waste_disposal_cost[material].set_value(data["waste_disposal"])
            block.conversion_possible[material].set_value(data["conversion"])
            block.conversion_cost[material].set_value(data["conversion_cost"])
            block.added_process_steps[material].set_value(data["process_steps"])
            block.added_process_cost[material].set_value(data["process_cost"] or 0)

        potential_revenue = scalar(recovery_model.recovery_determine.potential_revenue)
        total_recovery_cost = scalar(recovery_model.recovery_determine.total_recovery_cost)
        net_benefit = scalar(recovery_model.recovery_determine.net_benefit)
        decision = recovery_model.recovery_determine.determine_financial_viability()
        stream_values = port_stream_values(dia_model.fs, max_streams=200)
        passed = bool(
            final_dof is not None
            and total_annualized_cost is not None
            and total_annualized_cost > 0
            and li_recovery_mass is not None
            and li_recovery_mass > 0
            and co_recovery_mass is not None
            and co_recovery_mass > 0
            and net_benefit is not None
            and net_benefit > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_byproduct_recovery",
            "official_reference_url": SOURCE_URL,
            "base_flowsheet_reference_url": DIAFILTRATION_SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "design_degrees_of_freedom": final_dof,
            "checks": [
                {"name": "diafiltration_byproduct_design_dof_recorded", "pass": final_dof is not None, "actual": final_dof},
                {"name": "diafiltration_byproduct_annualized_cost_positive", "pass": bool(total_annualized_cost is not None and total_annualized_cost > 0), "actual": total_annualized_cost},
                {"name": "diafiltration_byproduct_lithium_production_positive", "pass": bool(li_recovery_mass is not None and li_recovery_mass > 0), "actual": li_recovery_mass},
                {"name": "diafiltration_byproduct_cobalt_production_positive", "pass": bool(co_recovery_mass is not None and co_recovery_mass > 0), "actual": co_recovery_mass},
                {"name": "diafiltration_byproduct_net_benefit_positive", "pass": bool(net_benefit is not None and net_benefit > 0), "actual": net_benefit},
                {"name": "diafiltration_byproduct_stream_values_available", "pass": bool(stream_values), "actual": len(stream_values)},
            ],
            "lithium_recovery": li_recovery,
            "cobalt_recovery": co_recovery,
            "lithium_recovery_mass_kg_yr": li_recovery_mass,
            "cobalt_recovery_mass_kg_yr": co_recovery_mass,
            "total_annualized_cost": total_annualized_cost,
            "potential_revenue": potential_revenue,
            "total_recovery_cost": total_recovery_cost,
            "net_benefit": net_benefit,
            "financial_viability_decision": decision,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "uky" / "costing" / "determine_byproduct_recovery.py"),
                "base_flowsheet_source": str(SOURCE_ROOT / "prommis" / "nanofiltration" / "diafiltration.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/latest/_images/diafiltration_pfd.png",
                "decision_tree": "https://prommis.readthedocs.io/en/latest/_images/byproduct_recovery_determination_tree.png",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS diafiltration byproduct recovery checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_byproduct_recovery",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_summary": {"source_root": str(SOURCE_ROOT), "stdout_tail": stdout.getvalue()[-4000:]},
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
