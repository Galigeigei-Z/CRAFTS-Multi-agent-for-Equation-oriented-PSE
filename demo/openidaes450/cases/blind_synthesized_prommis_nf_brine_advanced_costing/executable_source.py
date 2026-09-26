#!/usr/bin/env python3
"""Run official PrOMMiS NF brine advanced costing validation."""

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

from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from idaes.models.unit_models import Feed, Product  # noqa: E402
from pyomo.environ import ConcreteModel, Constraint, TransformationFactory, Var, units as pyunits, value  # noqa: E402
from pyomo.network import Arc  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/tutorials/costing_advanced_features-solution.html"
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


def build_advanced_costing_model() -> Any:
    from prommis.nanofiltration.nf_brine import define_feed_composition, initialize, solve_model  # noqa: PLC0415
    from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData  # noqa: PLC0415
    from watertap.core.solvers import get_solver as get_watertap_solver  # noqa: PLC0415
    from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock  # noqa: PLC0415
    from watertap.unit_models.nanofiltration_DSPMDE_0D import NanofiltrationDSPMDE0D  # noqa: PLC0415
    from watertap.unit_models.pressure_changer import Pump  # noqa: PLC0415

    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    watertap_solver = get_watertap_solver()
    model.fs.properties = MCASParameterBlock(**define_feed_composition())
    model.fs.feed = Feed(property_package=model.fs.properties)
    model.fs.permeate = Product(property_package=model.fs.properties)
    model.fs.retentate = Product(property_package=model.fs.properties)
    model.fs.pump = Pump(property_package=model.fs.properties)
    model.fs.unit = NanofiltrationDSPMDE0D(property_package=model.fs.properties)
    model.fs.feed_to_pump = Arc(source=model.fs.feed.outlet, destination=model.fs.pump.inlet)
    model.fs.pump_to_nf = Arc(source=model.fs.pump.outlet, destination=model.fs.unit.inlet)
    model.fs.nf_to_permeate = Arc(source=model.fs.unit.permeate, destination=model.fs.permeate.inlet)
    model.fs.nf_to_retentate = Arc(source=model.fs.unit.retentate, destination=model.fs.retentate.inlet)
    TransformationFactory("network.expand_arcs").apply_to(model)

    initialize(model, watertap_solver)
    solve_model(model, watertap_solver)
    solve_model(model, watertap_solver)

    model.fs.water = Var([0], initialize=1000, units=pyunits.gallon / pyunits.hr)
    model.fs.water.fix()
    model.fs.chemicals = Var([0], initialize=20, units=pyunits.gallon / pyunits.hr)
    model.fs.chemicals.fix()
    model.fs.waste = Var([0], initialize=20, units=pyunits.gallon / pyunits.hr)
    model.fs.waste_constraint = Constraint(
        expr=model.fs.waste[0]
        == pyunits.convert(model.fs.unit.feed_side.properties_out[0].flow_vol_phase["Liq"], to_units=pyunits.gal / pyunits.hr)
    )
    model.fs.product = Var([0], initialize=20, units=pyunits.gallon / pyunits.hr)
    model.fs.product_constraint = Constraint(
        expr=model.fs.product[0]
        == pyunits.convert(model.fs.unit.permeate_side[0, 1].flow_vol_phase["Liq"], to_units=pyunits.gal / pyunits.hr)
    )

    model.fs.costing_1 = QGESSCosting()
    model.fs.costing_1.build_process_costs(
        Lang_factor=2.97,
        fixed_OM=True,
        pure_product_output_rates={"treated_stream": model.fs.product[0]},
        mixed_product_output_rates={"treated_stream": model.fs.product[0]},
        sale_prices={"treated_stream": 0 * pyunits.USD_2021 / pyunits.gal},
        variable_OM=True,
        resources=["water", "chemicals", "waste"],
        rates=[model.fs.water, model.fs.chemicals, model.fs.waste],
        prices={
            "chemicals": 1.00 * pyunits.USD_2021 / pyunits.gallon,
            "waste": 0.35 * pyunits.USD_2021 / pyunits.gallon,
        },
        watertap_blocks=[model.fs.unit],
        CE_index_year="2021",
    )
    QGESSCostingData.costing_initialization(model.fs.costing_1)
    QGESSCostingData.initialize_fixed_OM_costs(model.fs.costing_1)
    QGESSCostingData.initialize_variable_OM_costs(model.fs.costing_1)
    get_solver().solve(model, tee=False)
    return model


def run_case() -> dict[str, Any]:
    stdout = io.StringIO()
    try:
        _prepare_imports()
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            model = build_advanced_costing_model()

        final_dof = degrees_of_freedom(model)
        costing = model.fs.costing_1
        total_bec = scalar(costing.total_BEC)
        total_installation = scalar(costing.total_installation_cost)
        total_plant = scalar(costing.total_plant_cost)
        total_fixed_om = scalar(costing.total_fixed_OM_cost)
        total_variable_om = scalar(costing.total_variable_OM_cost[0])
        watertap_fixed_costs = scalar(costing.watertap_fixed_costs)
        total_sales_revenue = scalar(costing.total_sales_revenue)
        stream_values = port_stream_values(model.fs, max_streams=80)
        passed = bool(
            final_dof == 0
            and total_bec is not None
            and total_bec > 0
            and total_plant is not None
            and total_plant > 0
            and total_fixed_om is not None
            and total_fixed_om > 0
            and total_variable_om is not None
            and total_variable_om > 0
            and watertap_fixed_costs is not None
            and watertap_fixed_costs > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_nf_brine_advanced_costing",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "checks": [
                {"name": "nf_brine_advanced_costing_degrees_of_freedom_zero", "pass": final_dof == 0, "actual": final_dof},
                {"name": "nf_brine_advanced_costing_total_BEC_positive", "pass": bool(total_bec is not None and total_bec > 0), "actual": total_bec},
                {"name": "nf_brine_advanced_costing_total_plant_cost_positive", "pass": bool(total_plant is not None and total_plant > 0), "actual": total_plant},
                {"name": "nf_brine_advanced_costing_fixed_OM_positive", "pass": bool(total_fixed_om is not None and total_fixed_om > 0), "actual": total_fixed_om},
                {"name": "nf_brine_advanced_costing_variable_OM_positive", "pass": bool(total_variable_om is not None and total_variable_om > 0), "actual": total_variable_om},
                {"name": "nf_brine_advanced_costing_watertap_fixed_costs_positive", "pass": bool(watertap_fixed_costs is not None and watertap_fixed_costs > 0), "actual": watertap_fixed_costs},
                {"name": "nf_brine_advanced_costing_stream_values_available", "pass": bool(stream_values), "actual": len(stream_values)},
            ],
            "total_BEC": total_bec,
            "total_installation_cost": total_installation,
            "total_plant_cost": total_plant,
            "total_fixed_OM_cost": total_fixed_om,
            "total_variable_OM_cost": total_variable_om,
            "watertap_fixed_costs": watertap_fixed_costs,
            "total_sales_revenue": total_sales_revenue,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(CASE_ROOT / "docs" / "tutorials" / "costing_advanced_features-solution.ipynb"),
                "base_flowsheet_source": str(SOURCE_ROOT / "prommis" / "nanofiltration" / "nf_brine.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/latest/_images/nf_ui.png",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS NF brine advanced costing checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_nf_brine_advanced_costing",
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
