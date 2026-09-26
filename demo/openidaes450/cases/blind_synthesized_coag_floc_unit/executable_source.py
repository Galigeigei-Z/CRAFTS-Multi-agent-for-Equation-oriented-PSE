#!/usr/bin/env python3
"""Run the official WaterTAP coagulation/flocculation unit model solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/unit_models/coag_floc_model.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def build_model() -> Any:
    import idaes.core.util.scaling as iscale  # noqa: PLC0415
    from idaes.core import FlowsheetBlock  # noqa: PLC0415
    from pyomo.environ import ConcreteModel, units as pyunits  # noqa: PLC0415
    from watertap.property_models.unit_specific.coagulation_prop_pack import CoagulationParameterBlock  # noqa: PLC0415
    from watertap.unit_models.coag_floc_model import CoagulationFlocculation  # noqa: PLC0415

    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = CoagulationParameterBlock()
    chemical_additives = {
        "Alum": {
            "parameter_data": {
                "mw_additive": (200, pyunits.g / pyunits.mol),
                "moles_salt_per_mole_additive": 3,
                "mw_salt": (100, pyunits.g / pyunits.mol),
            }
        },
        "Poly": {
            "parameter_data": {
                "mw_additive": (25, pyunits.g / pyunits.mol),
                "moles_salt_per_mole_additive": 0,
                "mw_salt": (23, pyunits.g / pyunits.mol),
            }
        },
    }
    model.fs.unit = CoagulationFlocculation(
        property_package=model.fs.properties,
        chemical_additives=chemical_additives,
    )

    unit = model.fs.unit
    unit.fix_tss_turbidity_relation_defaults()
    unit.initial_turbidity_ntu.fix()
    unit.final_turbidity_ntu.fix(5)
    unit.chemical_doses[0, "Alum"].fix(10)
    unit.chemical_doses[0, "Poly"].fix(5)

    unit.inlet.pressure.fix(101325)
    unit.inlet.temperature.fix(298.15)
    unit.inlet.flow_mass_phase_comp[0, "Liq", "H2O"].fix(1)
    unit.inlet.flow_mass_phase_comp[0, "Liq", "TDS"].fix(0.01)
    unit.inlet.flow_mass_phase_comp[0, "Liq", "TSS"].fix(0.01)
    unit.inlet.flow_mass_phase_comp[0, "Liq", "Sludge"].fix(0.0)

    unit.rapid_mixing_retention_time[0].fix(60)
    unit.num_rapid_mixing_basins.fix(4)
    unit.rapid_mixing_vel_grad[0].fix(750)
    unit.floc_retention_time[0].fix(1800)
    unit.single_paddle_length.fix(4)
    unit.single_paddle_width.fix(0.5)
    unit.paddle_rotational_speed[0].fix(0.03)
    unit.paddle_drag_coef[0].fix(1.5)
    unit.vel_fraction.fix(0.7)
    unit.num_paddle_wheels.fix(4)
    unit.num_paddles_per_wheel.fix(4)

    iscale.set_scaling_factor(
        unit.control_volume.properties_in[0.0].mass_frac_phase_comp["Liq", "Sludge"],
        1e12,
    )
    iscale.calculate_scaling_factors(unit)
    return model


def _stream(port: Any) -> dict[str, Any]:
    row = {"temperature_K": _value(port.temperature[0]), "pressure_Pa": _value(port.pressure[0])}
    for comp in ["H2O", "TDS", "TSS", "Sludge"]:
        row[f"flow_mass_Liq_{comp}_kg_s"] = _value(port.flow_mass_phase_comp[0, "Liq", comp])
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
            results = get_solver().solve(model)
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        unit = model.fs.unit
        outlet_tss = _value(unit.outlet.flow_mass_phase_comp[0, "Liq", "TSS"])
        outlet_sludge = _value(unit.outlet.flow_mass_phase_comp[0, "Liq", "Sludge"])
        outlet_tds = _value(unit.outlet.flow_mass_phase_comp[0, "Liq", "TDS"])
        mixing_power = _value(unit.rapid_mixing_power[0])
        floc_power = _value(unit.flocculation_power[0])
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and outlet_tss is not None
            and abs(outlet_tss - 9.36352627e-6) < 1e-8
            and outlet_sludge is not None
            and outlet_sludge > 0
            and mixing_power is not None
            and mixing_power > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_coagulation_flocculation_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "coag_floc_optimal", "pass": optimal},
                {"name": "coag_floc_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "coag_floc_final_dof_zero", "pass": final_dof == 0},
                {"name": "coag_floc_tss_target_met", "pass": outlet_tss is not None and abs(outlet_tss - 9.36352627e-6) < 1e-8},
                {"name": "coag_floc_sludge_positive", "pass": outlet_sludge is not None and outlet_sludge > 0},
                {"name": "coag_floc_mixing_power_positive", "pass": mixing_power is not None and mixing_power > 0},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "outlet_tss_kg_s": outlet_tss,
            "outlet_sludge_kg_s": outlet_sludge,
            "outlet_tds_kg_s": outlet_tds,
            "rapid_mixing_power_W": mixing_power,
            "flocculation_power_W": floc_power,
            "stream_values": {"inlet": _stream(unit.inlet), "outlet": _stream(unit.outlet)},
            "source_summary": {
                "source": "watertap.unit_models.coag_floc_model.CoagulationFlocculation",
                "property_package": "watertap.property_models.unit_specific.coagulation_prop_pack.CoagulationParameterBlock",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP coagulation/flocculation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_coagulation_flocculation_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "coag_floc_runner_exception", "pass": False}],
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
