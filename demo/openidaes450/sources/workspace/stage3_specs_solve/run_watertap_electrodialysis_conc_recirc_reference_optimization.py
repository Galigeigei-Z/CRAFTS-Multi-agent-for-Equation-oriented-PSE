#!/usr/bin/env python3
"""Run the WaterTAP one-stack electrodialysis concentrate-recirculation optimization solve."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))
from watertap_streams import streams_from_arcs  # noqa: E402
from optimization_plan_contract import plan_provenance, validate_optimization_plan  # noqa: E402

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/flowsheets/electrodialysis_1stack_conc_recirc.html"
ARC_ALIASES = {
    "arc0": "feed_to_separator",
    "arc1b": "separator_to_diluate_pump",
    "arc1f": "diluate_pump_to_edstack",
    "arc2": "separator_to_concentrate_mixer",
    "arc3b": "mixer_to_concentrate_pump",
    "arc3f": "concentrate_pump_to_edstack",
    "arc4": "edstack_diluate_to_product",
    "arc5": "edstack_concentrate_to_recycle_separator",
    "arc6": "recycle_separator_to_disposal",
    "arc7": "recycle_separator_to_mixer",
}
OPTIMIZATION_VARIABLES = (
    "fs.EDstack.voltage_applied[0]",
    "fs.EDstack.cell_pair_num",
    "fs.EDstack.cell_length",
)
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "minimize levelized cost of water",
    "variables_to_unfix": [
        "fs.EDstack.voltage_applied[0]",
        "fs.EDstack.cell_pair_num",
        "fs.EDstack.cell_length",
    ],
    "target_dof": 1,
    "constraints": ["product sodium concentration = 1.7094 mol/m3"],
}


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _set_simulation_conditions(model: Any, ed: Any) -> None:
    init_arg = {
        ("flow_vol_phase", "Liq"): 5.2e-4,
        ("conc_mol_phase_comp", ("Liq", "Na_+")): 34.188,
        ("conc_mol_phase_comp", ("Liq", "Cl_-")): 34.188,
    }
    model.fs.feed.properties.calculate_state(init_arg, hold_state=True)
    model.fs.EDstack.voltage_applied[0].fix(10)
    model.fs.recovery_vol_H2O.fix(0.7)
    ed._condition_base(model)


def _set_optimization_conditions(model: Any) -> None:
    from pyomo.environ import Objective  # noqa: PLC0415

    edstack = model.fs.EDstack
    voltage_upper = (
        edstack.voltage_x[0, 0].value
        / edstack.current_density_x[0, 0].value
        * edstack.current_dens_lim_x[0, 0].value
        * 1.5
    )
    edstack.voltage_applied[0].unfix()
    edstack.voltage_applied[0].setlb(0.1)
    edstack.voltage_applied[0].setub(voltage_upper)
    edstack.cell_pair_num.unfix()
    edstack.cell_pair_num.setlb(10)
    edstack.cell_pair_num.setub(1000)
    edstack.cell_length.unfix()
    model.fs.prod.properties[0].conc_mol_phase_comp["Liq", "Na_+"].fix(1.7094)
    model.fs.objective = Objective(expr=model.fs.costing.LCOW)


def run_case(optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        validate_optimization_plan(
            optimization_plan, OPTIMIZATION_PLAN_TEMPLATE, label="ED concentrate recirculation"
        )
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.flowsheets.electrodialysis import electrodialysis_1stack_conc_recirc as ed  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ed.build()
            _set_simulation_conditions(model, ed)
            ed.initialize_system(model)
            simulation_results = ed.solve(model, tee=False)
            _set_optimization_conditions(model)
            optimization_results = ed.solve(model, tee=False)
            model.fs.EDstack.cell_pair_num.fix(round(model.fs.EDstack.cell_pair_num.value))
            rounded_results = ed.solve(model, tee=False)

        sim_optimal = bool(check_optimal_termination(simulation_results))
        opt_optimal = bool(check_optimal_termination(optimization_results))
        rounded_optimal = bool(check_optimal_termination(rounded_results))
        lcow = _value(model.fs.costing.LCOW)
        sec = _value(model.fs.costing.specific_energy_consumption)
        recovery = _value(model.fs.recovery_vol_H2O)
        product_salinity = _value(model.fs.product_salinity)
        disposal_salinity = _value(model.fs.disposal_salinity)
        stream_values = streams_from_arcs(model, ARC_ALIASES)
        passed = (
            sim_optimal
            and opt_optimal
            and rounded_optimal
            and lcow is not None
            and lcow > 0
            and sec is not None
            and recovery is not None
            and product_salinity is not None
            and product_salinity <= 0.101
        )
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_electrodialysis_conc_recirc",
            "official_reference_url": SOURCE_URL,
            "simulation_termination_condition": str(simulation_results.solver.termination_condition),
            "optimization_termination_condition_before_integer_rounding": str(optimization_results.solver.termination_condition),
            "termination_condition": str(rounded_results.solver.termination_condition),
            "checks": [
                {"name": "ed_conc_recirc_pre_optimization_simulation_optimal", "pass": sim_optimal},
                {"name": "ed_conc_recirc_optimization_optimal", "pass": opt_optimal},
                {"name": "ed_conc_recirc_rounded_cell_pair_optimal", "pass": rounded_optimal},
                {"name": "ed_conc_recirc_lcow_positive", "pass": lcow is not None and lcow > 0},
                {"name": "ed_conc_recirc_product_quality_met", "pass": product_salinity is not None and product_salinity <= 0.101},
            ],
            "final_dof": degrees_of_freedom(model),
            "water_recovery": recovery,
            "levelized_cost_of_water": lcow,
            "specific_energy_consumption": sec,
            "product_salinity_kg_m3": product_salinity,
            "disposal_salinity_kg_m3": disposal_salinity,
            "membrane_area_m2": _value(model.fs.mem_area),
            "cell_pair_number": _value(model.fs.EDstack.cell_pair_num),
            "cell_length_m": _value(model.fs.EDstack.cell_length),
            "stack_voltage_v": _value(model.fs.EDstack.voltage_applied[0]),
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.electrodialysis.electrodialysis_1stack_conc_recirc",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            **plan_provenance(optimization_plan, OPTIMIZATION_PLAN_TEMPLATE),
            "error": None if passed else {"message": "WaterTAP ED concentrate recirculation optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_electrodialysis_conc_recirc",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ed_conc_recirc_optimization_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--optimization-plan", type=Path)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case(optimization_plan=args.optimization_plan)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
