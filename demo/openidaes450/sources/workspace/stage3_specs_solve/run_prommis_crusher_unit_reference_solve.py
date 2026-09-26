#!/usr/bin/env python3
"""Run official PrOMMiS crusher unit validation."""

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
from idaes.core.initialization import BlockTriangularizationInitializer, InitializationStatus  # noqa: E402
from idaes.core.solvers import get_solver  # noqa: E402
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import ConcreteModel, check_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.solid_handling.crusher.html"
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
    from prommis.solid_handling.crusher import Crusher  # noqa: PLC0415
    from prommis.solid_handling.crusher_solids_properties import CoalRefuseParameters  # noqa: PLC0415

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties_solid = CoalRefuseParameters(doc="solid property")
    m.fs.crusher = Crusher(property_package=m.fs.properties_solid)
    m.fs.crusher.inlet.mass_frac_comp[0, :].fix(0.1)
    m.fs.crusher.properties_in[0].flow_mass.fix(2000)
    m.fs.crusher.properties_in[0].particle_size_median.fix(80)
    m.fs.crusher.properties_in[0].particle_size_width.fix(1.5)
    m.fs.crusher.properties_out[0].particle_size_median.fix(58)
    m.fs.crusher.properties_out[0].particle_size_width.fix(1.5)
    return m


def run_case() -> dict[str, Any]:
    try:
        model = build_model()
        unit = model.fs.crusher
        initializer = BlockTriangularizationInitializer(constraint_tolerance=2e-5)
        initializer.initialize(unit)
        init_ok = initializer.summary[unit]["status"] == InitializationStatus.Ok
        results = get_solver().solve(model, tee=False)
        optimal = check_optimal_termination(results)
        final_dof = degrees_of_freedom(model)

        outputs = {
            "feed_flow_mass": scalar(unit.properties_in[0].flow_mass),
            "product_flow_mass": scalar(unit.properties_out[0].flow_mass),
            "feed_p80": scalar(unit.feed_p80[0]),
            "prod_p80": scalar(unit.prod_p80[0]),
            "work": scalar(unit.work[0]),
        }
        checks = [
            {"name": "crusher_initializer_ok", "pass": bool(init_ok), "actual": str(initializer.summary[unit]["status"])},
            {"name": "crusher_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "crusher_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "crusher_feed_p80_matches_official_test", "pass": approx(outputs["feed_p80"], 114.31301), "actual": outputs["feed_p80"]},
            {"name": "crusher_prod_p80_matches_official_test", "pass": approx(outputs["prod_p80"], 82.87693), "actual": outputs["prod_p80"]},
            {"name": "crusher_work_matches_official_test", "pass": approx(outputs["work"], 3915.710575), "actual": outputs["work"]},
            {"name": "crusher_mass_flow_conserved", "pass": approx(outputs["product_flow_mass"], 2000), "actual": outputs["product_flow_mass"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_crusher_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "solid_handling" / "crusher.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "solid_handling" / "tests" / "test_crusher.py"),
                "official_module": "prommis.solid_handling.crusher",
            },
            "error": None if passed else {"message": "PrOMMiS crusher checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_crusher_unit",
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
