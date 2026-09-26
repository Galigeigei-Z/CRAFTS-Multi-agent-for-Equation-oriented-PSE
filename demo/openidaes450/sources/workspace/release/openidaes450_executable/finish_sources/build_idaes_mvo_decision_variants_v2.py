#!/usr/bin/env python3
"""Build decision-distinct IDAES-MVO engineering variants."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from pyomo.environ import Constraint, Expression, NonNegativeReals, Objective, SolverFactory, Var, value
from pyomo.util.model_size import build_model_size_report


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_idaes_mvo_official_v1 as v1  # noqa: E402
from process_family.type.discretized import DiscretizedProcessFamily  # noqa: E402




SUITE = "idaes_mvo_decision_variants_v2"
MANIFEST_PATH = ROOT / f"experiment/case_variants/{SUITE}.json"
REGISTRY_PATH = ROOT / "experiment/case_registry/registry.json"
VALIDATION_ROOT = ROOT / "validation/VectorEngine_qwen36_validation"
MODULE_TYPES = ("Evaporator Area", "Condenser Area", "Compressor Design Flow")


@dataclass(frozen=True)
class DecisionCase:
    case_id: str
    label: str
    decision_type: str
    max_designs: tuple[int, int, int]
    policy: tuple[tuple[str, object], ...] = ()
    method: str = "discretized"
    filter_name: str = "all_56_variants"
    official_notebook: str = "discretized.ipynb"
    official_cell: int = 8

    @property
    def policy_dict(self) -> dict:
        return dict(self.policy)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


CASES = (
    DecisionCase("mvo_v2_full_standardized_111", "MVO Full-Family Standardized Platform 1/1/1", "module_budget", (1, 1, 1)),
    DecisionCase("mvo_v2_full_evaporator_limited_122", "MVO Full-Family Evaporator-Limited Platform 1/2/2", "module_budget", (1, 2, 2)),
    DecisionCase("mvo_v2_full_condenser_limited_212", "MVO Full-Family Condenser-Limited Platform 2/1/2", "module_budget", (2, 1, 2)),
    DecisionCase("mvo_v2_full_compressor_limited_221", "MVO Full-Family Compressor-Limited Platform 2/2/1", "module_budget", (2, 2, 1)),
    DecisionCase("mvo_v2_full_flexible_333", "MVO Full-Family Flexible Platform 3/3/3", "module_budget", (3, 3, 3)),
    DecisionCase("mvo_v2_hot_climate_weighted", "MVO Hot-Climate-Weighted Full Family", "scenario_weighting", (2, 2, 2), (("hot_temperature_threshold_c", 33), ("emphasis_weight", 3.0))),
    DecisionCase("mvo_v2_high_capacity_weighted", "MVO High-Capacity-Weighted Full Family", "scenario_weighting", (2, 2, 2), (("high_capacity_threshold_ton", 160), ("emphasis_weight", 3.0))),
    DecisionCase("mvo_v2_minimax_worst_variant_cost", "MVO Min-Max Worst-Variant-Cost Family", "minimax", (2, 2, 2)),
    DecisionCase("mvo_v2_legacy_platform_retrofit", "MVO Legacy Platform Retrofit and Expansion", "retrofit", (2, 2, 2), (("fixed_evaporator_area", 80.0), ("fixed_condenser_area", 25.0), ("fixed_compressor_flow", 120.0))),
    DecisionCase("mvo_v2_supply_constrained_alternatives", "MVO Supply-Constrained Module Alternatives", "supply_constraint", (2, 2, 2), (("unavailable_evaporator_area", 50.0), ("unavailable_condenser_area", 20.0), ("unavailable_compressor_flow", 60.0))),
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def scenario_weights(case: DecisionCase, variants) -> dict:
    weights = {tuple(v): 1.0 for v in variants}
    policy = case.policy_dict
    if "hot_temperature_threshold_c" in policy:
        threshold = policy["hot_temperature_threshold_c"]
        weights = {tuple(v): policy["emphasis_weight"] if v[1] >= threshold else 1.0 for v in variants}
    elif "high_capacity_threshold_ton" in policy:
        threshold = policy["high_capacity_threshold_ton"]
        weights = {tuple(v): policy["emphasis_weight"] if v[0] >= threshold else 1.0 for v in variants}
    return weights


def configure_model(family, case: DecisionCase) -> tuple[dict, float | None]:
    model = family.model
    policy = case.policy_dict
    weights = scenario_weights(case, family.V)
    formulation = {"decision_type": case.decision_type, "scenario_weights": weights}
    primary_optimum = None

    if case.decision_type == "scenario_weighting":
        model.obj.deactivate()
        model.weighted_family_cost = Expression(
            expr=sum(
                weights[tuple(v)] * model.x_va[v, a] * family.cost_va[tuple(v) + tuple(a)]
                for v in family.V for a in family.A_v[v]
            )
        )
        model.weighted_obj = Objective(expr=model.weighted_family_cost)
    elif case.decision_type == "minimax":
        model.obj.deactivate()
        model.worst_variant_cost = Var(domain=NonNegativeReals)

        def worst_cost_rule(m, *args):
            variant = tuple(args)
            return m.worst_variant_cost >= sum(
                m.x_va[variant, alternative] * family.cost_va[variant + tuple(alternative)]
                for alternative in family.A_v[variant]
            )

        model.worst_variant_cost_constraint = Constraint(family.V, rule=worst_cost_rule)
        model.minimax_obj = Objective(expr=model.worst_variant_cost)
    elif case.decision_type == "retrofit":
        fixed = {
            "Evaporator Area": policy["fixed_evaporator_area"],
            "Condenser Area": policy["fixed_condenser_area"],
            "Compressor Design Flow": policy["fixed_compressor_flow"],
        }
        for item in fixed.items():
            model.z_cl[item].fix(1)
        formulation["fixed_modules"] = fixed
    elif case.decision_type == "supply_constraint":
        unavailable = {
            "Evaporator Area": policy["unavailable_evaporator_area"],
            "Condenser Area": policy["unavailable_condenser_area"],
            "Compressor Design Flow": policy["unavailable_compressor_flow"],
        }
        for item in unavailable.items():
            model.z_cl[item].fix(0)
        formulation["unavailable_modules"] = unavailable
    return formulation, primary_optimum


def solve_case(case: DecisionCase) -> tuple[dict, bytes]:
    data = v1.filtered_data(case.filter_name)
    with tempfile.TemporaryDirectory(prefix="idaes_mvo_v2_") as temp:
        csv_path = Path(temp) / "transcritical-co2.csv"
        plot_path = Path(temp) / "result.png"
        data.to_csv(csv_path, index=False)
        started = time.monotonic()
        family = DiscretizedProcessFamily(v1.parameters(csv_path, case))
        initialize_seconds = time.monotonic() - started
        started = time.monotonic()
        family.build_model()
        formulation, _ = configure_model(family, case)
        build_seconds = time.monotonic() - started
        solver = SolverFactory("appsi_highs")
        solver.options["mip_rel_gap"] = 1e-4
        started = time.monotonic()
        family.results = solver.solve(family.model, tee=False)
        first_solve_seconds = time.monotonic() - started
        termination = str(family.results.solver.termination_condition)
        if termination != "optimal":
            raise RuntimeError(f"{case.case_id}: HiGHS termination {termination}")

        primary_worst_cost = None
        secondary_solve_seconds = 0.0
        if case.decision_type == "minimax":
            primary_worst_cost = value(family.model.worst_variant_cost)
            family.model.worst_variant_cost_cap = Constraint(
                expr=family.model.worst_variant_cost <= primary_worst_cost + 1e-6
            )
            family.model.minimax_obj.deactivate()
            family.model.lexicographic_total_cost = Objective(expr=family.model.family_cost)
            started = time.monotonic()
            family.results = solver.solve(family.model, tee=False)
            secondary_solve_seconds = time.monotonic() - started
            termination = str(family.results.solver.termination_condition)
            if termination != "optimal":
                raise RuntimeError(f"{case.case_id}: lexicographic HiGHS termination {termination}")

        selected = family.get_results_dict()
        family.plot(
            directory=str(plot_path),
            process_variant_column_names=["Capacity (tons)", "Max. Outside Air Temperature (deg. C)"],
            common_module_type_columns=["Evap. Area ($m^2$)", "Cond. Area ($m^2$)", "Compr. Flow (mol./s)"],
        )
        selected_costs = {}
        for v in family.V:
            raw_cost = family.cost_va[tuple(v) + tuple(selected[v])]
            selected_costs[str(tuple(v))] = float(raw_cost.item() if hasattr(raw_cost, "item") else raw_cost)
        weights = formulation["scenario_weights"]
        unweighted_total = sum(selected_costs[str(tuple(v))] for v in family.V)
        weighted_total = sum(weights[tuple(v)] * selected_costs[str(tuple(v))] for v in family.V)
        size = build_model_size_report(family.model)
        platform_modules = [
            {"module_type": str(module), "design": float(design)}
            for (module, design), variable in family.model.z_cl.items()
            if value(variable) >= 0.98
        ]
        if case.decision_type == "minimax":
            objective_value = primary_worst_cost
        elif case.decision_type == "scenario_weighting":
            objective_value = weighted_total
        else:
            objective_value = unweighted_total
        metrics = {
            "input_row_count": len(data),
            "process_variant_count": len(family.V),
            "feasible_alternative_count": sum(len(items) for items in family.A_v.values()),
            "variables": size.activated.variables,
            "constraints": size.activated.constraints,
            "objective_value": objective_value,
            "unweighted_total_cost": unweighted_total,
            "weighted_total_cost": weighted_total,
            "weighted_average_cost": weighted_total / sum(weights.values()),
            "worst_variant_cost": max(selected_costs.values()),
            "selected_family_design_count": len({tuple(items) for items in selected.values()}),
            "selected_platform_module_count": len(platform_modules),
            "selected_platform_modules": platform_modules,
            "selected_variant_costs": selected_costs,
            "initialize_seconds": initialize_seconds,
            "build_seconds": build_seconds,
            "solve_seconds": first_solve_seconds + secondary_solve_seconds,
            "primary_solve_seconds": first_solve_seconds,
            "secondary_solve_seconds": secondary_solve_seconds,
        }
        result_png = plot_path.read_bytes()

    configuration = {
        "decision_type": case.decision_type,
        "max_common_designs": dict(zip(MODULE_TYPES, case.max_designs)),
        "policy": case.policy_dict,
    }
    if case.decision_type == "scenario_weighting":
        emphasized = sum(weight > 1 for weight in weights.values())
        configuration["scenario_weight_summary"] = {
            "base_weight": 1.0,
            "emphasis_weight": case.policy_dict["emphasis_weight"],
            "emphasized_variant_count": emphasized,
            "total_variant_count": len(weights),
            "interpretation": "engineering emphasis weights, not observed probabilities",
        }
    configuration.update({key: value for key, value in formulation.items() if key != "scenario_weights"})
    report = {
        "pass": True,
        "status": "optimized",
        "stage": f"native_mvo_{case.decision_type}_highs",
        "termination_condition": "optimal",
        "solver": "appsi_highs",
        "execution_scope": "native",
        "metrics": metrics,
        "configuration": configuration,
        "error": None,
    }
    return report, result_png


def decision_kind(case: DecisionCase) -> tuple[str, str]:
    return {
        "module_budget": ("ModuleBudgetPolicy", "limits the number of standardized designs for each shared module type"),
        "scenario_weighting": ("ScenarioWeighting", "weights selected requirement scenarios in the family cost objective"),
        "minimax": ("WorstCaseObjective", "minimizes the most expensive process variant before total-cost tie breaking"),
        "retrofit": ("RetrofitConstraint", "retains installed platform modules while selecting expansion modules"),
        "supply_constraint": ("SupplyConstraint", "removes unavailable module sizes from the platform design space"),
    }[case.decision_type]


def topology(case: DecisionCase, report: dict) -> tuple[dict, dict]:
    ir, sir = v1.topology(case, report)
    kind, role = decision_kind(case)
    policy = {"id": "decision_policy", "kind": kind, "package": "pyomo", "stage": "policy", "role": role, "constructor": case.policy_dict, "constraint_template": None}
    platform_index = next(i for i, unit in enumerate(ir["units"]) if unit["id"] == "platform")
    ir["units"].insert(platform_index, policy)
    chain = [unit["id"] for unit in ir["units"]]
    ir["arcs"] = [{"id": f"{a}_to_{b}", "source": f"{a}.outlet", "destination": f"{b}.inlet", "stage": "optimization_link", "role": "MVO decision linkage", "tear_candidate": False} for a, b in zip(chain, chain[1:])]
    ir["case_id"] = case.case_id
    ir["process_type"] = case.label
    ir["source_basis"].append("Engineering decision variant; official dataset and discretized formulation are preserved, with the recorded policy applied explicitly.")
    ir["notes_for_agent_a"].append("This v2 case is distinct from the official 2/2/2 case through its explicit platform, objective, retrofit, or availability policy.")
    ir["initialization"]["solve_order"] = chain
    sir.update({"case_id": case.case_id, "initialization": ir["initialization"]})
    return ir, sir


def materialize(case: DecisionCase) -> dict:
    output = VALIDATION_ROOT / case.case_id
    report_path = output / "native_solve_report.json"
    if report_path.is_file():
        report = load(report_path)
        if report.get("case_fingerprint") != case.fingerprint:
            raise RuntimeError(f"Fingerprint mismatch for {case.case_id}")
        return report
    report, result_figure = solve_case(case)
    report.update({
        "case_id": case.case_id,
        "case_family": "idaes_mvo",
        "case_fingerprint": case.fingerprint,
        "suite": SUITE,
        "source_url": v1.source_url(case),
        "source_commit": v1.SOURCE_COMMIT,
        "official_figure_kind": "official_notebook_result_figure",
        "official_figure_source": "example/discretized.ipynb#cell-8",
        "claim_boundary": "Native HiGHS optimization of an engineering decision variant built on the official IDAES-MVO discretized formulation and complete 56-variant dataset.",
    })
    ir, sir = topology(case, report)
    output.mkdir(parents=True, exist_ok=False)
    write(output / f"{case.case_id}_topology_ir.json", ir)
    write(output / f"{case.case_id}_spec_ir.json", sir)
    write(report_path, report)
    write(output / "topology_prebuild_report_attempt0.json", {"pass": True, "case_id": case.case_id, "unit_count": len(ir["units"]), "arc_count": len(ir["arcs"])})
    official_figure = v1.notebook_png(case)
    (output / "official_notebook_result.png").write_bytes(official_figure)
    (output / "source_flowchart.png").write_bytes(official_figure)
    (output / "case_result.png").write_bytes(result_figure)
    write(output / "official_figure_provenance.json", {"source_commit": v1.SOURCE_COMMIT, "source_path": "example/discretized.ipynb", "notebook_cell": 8, "asset_kind": "executed_notebook_result_figure", "source_url": v1.source_url(case), "sha256": hashlib.sha256(official_figure).hexdigest()})
    fv = stage_fv_data(case.case_id, topology_ir_fv(case.case_id, ir), "solve")
    write(output / "idaes_flowsheet_visualization.json", fv)
    return report


def registry_record(case: DecisionCase, report: dict, order: int) -> dict:
    base = f"validation/VectorEngine_qwen36_validation/{case.case_id}"
    return {
        "case_key": case.case_id, "label": case.label, "family": "mvo", "ecosystem": "IDAES-MVO", "process_family": "process_family_design",
        "tags": ["mvo", "process_family_design", "transcritical_co2", "decision_variant", case.decision_type],
        "aliases": [case.label.lower(), case.case_id.replace("_", " ")], "suites": [SUITE], "order": order, "lifecycle": "active",
        "display_prompt": f"Optimize the {case.label} using the official IDAES-MVO transcritical CO2 dataset and the explicit {case.decision_type} policy.",
        "selection": {
            "case_key": case.case_id, "family": "mvo", "run_id": case.case_id, "selected_run_id": case.case_id,
            "status": "optimized", "selected_status": "optimized", "complexity_level": "process_family_decision_optimization",
            "execution_status": "executed_pass", "evidence_maturity": "native_optimized", "claim_boundary": report["claim_boundary"],
            "topology_ir_file": f"{base}/{case.case_id}_topology_ir.json", "spec_ir_file": f"{base}/{case.case_id}_spec_ir.json",
            "solve_report_file": f"{base}/native_solve_report.json", "selected_validation_dir": base,
            "source_flowchart_file": f"{base}/source_flowchart.png", "source_manifest_path": v1.source_url(case), "selected_by": SUITE,
        },
        "provenance": {"created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "created_by": Path(__file__).name, "source_commit": v1.SOURCE_COMMIT, "source_notebook": case.official_notebook, "case_fingerprint": case.fingerprint},
    }


def merge_registry(reports: dict[str, dict]) -> None:
    registry = load(REGISTRY_PATH)
    expected = {case.case_id for case in CASES}
    existing = [row for row in registry["cases"] if SUITE in row.get("suites", [])]
    if existing:
        if {row["case_key"] for row in existing} != expected:
            raise RuntimeError("Existing MVO v2 suite differs from manifest")
        return
    collisions = expected & {row["case_key"] for row in registry["cases"]}
    if collisions:
        raise RuntimeError(f"MVO v2 case ID collisions: {sorted(collisions)}")
    start = max(row["order"] for row in registry["cases"]) + 1
    registry["cases"].extend(registry_record(case, reports[case.case_id], start + index) for index, case in enumerate(CASES))
    registry["suite_contracts"][SUITE] = {"expected_case_count": len(CASES), "frozen": False, "stage": "native_optimized_decision_variant"}
    registry["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write(REGISTRY_PATH, registry)


def main() -> None:
    write(MANIFEST_PATH, {"schema_version": 1, "suite": SUITE, "case_count": len(CASES), "source_commit": v1.SOURCE_COMMIT, "cases": [{**asdict(case), "fingerprint": case.fingerprint, "source_url": v1.source_url(case)} for case in CASES]})
    reports = {case.case_id: materialize(case) for case in CASES}
    merge_registry(reports)
    print(json.dumps({"pass": True, "case_count": len(reports), "results": [{"case_id": case_id, "objective_value": report["metrics"]["objective_value"], "worst_variant_cost": report["metrics"]["worst_variant_cost"]} for case_id, report in reports.items()]}, indent=2))


if __name__ == "__main__":
    main()
