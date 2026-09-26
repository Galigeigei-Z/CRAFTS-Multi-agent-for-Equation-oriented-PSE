#!/usr/bin/env python3
"""Run the official IDAES NGCC steam turbine subflowsheet as a Stage-3 target."""

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
EXAMPLES_REPO = ROOT / "experiment" / "runtime_data" / "official_idaes_examples_snapshot_v1"
NGCC_SOURCE_DIR = EXAMPLES_REPO / "idaes_examples" / "mod" / "power_gen"
NGCC_NOTEBOOK_DIR = EXAMPLES_REPO / "idaes_examples" / "notebooks" / "docs" / "power_gen" / "ngcc"
OFFICIAL_REFERENCE_URL = "local://idaes_examples/power_gen/ngcc/steam_turbine_subflowsheet"
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


def load_official_steam_turbine_module() -> Any:
    source = NGCC_SOURCE_DIR / "steam_turbine.py"
    spec = importlib.util.spec_from_file_location("idaes_examples_ngcc_steam_turbine", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load official steam turbine source: {source}")
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
        steam_turbine = load_official_steam_turbine_module()

        work_dir = report_path.parent
        init_source = NGCC_NOTEBOOK_DIR / "steam_turbine_init.json.gz"
        if not init_source.is_file():
            raise RuntimeError(f"Official steam turbine init JSON not found: {init_source}")
        shutil.copy2(init_source, work_dir / "steam_turbine_init.json.gz")

        use_idaes_solver_configuration_defaults()
        idaes.cfg.ipopt.options.nlp_scaling_method = "user-scaling"
        idaes.cfg.ipopt.options.linear_solver = "ma57"
        idaes.cfg.ipopt.options.OF_ma57_automatic_scaling = "yes"
        idaes.cfg.ipopt.options.ma57_pivtol = 1e-5
        idaes.cfg.ipopt.options.ma57_pivtolmax = 0.1

        model = pyo.ConcreteModel()
        model.fs = steam_turbine.SteamTurbineFlowsheet(dynamic=False)
        iscale.calculate_scaling_factors(model)
        model.fs.initialize(
            load_from=str(work_dir / "steam_turbine_init.json.gz"),
            save_to=str(work_dir / "steam_turbine_init.json.gz"),
        )
        results = pyo.SolverFactory("ipopt").solve(model, tee=tee)
        optimal = (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )
        final_dof = degrees_of_freedom(model)
        power = component_value(model.fs.steam_turbine.power, 0)
        steam_turbine_power_mw = -power * 1e-6 if power is not None else None
        native_topology_binding = probe_native_topology(
            model,
            units={
                candidate: f"fs.{candidate}"
                for candidate in (
                    "steam_turbine", "dummy_reheat", "steam_turbine_lp_mix",
                    "steam_turbine_lp_split", "main_condenser", "hotwell", "cond_pump",
                    "reboiler", "return_mix",
                )
            },
            arcs={
                "hp_to_reheat": ("fs.steam_turbine.hp_stages[7].outlet", "fs.dummy_reheat.inlet"),
                "reheat_to_ip": ("fs.dummy_reheat.outlet", "fs.steam_turbine.ip_stages[1].inlet"),
                "ip_to_lp_mix": ("fs.steam_turbine.ip_stages[10].outlet", "fs.steam_turbine_lp_mix.turbine"),
                "lp_mix_to_split": ("fs.steam_turbine_lp_mix.outlet", "fs.steam_turbine_lp_split.inlet"),
                "split_to_lp": ("fs.steam_turbine_lp_split.turbine", "fs.steam_turbine.lp_stages[1].inlet"),
                "lp_to_condenser": ("fs.steam_turbine.outlet_stage.outlet", "fs.main_condenser.shell_inlet"),
                "condenser_to_hotwell": ("fs.main_condenser.shell_outlet", "fs.hotwell.condensate"),
                "hotwell_to_pump": ("fs.hotwell.outlet", "fs.cond_pump.inlet"),
                "pump_to_return": ("fs.cond_pump.outlet", "fs.return_mix.pump"),
                "split_to_reboiler": ("fs.steam_turbine_lp_split.reboiler", "fs.reboiler.inlet"),
                "reboiler_to_return": ("fs.reboiler.outlet", "fs.return_mix.reboiler"),
            },
        )
        passed = bool(
            optimal and final_dof == 0 and steam_turbine_power_mw is not None
            and steam_turbine_power_mw > 0 and native_topology_binding["passed"]
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "ngcc_steam_turbine_subflowsheet",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "final_dof": final_dof,
            "steam_turbine_power_mw": steam_turbine_power_mw,
            "stream_values": port_stream_values(model),
            "native_topology_binding": native_topology_binding,
            "source_summary": {
                "source": "idaes_examples.mod.power_gen.steam_turbine.SteamTurbineFlowsheet",
                "init_json": str(init_source),
            },
            "error": None if passed else {"message": "NGCC steam turbine subflowsheet did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "ngcc_steam_turbine_subflowsheet",
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
