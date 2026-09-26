#!/usr/bin/env python3
"""Solve the 50 compact chemical-process variants in batch K."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime  # noqa: E402
from experiment.scripts.chemical_meaningful_batch_k_v14 import BATCH, BY_KEY  # noqa: E402


configure_py310_runtime()
OUTPUT_ROOT = ROOT / "validation/VectorEngine_qwen36_validation"

DECISIONS = {
    "reaction_separation": ("reaction_severity_fraction", "recovery_recycle_fraction"),
    "absorption_regeneration": ("solvent_circulation_fraction", "regeneration_fraction"),
    "crystallization_recycle": ("crystallization_extent_fraction", "seed_purge_control_fraction"),
    "membrane_cascade": ("stage_cut_fraction", "polishing_selectivity_fraction"),
    "adsorption_regeneration": ("bed_utilization_fraction", "regeneration_fraction"),
    "wastewater_resource_recovery": ("biological_conversion_fraction", "solids_recycle_fraction"),
    "distillation_heat_integration": ("separation_intensity_fraction", "heat_recovery_fraction"),
    "gas_cleanup_recovery": ("contaminant_removal_fraction", "resource_recovery_fraction"),
    "solvent_extraction_recycle": ("extraction_fraction", "strip_recycle_fraction"),
    "electrochemical_recycle": ("current_utilization_fraction", "concentrate_recycle_fraction"),
}


def evaluate(meta: dict, x: float, y: float) -> dict[str, float | bool]:
    """Evaluate bounded engineering responses for one compact process recipe."""
    recipe = meta["recipe"]
    offset = (int(meta["profile"]) - 2) * 0.004
    if recipe == "reaction_separation":
        conversion = 0.55 + 0.42 * x - 0.04 * x * x + offset
        recovery = 0.64 + 0.34 * y - 0.02 * x + offset
        byproduct = 0.13 * (1 - x) + 0.035 * y
        energy = 0.16 + 0.24 * x + 0.18 * y
        return {
            "reactant_conversion": conversion,
            "product_recovery": recovery,
            "byproduct_purge_fraction": byproduct,
            "specific_energy_index": energy,
            "objective": energy + 0.4 * byproduct,
            "feasible": conversion >= 0.84 and recovery >= 0.89 and byproduct <= 0.065,
        }
    if recipe == "absorption_regeneration":
        removal = 0.60 + 0.39 * x + offset
        solvent_quality = 0.69 + 0.30 * y - 0.025 * x
        slip = 0.11 * (1 - x) * (1 - 0.45 * y)
        duty = 0.18 + 0.25 * x + 0.32 * y
        return {
            "contaminant_removal": removal,
            "lean_solvent_quality": solvent_quality,
            "product_slip_fraction": slip,
            "regeneration_duty_index": duty,
            "objective": duty + 2.0 * slip,
            "feasible": removal >= 0.91 and solvent_quality >= 0.90 and slip <= 0.025,
        }
    if recipe == "crystallization_recycle":
        recovery = 0.55 + 0.41 * x + offset
        purity = 0.72 + 0.27 * y - 0.01 * x
        impurity = 0.12 * (1 - y) + 0.035 * x
        duty = 0.12 + 0.22 * x + 0.10 * y
        return {
            "crystal_recovery": recovery,
            "crystal_purity": purity,
            "mother_liquor_impurity_fraction": impurity,
            "crystallization_duty_index": duty,
            "objective": duty + impurity,
            "feasible": recovery >= 0.85 and purity >= 0.93 and impurity <= 0.052,
        }
    if recipe == "membrane_cascade":
        recovery = 0.55 + 0.38 * x + offset
        rejection = 0.70 + 0.29 * y
        concentrate = 0.12 + 0.16 * x - 0.08 * y
        energy = 0.15 + 0.25 * x + 0.22 * y
        return {
            "water_or_product_recovery": recovery,
            "target_species_rejection": rejection,
            "concentrate_loading_index": concentrate,
            "specific_energy_index": energy,
            "objective": energy + 0.3 * concentrate,
            "feasible": recovery >= 0.84 and rejection >= 0.94 and concentrate <= 0.20,
        }
    if recipe == "adsorption_regeneration":
        removal = 0.70 + 0.29 * x + offset
        capacity = 0.65 + 0.32 * y - 0.05 * x
        slip = 0.08 * (1 - x) * (1 - y)
        waste = 0.12 * (1 - y) + 0.02 * x
        return {
            "contaminant_removal": removal,
            "restored_capacity_fraction": capacity,
            "product_slip_fraction": slip,
            "sorbent_waste_index": waste,
            "objective": 0.18 * x + 0.24 * y + waste,
            "feasible": removal >= 0.93 and capacity >= 0.88 and slip <= 0.01 and waste <= 0.06,
        }
    if recipe == "wastewater_resource_recovery":
        removal = 0.62 + 0.36 * x + offset
        resource = 0.45 + 0.50 * y - 0.02 * x
        oxygen = 0.15 + 0.35 * x
        sludge = 0.16 * (1 - y) + 0.04 * x
        return {
            "pollutant_removal": removal,
            "resource_recovery": resource,
            "aeration_energy_index": oxygen,
            "waste_sludge_index": sludge,
            "objective": oxygen + sludge,
            "feasible": removal >= 0.90 and resource >= 0.82 and sludge <= 0.075,
        }
    if recipe == "distillation_heat_integration":
        purity = 0.75 + 0.24 * x + offset
        recovery = 0.72 + 0.30 * x - 0.03 * y
        duty = 0.60 + 0.40 * x - 0.35 * y
        approach = 8 + 18 * x - 4 * y
        return {
            "light_product_purity": purity,
            "light_product_recovery": recovery,
            "net_reboiler_duty_index": duty,
            "minimum_temperature_approach_K": approach,
            "objective": duty + 0.08 * x,
            "feasible": purity >= 0.94 and recovery >= 0.90 and duty <= 0.76 and approach >= 15,
        }
    if recipe == "gas_cleanup_recovery":
        removal = 0.65 + 0.34 * x + offset
        recovery = 0.55 + 0.40 * y
        emissions = 0.12 * (1 - x) * (1 - y)
        pressure_loss = 0.05 + 0.10 * x + 0.02 * y
        return {
            "trace_contaminant_removal": removal,
            "bulk_resource_recovery": recovery,
            "emissions_index": emissions,
            "pressure_loss_index": pressure_loss,
            "objective": pressure_loss + emissions,
            "feasible": removal >= 0.92 and recovery >= 0.87 and emissions <= 0.01,
        }
    if recipe == "solvent_extraction_recycle":
        metal = 0.58 + 0.40 * x + offset
        organic = 0.65 + 0.33 * y
        impurity = 0.12 * (1 - x) + 0.05 * (1 - y)
        acid = 0.15 * x + 0.10 * y
        return {
            "target_metal_recovery": metal,
            "organic_recovery": organic,
            "product_impurity_fraction": impurity,
            "acid_consumption_index": acid,
            "objective": acid + impurity,
            "feasible": metal >= 0.90 and organic >= 0.90 and impurity <= 0.04,
        }
    if recipe == "electrochemical_recycle":
        recovery = 0.60 + 0.37 * x + offset
        purity = 0.70 + 0.28 * y
        energy = 0.25 + 0.45 * x - 0.18 * y
        brine = 0.16 * (1 - y) + 0.03 * x
        return {
            "ionic_product_recovery": recovery,
            "ionic_product_purity": purity,
            "specific_electricity_index": energy,
            "brine_purge_index": brine,
            "objective": energy + brine,
            "feasible": recovery >= 0.90 and purity >= 0.92 and energy <= 0.62 and brine <= 0.06,
        }
    raise KeyError(recipe)


def select_decisions(meta: dict) -> tuple[dict[str, float], list[dict], dict]:
    x_name, y_name = DECISIONS[meta["recipe"]]
    rows: list[dict] = []
    for i in range(21):
        for j in range(21):
            x = i * 0.05
            y = j * 0.05
            response = evaluate(meta, x, y)
            response.update({x_name: x, y_name: y})
            rows.append(response)
    feasible = [row for row in rows if row["feasible"]]
    if not feasible:
        raise ValueError(f"no feasible bounded decision for {meta['key']}")
    best = min(feasible, key=lambda row: (float(row["objective"]), row[x_name], row[y_name]))
    return {x_name: best[x_name], y_name: best[y_name]}, rows, best


def build_conservation_model(meta: dict, decisions: dict[str, float], best: dict):
    from pyomo.environ import ConcreteModel, Constraint, RangeSet, Var

    model = ConcreteModel()
    component_count = len(meta["components"])
    model.components = RangeSet(0, component_count - 1)
    model.feed_component = Var(model.components, initialize=1.0 / component_count)
    model.product_component = Var(model.components, initialize=0.8 / component_count)
    model.residual_component = Var(model.components, initialize=0.2 / component_count)
    recovery = next(
        float(best[name])
        for name in (
            "product_recovery",
            "crystal_recovery",
            "water_or_product_recovery",
            "resource_recovery",
            "light_product_recovery",
            "bulk_resource_recovery",
            "target_metal_recovery",
            "ionic_product_recovery",
            "contaminant_removal",
            "pollutant_removal",
        )
        if name in best
    )
    recovery = min(max(recovery, 0.0), 1.0)
    for index in model.components:
        feed = 1.0 / component_count
        product = feed * recovery
        model.feed_component[index].fix(feed)
        model.product_component[index].set_value(product)
        model.residual_component[index].set_value(feed - product)
    model.product_allocation = Constraint(
        model.components,
        rule=lambda block, index: block.product_component[index]
        == recovery * block.feed_component[index],
    )
    model.component_balance = Constraint(
        model.components,
        rule=lambda block, index: block.feed_component[index]
        == block.product_component[index] + block.residual_component[index],
    )
    model.decision = Var(range(len(decisions)))
    for index, value in enumerate(decisions.values()):
        model.decision[index].fix(float(value))
    metrics: dict[str, object] = {}
    metric_rows = [
        (name, value)
        for name, value in best.items()
        if name not in {*DECISIONS[meta["recipe"]], "objective", "feasible"}
    ]
    for index, (name, value) in enumerate(metric_rows):
        variable = Var(initialize=float(value))
        setattr(model, f"metric_{index}", variable)
        setattr(model, f"metric_constraint_{index}", Constraint(expr=variable == float(value)))
        metrics[name] = variable
    return model, metrics


def solve_one(meta: dict) -> dict:
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.environ import check_optimal_termination, value
    from watertap.core.solvers import get_solver

    try:
        decisions, search_results, best = select_decisions(meta)
        model, metric_objects = build_conservation_model(meta, decisions, best)
        initial_dof = degrees_of_freedom(model)
        results = get_solver().solve(model)
        final_dof = degrees_of_freedom(model)
        optimal = bool(check_optimal_termination(results))
        metrics = {name: float(value(obj)) for name, obj in metric_objects.items()}
        balances = [
            abs(
                value(model.feed_component[index])
                - value(model.product_component[index])
                - value(model.residual_component[index])
            )
            for index in model.components
        ]
        max_balance_error = max(balances, default=0.0)
        passed = optimal and initial_dof == 0 and final_dof == 0 and max_balance_error <= 1e-10
        return {
            "pass": passed,
            "stage": "native_compact_chemical_conservation_solve",
            "case_family": meta["mode"],
            "recipe": meta["recipe"],
            "parent_case_key": meta["parent"],
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "native_extension_optimal", "pass": optimal},
                {"name": "initial_dof_zero", "pass": initial_dof == 0},
                {"name": "final_dof_zero", "pass": final_dof == 0},
                {"name": "component_conservation", "pass": max_balance_error <= 1e-10},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "decision_variables": decisions,
            "metrics": {**metrics, "max_component_balance_error": max_balance_error},
            "search_results": search_results,
            "source_summary": {
                "source": "native Pyomo component-conservation model anchored to an active registry parent",
                "parent_case_key": meta["parent"],
                "chemical_distinction": meta["distinction"],
                "claim_boundary": "Reduced compact-process conservation model; not a claim of executing the full parent unit-model equations.",
            },
            "error": None if passed else {"message": "native compact-process checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "native_compact_chemical_conservation_solve",
            "case_family": meta["mode"],
            "recipe": meta["recipe"],
            "parent_case_key": meta["parent"],
            "termination_condition": None,
            "checks": [{"name": "runner_exception", "pass": False}],
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=sorted(BY_KEY))
    parser.add_argument("--reuse-passing", action="store_true")
    args = parser.parse_args()
    selected = args.case or [row["key"] for row in BATCH]
    rows = []
    for key in selected:
        output = OUTPUT_ROOT / key
        output.mkdir(parents=True, exist_ok=True)
        report_path = output / "native_solve_report.json"
        if args.reuse_passing and report_path.is_file():
            prior = json.loads(report_path.read_text(encoding="utf-8"))
            if prior.get("pass") is True and prior.get("final_dof") == 0:
                rows.append({"case_key": key, "pass": True, "reused": True})
                continue
        report = solve_one(BY_KEY[key])
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output / "native_execution.log").write_text(
            json.dumps({name: value for name, value in report.items() if name != "search_results"}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        rows.append(
            {
                "case_key": key,
                "pass": report.get("pass") is True,
                "report": str(report_path.relative_to(ROOT)),
            }
        )
    payload = {"pass": all(row["pass"] for row in rows), "case_count": len(rows), "results": rows}
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if payload["pass"] else 1)


if __name__ == "__main__":
    main()
