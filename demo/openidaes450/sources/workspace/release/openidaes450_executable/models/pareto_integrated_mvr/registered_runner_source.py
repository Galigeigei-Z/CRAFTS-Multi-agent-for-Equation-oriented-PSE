#!/usr/bin/env python3
"""Run PARETO source-backed examples and report solved stream values."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from source_runner_utils import port_values, read_topology_ir, stream_table_from_values, write_report  # noqa: E402


SOURCE_ROOT = ROOT / ".external_sources" / "project_pareto_source"
ZIP_URL = "https://github.com/project-pareto/project-pareto/archive/refs/heads/main.zip"


def ensure_pareto_source() -> Path:
    package_marker = SOURCE_ROOT / "project-pareto-main" / "pareto" / "__init__.py"
    if not package_marker.exists():
        SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
        zip_path = SOURCE_ROOT / "project-pareto-main.zip"
        with urllib.request.urlopen(ZIP_URL, timeout=180) as response:
            zip_path.write_bytes(response.read())
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(SOURCE_ROOT)
    src = SOURCE_ROOT / "project-pareto-main"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return src


def arc_stream_values(model: Any, arc_names: list[str]) -> dict[str, dict[str, Any]]:
    stream_values: dict[str, dict[str, Any]] = {}
    fs = model.fs
    for name in arc_names:
        arc = getattr(fs, name, None)
        port = getattr(arc, "source", None)
        if port is None:
            continue
        values = port_values(port)
        if values:
            stream_values[name] = values
    return stream_values


def run_md() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.environ import check_optimal_termination

    ensure_pareto_source()
    md_flow = importlib.import_module("pareto.models_extra.desalination_models.MD_single_stage_continuous_recirculation")
    model = md_flow.build()
    md_flow.set_operating_conditions(model, feed_flow_mass=1, feed_mass_frac_TDS=0.035, overall_recovery=0.5)
    md_flow.initialize_system(model, verbose=False)
    md_flow.optimize_set_up(model)
    results = md_flow.solve(model, tee=False)
    stream_values = arc_stream_values(model, [f"s{i:02d}" for i in range(1, 16)])
    return stream_values, {
        "source_runner": "pareto.models_extra.desalination_models.MD_single_stage_continuous_recirculation",
        "termination_condition": str(results.solver.termination_condition),
        "solver_status": str(results.solver.status),
        "final_dof": degrees_of_freedom(model),
        "optimal": bool(check_optimal_termination(results)),
    }


def run_operational() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    from importlib import resources
    from pyomo.environ import value

    ensure_pareto_source()
    model_mod = importlib.import_module("pareto.operational_water_management.operational_produced_water_optimization_model")
    data_mod = importlib.import_module("pareto.utilities.get_data")
    result_mod = importlib.import_module("pareto.utilities.results")
    solver_mod = importlib.import_module("pareto.utilities.solvers")

    set_list = [
        "ProductionPads", "CompletionsPads", "ProductionTanks", "ExternalWaterSources",
        "WaterQualityComponents", "StorageSites", "SWDSites", "TreatmentSites",
        "ReuseOptions", "NetworkNodes",
    ]
    parameter_list = [
        "Units", "RCA", "FCA", "PCT", "FCT", "CCT", "PKT", "PRT", "CKT", "CRT",
        "PAL", "CompletionsDemand", "PadRates", "TankFlowbackRates", "FlowbackRates",
        "ProductionTankCapacity", "DisposalCapacity", "CompletionsPadStorage",
        "TreatmentCapacity", "ExtWaterSourcingAvailability", "PadOffloadingCapacity",
        "TruckingTime", "DisposalOperationalCost", "TreatmentOperationalCost",
        "ReuseOperationalCost", "PadStorageCost", "PipelineOperationalCost",
        "TruckingHourlyCost", "ExternalSourcingCost", "ProductionRates",
        "TreatmentEfficiency", "ExternalWaterQuality", "PadWaterQuality",
        "StorageInitialWaterQuality",
    ]
    with resources.path("pareto.case_studies", "operational_generic_case_study.xlsx") as fpath:
        df_sets, df_parameters = data_mod.get_data(fpath, set_list, parameter_list)
    df_parameters["MinTruckFlow"] = 0
    df_parameters["MaxTruckFlow"] = 259000
    model = model_mod.create_model(
        df_sets,
        df_parameters,
        default={
            "has_pipeline_constraints": True,
            "production_tanks": model_mod.ProdTank.equalized,
            "water_quality": model_mod.WaterQuality.false,
        },
    )
    opt = solver_mod.get_solver("gurobi_direct", "gurobi", "cbc")
    solver_mod.set_timeout(opt, timeout_s=60)
    results = opt.solve(model, tee=False)
    feasible = result_mod.is_feasible(model)
    stream_values: dict[str, dict[str, Any]] = {}
    for var_name in ["v_F_Trucked", "v_C_Trucked"]:
        var = getattr(model, var_name, None)
        if var is None:
            continue
        for key in var:
            val = value(var[key], exception=False)
            if val is not None and abs(float(val)) > 1e-8:
                stream_values[f"{var_name}[{','.join(map(str, key if isinstance(key, tuple) else (key,)))}]"] = {"flow_bbl_per_day": float(val)}
    return stream_values, {
        "source_runner": "pareto.operational_water_management.run_operational_model",
        "termination_condition": str(results.solver.termination_condition),
        "solver_status": str(results.solver.status),
        "final_dof": None,
        "optimal": bool(feasible),
    }


def run_strategic() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    from importlib import resources
    from pyomo.environ import value

    ensure_pareto_source()
    strategic = importlib.import_module("pareto.strategic_water_management.strategic_produced_water_optimization")
    data_mod = importlib.import_module("pareto.utilities.get_data")
    result_mod = importlib.import_module("pareto.utilities.results")

    with resources.path("pareto.case_studies", "strategic_toy_case_study.xlsx") as fpath:
        df_sets, df_parameters = data_mod.get_data(fpath, model_type="strategic")
    model = strategic.create_model(
        df_sets,
        df_parameters,
        default={
            "objective": strategic.Objectives.cost,
            "pipeline_cost": strategic.PipelineCost.distance_based,
            "pipeline_capacity": strategic.PipelineCapacity.input,
            "hydraulics": strategic.Hydraulics.false,
            "desalination_model": strategic.DesalinationModel.false,
            "node_capacity": True,
            "water_quality": strategic.WaterQuality.false,
            "removal_efficiency_method": strategic.RemovalEfficiencyMethod.concentration_based,
            "infrastructure_timing": strategic.InfrastructureTiming.true,
            "subsurface_risk": strategic.SubsurfaceRisk.false,
        },
    )
    results = strategic.solve_model(
        model=model,
        options={"deactivate_slacks": True, "scale_model": False, "scaling_factor": 1000, "running_time": 200, "gap": 0},
    )
    feasible = result_mod.is_feasible(model)
    stream_values: dict[str, dict[str, Any]] = {}
    for var_name in ["v_F_Piped", "v_C_Piped", "v_F_Trucked", "v_C_Trucked"]:
        var = getattr(model, var_name, None)
        if var is None:
            continue
        for key in var:
            val = value(var[key], exception=False)
            if val is not None and abs(float(val)) > 1e-8:
                stream_values[f"{var_name}[{','.join(map(str, key if isinstance(key, tuple) else (key,)))}]"] = {"flow_bbl_per_day": float(val)}
    return stream_values, {
        "source_runner": "pareto.strategic_water_management.run_strategic_model",
        "termination_condition": str(getattr(results.solver, "termination_condition", None)),
        "solver_status": str(getattr(results.solver, "status", None)),
        "final_dof": None,
        "optimal": bool(feasible),
    }


def run_case(report_path: Path) -> dict[str, Any]:
    topology_ir = read_topology_ir(report_path)
    family = str(topology_ir.get("family") or "")
    try:
        if family == "family_nonofficial_pareto_membrane_distillation":
            stream_values, metadata = run_md()
        elif family == "family_nonofficial_pareto_strategic_network":
            stream_values, metadata = run_strategic()
        else:
            stream_values, metadata = run_operational()
        passed = bool(metadata["optimal"] and stream_values)
        return {
            "pass": passed,
            "status": "solved" if passed else "failed",
            "stage": "pareto_source_solve",
            "case_id": topology_ir.get("case_id"),
            "case_family": family,
            "source_url": topology_ir.get("source_url"),
            "source_runner": metadata["source_runner"],
            "termination_condition": metadata["termination_condition"],
            "solver_status": metadata["solver_status"],
            "final_dof": metadata["final_dof"],
            "stream_values": stream_values,
            "stream_table": stream_table_from_values(stream_values),
            "source_summary": {
                "source": "project-pareto source model",
                "stream_count": len(stream_values),
            },
            "error": None,
        }
    except Exception as exc:
        return {
            "pass": False,
            "status": "failed",
            "stage": "pareto_source_solve",
            "case_id": topology_ir.get("case_id"),
            "case_family": family,
            "source_url": topology_ir.get("source_url"),
            "termination_condition": None,
            "solver_status": None,
            "final_dof": None,
            "stream_values": {},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report_path = Path(args.report)
    report = run_case(report_path)
    write_report(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
