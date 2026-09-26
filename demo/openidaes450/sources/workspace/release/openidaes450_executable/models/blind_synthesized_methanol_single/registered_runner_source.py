#!/usr/bin/env python3
"""Run the local official methanol single-pass reference case as Stage-3 validation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "examples" / "methanol"
CURRENT_SOURCE_ROOT = CASE_PATH / "source_root"
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/langgraph_idaes_pipeline"
)
LEGACY_SOURCE_RELATIVE = Path("examples/methanol/source_root")
SOURCE_ROOT = (
    CURRENT_SOURCE_ROOT
    if (CURRENT_SOURCE_ROOT / "notebook_build.py").is_file()
    else LEGACY_ARTIFACT_ROOT / LEGACY_SOURCE_RELATIVE
)
LOCAL_REFERENCE_URL = "local://examples/methanol"
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/methanol_synthesis_doc.html"
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


def port_values(port: Any) -> dict[str, Any]:
    comps = ("H2", "CO", "CH3OH", "CH4")
    data = {
        "flow_mol": component_value(port.flow_mol, 0) if hasattr(port, "flow_mol") else None,
        "temperature": component_value(port.temperature, 0) if hasattr(port, "temperature") else None,
        "pressure": component_value(port.pressure, 0) if hasattr(port, "pressure") else None,
        "enth_mol": component_value(port.enth_mol, 0) if hasattr(port, "enth_mol") else None,
    }
    if hasattr(port, "mole_frac_comp"):
        data["mole_frac_comp"] = {comp: component_value(port.mole_frac_comp, 0, comp) for comp in comps}
    return data


def stream_values(model: Any) -> dict[str, Any]:
    fs = model.fs
    return {
        "s01_H2_feed": port_values(fs.H2.outlet),
        "s02_CO_feed": port_values(fs.CO.outlet),
        "s03_fresh_syngas": port_values(fs.M101.outlet),
        "s04_compressor_outlet": port_values(fs.C101.outlet),
        "s05_reactor_feed": port_values(fs.H101.outlet),
        "s06_reactor_effluent": port_values(fs.R101.outlet),
        "s07_turbine_outlet": port_values(fs.T101.outlet),
        "s08_flash_feed": port_values(fs.H102.outlet),
        "s09_flash_vapor_exhaust": port_values(fs.EXHAUST.inlet),
        "s10_methanol_product": port_values(fs.CH3OH.inlet),
    }


def methanol_recovery_pct(model: Any) -> float | None:
    try:
        fs = model.fs
        inlet = value(fs.F101.inlet.flow_mol[0] * fs.F101.inlet.mole_frac_comp[0, "CH3OH"])
        liquid = value(fs.F101.liq_outlet.flow_mol[0] * fs.F101.liq_outlet.mole_frac_comp[0, "CH3OH"])
        return float((liquid / inlet) * 100) if inlet else None
    except Exception:
        return None


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        source_file = SOURCE_ROOT / "notebook_build.py"
        if not source_file.is_file():
            raise FileNotFoundError(f"Methanol single source binding is missing: {source_file}")
        spec = importlib.util.spec_from_file_location(
            "methanol_single_registered_notebook_build",
            source_file,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load Methanol single source binding: {source_file}")
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
        fs = model.fs
        return {
            "pass": True,
            "stage": "steady_state_solver",
            "case_family": "methanol_single",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "local_reference_url": LOCAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": degrees_of_freedom(model),
            "reactor_co_conversion": component_value(fs.R101.co_conversion),
            "reactor_heat_duty_w": component_value(fs.R101.heat_duty, 0),
            "turbine_work_w": component_value(fs.T101.work_isentropic, 0),
            "flash_liquid_methanol_recovery_pct": methanol_recovery_pct(model),
            "stream_values": stream_values(model),
            "source_binding": {
                "kind": "current_source"
                if SOURCE_ROOT == CURRENT_SOURCE_ROOT
                else "explicit_legacy_artifact_root",
                "legacy_artifact_root": str(LEGACY_ARTIFACT_ROOT)
                if SOURCE_ROOT != CURRENT_SOURCE_ROOT
                else None,
                "relative_path": str(LEGACY_SOURCE_RELATIVE / "notebook_build.py"),
                "module_namespace": "methanol_single_registered_notebook_build",
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "methanol_single",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "local_reference_url": LOCAL_REFERENCE_URL,
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
