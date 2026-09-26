#!/usr/bin/env python3
"""Run the official IDAES NGCC gas turbine subflowsheet as a Stage-3 target."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_REPO = ROOT / "examples" / "github_examples" / "clones" / "examples"
NGCC_SOURCE_DIR = EXAMPLES_REPO / "src" / "Examples" / "Flowsheets" / "power_generation" / "ngcc"
OFFICIAL_REFERENCE_URL = "local://idaes_examples/power_gen/ngcc/gas_turbine_subflowsheet"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402
from stage3_specs_solve.stream_extract import port_stream_values  # noqa: E402
from stage3_specs_solve.native_topology_probe import probe_native_topology  # noqa: E402


def component_value(obj: Any, *index: Any) -> float | None:
    if index:
        try:
            return float(value(obj[index]))
        except Exception:
            pass
    try:
        if hasattr(obj, "is_indexed") and obj.is_indexed():
            return float(value(obj[next(iter(obj))]))
    except Exception:
        pass
    try:
        return float(value(obj))
    except Exception:
        return None


def load_official_gas_turbine_module() -> Any:
    source = NGCC_SOURCE_DIR / "gas_turbine.py"
    spec = importlib.util.spec_from_file_location("idaes_examples_ngcc_gas_turbine", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load official gas turbine source: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_case(report_path: Path, tee: bool = False) -> dict[str, Any]:
    try:
        import idaes  # noqa: PLC0415
        import idaes.core.util.scaling as iscale  # noqa: PLC0415
        import pyomo.environ as pyo  # noqa: PLC0415
        from idaes.core.solvers import use_idaes_solver_configuration_defaults  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.opt import SolverStatus, TerminationCondition  # noqa: PLC0415

        if not EXAMPLES_REPO.is_dir():
            raise RuntimeError(f"IDAES examples repo not found: {EXAMPLES_REPO}")
        gas_turbine = load_official_gas_turbine_module()

        work_dir = report_path.parent
        init_source = NGCC_SOURCE_DIR / "gas_turbine_init.json.gz"
        if not init_source.is_file():
            raise RuntimeError(f"Official gas turbine init JSON not found: {init_source}")
        shutil.copy2(init_source, work_dir / "gas_turbine_init.json.gz")

        use_idaes_solver_configuration_defaults()
        idaes.cfg.ipopt.options.nlp_scaling_method = "user-scaling"
        idaes.cfg.ipopt.options.linear_solver = "ma57"
        idaes.cfg.ipopt.options.OF_ma57_automatic_scaling = "yes"
        idaes.cfg.ipopt.options.ma57_pivtol = 1e-5
        idaes.cfg.ipopt.options.ma57_pivtolmax = 0.1

        model = pyo.ConcreteModel()
        model.fs = gas_turbine.GasTurbineFlowsheet(dynamic=False)
        iscale.calculate_scaling_factors(model)
        model.fs.initialize(
            load_from=str(work_dir / "gas_turbine_init.json.gz"),
            save_to=str(work_dir / "gas_turbine_init.json.gz"),
        )
        results = pyo.SolverFactory("ipopt").solve(model, tee=tee)
        optimal = (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )
        final_dof = degrees_of_freedom(model)
        gt_power_mw = None
        gt_power = component_value(model.fs.gt_power, 0)
        if gt_power is not None:
            gt_power_mw = -gt_power * 1e-6
        native_topology_binding = probe_native_topology(
            model,
            units={
                candidate: f"fs.{candidate}"
                for candidate in (
                    "feed_air1", "vsv", "cmp1", "splt1", "feed_fuel1", "ng_preheat",
                    "inject1", "cmb1", "gts1", "mx1", "gts2", "mx2", "gts3", "mx3",
                    "exhaust_1",
                )
            },
            arcs={
                "air_to_vsv": ("fs.feed_air1.outlet", "fs.vsv.inlet"),
                "vsv_to_cmp": ("fs.vsv.outlet", "fs.cmp1.inlet"),
                "cmp_to_split": ("fs.cmp1.outlet", "fs.splt1.inlet"),
                "fuel_to_preheat": ("fs.feed_fuel1.outlet", "fs.ng_preheat.cold_side_inlet"),
                "preheat_to_mixer": ("fs.ng_preheat.cold_side_outlet", "fs.inject1.gas"),
                "air_to_mixer": ("fs.splt1.air04", "fs.inject1.air"),
                "mixer_to_combustor": ("fs.inject1.outlet", "fs.cmb1.inlet"),
                "combustor_to_stage1": ("fs.cmb1.outlet", "fs.gts1.inlet"),
                "stage1_to_mx1": ("fs.gts1.outlet", "fs.mx1.gas"),
                "cool1_to_mx1": ("fs.splt1.air05", "fs.mx1.air"),
                "mx1_to_stage2": ("fs.mx1.outlet", "fs.gts2.inlet"),
                "stage2_to_mx2": ("fs.gts2.outlet", "fs.mx2.gas"),
                "cool2_to_mx2": ("fs.splt1.air07", "fs.mx2.air"),
                "mx2_to_stage3": ("fs.mx2.outlet", "fs.gts3.inlet"),
                "stage3_to_mx3": ("fs.gts3.outlet", "fs.mx3.gas"),
                "cool3_to_mx3": ("fs.splt1.air09", "fs.mx3.air"),
                "mx3_to_exhaust": ("fs.mx3.outlet", "fs.exhaust_1.inlet"),
            },
        )
        passed = bool(
            optimal and final_dof == 0 and gt_power_mw is not None and gt_power_mw > 0
            and native_topology_binding["passed"]
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "ngcc_gas_turbine_subflowsheet",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "final_dof": final_dof,
            "gt_power_mw": gt_power_mw,
            "stream_values": port_stream_values(model),
            "native_topology_binding": native_topology_binding,
            "source_summary": {
                "source": "idaes_examples.mod.power_gen.gas_turbine.GasTurbineFlowsheet",
                "init_json": str(init_source),
            },
            "error": None if passed else {"message": "NGCC gas turbine subflowsheet did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "ngcc_gas_turbine_subflowsheet",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_case(report_path, tee=args.tee)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
