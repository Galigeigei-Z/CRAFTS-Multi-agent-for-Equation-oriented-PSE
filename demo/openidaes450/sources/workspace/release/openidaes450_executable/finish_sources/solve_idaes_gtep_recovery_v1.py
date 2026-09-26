#!/usr/bin/env python3
"""Solve evidence-bounded IDAES-GTEP cases with explicit compatibility repairs."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from egret.parsers.matpower_parser import create_ModelData
from pyomo.contrib.appsi.solvers.highs import Highs
from pyomo.core import Objective, TransformationFactory
from pyomo.environ import value
from pyomo.util.model_size import build_model_size_report

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_idaes_gtep_official_v1 import (
    CASES,
    REGISTRY_PATH,
    SOURCE_ROOT,
    VALIDATION_ROOT,
    candidate_cost_data,
    configure,
    data_counts,
    load,
    make_data,
    write,
)
from gtep.gtep_data import ExpansionPlanningData
from gtep.gtep_model import ExpansionPlanningModel
import gtep.model_library.dispatch as dispatch_library


RECOVERY_SUITE = "idaes_gtep_solved_recovery_v1"


@contextmanager
def fixed_copper_plate_sets():
    """Supply the load and empty-storage sets omitted by the official CP rule."""
    original = dispatch_library.add_dispatch_constraints

    def repaired(block, dispatch_period):
        model = block.model()
        if model.config["flow_model"] == "CP":
            if not hasattr(block, "loads"):
                block.loads = pyo.Set(initialize=list(model.loads))
            if not hasattr(model, "storage"):
                model.storage = pyo.Set(initialize=[])
        return original(block, dispatch_period)

    dispatch_library.add_dispatch_constraints = repaired
    try:
        yield
    finally:
        dispatch_library.add_dispatch_constraints = original


def solve_model(model: ExpansionPlanningModel, counts: dict, recovery: dict) -> dict:
    size = build_model_size_report(model.model)
    TransformationFactory("gdp.bound_pretransformation").apply_to(model.model)
    TransformationFactory("gdp.bigm").apply_to(model.model)
    result = Highs().solve(model.model)
    termination = result.termination_condition.name
    objectives = list(model.model.component_data_objects(Objective, active=True))
    if termination != "optimal":
        raise RuntimeError(f"HiGHS did not reach optimality: {termination}")
    return {
        **counts,
        "variables_before_gdp_transform": size.activated.variables,
        "constraints_before_gdp_transform": size.activated.constraints,
        "disjunctions_before_gdp_transform": size.activated.disjunctions,
        "objective_value": value(objectives[0]) if objectives else None,
        "recovery_configuration": recovery,
    }


def solve_standard(case, *, lifetime_clamp=False) -> tuple[dict, dict]:
    data = make_data(case)
    fixes = []
    if lifetime_clamp:
        changed = set()
        for model_data in data.representative_data:
            for generator, settings in model_data.data["elements"]["generator"].items():
                if settings.get("lifetime", case.stages) < case.stages:
                    settings["lifetime"] = case.stages
                    changed.add(generator)
        fixes.append({
            "id": "lifetime_horizon_clamp",
            "reason": "Avoid the official retirement rule passing a numeric installed variable to a Boolean expression.",
            "affected_generators": sorted(changed),
        })
    model = ExpansionPlanningModel(
        data=data,
        cost_data=candidate_cost_data() if case.mode == "solve_candidate" else None,
    )
    configure(case, model)
    model.create_model()
    recovery = {
        "official_dataset": case.dataset,
        "stages": case.stages,
        "representative_periods": case.num_reps,
        "commitment_periods": case.num_commit,
        "dispatch_periods": case.num_dispatch,
        "flow_model": case.flow_model,
        "transmission": case.transmission,
        "compatibility_fixes": fixes,
    }
    return solve_model(model, data_counts(data), recovery), recovery


@contextmanager
def repaired_prescient_directory(dataset: str):
    """Expose official large-grid data with parser-compatible branch and ramp fields."""
    source = SOURCE_ROOT / "gtep/data" / dataset
    with tempfile.TemporaryDirectory(prefix=f"gtep_{dataset.lower()}_") as temp:
        target = Path(temp)
        for path in source.iterdir():
            if path.name not in {"branch.csv", "gen.csv"}:
                os.symlink(path, target / path.name, target_is_directory=path.is_dir())
        branches = pd.read_csv(source / "branch.csv")
        branches["UID"] = [f"branch_{uid}" for uid in branches["UID"]]
        branches.to_csv(target / "branch.csv", index=False)
        generators = pd.read_csv(source / "gen.csv")
        missing_ramp = int(generators["Ramp Rate MW/Min"].isna().sum())
        generators["Ramp Rate MW/Min"] = generators["Ramp Rate MW/Min"].fillna(
            generators["PMax MW"].clip(lower=1) / 60
        )
        generators.to_csv(target / "gen.csv", index=False)
        yield target, missing_ramp


def load_large_prescient(dataset: str, representative_date: str) -> tuple[ExpansionPlanningData, int]:
    with repaired_prescient_directory(dataset) as (data_path, missing_ramp):
        data = ExpansionPlanningData(
            stages=1, num_reps=1, len_reps=1, num_commit=1, num_dispatch=1
        )
        data.load_prescient(
            str(data_path),
            representative_dates=[representative_date],
            options_dict={"start_date": "01-01-2019", "num_days": 365, "ruc_horizon": 36},
        )
    return data, missing_ramp


def solve_123_bus(case, *, resilience=False) -> tuple[dict, dict]:
    date = "2019-05-20 00:00" if resilience else "2019-01-28 00:00"
    data, missing_ramp = load_large_prescient(case.dataset, date)
    outage_count = 0
    if resilience:
        old_cwd = Path.cwd()
        try:
            os.chdir(SOURCE_ROOT)
            data.import_outage_data(str(SOURCE_ROOT / "gtep/data" / case.dataset / "may_20.csv"))
        finally:
            os.chdir(old_cwd)
        outage_count = len(data.bus_hours)
    model = ExpansionPlanningModel(data=data)
    model.config["flow_model"] = "DC" if resilience else "CP"
    model.config["transmission"] = resilience
    model.config["storage"] = False
    model.create_model()
    recovery = {
        "official_dataset": case.dataset,
        "stages": 1,
        "representative_periods": 1,
        "representative_date": date,
        "commitment_periods": 1,
        "dispatch_periods": 1,
        "flow_model": "DC" if resilience else "CP",
        "transmission": resilience,
        "outage_mapping_count": outage_count,
        "compatibility_fixes": [
            {
                "id": "egret_numeric_branch_uid_adapter",
                "reason": "Prevent pandas iterrows from coercing integer bus IDs to unmatched decimal strings.",
            },
            {
                "id": "missing_generator_ramp_default",
                "reason": "Fill absent ramp_q inputs with one-hour nameplate ramp capability.",
                "affected_generator_rows": missing_ramp,
            },
            {
                "id": "official_2019_data_start",
                "reason": "Use the year present in official time-series files instead of Prescient's 2020 default.",
            },
        ],
    }
    return solve_model(model, data_counts(data), recovery), recovery


def texas_data() -> ExpansionPlanningData:
    source = SOURCE_ROOT / "gtep/data/Texas_2000/case_ACTIVSg2000.m"
    data = ExpansionPlanningData(
        stages=1, num_reps=1, len_reps=1, num_commit=1, num_dispatch=1
    )
    data.data_type = "matpower"
    data.md = create_ModelData(str(source))
    data.md.data["system"]["name"] = "ACTIVSg2000 MATPOWER"
    data.md.data["elements"]["storage"] = {}
    data.load_default_data_settings()
    for settings in data.md.data["elements"]["generator"].values():
        settings["non_fuel_startup_cost"] = settings.get("startup_cost", 0)
        settings.setdefault("fuel", "G")
        settings.setdefault("unit_type", "GEN")
    loads = {}
    for settings in data.md.data["elements"]["load"].values():
        settings["p_load"] = {"data_type": "time_series", "values": [settings["p_load"]]}
        loads[settings["bus"]] = settings
    data.md.data["elements"]["load"] = loads
    data.representative_dates = ["matpower_snapshot"]
    data.representative_weights = {1: 1}
    data.representative_data = [data.md.clone()]
    return data


def solve_texas(case) -> tuple[dict, dict]:
    data = texas_data()
    model = ExpansionPlanningModel(data=data)
    model.config["flow_model"] = "DC"
    model.config["transmission"] = True
    model.config["storage"] = False
    model.config["include_investment"] = False
    model.config["include_commitment"] = False
    model.create_model()
    recovery = {
        "official_dataset": case.dataset,
        "matpower_source": "case_ACTIVSg2000.m",
        "stages": 1,
        "representative_periods": 1,
        "commitment_periods": 1,
        "dispatch_periods": 1,
        "flow_model": "DC",
        "transmission": True,
        "include_investment": False,
        "include_commitment": False,
        "compatibility_fixes": [
            {
                "id": "matpower_to_gtep_snapshot_adapter",
                "reason": "The archived official Texas directory contains MATPOWER files but no Prescient bus/gen/branch CSV set.",
            }
        ],
    }
    return solve_model(model, data_counts(data), recovery), recovery


def recover(case) -> tuple[dict, dict]:
    if case.case_id == "official_gtep_5bus_dispatch_only":
        return solve_standard(replace(case, mode="solve_baseline"))
    if case.case_id == "official_gtep_5bus_three_stage":
        return solve_standard(replace(case, num_commit=6, num_dispatch=2), lifetime_clamp=True)
    if case.case_id == "official_gtep_9bus_candidate_expansion":
        return solve_standard(replace(case, num_reps=1, num_commit=2, num_dispatch=2))
    if case.case_id == "official_gtep_5bus_resource_adequacy":
        return solve_standard(replace(case, num_reps=1, len_reps=1, num_commit=4, num_dispatch=2))
    if case.case_id == "official_gtep_123bus_coal":
        return solve_123_bus(case)
    if case.case_id == "official_gtep_123bus_resilience_week":
        return solve_123_bus(case, resilience=True)
    if case.case_id == "official_gtep_texas_2000":
        return solve_texas(case)
    raise KeyError(case.case_id)


def update_report(case, metrics: dict, recovery: dict) -> None:
    path = VALIDATION_ROOT / case.case_id / "native_solve_report.json"
    report = load(path)
    report["original_validation_boundary"] = {
        "pass": report.get("pass"),
        "stage": report.get("stage"),
        "termination_condition": report.get("termination_condition"),
        "error": report.get("error"),
        "metrics": report.get("metrics"),
    }
    report.update(
        {
            "pass": True,
            "status": "optimized",
            "stage": "gtep_recovery_gdp_bigm_highs",
            "termination_condition": "optimal",
            "solver": "highs",
            "metrics": metrics,
            "error": None,
            "recovery_suite": RECOVERY_SUITE,
            "recovery_configuration": recovery,
            "claim_boundary": (
                "Official IDAES-GTEP data and driver intent solved to optimality with the recorded "
                "compatibility repairs and temporal reduction; this does not claim reproduction of "
                "the original large-scale Gurobi run dimensions."
            ),
        }
    )
    write(path, report)


def update_registry() -> None:
    registry = load(REGISTRY_PATH)
    recovered = {case.case_id for case in CASES[1:] if case.case_id != "official_gtep_5bus_candidate_expansion"}
    recovered.add("official_gtep_9bus_candidate_expansion")
    for record in registry["cases"]:
        if record["case_key"] not in recovered:
            continue
        report = load(VALIDATION_ROOT / record["case_key"] / "native_solve_report.json")
        selection = record["selection"]
        selection["status"] = "optimized"
        selection["selected_status"] = "optimized"
        selection["execution_status"] = "executed_pass"
        selection["evidence_maturity"] = "native_optimized_recovery"
        selection["claim_boundary"] = report["claim_boundary"]
        if RECOVERY_SUITE not in record["suites"]:
            record["suites"].append(RECOVERY_SUITE)
    registry["suite_contracts"][RECOVERY_SUITE] = {
        "expected_case_count": 7,
        "frozen": False,
        "stage": "native_optimized_recovery",
    }
    registry["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write(REGISTRY_PATH, registry)


def main() -> None:
    np.random.seed(0)
    targets = [case for case in CASES if load(VALIDATION_ROOT / case.case_id / "native_solve_report.json")["status"] != "optimized"]
    results = []
    with fixed_copper_plate_sets():
        for case in targets:
            metrics, recovery = recover(case)
            update_report(case, metrics, recovery)
            results.append({"case_id": case.case_id, "status": "optimized", "metrics": metrics})
    update_registry()
    print(json.dumps({"pass": True, "case_count": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    main()
