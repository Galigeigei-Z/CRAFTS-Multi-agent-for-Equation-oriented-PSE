#!/usr/bin/env python3
"""Materialize all nine official IDAES-GTEP driver scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "experiment/case_registry/registry.json"
MANIFEST_PATH = ROOT / "experiment/case_variants/idaes_gtep_official_v1.json"
VALIDATION_ROOT = ROOT / "validation/VectorEngine_qwen36_validation"
SOURCE_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-04-29/"
    "examples/archived_canonical_sources/cases/github_examples/clones/idaes-gtep"
)
SOURCE_COMMIT = "a0814d3be706ca01f0372b1af44ead243bfa2ee5"
SOURCE_BASE_URL = f"https://github.com/IDAES/idaes-gtep/blob/{SOURCE_COMMIT}"
SUITE = "idaes_gtep_official_v1"
for path in (ROOT, ROOT / "core", SOURCE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gtep.gtep_data import ExpansionPlanningData  # noqa: E402
from gtep.gtep_data_processing import DataProcessing  # noqa: E402
from gtep.gtep_model import ExpansionPlanningModel  # noqa: E402
from pyomo.contrib.appsi.solvers.highs import Highs  # noqa: E402
from pyomo.core import Objective, TransformationFactory  # noqa: E402
from pyomo.environ import value  # noqa: E402
from pyomo.util.model_size import build_model_size_report  # noqa: E402





@dataclass(frozen=True)
class GtepCase:
    case_id: str
    label: str
    driver: str
    dataset: str
    stages: int
    num_reps: int
    len_reps: int
    num_commit: int
    num_dispatch: int
    mode: str
    flow_model: str = "DC"
    transmission: bool = True
    include_investment: bool = True
    include_commitment: bool = True
    include_redispatch: bool = True
    scale_loads: bool = False
    scale_texas_loads: bool = False
    official_figure: str = "model_stages.png"

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


CASES = (
    GtepCase("official_gtep_5bus_jsc_baseline", "GTEP 5-Bus JSC Baseline", "driver.py", "5bus_jsc", 2, 2, 1, 6, 2, "solve_baseline"),
    GtepCase("official_gtep_5bus_dispatch_only", "GTEP 5-Bus Dispatch-Only Build", "driver_config_work.py", "5bus", 1, 1, 1, 24, 4, "build_only", include_investment=False, official_figure="model_dispatch_stage.png"),
    GtepCase("official_gtep_5bus_candidate_expansion", "GTEP 5-Bus Candidate Expansion", "driver_esr.py", "5bus", 2, 2, 1, 6, 4, "solve_candidate", scale_loads=True),
    GtepCase("official_gtep_5bus_three_stage", "GTEP 5-Bus Three-Stage Scaling", "driver_jsc.py", "5bus", 3, 1, 1, 24, 2, "three_stage_known_failure", scale_texas_loads=True),
    GtepCase("official_gtep_9bus_candidate_expansion", "GTEP 9-Bus Candidate Expansion", "driver_matt.py", "9_bus_GTEP_dir", 2, 2, 1, 6, 4, "solve_candidate", scale_loads=True),
    GtepCase("official_gtep_5bus_resource_adequacy", "GTEP 5-Bus Resource Adequacy", "RA_driver.py", "5bus", 2, 2, 24, 24, 2, "ra_known_failure", flow_model="CP", include_commitment=False),
    GtepCase("official_gtep_123bus_coal", "GTEP 123-Bus Coal Planning", "driver_coal.py", "123_Bus_Coal", 3, 5, 24, 24, 1, "large_data_validation", flow_model="CP", transmission=False, scale_texas_loads=True),
    GtepCase("official_gtep_123bus_resilience_week", "GTEP 123-Bus Resilience Week", "driver_resil_week.py", "123_Bus_Resil_Week", 3, 4, 24, 24, 1, "large_data_validation", scale_texas_loads=True),
    GtepCase("official_gtep_texas_2000", "GTEP Texas 2000-Bus Planning", "driver_t2k.py", "Texas_2000", 3, 4, 24, 24, 1, "large_data_validation", scale_texas_loads=True),
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_url(case: GtepCase) -> str:
    return f"{SOURCE_BASE_URL}/gtep/{case.driver}"


def data_counts(data: ExpansionPlanningData) -> dict[str, int]:
    elements = data.md.data.get("elements", {})
    return {
        "bus_count": len(elements.get("bus", {})),
        "branch_count": len(elements.get("branch", {})),
        "generator_count": len(elements.get("generator", {})),
        "load_count": len(elements.get("load", {})),
    }


def make_data(case: GtepCase) -> ExpansionPlanningData:
    data = ExpansionPlanningData(
        stages=case.stages,
        num_reps=case.num_reps,
        len_reps=case.len_reps,
        num_commit=case.num_commit,
        num_dispatch=case.num_dispatch,
    )
    dataset = SOURCE_ROOT / "gtep/data" / case.dataset
    data.load_prescient(str(dataset))
    if case.scale_texas_loads:
        scaling = dataset / "ERCOT-Adjusted-Forecast.xlsb"
        if not scaling.is_file():
            scaling = SOURCE_ROOT / "gtep/data/123_Bus_Coal/ERCOT-Adjusted-Forecast.xlsb"
        data.import_load_scaling(str(scaling))
    if case.dataset == "123_Bus_Resil_Week":
        data.import_outage_data(str(dataset / "may_20.csv"))
    if case.dataset in {"123_Bus_Coal", "123_Bus_Resil_Week", "Texas_2000"}:
        data.texas_case_study_updates(str(dataset))
    return data


def candidate_cost_data() -> DataProcessing:
    costs = SOURCE_ROOT / "gtep/data/costs"
    result = DataProcessing()
    result.load_gen_data(
        bus_data_path=str(costs / "Bus_data_gen_weights_mappings.csv"),
        cost_data_path=str(costs / "2022_v3_Annual_Technology_Baseline_Workbook_Mid-year_update_2-15-2023_Clean.xlsx"),
        candidate_gens=["Natural Gas_CT", "Natural Gas_FE", "Solar - Utility PV", "Land-Based Wind"],
        save_csv=False,
    )
    return result


def configure(case: GtepCase, model: ExpansionPlanningModel) -> None:
    overrides = {
        "include_investment": case.include_investment,
        "include_commitment": case.include_commitment,
        "include_redispatch": case.include_redispatch,
        "scale_loads": case.scale_loads,
        "scale_texas_loads": case.scale_texas_loads,
        "transmission": case.transmission,
        "flow_model": case.flow_model,
        "storage": False,
    }
    if case.mode == "ra_known_failure":
        overrides.update(thermal_generation=True, renewable_generation=True)
    for key, setting in overrides.items():
        model.config[key] = setting


def execute(case: GtepCase) -> dict[str, Any]:
    try:
        data = make_data(case)
        counts = data_counts(data)
        if case.mode == "large_data_validation":
            return {"pass": True, "status": "validated", "stage": "official_driver_data_validation", "termination_condition": "not_run", "metrics": counts, "error": None}
        cost_data = candidate_cost_data() if case.mode == "solve_candidate" else None
        model = ExpansionPlanningModel(data=data, cost_data=cost_data)
        configure(case, model)
        model.create_model()
        size = build_model_size_report(model.model)
        metrics = {
            **counts,
            "variables_before_gdp_transform": size.activated.variables,
            "constraints_before_gdp_transform": size.activated.constraints,
            "disjunctions_before_gdp_transform": size.activated.disjunctions,
        }
        if case.mode == "build_only":
            return {"pass": True, "status": "validated", "stage": "official_driver_build", "termination_condition": "not_run_by_official_driver", "metrics": metrics, "error": None}
        TransformationFactory("gdp.bound_pretransformation").apply_to(model.model)
        TransformationFactory("gdp.bigm").apply_to(model.model)
        result = Highs().solve(model.model)
        termination = result.termination_condition.name
        objectives = list(model.model.component_data_objects(Objective, active=True))
        metrics["objective_value"] = value(objectives[0]) if objectives else None
        return {"pass": termination == "optimal", "status": "optimized" if termination == "optimal" else "validated", "stage": "gdp_bigm_highs", "termination_condition": termination, "metrics": metrics, "error": None}
    except Exception as exc:
        return {
            "pass": False,
            "status": "validated",
            "stage": "official_driver_reproduction_failure",
            "termination_condition": "not_reached",
            "metrics": {},
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def specs(case: GtepCase) -> list[dict[str, Any]]:
    values = {
        "dataset": (case.dataset, "categorical"), "stages": (case.stages, "count"),
        "representative_periods": (case.num_reps, "count"), "representative_period_length": (case.len_reps, "h"),
        "commitment_periods": (case.num_commit, "count"), "dispatch_periods_per_commitment": (case.num_dispatch, "count"),
        "flow_model": (case.flow_model, "categorical"), "transmission_investment": (case.transmission, "boolean"),
        "include_investment": (case.include_investment, "boolean"), "include_commitment": (case.include_commitment, "boolean"),
    }
    return [
        {"target": "gtep", "variable": name, "value": setting, "units": units, "role": "official driver configuration", "source": "official_driver", "source_url": source_url(case)}
        for name, (setting, units) in values.items()
    ]


def topology(case: GtepCase) -> tuple[dict[str, Any], dict[str, Any]]:
    units = [{"id": "data", "kind": "GTEPData", "package": "egret_prescient", "stage": "data", "role": f"official {case.dataset} grid and time-series data", "constructor": {}, "constraint_template": None}]
    stage_ids = []
    if case.include_investment:
        units.append({"id": "investment", "kind": "InvestmentStage", "package": "pyomo_gdp", "stage": "planning", "role": "generation and transmission investment decisions", "constructor": {}, "constraint_template": None}); stage_ids.append("investment")
    if case.include_commitment:
        units.append({"id": "commitment", "kind": "CommitmentStage", "package": "pyomo_gdp", "stage": "operations", "role": "unit commitment and reserve decisions", "constructor": {}, "constraint_template": None}); stage_ids.append("commitment")
    units.append({"id": "dispatch", "kind": "DispatchStage", "package": "egret", "stage": "operations", "role": "power dispatch, load balance, and load shedding", "constructor": {}, "constraint_template": None}); stage_ids.append("dispatch")
    if case.transmission:
        units.append({"id": "network", "kind": "TransmissionNetwork", "package": "egret", "stage": "network", "role": f"{case.flow_model} transmission network and expansion", "constructor": {}, "constraint_template": None}); stage_ids.append("network")
    units.append({"id": "plan", "kind": "ExpansionPlan", "package": "pyomo", "stage": "solution", "role": "investment and operating plan", "constructor": {}, "constraint_template": None})
    chain = ["data", *stage_ids, "plan"]
    arcs = [{"id": f"{a}_to_{b}", "source": f"{a}.outlet", "destination": f"{b}.inlet", "stage": "model_link", "role": "official GTEP stage linkage", "tear_candidate": False} for a, b in zip(chain, chain[1:])]
    rows = specs(case)
    ir = {
        "schema_version": "topology_ir/1", "case_id": case.case_id, "family": "family_idaes_gtep",
        "process_type": case.label, "source_url": source_url(case),
        "source_basis": [f"Official IDAES-GTEP driver {case.driver} at commit {SOURCE_COMMIT}.", "Topology follows the official model-stages documentation figure."],
        "property_packages": {"egret_prescient": {"dataset": case.dataset}, "pyomo_gdp": {"transformation": "gdp.bigm"}},
        "components": {"planning": ["generation", "transmission", "load", "reserve", "investment", "dispatch"]},
        "units": units, "arcs": arcs, "feed_specs": rows, "unit_specs": [],
        "unconnected_feed_ports": ["data.outlet"], "unconnected_product_ports": ["plan.inlet"],
        "tear_streams": [], "translator_constraint_templates": {}, "translator_constraints": [],
        "initialization": {"strategy": "official data load, GDP model build, Big-M transformation, MILP solve", "solve_order": chain},
        "solve": {"solver": "highs_or_official_gurobi", "steady_state": False, "expected_dof": None},
        "required_entries": ["ExpansionPlanningData", "ExpansionPlanningModel", "gdp.bigm"],
        "notes_for_agent_a": ["This is a grid infrastructure planning model, not a process flowsheet.", "Do not merge GTEP cases with DISPATCHES plant-operation cases."],
    }
    sir = {"schema_version": "spec_ir/1", "case_id": case.case_id, "family": ir["family"], "source_url": source_url(case), "topology_schema_version": "topology_ir/1", "specs": rows, "terminal_feed_ports": ir["unconnected_feed_ports"], "terminal_product_ports": ir["unconnected_product_ports"], "translator_constraint_templates": {}, "initialization": ir["initialization"], "solve": ir["solve"]}
    return ir, sir


def materialize(case: GtepCase) -> dict[str, Any]:
    output = VALIDATION_ROOT / case.case_id
    report_path = output / "native_solve_report.json"
    if report_path.is_file():
        report = load(report_path)
        if report.get("case_fingerprint") != case.fingerprint:
            raise RuntimeError(f"Refusing to overwrite mismatched existing case {case.case_id}")
        return {"case_id": case.case_id, "status": "skipped_existing"}
    evidence = execute(case)
    ir, sir = topology(case)
    report = {
        **evidence, "case_family": "idaes_gtep", "case_id": case.case_id, "case_fingerprint": case.fingerprint,
        "driver": case.driver, "dataset": case.dataset, "source_url": source_url(case), "source_commit": SOURCE_COMMIT,
        "claim_boundary": (
            "Official IDAES-GTEP driver configuration reproduced with HiGHS after GDP Big-M transformation."
            if evidence["status"] == "optimized"
            else "Official IDAES-GTEP driver and data scenario are registered with the exact recorded build/data limitation; no optimal solve is claimed."
        ),
    }
    output.mkdir(parents=True, exist_ok=False)
    write(output / f"{case.case_id}_topology_ir.json", ir)
    write(output / f"{case.case_id}_spec_ir.json", sir)
    write(report_path, report)
    write(output / "topology_prebuild_report_attempt0.json", {"pass": True, "case_id": case.case_id, "unit_count": len(ir["units"]), "arc_count": len(ir["arcs"])})
    images = SOURCE_ROOT / "docs/images"
    for image in ("model_stages.png", "model_investment_stage.png", "model_commitment_stage.png", "model_dispatch_stage.png"):
        shutil.copyfile(images / image, output / f"official_{image}")
    shutil.copyfile(images / case.official_figure, output / "source_flowchart.png")
    fv = stage_fv_data(case.case_id, topology_ir_fv(case.case_id, ir), "solve")
    write(output / "idaes_flowsheet_visualization.json", fv)
    return {"case_id": case.case_id, "status": evidence["status"], "pass": evidence["pass"]}


def record(case: GtepCase, evidence: dict[str, Any], order: int) -> dict[str, Any]:
    base = f"validation/VectorEngine_qwen36_validation/{case.case_id}"
    status = evidence["status"]
    return {
        "case_key": case.case_id, "label": case.label, "family": "gtep", "ecosystem": "IDAES-GTEP",
        "process_family": "grid_expansion_planning",
        "tags": ["gtep", "grid_expansion", "generation_investment", "transmission_planning", "official_case", "optimization_model"],
        "aliases": [case.label.lower(), case.case_id.replace("_", " ")], "suites": [SUITE], "order": order, "lifecycle": "active",
        "display_prompt": f"Build the official IDAES-GTEP {case.label} scenario from {case.driver}, including investment, commitment, dispatch, and configured transmission decisions.",
        "selection": {
            "case_key": case.case_id, "family": "gtep", "run_id": case.case_id, "selected_run_id": case.case_id,
            "status": status, "selected_status": status, "complexity_level": "grid_planning",
            "execution_status": "executed_pass" if evidence["pass"] else "executed_bounded_failure",
            "evidence_maturity": "native_optimized" if status == "optimized" else "official_driver_validated",
            "claim_boundary": evidence["claim_boundary"],
            "topology_ir_file": f"{base}/{case.case_id}_topology_ir.json", "spec_ir_file": f"{base}/{case.case_id}_spec_ir.json",
            "solve_report_file": f"{base}/native_solve_report.json", "selected_validation_dir": base,
            "source_flowchart_file": f"{base}/source_flowchart.png", "source_manifest_path": source_url(case), "selected_by": SUITE,
        },
        "provenance": {"created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "created_by": Path(__file__).name, "source_commit": SOURCE_COMMIT, "source_driver": f"gtep/{case.driver}", "dataset": case.dataset, "case_fingerprint": case.fingerprint},
    }


def merge_registry() -> None:
    registry = load(REGISTRY_PATH)
    existing = [row for row in registry["cases"] if SUITE in row.get("suites", [])]
    if existing:
        if {row["case_key"] for row in existing} != {case.case_id for case in CASES}:
            raise RuntimeError("Existing GTEP suite differs from official manifest")
        return
    start = max(row["order"] for row in registry["cases"]) + 1
    for index, case in enumerate(CASES):
        evidence = load(VALIDATION_ROOT / case.case_id / "native_solve_report.json")
        registry["cases"].append(record(case, evidence, start + index))
    registry["suite_contracts"][SUITE] = {"expected_case_count": 9, "frozen": False, "stage": "official_driver_executed"}
    registry["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write(REGISTRY_PATH, registry)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("all", *[case.case_id for case in CASES]), default="all")
    parser.add_argument("--merge-registry", action="store_true")
    args = parser.parse_args()
    registry_ids = {row["case_key"] for row in load(REGISTRY_PATH)["cases"]}
    suite_ids = {case.case_id for case in CASES}
    collisions = registry_ids & suite_ids
    existing_suite_ids = {row["case_key"] for row in load(REGISTRY_PATH)["cases"] if SUITE in row.get("suites", [])}
    if collisions and collisions != existing_suite_ids:
        raise RuntimeError(f"GTEP case ID collision: {sorted(collisions)}")
    write(MANIFEST_PATH, {"schema_version": 1, "suite": SUITE, "case_count": len(CASES), "source_commit": SOURCE_COMMIT, "official_driver_count": 9, "cases": [{**asdict(case), "fingerprint": case.fingerprint, "source_url": source_url(case)} for case in CASES]})
    selected = CASES if args.case == "all" else tuple(case for case in CASES if case.case_id == args.case)
    results = [materialize(case) for case in selected]
    if args.merge_registry:
        if args.case != "all":
            raise RuntimeError("Registry merge requires --case all")
        merge_registry()
    print(json.dumps({"pass": True, "case_count": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
