#!/usr/bin/env python3
"""Select WaterTAP ion-exchange regenerant reuse cycles under a Ca limit."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

SOURCE_URL = "https://watertap.readthedocs.io/en/1.4.0rc0/technical_reference/flowsheets/ion_exchange.html"
CA_MOLAR_MASS_KG_MOL = 0.040078
SPENT_REGENERANT_CA_LIMIT_KG_M3 = 30.0
SEARCH_CYCLES = range(1, 6)
OPTIMIZATION_PLAN_TEMPLATE = {
    "objective": "minimize levelized cost of water over regenerant reuse cycles",
    "variables_to_unfix": ["regenerant_use_cycles"],
    "target_dof": 1,
    "constraints": ["spent_regenerant_calcium_limit", "treated_product_calcium_limit"],
}


def _validate_plan(path: Path | None) -> None:
    if path is None:
        return
    candidate = json.loads(path.read_text(encoding="utf-8"))
    if candidate != OPTIMIZATION_PLAN_TEMPLATE:
        raise ValueError("OptimizationPlanIR does not match the registered ion-exchange template")


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case(optimization_plan: Path | None = None) -> dict[str, Any]:
    try:
        _validate_plan(optimization_plan)
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination, value  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.ion_exchange import ion_exchange_demo as ix_demo  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = ix_demo.ix_build(["Ca_2+"])
            ix_demo.set_operating_conditions(model)
            ix_demo.initialize_system(model)
            solver = get_solver()
            ix = model.fs.ion_exchange
            reuse_cycles = model.fs.costing.ion_exchange.regen_recycle

            ca_removed_mol_s = value(ix.regen.flow_mol_phase_comp[0, "Liq", "Ca_2+"])
            ca_load_per_service_cycle_mol = ca_removed_mol_s * value(ix.t_breakthru)
            regen_tank_volume_m3 = value(ix.regen_tank_vol)
            once_through_ca_kg_m3 = (
                ca_load_per_service_cycle_mol
                * CA_MOLAR_MASS_KG_MOL
                / regen_tank_volume_m3
            )

            search = []
            for cycles in SEARCH_CYCLES:
                reuse_cycles.fix(cycles)
                results = solver.solve(model)
                accumulated_ca = once_through_ca_kg_m3 * cycles
                feasible = accumulated_ca <= SPENT_REGENERANT_CA_LIMIT_KG_M3
                search.append(
                    {
                        "regenerant_use_cycles": cycles,
                        "termination_condition": str(results.solver.termination_condition),
                        "optimal": bool(check_optimal_termination(results)),
                        "contaminant_limit_feasible": feasible,
                        "spent_regenerant_ca_kg_m3": accumulated_ca,
                        "levelized_cost_of_water": value(model.fs.costing.LCOW),
                        "fresh_nacl_kg_year": value(ix.costing.flow_mass_regen_soln),
                        "average_brine_waste_m3_per_cycle": regen_tank_volume_m3 / cycles,
                    }
                )

            feasible_rows = [row for row in search if row["optimal"] and row["contaminant_limit_feasible"]]
            selected = min(feasible_rows, key=lambda row: row["levelized_cost_of_water"])
            selected_cycles = int(selected["regenerant_use_cycles"])
            reuse_cycles.fix(selected_cycles)
            final_results = solver.solve(model)

        final_optimal = bool(check_optimal_termination(final_results))
        final_dof = degrees_of_freedom(model)
        base = next(row for row in search if row["regenerant_use_cycles"] == 1)
        product_ca = _value(model.fs.product.properties[0].conc_mass_phase_comp["Liq", "Ca_2+"])
        salt_reduction = 1.0 - selected["fresh_nacl_kg_year"] / base["fresh_nacl_kg_year"]
        brine_reduction = 1.0 - selected["average_brine_waste_m3_per_cycle"] / base["average_brine_waste_m3_per_cycle"]
        passed = (
            final_optimal
            and final_dof == 0
            and selected_cycles == 3
            and selected["spent_regenerant_ca_kg_m3"] <= SPENT_REGENERANT_CA_LIMIT_KG_M3
            and product_ca is not None
            and product_ca <= 0.025
            and salt_reduction > 0.0
            and brine_reduction > 0.0
        )
        return {
            "pass": passed,
            "stage": "bounded_native_cycle_optimization",
            "case_family": "watertap_ix_regeneration_recycle",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(final_results.solver.termination_condition),
            "checks": [
                {"name": "ix_recycle_final_optimal", "pass": final_optimal},
                {"name": "ix_recycle_final_dof_zero", "pass": final_dof == 0},
                {"name": "spent_regenerant_ca_limit_met", "pass": selected["spent_regenerant_ca_kg_m3"] <= SPENT_REGENERANT_CA_LIMIT_KG_M3},
                {"name": "product_calcium_target_met", "pass": product_ca is not None and product_ca <= 0.025},
                {"name": "fresh_salt_reduced", "pass": salt_reduction > 0.0},
                {"name": "brine_waste_reduced", "pass": brine_reduction > 0.0},
            ],
            "final_dof": final_dof,
            "optimization_dof": 1,
            "decision_variables": {
                "regenerant_use_cycles": selected_cycles,
                "equivalent_regenerant_recycle_fraction": 1.0 - 1.0 / selected_cycles,
            },
            "metrics": {
                "spent_regenerant_ca_limit_kg_m3": SPENT_REGENERANT_CA_LIMIT_KG_M3,
                "spent_regenerant_ca_kg_m3": selected["spent_regenerant_ca_kg_m3"],
                "calcium_load_per_service_cycle_mol": ca_load_per_service_cycle_mol,
                "regeneration_tank_volume_m3": regen_tank_volume_m3,
                "breakthrough_time_s": _value(ix.t_breakthru),
                "rinse_time_s": _value(ix.t_rinse),
                "fresh_nacl_kg_year": selected["fresh_nacl_kg_year"],
                "fresh_nacl_reduction_fraction": salt_reduction,
                "average_brine_waste_m3_per_cycle": selected["average_brine_waste_m3_per_cycle"],
                "brine_waste_reduction_fraction": brine_reduction,
                "product_ca_kg_m3": product_ca,
                "target_ion_removal_fraction": 1.0 - product_ca / _value(model.fs.feed.properties[0].conc_mass_phase_comp["Liq", "Ca_2+"]),
                "levelized_cost_of_water": selected["levelized_cost_of_water"],
                "once_through_levelized_cost_of_water": base["levelized_cost_of_water"],
            },
            "search_results": search,
            "stream_values": {
                "service_feed": {"flow_m3_s": _value(model.fs.feed.properties[0].flow_vol_phase["Liq"]), "ca_kg_m3": _value(model.fs.feed.properties[0].conc_mass_phase_comp["Liq", "Ca_2+"])},
                "treated_product": {"flow_m3_s": _value(model.fs.product.properties[0].flow_vol_phase["Liq"]), "ca_kg_m3": product_ca},
                "spent_regenerant": {"tank_volume_m3": regen_tank_volume_m3, "ca_kg_m3_at_disposal": selected["spent_regenerant_ca_kg_m3"]},
                "regenerant_recycle": {"fraction": 1.0 - 1.0 / selected_cycles, "use_cycles": selected_cycles},
                "brine_waste": {"average_m3_per_service_cycle": selected["average_brine_waste_m3_per_cycle"]},
            },
            "source_summary": {
                "source": "watertap.flowsheets.ion_exchange.ion_exchange_demo with native WaterTAP regen_recycle costing parameter",
                "basis": "Discrete 1-5 use-cycle search; accumulated Ca is closed from the native regeneration outlet, breakthrough time, and regeneration-tank volume; specified disposal limit is 30 kg Ca/m3.",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "IX regenerant-recycle optimization checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "bounded_native_cycle_optimization",
            "case_family": "watertap_ix_regeneration_recycle",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ix_recycle_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--optimization-plan", type=Path)
    args = parser.parse_args()
    report = run_case(optimization_plan=args.optimization_plan)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
