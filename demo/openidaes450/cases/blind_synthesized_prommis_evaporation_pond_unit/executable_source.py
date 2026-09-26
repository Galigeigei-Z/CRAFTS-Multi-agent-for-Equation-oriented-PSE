#!/usr/bin/env python3
"""Run official PrOMMiS evaporation pond unit validation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core import FlowsheetBlock  # noqa: E402
from idaes.core.initialization import InitializationStatus  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import ConcreteModel, check_optimal_termination, units, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.evaporation_pond.evaporation_pond.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"


def _prepare_imports() -> None:
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))


def scalar(obj: Any) -> float | None:
    try:
        return float(value(obj))
    except Exception:
        return None


def approx(actual: float | None, expected: float, *, rel: float = 1e-5, abs_tol: float = 0.0) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def build_model() -> Any:
    _prepare_imports()
    from prommis.evaporation_pond.evaporation_pond import EvaporationPond  # noqa: PLC0415
    from prommis.evaporation_pond.tests.example_properties import BrineParameters  # noqa: PLC0415
    from prommis.evaporation_pond.tests.example_reactions import BrineReactionParameters  # noqa: PLC0415

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.brine_props = BrineParameters()
    m.fs.brine_rxns = BrineReactionParameters(property_package=m.fs.brine_props)
    m.fs.pond = EvaporationPond(property_package=m.fs.brine_props, reaction_package=m.fs.brine_rxns)
    m.fs.pond.inlet.flow_vol.fix(240 * units.L / units.s)
    m.fs.pond.inlet.conc_mass_comp[0, "Li"].fix(650 * units.mg / units.L)
    m.fs.pond.inlet.conc_mass_comp[0, "Na"].fix(650 * units.mg / units.L)
    m.fs.pond.inlet.conc_mass_comp[0, "Cl"].fix(4310 * units.mg / units.L)
    m.fs.pond.inlet.conc_mass_comp[0, "H2O"].fix(1 * units.kg / units.L)
    m.fs.pond.surface_area.fix(50000 * units.m**2)
    m.fs.pond.average_pond_depth.fix(0.5 * units.m)
    m.fs.pond.evaporation_rate.fix(4.75 * units.mm / units.day)
    return m


def run_case() -> dict[str, Any]:
    try:
        _prepare_imports()
        from prommis.evaporation_pond.evaporation_pond import EvaporationPondInitializer  # noqa: PLC0415

        model = build_model()
        unit = model.fs.pond
        initializer = EvaporationPondInitializer()
        initializer.initialize(unit)
        init_ok = initializer.summary[unit]["status"] == InitializationStatus.Ok
        results = get_solver().solve(model, tee=False)
        optimal = check_optimal_termination(results)
        final_dof = degrees_of_freedom(model)
        outputs = {
            "outlet_flow_vol": scalar(unit.outlet.flow_vol[0]),
            "outlet_h2o": scalar(unit.outlet.conc_mass_comp[0, "H2O"]),
            "outlet_cl": scalar(unit.outlet.conc_mass_comp[0, "Cl"]),
            "outlet_li": scalar(unit.outlet.conc_mass_comp[0, "Li"]),
            "outlet_na": scalar(unit.outlet.conc_mass_comp[0, "Na"]),
            "volume": scalar(unit.volume[0]),
            "precipitation_na": scalar(unit.precipitation_rate[0, "Na"]),
            "precipitation_cl": scalar(unit.precipitation_rate[0, "Cl"]),
            "precipitation_li": scalar(unit.precipitation_rate[0, "Li"]),
        }
        checks = [
            {"name": "evaporation_pond_initializer_ok", "pass": bool(init_ok), "actual": str(initializer.summary[unit]["status"])},
            {"name": "evaporation_pond_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "evaporation_pond_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "evaporation_pond_outlet_flow_matches_official_test", "pass": approx(outputs["outlet_flow_vol"], 854104), "actual": outputs["outlet_flow_vol"]},
            {"name": "evaporation_pond_outlet_cl_matches_official_test", "pass": approx(outputs["outlet_cl"], 3933.85), "actual": outputs["outlet_cl"]},
            {"name": "evaporation_pond_outlet_li_matches_official_test", "pass": approx(outputs["outlet_li"], 657.531), "actual": outputs["outlet_li"]},
            {"name": "evaporation_pond_outlet_na_matches_official_test", "pass": approx(outputs["outlet_na"], 381.203), "actual": outputs["outlet_na"]},
            {"name": "evaporation_pond_volume_matches_official_test", "pass": approx(outputs["volume"], 25000), "actual": outputs["volume"]},
            {"name": "evaporation_pond_na_precipitation_matches_official_test", "pass": approx(outputs["precipitation_na"], -10265.9), "actual": outputs["precipitation_na"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_evaporation_pond_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "evaporation_pond" / "evaporation_pond.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "evaporation_pond" / "tests" / "test_evaporation_pond.py"),
                "official_module": "prommis.evaporation_pond.evaporation_pond",
            },
            "error": None if passed else {"message": "PrOMMiS evaporation pond checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_evaporation_pond_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_summary": {"source_root": str(SOURCE_ROOT)},
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
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
