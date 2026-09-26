#!/usr/bin/env python3
"""Build twelve non-duplicative, solved IDAES-GTEP engineering variants."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyomo.contrib.appsi.solvers.highs import Highs
from pyomo.core import Objective, TransformationFactory
from pyomo.environ import value
from pyomo.util.model_size import build_model_size_report

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_idaes_gtep_official_v1 import (  # noqa: E402
    REGISTRY_PATH,
    SOURCE_BASE_URL,
    SOURCE_COMMIT,
    SOURCE_ROOT,
    VALIDATION_ROOT,
    data_counts,
    load,
    write,
)
from solve_idaes_gtep_recovery_v1 import (  # noqa: E402
    fixed_copper_plate_sets,
    load_large_prescient,
)
from gtep.gtep_data import ExpansionPlanningData  # noqa: E402
from gtep.gtep_model import ExpansionPlanningModel  # noqa: E402




SUITE = "idaes_gtep_engineering_variants_v2"
MANIFEST_PATH = ROOT / "experiment/case_variants/idaes_gtep_engineering_variants_v2.json"


@dataclass(frozen=True)
class Variant:
    case_id: str
    label: str
    dataset: str
    scenario: str
    flow_model: str
    official_figure: str
    source_file: str

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


VARIANTS = (
    Variant("gtep_v2_wecc_reduced_dc_expansion", "GTEP WECC Reduced DC Expansion", "WECC_Reduced_USAEE", "wecc_reduced_dc", "DC", "model_investment_stage.png", "gtep/data/WECC_Reduced_USAEE"),
    Variant("gtep_v2_wecc_reduced_copperplate", "GTEP WECC Reduced Copper-Plate Planning", "WECC_Reduced_USAEE", "wecc_reduced_cp", "CP", "model_investment_stage.png", "gtep/data/WECC_Reduced_USAEE"),
    Variant("gtep_v2_wecc_34bus_dc_corridor", "GTEP WECC 34-Bus DC Corridor Planning", "WECC_USAEE", "wecc_full_corridor", "DC", "model_investment_stage.png", "gtep/data/WECC_USAEE"),
    Variant("gtep_v2_9bus_generation_storage_expansion", "GTEP 9-Bus Generation and Storage Expansion", "9_bus_GTEP_dir", "generation_storage", "DC", "model_stages.png", "gtep/data/9_bus_GTEP_dir/storage.csv"),
    Variant("gtep_v2_9bus_storage_only_investment", "GTEP 9-Bus Storage-Only Investment", "9_bus_GTEP_dir", "storage_only", "DC", "model_investment_stage.png", "gtep/data/9_bus_GTEP_dir/storage.csv"),
    Variant("gtep_v2_9bus_renewable_candidates", "GTEP 9-Bus Renewable-Only Candidates", "9_bus_GTEP_dir", "renewable_candidates", "DC", "model_investment_stage.png", "gtep/driver_matt.py"),
    Variant("gtep_v2_9bus_firm_candidates", "GTEP 9-Bus Firm-Capacity Candidates", "9_bus_GTEP_dir", "firm_candidates", "DC", "model_investment_stage.png", "gtep/driver_matt.py"),
    Variant("gtep_v2_9bus_generation_transmission_coexpansion", "GTEP 9-Bus Generation and Transmission Co-Expansion", "9_bus_GTEP_dir", "generation_transmission", "DC", "model_stages.png", "gtep/driver_matt.py"),
    Variant("gtep_v2_5bus_reserve_constrained_commitment", "GTEP 5-Bus Reserve-Constrained Commitment", "5bus", "reserve_commitment", "DC", "model_commitment_stage.png", "gtep/RA_driver.py"),
    Variant("gtep_v2_5bus_n1_line_derating", "GTEP 5-Bus N-1 Line-Derating Proxy", "5bus", "line_derating", "DC", "model_dispatch_stage.png", "gtep/driver.py"),
    Variant("gtep_v2_123bus_high_growth_coal_transition", "GTEP 123-Bus High-Growth Coal Transition", "123_Bus_Coal", "high_growth_coal", "CP", "model_stages.png", "gtep/driver_coal.py"),
    Variant("gtep_v2_123bus_resilience_no_outage_baseline", "GTEP 123-Bus Resilience No-Outage Baseline", "123_Bus_Resil_Week", "resilience_baseline", "DC", "model_dispatch_stage.png", "gtep/driver_resil_week.py"),
)


def source_url(variant: Variant) -> str:
    return f"{SOURCE_BASE_URL}/{variant.source_file}"


def all_model_data(data: ExpansionPlanningData):
    seen = set()
    for model_data in [data.md, *data.representative_data]:
        if id(model_data) not in seen:
            seen.add(id(model_data))
            yield model_data


def clone_generator_candidates(data: ExpansionPlanningData, allowed_types: set[str]) -> int:
    count = 0
    for model_data in all_model_data(data):
        generators = model_data.data["elements"]["generator"]
        additions = {}
        for name, settings in generators.items():
            if str(settings.get("unit_type") or "").upper() not in allowed_types:
                continue
            candidate = copy.deepcopy(settings)
            candidate["in_service"] = False
            candidate["investment_cost"] = max(float(candidate.get("investment_cost") or 1), 1)
            additions[f"candidate_{name}-c"] = candidate
        generators.update(additions)
        count = max(count, len(additions))
    return count


def clone_branch_candidates(data: ExpansionPlanningData, count: int = 3) -> int:
    cloned = 0
    for model_data in all_model_data(data):
        branches = model_data.data["elements"]["branch"]
        ranked = sorted(
            branches.items(),
            key=lambda row: float(row[1].get("rating_long_term") or 0),
            reverse=True,
        )[:count]
        additions = {}
        for name, settings in ranked:
            candidate = copy.deepcopy(settings)
            candidate["in_service"] = False
            candidate["capital_cost"] = max(float(candidate.get("capital_cost") or 1), 1)
            additions[f"candidate_{name}-c"] = candidate
        branches.update(additions)
        cloned = max(cloned, len(additions))
    return cloned


def load_small(dataset: str, *, stages=1, commitment=1, dispatch=1) -> ExpansionPlanningData:
    data = ExpansionPlanningData(
        stages=stages,
        num_reps=1,
        len_reps=1,
        num_commit=commitment,
        num_dispatch=dispatch,
    )
    kwargs = {}
    if dataset.startswith("WECC"):
        kwargs["representative_dates"] = ["2020-01-28 00:00"]
    data.load_prescient(str(SOURCE_ROOT / "gtep/data" / dataset), **kwargs)
    return data


def adapt_wecc_dc_corridors(data: ExpansionPlanningData) -> int:
    count = 0
    for model_data in all_model_data(data):
        elements = model_data.data["elements"]
        corridors = elements.get("dc_branch", {})
        for settings in corridors.values():
            settings.setdefault("reactance", 0.1)
            settings.setdefault("branch_type", "line")
            settings.setdefault("in_service", True)
            settings.setdefault("resistance", 0.0)
            settings.setdefault("charging_susceptance", 0.0)
            settings.setdefault("loss_rate", 0.0)
            settings.setdefault("distance", 1.0)
            settings.setdefault("capital_cost", 1.0)
            settings.setdefault("capital_multiplier", 1.0)
            settings.setdefault("extension_multiplier", 1.0)
        elements["branch"] = corridors
        elements["dc_branch"] = {}
        count = max(count, len(corridors))
    return count


def multiply_load(data: ExpansionPlanningData, factor: float) -> None:
    for model_data in all_model_data(data):
        for settings in model_data.data["elements"]["load"].values():
            load_value = settings.get("p_load")
            if isinstance(load_value, dict):
                load_value["values"] = [factor * float(item) for item in load_value["values"]]
            else:
                settings["p_load"] = factor * float(load_value or 0)


def solve_variant(variant: Variant) -> dict:
    scenario = variant.scenario
    configuration = {
        "scenario": scenario,
        "dataset": variant.dataset,
        "flow_model": variant.flow_model,
        "big_m": 1e6,
        "compatibility_fixes": [],
    }
    config = {
        "flow_model": variant.flow_model,
        "transmission": variant.flow_model == "DC",
        "storage": False,
        "include_investment": True,
        "include_commitment": False,
        "include_redispatch": True,
        "scale_loads": False,
        "scale_texas_loads": False,
    }

    if scenario.startswith("wecc_reduced"):
        data = load_small(variant.dataset)
        config["transmission"] = scenario.endswith("dc")
        configuration["candidate_generator_count"] = clone_generator_candidates(data, {"WIND", "PV", "CC", "CT"})
        if config["transmission"]:
            configuration["candidate_corridor_count"] = clone_branch_candidates(data)
    elif scenario == "wecc_full_corridor":
        data = load_small(variant.dataset)
        configuration["dc_corridor_count"] = adapt_wecc_dc_corridors(data)
        configuration["candidate_corridor_count"] = clone_branch_candidates(data, 5)
        configuration["compatibility_fixes"].append({
            "id": "wecc_dc_corridor_reactance_proxy",
            "reason": "Official dc_branch rows omit reactance required by the current GTEP DC-flow equation; use a uniform 0.1 p.u. corridor proxy.",
        })
    elif scenario in {"generation_storage", "storage_only", "renewable_candidates", "firm_candidates", "generation_transmission"}:
        data = load_small(variant.dataset, stages=1, commitment=2, dispatch=2)
        if scenario in {"generation_storage", "storage_only"}:
            config["storage"] = True
            configuration["official_storage_candidate_count"] = len(data.md.data["elements"].get("storage", {}))
        if scenario == "generation_storage":
            configuration["candidate_generator_count"] = clone_generator_candidates(data, {"WIND", "PV", "CC", "CT"})
        elif scenario == "renewable_candidates":
            configuration["candidate_generator_count"] = clone_generator_candidates(data, {"WIND", "PV"})
        elif scenario == "firm_candidates":
            configuration["candidate_generator_count"] = clone_generator_candidates(data, {"CC", "CT"})
        elif scenario == "generation_transmission":
            configuration["candidate_generator_count"] = clone_generator_candidates(data, {"WIND", "PV", "CC", "CT"})
            configuration["candidate_corridor_count"] = clone_branch_candidates(data)
    elif scenario == "reserve_commitment":
        data = load_small(variant.dataset, commitment=4, dispatch=2)
        config["include_investment"] = False
        config["include_commitment"] = True
        for model_data in all_model_data(data):
            model_data.data["system"]["min_operating_reserve"] = 0.20
            model_data.data["system"]["min_spinning_reserve"] = 0.15
        configuration.update(min_operating_reserve=0.20, min_spinning_reserve=0.15)
    elif scenario == "line_derating":
        data = load_small(variant.dataset, commitment=1, dispatch=2)
        config["include_investment"] = False
        target = None
        for model_data in all_model_data(data):
            branches = model_data.data["elements"]["branch"]
            if target is None:
                target = max(branches, key=lambda name: float(branches[name].get("rating_long_term") or 0))
            for field in ("rating_long_term", "rating_short_term", "rating_emergency"):
                if branches[target].get(field) is not None:
                    branches[target][field] = 0.40 * float(branches[target][field])
        configuration.update(derated_branch=target, retained_rating_fraction=0.40)
    elif scenario == "high_growth_coal":
        data, repaired_ramps = load_large_prescient(variant.dataset, "2019-01-28 00:00")
        multiply_load(data, 1.15)
        configuration["load_growth_factor"] = 1.15
        configuration["repaired_ramp_rows"] = repaired_ramps
        configuration["candidate_generator_count"] = clone_generator_candidates(data, {"WIND", "PV"})
        config["transmission"] = False
    elif scenario == "resilience_baseline":
        data, repaired_ramps = load_large_prescient(variant.dataset, "2019-05-20 00:00")
        configuration["repaired_ramp_rows"] = repaired_ramps
        configuration["outage_mapping_count"] = 0
        config["include_investment"] = False
    else:
        raise KeyError(scenario)

    model = ExpansionPlanningModel(data=data)
    for name, setting in config.items():
        model.config[name] = setting
    with fixed_copper_plate_sets():
        model.create_model()
        size = build_model_size_report(model.model)
        TransformationFactory("gdp.bound_pretransformation").apply_to(model.model)
        TransformationFactory("gdp.bigm").apply_to(model.model, bigM=configuration["big_m"])
        result = Highs().solve(model.model)
    termination = result.termination_condition.name
    if termination != "optimal":
        raise RuntimeError(f"{variant.case_id}: HiGHS termination {termination}")
    objectives = list(model.model.component_data_objects(Objective, active=True))
    return {
        "pass": True,
        "status": "optimized",
        "stage": "gtep_variant_gdp_bigm_highs",
        "termination_condition": termination,
        "solver": "highs",
        "metrics": {
            **data_counts(data),
            "storage_count": len(data.md.data["elements"].get("storage", {})),
            "variables_before_gdp_transform": size.activated.variables,
            "constraints_before_gdp_transform": size.activated.constraints,
            "disjunctions_before_gdp_transform": size.activated.disjunctions,
            "objective_value": value(objectives[0]) if objectives else None,
        },
        "configuration": configuration,
        "error": None,
    }


def topology(variant: Variant, evidence: dict) -> tuple[dict, dict]:
    specialty = {
        "generation_storage": ("storage", "StoragePortfolio", "candidate battery storage investment and operation"),
        "storage_only": ("storage", "StoragePortfolio", "storage-only investment portfolio"),
        "renewable_candidates": ("portfolio", "RenewablePortfolio", "wind and photovoltaic candidate portfolio"),
        "firm_candidates": ("portfolio", "FirmCapacityPortfolio", "firm thermal candidate portfolio"),
        "generation_transmission": ("corridors", "TransmissionNetwork", "candidate transmission corridors"),
        "reserve_commitment": ("reserve", "ReserveRequirement", "operating and spinning reserve requirements"),
        "line_derating": ("contingency", "TransmissionNetwork", "critical line derating proxy"),
        "high_growth_coal": ("growth", "LoadGrowthScenario", "15 percent high-load growth scenario"),
        "resilience_baseline": ("baseline", "OutageScenario", "no-outage resilience comparator"),
    }.get(variant.scenario)
    units = [
        {"id": "data", "kind": "GTEPData", "package": "egret_prescient", "stage": "data", "role": f"official {variant.dataset} data", "constructor": {}, "constraint_template": None},
        {"id": "investment", "kind": "InvestmentStage", "package": "pyomo_gdp", "stage": "planning", "role": "generation, storage, and transmission investment decisions", "constructor": {}, "constraint_template": None},
        {"id": "commitment", "kind": "CommitmentStage", "package": "pyomo_gdp", "stage": "operations", "role": "commitment and reserve decisions", "constructor": {}, "constraint_template": None},
        {"id": "dispatch", "kind": "DispatchStage", "package": "egret", "stage": "operations", "role": "economic dispatch and load balance", "constructor": {}, "constraint_template": None},
        {"id": "network", "kind": "TransmissionNetwork", "package": "egret", "stage": "network", "role": f"{variant.flow_model} network representation", "constructor": {}, "constraint_template": None},
    ]
    if specialty:
        units.append({"id": specialty[0], "kind": specialty[1], "package": "gtep", "stage": "scenario", "role": specialty[2], "constructor": {}, "constraint_template": None})
    units.append({"id": "plan", "kind": "ExpansionPlan", "package": "pyomo", "stage": "solution", "role": "optimized investment and operating plan", "constructor": {}, "constraint_template": None})
    chain = [unit["id"] for unit in units]
    arcs = [{"id": f"{a}_to_{b}", "source": f"{a}.outlet", "destination": f"{b}.inlet", "stage": "model_link", "role": "GTEP hierarchy linkage", "tear_candidate": False} for a, b in zip(chain, chain[1:])]
    specs = [{"target": "gtep", "variable": key, "value": val, "units": "categorical", "role": "engineering variant configuration", "source": "variant_manifest", "source_url": source_url(variant)} for key, val in evidence["configuration"].items() if key != "compatibility_fixes"]
    ir = {
        "schema_version": "topology_ir/1", "case_id": variant.case_id, "family": "family_idaes_gtep",
        "process_type": variant.label, "source_url": source_url(variant),
        "source_basis": [f"Official IDAES-GTEP data and model at commit {SOURCE_COMMIT}.", f"Official flowchart: docs/images/{variant.official_figure}."],
        "property_packages": {"egret_prescient": {"dataset": variant.dataset}, "pyomo_gdp": {"transformation": "gdp.bigm"}},
        "components": {"planning": ["generation", "storage", "transmission", "load", "reserve", "investment", "dispatch"]},
        "units": units, "arcs": arcs, "feed_specs": specs, "unit_specs": [],
        "unconnected_feed_ports": ["data.outlet"], "unconnected_product_ports": ["plan.inlet"],
        "tear_streams": [], "translator_constraint_templates": {}, "translator_constraints": [],
        "initialization": {"strategy": "official data load, recorded scenario mutation, GDP Big-M, HiGHS", "solve_order": chain},
        "solve": {"solver": "highs", "steady_state": False, "expected_dof": None},
        "required_entries": ["ExpansionPlanningData", "ExpansionPlanningModel", "gdp.bigm"],
        "notes_for_agent_a": ["Engineering variant suite; do not merge with the nine official-driver identities.", "The source flowchart is copied byte-for-byte from the official GTEP repository."],
    }
    sir = {"schema_version": "spec_ir/1", "case_id": variant.case_id, "family": ir["family"], "source_url": source_url(variant), "topology_schema_version": "topology_ir/1", "specs": specs, "terminal_feed_ports": ir["unconnected_feed_ports"], "terminal_product_ports": ir["unconnected_product_ports"], "translator_constraint_templates": {}, "initialization": ir["initialization"], "solve": ir["solve"]}
    return ir, sir


def materialize(variant: Variant) -> dict:
    output = VALIDATION_ROOT / variant.case_id
    report_path = output / "native_solve_report.json"
    if report_path.is_file():
        report = load(report_path)
        if report.get("case_fingerprint") != variant.fingerprint:
            raise RuntimeError(f"Fingerprint mismatch for {variant.case_id}")
        return report
    evidence = solve_variant(variant)
    evidence.update({
        "case_id": variant.case_id, "case_family": "idaes_gtep", "case_fingerprint": variant.fingerprint,
        "suite": SUITE, "dataset": variant.dataset, "source_url": source_url(variant), "source_commit": SOURCE_COMMIT,
        "official_flowchart": f"docs/images/{variant.official_figure}",
        "claim_boundary": "Solved IDAES-GTEP engineering variant with the exact recorded data mutation and reduced temporal configuration; distinct from official-driver case identities.",
    })
    ir, sir = topology(variant, evidence)
    output.mkdir(parents=True, exist_ok=False)
    write(output / f"{variant.case_id}_topology_ir.json", ir)
    write(output / f"{variant.case_id}_spec_ir.json", sir)
    write(report_path, evidence)
    write(output / "topology_prebuild_report_attempt0.json", {"pass": True, "case_id": variant.case_id, "unit_count": len(ir["units"]), "arc_count": len(ir["arcs"])})
    images = SOURCE_ROOT / "docs/images"
    for image in ("model_stages.png", "model_investment_stage.png", "model_commitment_stage.png", "model_dispatch_stage.png"):
        shutil.copyfile(images / image, output / f"official_{image}")
    shutil.copyfile(images / variant.official_figure, output / "source_flowchart.png")
    write(output / "official_flowchart_provenance.json", {"source_commit": SOURCE_COMMIT, "source_path": f"docs/images/{variant.official_figure}", "source_url": f"{SOURCE_BASE_URL}/docs/images/{variant.official_figure}"})
    fv = stage_fv_data(variant.case_id, topology_ir_fv(variant.case_id, ir), "solve")
    write(output / "idaes_flowsheet_visualization.json", fv)
    return evidence


def registry_record(variant: Variant, evidence: dict, order: int) -> dict:
    base = f"validation/VectorEngine_qwen36_validation/{variant.case_id}"
    return {
        "case_key": variant.case_id, "label": variant.label, "family": "gtep", "ecosystem": "IDAES-GTEP", "process_family": "grid_expansion_planning",
        "tags": ["gtep", "grid_expansion", "engineering_variant", variant.scenario, variant.dataset.lower()],
        "aliases": [variant.label.lower(), variant.case_id.replace("_", " ")], "suites": [SUITE], "order": order, "lifecycle": "active",
        "display_prompt": f"Build and optimize the {variant.label} engineering scenario using official IDAES-GTEP data and the corresponding official model-stage flowchart.",
        "selection": {
            "case_key": variant.case_id, "family": "gtep", "run_id": variant.case_id, "selected_run_id": variant.case_id,
            "status": "optimized", "selected_status": "optimized", "complexity_level": "grid_planning_variant",
            "execution_status": "executed_pass", "evidence_maturity": "native_optimized_variant", "claim_boundary": evidence["claim_boundary"],
            "topology_ir_file": f"{base}/{variant.case_id}_topology_ir.json", "spec_ir_file": f"{base}/{variant.case_id}_spec_ir.json",
            "solve_report_file": f"{base}/native_solve_report.json", "selected_validation_dir": base,
            "source_flowchart_file": f"{base}/source_flowchart.png", "source_manifest_path": source_url(variant), "selected_by": SUITE,
        },
        "provenance": {"created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "created_by": Path(__file__).name, "source_commit": SOURCE_COMMIT, "source_path": variant.source_file, "dataset": variant.dataset, "case_fingerprint": variant.fingerprint},
    }


def merge_registry(evidence_by_id: dict[str, dict]) -> None:
    registry = load(REGISTRY_PATH)
    existing = [row for row in registry["cases"] if SUITE in row.get("suites", [])]
    expected = {variant.case_id for variant in VARIANTS}
    if existing:
        if {row["case_key"] for row in existing} != expected:
            raise RuntimeError("Existing GTEP v2 suite differs from manifest")
        return
    collisions = expected & {row["case_key"] for row in registry["cases"]}
    if collisions:
        raise RuntimeError(f"Case ID collisions: {sorted(collisions)}")
    start = max(row["order"] for row in registry["cases"]) + 1
    registry["cases"].extend(registry_record(variant, evidence_by_id[variant.case_id], start + index) for index, variant in enumerate(VARIANTS))
    registry["suite_contracts"][SUITE] = {"expected_case_count": 12, "frozen": False, "stage": "native_optimized_variant"}
    registry["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write(REGISTRY_PATH, registry)


def main() -> None:
    np.random.seed(0)
    write(MANIFEST_PATH, {"schema_version": 1, "suite": SUITE, "case_count": 12, "source_commit": SOURCE_COMMIT, "cases": [{**asdict(variant), "fingerprint": variant.fingerprint, "source_url": source_url(variant)} for variant in VARIANTS]})
    evidence = {variant.case_id: materialize(variant) for variant in VARIANTS}
    merge_registry(evidence)
    print(json.dumps({"pass": True, "case_count": len(evidence), "results": [{"case_id": key, "status": value_["status"], "objective_value": value_["metrics"]["objective_value"]} for key, value_ in evidence.items()]}, indent=2))


if __name__ == "__main__":
    main()
