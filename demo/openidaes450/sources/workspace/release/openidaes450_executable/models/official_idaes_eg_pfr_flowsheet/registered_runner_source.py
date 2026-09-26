#!/usr/bin/env python3
"""Run the official IDAES ethylene glycol PFR flowsheet benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "core"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import TerminationCondition, value  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402


SOURCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/UnitModels/Reactors/plug_flow_reactor_doc.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/pfr_ethylene_glycol_flowsheet/source_root")
COMPONENTS = ("ethylene_oxide", "water", "sulfuric_acid", "ethylene_glycol")


def load_notebook_build() -> Any:
    if str(CASE_ROOT) not in sys.path:
        sys.path.insert(0, str(CASE_ROOT))
    spec = importlib.util.spec_from_file_location("official_eg_pfr_notebook_build", CASE_ROOT / "notebook_build.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def liquid_stream(port: Any) -> dict[str, Any]:
    comp_flows = {component: scalar(port.flow_mol_phase_comp, 0, "Liq", component) or 0.0 for component in COMPONENTS}
    total = sum(comp_flows.values())
    return {
        "flow_mol": total,
        "temperature": scalar(port.temperature, 0),
        "pressure": scalar(port.pressure, 0),
        "mole_frac_comp": {component: (flow / total if total else None) for component, flow in comp_flows.items()},
        "flow_mol_comp": comp_flows,
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        nb = load_notebook_build()
        model = nb.build_model()
        nb.set_operating_conditions(model)
        initial_dof = degrees_of_freedom(model)
        results = nb.solve_model(model, tee=tee)
        termination = results.solver.termination_condition
        final_dof = degrees_of_freedom(model)
        passed = bool(termination == TerminationCondition.optimal and final_dof == 0)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "eg_pfr_flowsheet",
            "source_url": SOURCE_URL,
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "termination_condition": str(termination),
            "ethylene_glycol_production_mlb_per_year": scalar(model.fs.eg_prod),
            "pfr_conversion": scalar(model.fs.R101.conversion),
            "stream_values": {
                "oxide_feed": liquid_stream(model.fs.OXIDE.outlet),
                "acid_feed": liquid_stream(model.fs.ACID.outlet),
                "mixed_feed": liquid_stream(model.fs.M101.outlet),
                "heated_feed": liquid_stream(model.fs.H101.outlet),
                "reactor_outlet": liquid_stream(model.fs.R101.outlet),
                "product": liquid_stream(model.fs.PROD.inlet),
            },
            "error": None if passed else {"message": "EG PFR solve did not reach optimal zero-DOF state"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "eg_pfr_flowsheet",
            "source_url": SOURCE_URL,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case(tee=args.tee)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
