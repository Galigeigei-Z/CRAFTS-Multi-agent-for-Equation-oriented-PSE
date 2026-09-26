#!/usr/bin/env python3
"""Build the initial IDAES-MVO process-family-design case category."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pyomo.environ import Constraint, SolverFactory, Var, value
from pyomo.util.model_size import build_model_size_report


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-04-29/"
    "examples/archived_canonical_sources/cases/github_examples/clones/idaes-mvo"
)
SOURCE_COMMIT = "4af5203a41319fea9f9ee994abe9f681fa0cadb1"
SOURCE_BASE_URL = f"https://github.com/IDAES/idaes-mvo/blob/{SOURCE_COMMIT}"
REGISTRY_PATH = ROOT / "experiment/case_registry/registry.json"
VALIDATION_ROOT = ROOT / "validation/VectorEngine_qwen36_validation"
MANIFEST_PATH = ROOT / "experiment/case_variants/idaes_mvo_official_v1.json"
SUITE = "idaes_mvo_official_v1"
for path in (ROOT, SOURCE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_family.type.discretized import DiscretizedProcessFamily  # noqa: E402
from process_family.utils.parameters.base import Parameters  # noqa: E402




@dataclass(frozen=True)
class MvoCase:
    case_id: str
    label: str
    method: str
    filter_name: str
    max_designs: tuple[int, int, int]
    official_notebook: str
    official_cell: int

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


CASES = (
    MvoCase("mvo_official_transcritical_co2_discretized", "MVO Official Transcritical CO2 Discretized Family", "discretized", "all_56_variants", (2, 2, 2), "discretized.ipynb", 8),
    MvoCase("mvo_official_transcritical_co2_surrogate_gbdt", "MVO Official Transcritical CO2 GBDT Surrogate Family", "surrogate_gbdt", "all_56_variants", (2, 2, 2), "surrogates.ipynb", 22),
    MvoCase("mvo_variant_transcritical_co2_cool_climate", "MVO Transcritical CO2 Cool-Climate Family", "discretized", "temperature_le_31", (2, 2, 2), "discretized.ipynb", 8),
    MvoCase("mvo_variant_transcritical_co2_hot_climate", "MVO Transcritical CO2 Hot-Climate Family", "discretized", "temperature_ge_32", (2, 2, 2), "discretized.ipynb", 8),
    MvoCase("mvo_variant_transcritical_co2_low_capacity", "MVO Transcritical CO2 Low-Capacity Family", "discretized", "capacity_le_140", (2, 2, 2), "discretized.ipynb", 8),
    MvoCase("mvo_variant_transcritical_co2_high_capacity", "MVO Transcritical CO2 High-Capacity Family", "discretized", "capacity_ge_160", (2, 2, 2), "discretized.ipynb", 8),
    MvoCase("mvo_variant_transcritical_co2_high_demand_standardized", "MVO Transcritical CO2 High-Demand Standardized Platform", "discretized", "capacity_ge_160", (1, 1, 1), "discretized.ipynb", 8),
    MvoCase("mvo_variant_transcritical_co2_high_demand_flexible", "MVO Transcritical CO2 High-Demand Flexible Platform", "discretized", "capacity_ge_160", (3, 3, 3), "discretized.ipynb", 8),
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_url(case: MvoCase) -> str:
    return f"{SOURCE_BASE_URL}/example/{case.official_notebook}"


def notebook_png(case: MvoCase) -> bytes:
    notebook = load(SOURCE_ROOT / "example" / case.official_notebook)
    images = []
    for output in notebook["cells"][case.official_cell].get("outputs", []):
        encoded = output.get("data", {}).get("image/png")
        if encoded:
            images.append("".join(encoded) if isinstance(encoded, list) else encoded)
    if not images:
        raise RuntimeError(f"No official PNG in {case.official_notebook} cell {case.official_cell}")
    return base64.b64decode(images[-1])


def filtered_data(filter_name: str) -> pd.DataFrame:
    data = pd.read_csv(SOURCE_ROOT / "example/data/transcritical-co2-data.csv")
    if filter_name == "temperature_le_31":
        data = data[data["Outside Air Temperature"] <= 31]
    elif filter_name == "temperature_ge_32":
        data = data[data["Outside Air Temperature"] >= 32]
    elif filter_name == "capacity_le_140":
        data = data[data["Capacity"] <= 140]
    elif filter_name == "capacity_ge_160":
        data = data[data["Capacity"] >= 160]
    elif filter_name != "all_56_variants":
        raise KeyError(filter_name)
    return data.copy()


def parameters(csv_path: Path, case: MvoCase) -> Parameters:
    names = ("Evaporator Area", "Condenser Area", "Compressor Design Flow")
    params = Parameters("transcritical-co2")
    params.csv_filepath = str(csv_path)
    params.process_variant_columns = ["Capacity", "Outside Air Temperature"]
    params.common_unit_types_column = list(names)
    params.feasibility_column = ["Success"]
    params.annualized_cost_column = ["Total Annualized Cost"]
    params.num_common_unit_type_designs = dict(zip(names, case.max_designs))
    params.labels_for_common_unit_module_designs = {
        name: range(limit) for name, limit in zip(names, case.max_designs)
    }
    params.process_variant_column_names = [
        "Capacity (tons)",
        "Max. Outside Air Temperature (deg. C)",
    ]
    params.common_module_type_column_names = [
        "Evap. Area ($m^2$)",
        "Cond. Area ($m^2$)",
        "Compr. Flow (mol./s)",
    ]
    return params


def solve_discretized(case: MvoCase) -> tuple[dict, bytes]:
    data = filtered_data(case.filter_name)
    with tempfile.TemporaryDirectory(prefix="idaes_mvo_") as temp:
        csv_path = Path(temp) / "transcritical-co2-filtered.csv"
        plot_path = Path(temp) / "result.png"
        data.to_csv(csv_path, index=False)
        started = time.monotonic()
        family = DiscretizedProcessFamily(parameters(csv_path, case))
        initialize_seconds = time.monotonic() - started
        started = time.monotonic()
        family.build_model()
        build_seconds = time.monotonic() - started
        solver = SolverFactory("appsi_highs")
        solver.options["mip_rel_gap"] = 1e-4
        started = time.monotonic()
        family.results = solver.solve(family.model, tee=False)
        solve_seconds = time.monotonic() - started
        termination = str(family.results.solver.termination_condition)
        if termination != "optimal":
            raise RuntimeError(f"{case.case_id}: HiGHS termination {termination}")
        selected = family.get_results_dict()
        family.plot(
            directory=str(plot_path),
            process_variant_column_names=family.params.process_variant_column_names
            if hasattr(family, "params")
            else ["Capacity (tons)", "Max. Outside Air Temperature (deg. C)"],
            common_module_type_columns=[
                "Evap. Area ($m^2$)",
                "Cond. Area ($m^2$)",
                "Compr. Flow (mol./s)",
            ],
        )
        size = build_model_size_report(family.model)
        platform_modules = [
            {"module_type": str(module), "design": float(design)}
            for (module, design), variable in family.model.z_cl.items()
            if value(variable) >= 0.98
        ]
        metrics = {
            "input_row_count": len(data),
            "process_variant_count": len(family.V),
            "feasible_alternative_count": sum(len(items) for items in family.A_v.values()),
            "x_selection_variable_count": len(family.model.x_va),
            "platform_binary_count": len(family.model.z_cl),
            "variables": size.activated.variables,
            "constraints": size.activated.constraints,
            "objective_value": value(family.model.obj),
            "selected_family_design_count": len(set(tuple(items) for items in selected.values())),
            "selected_platform_module_count": len(platform_modules),
            "selected_platform_modules": platform_modules,
            "initialize_seconds": initialize_seconds,
            "build_seconds": build_seconds,
            "solve_seconds": solve_seconds,
        }
        result_png = plot_path.read_bytes()
    report = {
        "pass": True,
        "status": "optimized",
        "stage": "native_mvo_discretized_highs",
        "termination_condition": "optimal",
        "solver": "appsi_highs",
        "execution_scope": "native",
        "metrics": metrics,
        "configuration": {
            "filter_name": case.filter_name,
            "max_common_designs": {
                "Evaporator Area": case.max_designs[0],
                "Condenser Area": case.max_designs[1],
                "Compressor Design Flow": case.max_designs[2],
            },
        },
        "error": None,
    }
    return report, result_png


def official_surrogate_evidence(case: MvoCase) -> tuple[dict, bytes]:
    figure = notebook_png(case)
    report = {
        "pass": True,
        "status": "optimized",
        "stage": "official_notebook_gbdt_gurobi",
        "termination_condition": "optimal",
        "solver": "gurobi_12.0.1_official_notebook",
        "execution_scope": "official_notebook_evidence",
        "metrics": {
            "input_row_count": 78400,
            "process_variant_count": 56,
            "variables": 353310,
            "constraints": 697707,
            "binary_variables": 4704,
            "objective_value": 4.479231336956,
            "selected_family_design_count": 2,
        },
        "configuration": {
            "classification_surrogate": "GBDT",
            "cost_surrogate": "GBDT",
            "classification_threshold": 0.99,
            "max_common_designs": {
                "Evaporator Area": 2,
                "Condenser Area": 2,
                "Compressor Design Flow": 2,
            },
        },
        "error": None,
        "local_reproduction_boundary": (
            "The official repository does not commit the trained surrogates directory used by the example, "
            "and the local environment lacks its pinned OMLT/ONNX stack. Optimization evidence and the result "
            "figure are preserved from the official executed notebook; no local surrogate solve is claimed."
        ),
    }
    return report, figure


def topology(case: MvoCase, report: dict) -> tuple[dict, dict]:
    surrogate = case.method == "surrogate_gbdt"
    units = [
        {"id": "requirements", "kind": "ProcessVariantSet", "package": "pandas", "stage": "data", "role": "capacity and outside-air-temperature requirements for the process family", "constructor": {}, "constraint_template": None},
        {"id": "alternatives", "kind": "FeasibleAlternativeLibrary", "package": "idaes_mvo", "stage": "data", "role": "feasible transcritical CO2 equipment alternatives and annualized cost", "constructor": {}, "constraint_template": None},
    ]
    if surrogate:
        units.extend([
            {"id": "feasibility_surrogate", "kind": "SurrogateFeasibility", "package": "omlt", "stage": "surrogate", "role": "GBDT feasibility classifier embedded as MILP", "constructor": {}, "constraint_template": None},
            {"id": "cost_surrogate", "kind": "SurrogateCost", "package": "omlt", "stage": "surrogate", "role": "GBDT annualized-cost surrogate embedded as MILP", "constructor": {}, "constraint_template": None},
        ])
    units.extend([
        {"id": "platform", "kind": "SharedModulePlatform", "package": "idaes_mvo", "stage": "design", "role": "shared evaporator, condenser, and compressor module designs", "constructor": {}, "constraint_template": None},
        {"id": "selection", "kind": "AlternativeSelection", "package": "pyomo", "stage": "design", "role": "one feasible equipment alternative per process variant", "constructor": {}, "constraint_template": None},
        {"id": "objective", "kind": "FamilyCostObjective", "package": "pyomo", "stage": "optimization", "role": "minimum total annualized process-family cost", "constructor": {}, "constraint_template": None},
        {"id": "family", "kind": "ProcessFamilyDesign", "package": "idaes_mvo", "stage": "solution", "role": "optimized standardized process family", "constructor": {}, "constraint_template": None},
    ])
    chain = [unit["id"] for unit in units]
    arcs = [{"id": f"{a}_to_{b}", "source": f"{a}.outlet", "destination": f"{b}.inlet", "stage": "optimization_link", "role": "MVO model linkage", "tear_candidate": False} for a, b in zip(chain, chain[1:])]
    specs = [{"target": "mvo", "variable": key, "value": setting, "units": "categorical", "role": "process-family configuration", "source": "official_or_variant", "source_url": source_url(case)} for key, setting in report["configuration"].items()]
    ir = {
        "schema_version": "topology_ir/1", "case_id": case.case_id, "family": "family_idaes_mvo", "process_type": case.label,
        "source_url": source_url(case),
        "source_basis": [f"Official IDAES-MVO repository at commit {SOURCE_COMMIT}.", f"Official notebook result figure extracted from example/{case.official_notebook}, cell {case.official_cell}."],
        "property_packages": {"idaes_mvo": {"dataset": "transcritical-co2-data.csv", "method": case.method}},
        "components": {"shared_modules": ["evaporator", "condenser", "compressor"], "variant_descriptors": ["capacity", "outside_air_temperature"]},
        "units": units, "arcs": arcs, "feed_specs": specs, "unit_specs": [],
        "unconnected_feed_ports": ["requirements.outlet"], "unconnected_product_ports": ["family.inlet"], "tear_streams": [],
        "translator_constraint_templates": {}, "translator_constraints": [],
        "initialization": {"strategy": "load official design table, construct process-family MILP, solve or preserve official notebook evidence", "solve_order": chain},
        "solve": {"solver": report["solver"], "steady_state": False, "expected_dof": None},
        "required_entries": ["ProcessFamilyBase", "DiscretizedProcessFamily" if not surrogate else "SurrogatesProcessFamily"],
        "notes_for_agent_a": ["This is a process-family design optimization, not a physical stream flowsheet.", "source_flowchart.png is an official notebook result figure; the repository contains no official architecture flowchart."],
    }
    sir = {"schema_version": "spec_ir/1", "case_id": case.case_id, "family": ir["family"], "source_url": ir["source_url"], "topology_schema_version": "topology_ir/1", "specs": specs, "terminal_feed_ports": ir["unconnected_feed_ports"], "terminal_product_ports": ir["unconnected_product_ports"], "translator_constraint_templates": {}, "initialization": ir["initialization"], "solve": ir["solve"]}
    return ir, sir


def materialize(case: MvoCase) -> dict:
    output = VALIDATION_ROOT / case.case_id
    report_path = output / "native_solve_report.json"
    if report_path.is_file():
        report = load(report_path)
        if report.get("case_fingerprint") != case.fingerprint:
            raise RuntimeError(f"Fingerprint mismatch for {case.case_id}")
        return report
    if case.method == "surrogate_gbdt":
        report, result_figure = official_surrogate_evidence(case)
    else:
        report, result_figure = solve_discretized(case)
    report.update({
        "case_id": case.case_id, "case_family": "idaes_mvo", "case_fingerprint": case.fingerprint,
        "suite": SUITE, "source_url": source_url(case), "source_commit": SOURCE_COMMIT,
        "official_figure_kind": "official_notebook_result_figure",
        "official_figure_source": f"example/{case.official_notebook}#cell-{case.official_cell}",
        "claim_boundary": (
            "Native HiGHS optimization of the official IDAES-MVO discretized formulation and recorded subset."
            if report["execution_scope"] == "native"
            else "Official executed-notebook optimization evidence; trained surrogate artifacts are absent from the repository, so no local surrogate solve is claimed."
        ),
    })
    ir, sir = topology(case, report)
    output.mkdir(parents=True, exist_ok=False)
    write(output / f"{case.case_id}_topology_ir.json", ir)
    write(output / f"{case.case_id}_spec_ir.json", sir)
    write(report_path, report)
    write(output / "topology_prebuild_report_attempt0.json", {"pass": True, "case_id": case.case_id, "unit_count": len(ir["units"]), "arc_count": len(ir["arcs"])})
    official_figure = notebook_png(case)
    (output / "official_notebook_result.png").write_bytes(official_figure)
    (output / "source_flowchart.png").write_bytes(official_figure)
    (output / "case_result.png").write_bytes(result_figure)
    write(output / "official_figure_provenance.json", {"source_commit": SOURCE_COMMIT, "source_path": f"example/{case.official_notebook}", "notebook_cell": case.official_cell, "asset_kind": "executed_notebook_result_figure", "source_url": source_url(case), "sha256": hashlib.sha256(official_figure).hexdigest()})
    fv = stage_fv_data(case.case_id, topology_ir_fv(case.case_id, ir), "solve")
    write(output / "idaes_flowsheet_visualization.json", fv)
    return report


def registry_record(case: MvoCase, report: dict, order: int) -> dict:
    base = f"validation/VectorEngine_qwen36_validation/{case.case_id}"
    maturity = "native_optimized" if report["execution_scope"] == "native" else "official_notebook_optimized"
    return {
        "case_key": case.case_id, "label": case.label, "family": "mvo", "ecosystem": "IDAES-MVO", "process_family": "process_family_design",
        "tags": ["mvo", "process_family_design", "transcritical_co2", case.method, case.filter_name],
        "aliases": [case.label.lower(), case.case_id.replace("_", " ")], "suites": [SUITE], "order": order, "lifecycle": "active",
        "display_prompt": f"Optimize the {case.label} using the official IDAES-MVO transcritical CO2 process-family formulation.",
        "selection": {
            "case_key": case.case_id, "family": "mvo", "run_id": case.case_id, "selected_run_id": case.case_id,
            "status": "optimized", "selected_status": "optimized", "complexity_level": "process_family_optimization",
            "execution_status": "executed_pass" if report["execution_scope"] == "native" else "official_evidence_pass",
            "evidence_maturity": maturity, "claim_boundary": report["claim_boundary"],
            "topology_ir_file": f"{base}/{case.case_id}_topology_ir.json", "spec_ir_file": f"{base}/{case.case_id}_spec_ir.json",
            "solve_report_file": f"{base}/native_solve_report.json", "selected_validation_dir": base,
            "source_flowchart_file": f"{base}/source_flowchart.png", "source_manifest_path": source_url(case), "selected_by": SUITE,
        },
        "provenance": {"created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "created_by": Path(__file__).name, "source_commit": SOURCE_COMMIT, "source_notebook": case.official_notebook, "case_fingerprint": case.fingerprint},
    }


def merge_registry(reports: dict[str, dict]) -> None:
    registry = load(REGISTRY_PATH)
    expected = {case.case_id for case in CASES}
    existing = [row for row in registry["cases"] if SUITE in row.get("suites", [])]
    if existing:
        if {row["case_key"] for row in existing} != expected:
            raise RuntimeError("Existing MVO suite differs from manifest")
        return
    collisions = expected & {row["case_key"] for row in registry["cases"]}
    if collisions:
        raise RuntimeError(f"MVO case ID collisions: {sorted(collisions)}")
    start = max(row["order"] for row in registry["cases"]) + 1
    registry["cases"].extend(registry_record(case, reports[case.case_id], start + index) for index, case in enumerate(CASES))
    registry["suite_contracts"][SUITE] = {"expected_case_count": len(CASES), "frozen": False, "stage": "official_and_native_optimized"}
    registry["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write(REGISTRY_PATH, registry)


def main() -> None:
    write(MANIFEST_PATH, {"schema_version": 1, "suite": SUITE, "case_count": len(CASES), "source_commit": SOURCE_COMMIT, "cases": [{**asdict(case), "fingerprint": case.fingerprint, "source_url": source_url(case)} for case in CASES]})
    # Validate the smaller engineering subsets before spending several minutes on
    # the full 56-variant official discretized model. Registry order remains CASES.
    execution_order = (*CASES[2:], CASES[1], CASES[0])
    reports = {case.case_id: materialize(case) for case in execution_order}
    merge_registry(reports)
    print(json.dumps({"pass": True, "case_count": len(reports), "results": [{"case_id": case_id, "status": report["status"], "execution_scope": report["execution_scope"], "objective_value": report["metrics"]["objective_value"]} for case_id, report in reports.items()]}, indent=2))


if __name__ == "__main__":
    main()
