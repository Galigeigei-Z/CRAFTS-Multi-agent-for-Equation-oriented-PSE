#!/usr/bin/env python3
"""Run the official IDAES SMR GibbsReactor flowsheet benchmark."""

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


SOURCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/UnitModels/Reactors/gibbs_reactor_doc.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/gibbs_reactor_smr_flowsheet/source_root")
COMPONENTS = ("CH4", "H2O", "H2", "CO", "CO2")


def load_notebook_build() -> Any:
    if str(CASE_ROOT) not in sys.path:
        sys.path.insert(0, str(CASE_ROOT))
    spec = importlib.util.spec_from_file_location("official_smr_gibbs_notebook_build", CASE_ROOT / "notebook_build.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def scalar(obj: Any, *index: Any) -> float | None:
    try:
        return float(value(obj[index] if index else obj))
    except Exception:
        return None


def vapor_stream(port: Any) -> dict[str, Any]:
    flow_mol = scalar(port.flow_mol, 0) or 0.0
    mole_frac = {component: scalar(port.mole_frac_comp, 0, component) for component in COMPONENTS}
    return {
        "flow_mol": flow_mol,
        "temperature": scalar(port.temperature, 0),
        "pressure": scalar(port.pressure, 0),
        "mole_frac_comp": mole_frac,
        "flow_mol_comp": {
            component: (flow_mol * frac if isinstance(frac, (int, float)) else None)
            for component, frac in mole_frac.items()
        },
    }


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        nb = load_notebook_build()
        model = nb.build_model()
        nb.set_operating_conditions(model)
        initial_dof = degrees_of_freedom(model)
        nb.initialize_model(model)
        results = nb.solve_model(model, tee=tee)
        termination = results.solver.termination_condition
        final_dof = degrees_of_freedom(model)
        passed = bool(termination == TerminationCondition.optimal and final_dof == 0)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "smr_gibbs_flowsheet",
            "source_url": SOURCE_URL,
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "termination_condition": str(termination),
            "hydrogen_production_mlb_per_year": scalar(model.fs.hyd_prod),
            "methane_conversion": scalar(model.fs.R101.conversion),
            "stream_values": {
                "methane_feed": vapor_stream(model.fs.CH4.outlet),
                "steam_feed": vapor_stream(model.fs.H2O.outlet),
                "mixed_feed": vapor_stream(model.fs.M101.outlet),
                "compressed_feed": vapor_stream(model.fs.C101.outlet),
                "heated_feed": vapor_stream(model.fs.H101.outlet),
                "reactor_outlet": vapor_stream(model.fs.R101.outlet),
                "product": vapor_stream(model.fs.PROD.inlet),
            },
            "error": None if passed else {"message": "SMR Gibbs solve did not reach optimal zero-DOF state"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "smr_gibbs_flowsheet",
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
