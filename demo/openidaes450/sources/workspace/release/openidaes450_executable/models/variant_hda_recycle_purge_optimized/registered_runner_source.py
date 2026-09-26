#!/usr/bin/env python3
"""Run the local HDA distillation reference case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any
from pyomo.environ import value


ROOT = Path(__file__).resolve().parents[1]
CURRENT_SOURCE_ROOT = ROOT / "examples" / "hda_distillation" / "source_root"
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/langgraph_idaes_pipeline"
)
LEGACY_SOURCE_RELATIVE = Path("examples/hda_distillation/source_root")
LEGACY_DEPENDENCY_RELATIVE = Path("examples/hda/source_root")
SOURCE_ROOT = (
    CURRENT_SOURCE_ROOT
    if (CURRENT_SOURCE_ROOT / "notebook_build.py").is_file()
    else LEGACY_ARTIFACT_ROOT / LEGACY_SOURCE_RELATIVE
)
SOURCE = SOURCE_ROOT / "notebook_build.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()


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


def btx_port_values(port: Any) -> dict[str, Any]:
    return {
        "flow_mol": component_value(port.flow_mol, 0),
        "mole_frac_comp": {
            "benzene": component_value(port.mole_frac_comp, 0, "benzene"),
            "toluene": component_value(port.mole_frac_comp, 0, "toluene"),
        },
        "temperature": component_value(port.temperature, 0),
        "pressure": component_value(port.pressure, 0),
    }


def hda_port_values(port: Any) -> dict[str, Any]:
    phases = ("Liq", "Vap")
    comps = ("benzene", "toluene", "hydrogen", "methane")
    return {
        "flow_mol_phase_comp": {
            f"{phase}:{comp}": component_value(port.flow_mol_phase_comp, 0, phase, comp)
            for phase in phases
            for comp in comps
        },
        "temperature": component_value(port.temperature, 0),
        "pressure": component_value(port.pressure, 0),
    }


def hda_stream_values(model: Any) -> dict[str, Any]:
    return {
        "s_toluene_feed_1": hda_port_values(model.fs.M101.toluene_feed),
        "s_hydrogen_feed_1": hda_port_values(model.fs.M101.hydrogen_feed),
        "s03": hda_port_values(model.fs.M101.outlet),
        "s04": hda_port_values(model.fs.H101.outlet),
        "s05": hda_port_values(model.fs.R101.outlet),
        "s06": hda_port_values(model.fs.F101.vap_outlet),
        "s08": hda_port_values(model.fs.S101.recycle),
        "s09": hda_port_values(model.fs.C101.outlet),
        "s10": hda_port_values(model.fs.F101.liq_outlet),
        "s11_pre_column": btx_port_values(model.fs.T101.outlet),
        "s11": btx_port_values(model.fs.H102.outlet),
        "H102_outlet_to_column_feed": btx_port_values(model.fs.H102.outlet),
        "COL1_condenser_distillate": btx_port_values(model.fs.COL1.condenser.distillate),
        "COL1_reboiler_bottoms": btx_port_values(model.fs.COL1.reboiler.bottoms),
    }


def run_case() -> dict[str, Any]:
    legacy_dependency_root = LEGACY_ARTIFACT_ROOT / LEGACY_DEPENDENCY_RELATIVE
    if SOURCE_ROOT != CURRENT_SOURCE_ROOT and str(legacy_dependency_root) not in sys.path:
        sys.path.insert(0, str(legacy_dependency_root))
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        if not SOURCE.is_file():
            raise FileNotFoundError(f"HDA distillation source binding is missing: {SOURCE}")
        spec = importlib.util.spec_from_file_location("hda_distillation_parent", SOURCE)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {SOURCE}")
        parent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parent)
        model = parent.build_model()
        parent.set_operating_conditions(model)
        parent.scale_flowsheet(model)
        parent.initialize_model(model)
        parent.solve_model(model)
        results = parent.add_column_and_solve(model)
        termination = str(results.solver.termination_condition)
        return {
            "pass": termination.lower() == "optimal" and degrees_of_freedom(model) == 0,
            "stage": "steady_state_solver",
            "termination_condition": termination,
            "final_dof": degrees_of_freedom(model),
            "stream_values": hda_stream_values(model),
            "source_model": (
                str(SOURCE.relative_to(ROOT))
                if SOURCE_ROOT == CURRENT_SOURCE_ROOT
                else str(LEGACY_SOURCE_RELATIVE / "notebook_build.py")
            ),
            "source_binding": {
                "kind": "current_source"
                if SOURCE_ROOT == CURRENT_SOURCE_ROOT
                else "explicit_legacy_artifact_root",
                "legacy_artifact_root": str(LEGACY_ARTIFACT_ROOT)
                if SOURCE_ROOT != CURRENT_SOURCE_ROOT
                else None,
                "relative_path": str(LEGACY_SOURCE_RELATIVE / "notebook_build.py"),
                "dependency_relative_path": str(LEGACY_DEPENDENCY_RELATIVE),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - serialize the validation failure.
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main_cli()
