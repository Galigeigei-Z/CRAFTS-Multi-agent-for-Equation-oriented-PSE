#!/usr/bin/env python3
"""Run official PrOMMiS hydrogen decrepitation furnace unit validation."""

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
from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock  # noqa: E402
from idaes.models_extra.power_generation.properties.natural_gas_PR import EosType, get_prop  # noqa: E402
from pyomo.environ import ConcreteModel, SolverFactory, check_optimal_termination, units as pyunits, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.hydrogen_decrepitation.hydrogen_decrepitation_furnace.html"
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
    from prommis.hydrogen_decrepitation.hydrogen_decrepitation_furnace import REPMHydrogenDecrepitationFurnace  # noqa: PLC0415
    from prommis.hydrogen_decrepitation.repm_solids_properties import REPMParameters  # noqa: PLC0415

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.prop_gas = GenericParameterBlock(**get_prop({"H2"}, ["Vap"], EosType.IDEAL), doc="gas property")
    m.fs.prop_solid = REPMParameters(doc="solid property")

    for name, factor in (
        ("enth_mol_phase", 1e-3),
        ("pressure", 1e-5),
        ("temperature", 1e-2),
        ("flow_mol", 1e1),
        ("flow_mol_phase", 1e1),
        ("_energy_density_term", 1e-4),
        ("phase_frac", 1),
    ):
        m.fs.prop_gas.set_default_scaling(name, factor)
    for comp, factor in {"H2": 1}.items():
        m.fs.prop_gas.set_default_scaling("mole_frac_comp", factor, index=comp)
        m.fs.prop_gas.set_default_scaling("mole_frac_phase_comp", factor, index=("Vap", comp))
        m.fs.prop_gas.set_default_scaling("flow_mol_phase_comp", factor * 1e1, index=("Vap", comp))

    m.fs.furnace = REPMHydrogenDecrepitationFurnace(
        gas_property_package=m.fs.prop_gas,
        solid_property_package=m.fs.prop_solid,
        has_heat_transfer=False,
        has_pressure_change=False,
    )
    unit = m.fs.furnace
    unit.solid_in[0].flow_mass.fix(0.0057367 * pyunits.kg / pyunits.s)
    unit.solid_in[0].mass_frac_comp["Nd2Fe14B"].fix(0.99)
    unit.solid_in[0].mass_frac_comp["Nd"].fix(0.01)
    unit.gas_inlet.mole_frac_comp[0, "H2"].fix(1)

    @unit.Constraint(m.fs.time)
    def flow_mol_gas_constraint(b, t):
        return b.gas_inlet.flow_mol[t] == sum(b.flow_mol_comp_impurity_feed[t, c] for c in m.fs.prop_solid.component_list)

    unit.operating_temperature.fix(443.15)
    unit.gas_inlet.pressure.fix(101325)
    unit.decrepitation_duration.set_value(10800 * pyunits.s)
    unit.sample_density.set_value(7500 * pyunits.kg / pyunits.m**3)
    unit.chamber_to_sample_ratio[0].set_value(2)
    unit.aspect_ratio.set_value(6)
    unit.temp_feed.fix(298.15)
    unit.temp_prod.fix(298.15)
    unit.gas_in[0].temperature.fix(443.15)
    return m


def run_case() -> dict[str, Any]:
    try:
        model = build_model()
        unit = model.fs.furnace
        initializer = BlockTriangularizationInitializer()
        unit.flow_mol_gas_constraint.deactivate()
        initializer.initialize(unit)
        unit.flow_mol_gas_constraint.activate()
        init_ok = initializer.summary[unit]["status"] == InitializationStatus.Ok
        results = SolverFactory("ipopt").solve(model, tee=False)
        optimal = check_optimal_termination(results)
        final_dof = degrees_of_freedom(model)

        values = {
            "solid_out_flow_mass": scalar(unit.solid_out[0].flow_mass),
            "solid_out_nd": scalar(unit.solid_out[0].mass_frac_comp["Nd"]),
            "solid_out_nd2fe14b": scalar(unit.solid_out[0].mass_frac_comp["Nd2Fe14B"]),
            "gas_out_flow_mol": scalar(unit.gas_out[0].flow_mol),
            "gas_out_h2": scalar(unit.gas_out[0].mole_frac_comp["H2"]),
            "total_heat_duty": scalar(unit.total_heat_duty[0]),
            "furnace_weight": scalar(unit.furnace_weight),
        }
        checks = [
            {"name": "hydrogen_decrepitation_furnace_initializer_ok", "pass": bool(init_ok), "actual": str(initializer.summary[unit]["status"])},
            {"name": "hydrogen_decrepitation_furnace_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "hydrogen_decrepitation_furnace_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "hydrogen_decrepitation_furnace_solid_flow_matches_official_test", "pass": approx(values["solid_out_flow_mass"], 0.0057367), "actual": values["solid_out_flow_mass"]},
            {"name": "hydrogen_decrepitation_furnace_nd_matches_official_test", "pass": approx(values["solid_out_nd"], 0.0100001), "actual": values["solid_out_nd"]},
            {"name": "hydrogen_decrepitation_furnace_h2_flow_matches_official_test", "pass": approx(values["gas_out_flow_mol"], 0.0056509), "actual": values["gas_out_flow_mol"]},
            {"name": "hydrogen_decrepitation_furnace_heat_duty_matches_official_test", "pass": approx(values["total_heat_duty"], 3761.75), "actual": values["total_heat_duty"]},
            {"name": "hydrogen_decrepitation_furnace_weight_matches_official_test", "pass": approx(values["furnace_weight"], 454.389), "actual": values["furnace_weight"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_hydrogen_decrepitation_furnace",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "outputs": values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "hydrogen_decrepitation" / "hydrogen_decrepitation_furnace.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "hydrogen_decrepitation" / "tests" / "test_hydrogen_decrepitation_furnace.py"),
                "official_module": "prommis.hydrogen_decrepitation.hydrogen_decrepitation_furnace",
            },
            "error": None if passed else {"message": "PrOMMiS hydrogen decrepitation furnace checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_hydrogen_decrepitation_furnace",
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
