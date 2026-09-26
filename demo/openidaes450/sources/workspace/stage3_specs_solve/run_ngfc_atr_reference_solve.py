#!/usr/bin/env python3
"""Run the official NGFC autothermal reformer subsystem as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import traceback
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/langgraph_idaes_pipeline"
)
LEGACY_SOURCE_RELATIVE = Path(
    "examples/archived_canonical_sources/cases/sources/official_examples_power_gen"
)
SOURCE_ROOT = LEGACY_ARTIFACT_ROOT / LEGACY_SOURCE_RELATIVE
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/ngfc/NGFC_flowsheet_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

import pyomo.environ as pyo  # noqa: E402
import idaes.core.util.scaling as iscale  # noqa: E402
from idaes.core import FlowsheetBlock  # noqa: E402
from pyomo.environ import value  # noqa: E402


def register_local_sofc_rom() -> None:
    for name in ("idaes_examples", "idaes_examples.mod", "idaes_examples.mod.power_gen"):
        sys.modules.setdefault(name, types.ModuleType(name))
    spec = importlib.util.spec_from_file_location(
        "idaes_examples.mod.power_gen.SOFC_ROM", SOURCE_ROOT / "SOFC_ROM.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)


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


def stream_values(model: Any) -> dict[str, Any]:
    fs = model.fs
    comps = ("H2", "CO", "H2O", "CO2", "CH4", "C2H6", "C3H8", "C4H10", "N2", "O2", "Ar")

    def port_values(port: Any) -> dict[str, Any]:
        return {
            "flow_mol": component_value(port.flow_mol, 0),
            "temperature": component_value(port.temperature, 0),
            "pressure": component_value(port.pressure, 0),
            "mole_frac_comp": {
                comp: component_value(port.mole_frac_comp, 0, comp)
                for comp in comps
                if hasattr(port, "mole_frac_comp")
            },
        }

    return {
        "natural_gas_feed": port_values(fs.reformer_recuperator.tube_inlet),
        "air_feed": port_values(fs.air_compressor_s1.inlet),
        "steam_feed": port_values(fs.reformer_mix.steam_inlet),
        "reformer_inlet": port_values(fs.reformer.inlet),
        "reformer_outlet": port_values(fs.reformer.outlet),
        "atr_syngas_product": port_values(fs.bypass_rejoin.outlet),
    }


def scale_reformer_subsystem(model: Any) -> None:
    """Apply the official NGFC scaling entries that only touch build_reformer()."""
    fs = model.fs
    fs.NG_props.set_default_scaling("flow_mol", 1e-3)
    fs.NG_props.set_default_scaling("flow_mol_phase", 1e-3)
    fs.NG_props.set_default_scaling("temperature", 1e-2)
    fs.NG_props.set_default_scaling("pressure", 1e-5)
    fs.NG_props.set_default_scaling("mole_frac_comp", 1e2)
    fs.NG_props.set_default_scaling("mole_frac_phase_comp", 1e2)
    fs.NG_props.set_default_scaling("enth_mol_phase", 1e-6)
    fs.NG_props.set_default_scaling("entr_mol_phase", 1e-1)
    fs.NG_props.set_default_scaling("entr_mol", 1e-1)

    iscale.set_scaling_factor(fs.reformer.lagrange_mult, 1e-4)
    iscale.set_scaling_factor(fs.reformer_recuperator.area, 1e-3)
    iscale.set_scaling_factor(fs.reformer_recuperator.overall_heat_transfer_coefficient, 1e-1)
    iscale.set_scaling_factor(fs.intercooler_s1.control_volume.heat, 1e-4)
    iscale.set_scaling_factor(fs.intercooler_s2.control_volume.heat, 1e-5)
    iscale.set_scaling_factor(fs.reformer.control_volume.heat, 1e-6)
    iscale.set_scaling_factor(fs.reformer_recuperator.shell.heat, 1e-6)
    iscale.set_scaling_factor(fs.reformer_recuperator.tube.heat, 1e-6)
    iscale.set_scaling_factor(fs.air_compressor_s1.control_volume.work, 1e-5)
    iscale.set_scaling_factor(fs.air_compressor_s2.control_volume.work, 1e-5)
    iscale.set_scaling_factor(fs.NG_expander.control_volume.work, 1e-6)

    for name in (
        "reformer_recuperator",
        "NG_expander",
        "reformer_bypass",
        "air_compressor_s1",
        "intercooler_s1",
        "air_compressor_s2",
        "intercooler_s2",
        "reformer_mix",
        "reformer",
        "bypass_rejoin",
    ):
        unit = getattr(fs, name)
        if hasattr(unit, "material_mixing_equations"):
            for constraint in unit.material_mixing_equations.values():
                iscale.constraint_scaling_transform(constraint, 1e-3, overwrite=False)
        if hasattr(unit, "isentropic_energy_balance"):
            for constraint in unit.isentropic_energy_balance.values():
                iscale.constraint_scaling_transform(constraint, 1e-3, overwrite=False)
        if hasattr(unit, "heat_transfer_equation"):
            for constraint in unit.heat_transfer_equation.values():
                iscale.constraint_scaling_transform(constraint, 1e-7, overwrite=False)

    for element in ("H", "C", "O", "N", "Ar"):
        if (0.0, element) in fs.reformer.control_volume.element_balances:
            constraint = fs.reformer.control_volume.element_balances[0.0, element]
            iscale.constraint_scaling_transform(constraint, 1e-2, overwrite=False)
    iscale.calculate_scaling_factors(model)


def run_case(tee: bool = False) -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415

        register_local_sofc_rom()
        if str(SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(SOURCE_ROOT))
        import NGFC_flowsheet as ngfc  # noqa: PLC0415

        model = pyo.ConcreteModel(name="NGFC ATR subsystem")
        model.fs = FlowsheetBlock(dynamic=False)
        ngfc.build_properties(model)
        ngfc.build_reformer(model)
        ngfc.set_reformer_inputs(model)
        scale_reformer_subsystem(model)
        ngfc.initialize_reformer(model, outlvl=50)
        solver = pyo.SolverFactory("ipopt")
        solver.options["max_iter"] = 500
        solver.options["tol"] = 1e-5
        results = solver.solve(model, tee=tee)
        return {
            "pass": str(results.solver.termination_condition) == "optimal",
            "stage": "steady_state_solver",
            "case_family": "ngfc_atr",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "final_dof": degrees_of_freedom(model),
            "stream_values": stream_values(model),
            "source_binding": {
                "kind": "explicit_legacy_artifact_root",
                "artifact_root": str(LEGACY_ARTIFACT_ROOT),
                "relative_path": str(LEGACY_SOURCE_RELATIVE),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "ngfc_atr",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_binding": {
                "kind": "explicit_legacy_artifact_root",
                "artifact_root": str(LEGACY_ARTIFACT_ROOT),
                "relative_path": str(LEGACY_SOURCE_RELATIVE),
            },
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
