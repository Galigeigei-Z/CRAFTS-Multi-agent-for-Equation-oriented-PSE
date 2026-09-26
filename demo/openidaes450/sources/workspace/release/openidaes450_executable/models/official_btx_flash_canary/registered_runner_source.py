#!/usr/bin/env python3
"""Run the local BTX flash canary as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "examples" / "official_structfs_flash_flowsheet"
SOURCE_ROOT = CASE_PATH / "source_root"
LOCAL_REFERENCE_URL = "local://examples/official_structfs_flash_flowsheet"
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


def btx_port_values(port: Any) -> dict[str, Any]:
    comps = ("benzene", "toluene")
    return {
        "flow_mol": component_value(port.flow_mol, 0),
        "temperature": component_value(port.temperature, 0),
        "pressure": component_value(port.pressure, 0),
        "mole_frac_comp": {
            comp: component_value(port.mole_frac_comp, 0, comp)
            for comp in comps
        },
    }


def stream_values(model: Any) -> dict[str, Any]:
    fs = model.fs
    return {
        "flash_feed": btx_port_values(fs.flash.inlet),
        "flash_vapor_product": btx_port_values(fs.flash.vap_outlet),
        "flash_liquid_product": btx_port_values(fs.flash.liq_outlet),
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from notebook_build import (  # noqa: PLC0415
            build_model,
            initialize_model,
            set_operating_conditions,
            solve_model,
        )

        model = build_model()
        set_operating_conditions(model)
        initialize_model(model)
        results = solve_model(model, tee=tee)
        return {
            "pass": True,
            "stage": "steady_state_solver",
            "case_family": "btx_flash_canary",
            "official_reference_url": LOCAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": degrees_of_freedom(model),
            "stream_values": stream_values(model),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "btx_flash_canary",
            "official_reference_url": LOCAL_REFERENCE_URL,
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
