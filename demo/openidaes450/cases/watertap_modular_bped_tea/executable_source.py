#!/usr/bin/env python3
"""Run the official WaterTAP bipolar electrodialysis unit model solve."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/unit_models/electrodialysis_bipolar_1D.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def build_model() -> Any:
    import idaes.core.util.scaling as iscale  # noqa: PLC0415
    from idaes.core import FlowsheetBlock  # noqa: PLC0415
    from pyomo.environ import ConcreteModel  # noqa: PLC0415
    from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock  # noqa: PLC0415
    from watertap.unit_models.electrodialysis_bipolar_1D import (  # noqa: PLC0415
        Electrodialysis_Bipolar_1D,
        ElectricalOperationMode,
        LimitingCurrentDensitybpmMethod,
    )

    ion_dict = {
        "solute_list": ["Na_+", "Cl_-", "H_+", "OH_-"],
        "mw_data": {"Na_+": 23e-3, "Cl_-": 35.5e-3, "H_+": 1e-3, "OH_-": 17.0e-3},
        "elec_mobility_data": {
            ("Liq", "Na_+"): 5.19e-8,
            ("Liq", "Cl_-"): 7.92e-8,
            ("Liq", "H_+"): 36.23e-8,
            ("Liq", "OH_-"): 20.64e-8,
        },
        "charge": {"Na_+": 1, "Cl_-": -1, "H_+": 1, "OH_-": -1},
        "diffusivity_data": {
            ("Liq", "Na_+"): 1.33e-9,
            ("Liq", "Cl_-"): 2.03e-9,
            ("Liq", "H_+"): 9.31e-9,
            ("Liq", "OH_-"): 5.27e-9,
        },
    }
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = MCASParameterBlock(**ion_dict)
    model.fs.unit = Electrodialysis_Bipolar_1D(
        property_package=model.fs.properties,
        operation_mode=ElectricalOperationMode.Constant_Voltage,
        limiting_current_density_method_bpm=LimitingCurrentDensitybpmMethod.Empirical,
        salt_calculation=False,
    )
    unit = model.fs.unit
    unit.diffus_mass.fix((2.03 + 1.96) * 10**-9 / 2)
    unit.membrane_fixed_charge.fix(5e3)
    unit.salt_conc_ael_ref.fix(2000)
    unit.salt_conc_cel_ref.fix(2000)
    unit.conc_water.fix(50 * 1e3)
    unit.k2_zero.fix(2 * 10**-6)
    unit.relative_permittivity.fix(30)
    unit.membrane_fixed_catalyst_cel.fix(5e3)
    unit.membrane_fixed_catalyst_ael.fix(5e3)
    unit.k_a.fix(447)
    unit.k_b.fix(5e4)

    for ion, val in {"Na_+": 0, "Cl_-": 0, "H_+": 1, "OH_-": 1}.items():
        unit.ion_trans_number_membrane["bpm", ion].fix(val)
    for ion, val in {"Na_+": 0.94, "Cl_-": 0, "H_+": 0.03, "OH_-": 0.03}.items():
        unit.ion_trans_number_membrane["cem", ion].fix(val)
    for ion, val in {"Na_+": 0, "Cl_-": 0.94, "H_+": 0.03, "OH_-": 0.03}.items():
        unit.ion_trans_number_membrane["aem", ion].fix(val)
    for ion in ["Na_+", "Cl_-", "H_+", "OH_-"]:
        unit.solute_diffusivity_membrane["bpm", ion].fix(0)
    for membrane in ["cem", "aem"]:
        unit.solute_diffusivity_membrane[membrane, "Na_+"].fix((1.8e-10 + 1.25e-10) / 2)
        unit.solute_diffusivity_membrane[membrane, "Cl_-"].fix((1.8e-10 + 1.25e-10) / 2)
        unit.solute_diffusivity_membrane[membrane, "H_+"].fix(0)
        unit.solute_diffusivity_membrane[membrane, "OH_-"].fix(0)

    for inlet in [unit.inlet_basic, unit.inlet_acidic, unit.inlet_diluate]:
        inlet.pressure.fix(101325)
        inlet.temperature.fix(298.15)
        inlet.flow_mol_phase_comp[0, "Liq", "H2O"].fix(2.40e-1)
    unit.inlet_basic.flow_mol_phase_comp[0, "Liq", "Na_+"].fix(7.38e-2)
    unit.inlet_basic.flow_mol_phase_comp[0, "Liq", "Cl_-"].fix(0)
    unit.inlet_basic.flow_mol_phase_comp[0, "Liq", "H_+"].fix(0)
    unit.inlet_basic.flow_mol_phase_comp[0, "Liq", "OH_-"].fix(7.38e-2)
    unit.inlet_acidic.flow_mol_phase_comp[0, "Liq", "Na_+"].fix(0)
    unit.inlet_acidic.flow_mol_phase_comp[0, "Liq", "Cl_-"].fix(7.38e-2)
    unit.inlet_acidic.flow_mol_phase_comp[0, "Liq", "H_+"].fix(7.38e-2)
    unit.inlet_acidic.flow_mol_phase_comp[0, "Liq", "OH_-"].fix(0)
    unit.inlet_diluate.flow_mol_phase_comp[0, "Liq", "Na_+"].fix(7.38e-2)
    unit.inlet_diluate.flow_mol_phase_comp[0, "Liq", "Cl_-"].fix(7.38e-2)
    unit.inlet_diluate.flow_mol_phase_comp[0, "Liq", "H_+"].fix(0)
    unit.inlet_diluate.flow_mol_phase_comp[0, "Liq", "OH_-"].fix(0)

    unit.spacer_porosity.fix(1)
    unit.shadow_factor.fix(1)
    for membrane in ["cem", "aem", "bpm"]:
        unit.water_trans_number_membrane[membrane].fix((5.8 + 4.3) / 2)
        unit.water_permeability_membrane[membrane].fix((2.16e-14 + 1.75e-14) / 2)
    unit.electrodes_resistance.fix(0)
    unit.current_utilization.fix(1)
    unit.channel_height.fix(2.7e-4)
    unit.membrane_areal_resistance_coef_0.fix((1.89e-4 + 1.77e-4) / 2)
    unit.membrane_areal_resistance_coef_1.fix(0)
    unit.cell_width.fix(0.1)
    unit.cell_length.fix(0.79)
    unit.membrane_thickness["bpm"].fix(8e-4)
    unit.membrane_thickness["aem"].fix(4e-4)
    unit.membrane_thickness["cem"].fix(4e-4)
    unit.cell_triplet_num.fix(10)
    unit.voltage_applied.fix(1e1)

    for ion in ["Na_+", "Cl_-", "H_+", "OH_-"]:
        model.fs.properties.set_default_scaling("flow_mol_phase_comp", 1e3, index=("Liq", ion))
    model.fs.properties.set_default_scaling("flow_mol_phase_comp", 1e2, index=("Liq", "H2O"))
    iscale.set_scaling_factor(unit.k_a, 1e-2)
    iscale.set_scaling_factor(unit.k_b, 1e-4)
    iscale.set_scaling_factor(unit.voltage_x, 1e-1)
    iscale.set_scaling_factor(unit.flux_splitting, 1e4)
    iscale.set_scaling_factor(unit.current_density_x, 1e-3)
    iscale.calculate_scaling_factors(model)
    return model


def _port_values(port: Any) -> dict[str, Any]:
    row = {"temperature_K": _value(port.temperature[0]), "pressure_Pa": _value(port.pressure[0])}
    for comp in ["H2O", "Na_+", "Cl_-", "H_+", "OH_-"]:
        row[f"flow_mol_Liq_{comp}_mol_s"] = _value(port.flow_mol_phase_comp[0, "Liq", comp])
    return row


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = build_model()
            initial_dof = degrees_of_freedom(model)
            model.fs.unit.initialize()
            results = get_solver().solve(model)
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        unit = model.fs.unit
        diluate_na = _value(unit.outlet_diluate.flow_mol_phase_comp[0, "Liq", "Na_+"])
        acidic_h = _value(unit.outlet_acidic.flow_mol_phase_comp[0, "Liq", "H_+"])
        basic_oh = _value(unit.outlet_basic.flow_mol_phase_comp[0, "Liq", "OH_-"])
        current_var = getattr(unit, "current", None)
        power_var = getattr(unit, "power_electrical", None)
        current = _value(current_var[0]) if current_var is not None else None
        power = _value(power_var[0]) if power_var is not None else None
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and diluate_na is not None
            and abs(diluate_na - 0.06896) < 2e-4
            and acidic_h is not None
            and acidic_h > 0.07
            and basic_oh is not None
            and basic_oh > 0.07
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_bped_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "bped_optimal", "pass": optimal},
                {"name": "bped_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "bped_final_dof_zero", "pass": final_dof == 0},
                {"name": "bped_diluate_na_target_met", "pass": diluate_na is not None and abs(diluate_na - 0.06896) < 2e-4},
                {"name": "bped_acidic_h_positive", "pass": acidic_h is not None and acidic_h > 0.07},
                {"name": "bped_basic_oh_positive", "pass": basic_oh is not None and basic_oh > 0.07},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "diluate_na_mol_s": diluate_na,
            "acidic_h_mol_s": acidic_h,
            "basic_oh_mol_s": basic_oh,
            "current_A": current,
            "electrical_power_W": power,
            "stream_values": {
                "inlet_diluate": _port_values(unit.inlet_diluate),
                "outlet_diluate": _port_values(unit.outlet_diluate),
                "inlet_acidic": _port_values(unit.inlet_acidic),
                "outlet_acidic": _port_values(unit.outlet_acidic),
                "inlet_basic": _port_values(unit.inlet_basic),
                "outlet_basic": _port_values(unit.outlet_basic),
            },
            "source_summary": {
                "source": "watertap.unit_models.electrodialysis_bipolar_1D.Electrodialysis_Bipolar_1D",
                "property_package": "watertap.property_models.multicomp_aq_sol_prop_pack.MCASParameterBlock",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP BPED unit did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_bped_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "bped_runner_exception", "pass": False}],
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
