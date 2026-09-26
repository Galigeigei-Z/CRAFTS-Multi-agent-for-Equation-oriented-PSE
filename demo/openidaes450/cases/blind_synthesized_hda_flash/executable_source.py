#!/usr/bin/env python3
"""Run the local HDA flash reference case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "examples" / "hda_flash"
CURRENT_SOURCE_ROOT = CASE_PATH / "source_root"
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/langgraph_idaes_pipeline"
)
LEGACY_SOURCE_RELATIVE = Path("examples/hda_flash/source_root")
SOURCE_ROOT = (
    CURRENT_SOURCE_ROOT
    if (CURRENT_SOURCE_ROOT / "notebook_build.py").is_file()
    else LEGACY_ARTIFACT_ROOT / LEGACY_SOURCE_RELATIVE
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402


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


def stream_values(model: Any) -> dict[str, Any]:
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
        "S101_purge": hda_port_values(model.fs.S101.purge),
        "F102_vapor_product": hda_port_values(model.fs.F102.vap_outlet),
        "F102_liquid_product": hda_port_values(model.fs.F102.liq_outlet),
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        source_file = SOURCE_ROOT / "notebook_build.py"
        if not source_file.is_file():
            raise FileNotFoundError(f"HDA Flash source binding is missing: {source_file}")
        spec = importlib.util.spec_from_file_location("hda_flash_registered_notebook_build", source_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load HDA Flash source binding: {source_file}")
        source_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source_module)
        build_model = source_module.build_model
        initialize_model = source_module.initialize_model
        set_operating_conditions = source_module.set_operating_conditions
        solve_model = source_module.solve_model

        model = build_model()
        set_operating_conditions(model)
        initialize_model(model)
        results = solve_model(model, tee=tee)
        return {
            "pass": True,
            "stage": "steady_state_solver",
            "case_family": "hda_flash",
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": degrees_of_freedom(model),
            "stream_values": stream_values(model),
            "source_binding": {
                "kind": "current_source"
                if SOURCE_ROOT == CURRENT_SOURCE_ROOT
                else "explicit_legacy_artifact_root",
                "legacy_artifact_root": str(LEGACY_ARTIFACT_ROOT)
                if SOURCE_ROOT != CURRENT_SOURCE_ROOT
                else None,
                "relative_path": str(LEGACY_SOURCE_RELATIVE / "notebook_build.py"),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - serialize validation failure.
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "hda_flash",
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case(tee=args.tee)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
