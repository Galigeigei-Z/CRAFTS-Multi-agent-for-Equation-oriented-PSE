#!/usr/bin/env python3
"""Run official PrOMMiS REE oxalate roaster validation."""

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
from pyomo.environ import ComponentMap, ConcreteModel, SolverFactory, check_optimal_termination, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.roasting.ree_oxalate_roaster.html"
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


def approx(actual: float | None, expected: float, *, rel: float = 1e-5, abs_tol: float = 1e-9) -> bool:
    if actual is None:
        return False
    return abs(actual - expected) <= max(abs_tol, rel * abs(expected))


def build_model() -> Any:
    _prepare_imports()
    from prommis.properties import HClStrippingParameterBlock, REEOxalateParameterBlock  # noqa: PLC0415
    from prommis.roasting.ree_oxalate_roaster import REEOxalateRoaster  # noqa: PLC0415

    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    gas_species = {"O2", "H2O", "CO2", "N2"}
    m.fs.prop_gas = GenericParameterBlock(**get_prop(gas_species, ["Vap"], EosType.IDEAL), doc="gas property")
    m.fs.prop_solid = REEOxalateParameterBlock()
    m.fs.prop_liquid = HClStrippingParameterBlock()
    m.fs.roaster = REEOxalateRoaster(
        property_package_gas=m.fs.prop_gas,
        property_package_precipitate_solid=m.fs.prop_solid,
        property_package_precipitate_liquid=m.fs.prop_liquid,
        has_holdup=False,
        has_heat_transfer=True,
        has_pressure_change=True,
        metal_list=["Al", "Fe", "Ca", "Sc", "Y", "La", "Ce", "Pr", "Nd", "Sm", "Gd", "Dy"],
    )
    unit = m.fs.roaster
    unit.deltaP.fix(0)
    unit.gas_inlet.temperature.fix(1330)
    unit.gas_inlet.pressure.fix(101325)
    fgas = 0.00781
    for comp, frac in {"O2": 0.1118, "H2O": 0.1005, "CO2": 0.0431, "N2": 0.7446}.items():
        unit.gas_inlet.mole_frac_comp[0, comp].fix(frac)
    unit.gas_inlet.flow_mol.fix(fgas)
    unit.gas_outlet.temperature.fix(873.15)
    unit.solid_in[0].temperature.fix(299.15)
    unit.solid_in[0].flow_mol_comp.fix(6.1e-5)
    unit.liquid_in[0].flow_vol.fix(6.75e-4 * 0.018 * 3600)
    unit.liquid_in[0].conc_mass_comp.fix(1e-5)
    unit.liquid_in[0].conc_mass_comp["H2O"].fix(1e6)
    unit.frac_comp_recovery.fix(0.95)

    generic_prop_scaler = unit.gas_in.default_scaler()
    generic_prop_scaler.default_scaling_factors["flow_mol_phase"] = 1 / fgas
    hcl_prop_scaler = unit.liquid_in.default_scaler()
    hcl_prop_scaler.default_scaling_factors["flow_vol"] = 1 / (6.75e-4 * 0.018 * 3600)
    submodel_scalers = ComponentMap()
    submodel_scalers[unit.gas_in] = generic_prop_scaler
    submodel_scalers[unit.gas_out] = generic_prop_scaler
    submodel_scalers[unit.liquid_in] = hcl_prop_scaler
    unit.default_scaler().scale_model(unit, submodel_scalers=submodel_scalers)
    return m


def run_case() -> dict[str, Any]:
    try:
        model = build_model()
        unit = model.fs.roaster
        initializer = BlockTriangularizationInitializer()
        initializer.initialize(unit)
        init_ok = initializer.summary[unit]["status"] == InitializationStatus.Ok
        results = SolverFactory("ipopt").solve(model, tee=False)
        optimal = check_optimal_termination(results)
        final_dof = degrees_of_freedom(model)
        outputs = {
            "gas_out_flow_mol": scalar(unit.gas_out[0].flow_mol),
            "gas_out_h2o": scalar(unit.gas_out[0].mole_frac_comp["H2O"]),
            "gas_out_o2": scalar(unit.gas_out[0].mole_frac_comp["O2"]),
            "gas_out_co2": scalar(unit.gas_out[0].mole_frac_comp["CO2"]),
            "heat_duty": scalar(unit.heat_duty[0]),
            "flow_mass_product": scalar(unit.flow_mass_product[0]),
            "product_mass_frac_nd": scalar(unit.mass_frac_comp_product[0, "Nd"]),
            "product_mass_frac_dy": scalar(unit.mass_frac_comp_product[0, "Dy"]),
        }
        checks = [
            {"name": "ree_oxalate_roaster_initializer_ok", "pass": bool(init_ok), "actual": str(initializer.summary[unit]["status"])},
            {"name": "ree_oxalate_roaster_termination_optimal", "pass": bool(optimal), "actual": str(results.solver.termination_condition)},
            {"name": "ree_oxalate_roaster_dof_zero", "pass": final_dof == 0, "actual": final_dof},
            {"name": "ree_oxalate_roaster_gas_flow_matches_official_test", "pass": approx(outputs["gas_out_flow_mol"], 0.008487, abs_tol=1e-6), "actual": outputs["gas_out_flow_mol"]},
            {"name": "ree_oxalate_roaster_h2o_matches_official_test", "pass": approx(outputs["gas_out_h2o"], 0.172195, abs_tol=1e-6), "actual": outputs["gas_out_h2o"]},
            {"name": "ree_oxalate_roaster_o2_matches_official_test", "pass": approx(outputs["gas_out_o2"], 0.102842, abs_tol=1e-6), "actual": outputs["gas_out_o2"]},
            {"name": "ree_oxalate_roaster_heat_duty_matches_official_test", "pass": approx(outputs["heat_duty"], -82.248, abs_tol=1e-6), "actual": outputs["heat_duty"]},
            {"name": "ree_oxalate_roaster_product_flow_matches_official_test", "pass": approx(outputs["flow_mass_product"], 4.9676e-08, abs_tol=1e-9), "actual": outputs["flow_mass_product"]},
            {"name": "ree_oxalate_roaster_nd_product_fraction_matches_official_test", "pass": approx(outputs["product_mass_frac_nd"], 0.10903330587601676, abs_tol=1e-6), "actual": outputs["product_mass_frac_nd"]},
        ]
        passed = all(bool(check["pass"]) for check in checks)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_ree_oxalate_roaster",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": final_dof,
            "checks": checks,
            "outputs": outputs,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "roasting" / "ree_oxalate_roaster.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "roasting" / "tests" / "test_ree_oxalate_roaster.py"),
                "official_module": "prommis.roasting.ree_oxalate_roaster",
            },
            "error": None if passed else {"message": "PrOMMiS REE oxalate roaster checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_ree_oxalate_roaster",
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
