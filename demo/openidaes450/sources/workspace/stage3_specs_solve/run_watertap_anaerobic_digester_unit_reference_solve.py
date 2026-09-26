#!/usr/bin/env python3
"""Run the official WaterTAP anaerobic digester unit model solve."""

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

SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/unit_models/anaerobic_digester.html"


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
    from watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties import ADM1ParameterBlock  # noqa: PLC0415
    from watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties_vapor import ADM1_vaporParameterBlock  # noqa: PLC0415
    from watertap.property_models.unit_specific.anaerobic_digestion.adm1_reactions import ADM1ReactionParameterBlock  # noqa: PLC0415
    from watertap.unit_models.anaerobic_digester import AD  # noqa: PLC0415

    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.props = ADM1ParameterBlock()
    model.fs.props_vap = ADM1_vaporParameterBlock()
    model.fs.rxn_props = ADM1ReactionParameterBlock(property_package=model.fs.props)
    model.fs.unit = AD(
        liquid_property_package=model.fs.props,
        vapor_property_package=model.fs.props_vap,
        reaction_package=model.fs.rxn_props,
        has_heat_transfer=True,
        has_pressure_change=False,
    )
    unit = model.fs.unit
    unit.inlet.flow_vol.fix(170 / 24 / 3600)
    unit.inlet.temperature.fix(308.15)
    unit.inlet.pressure.fix(101325)
    for comp, conc in {
        "S_su": 0.01,
        "S_aa": 0.001,
        "S_fa": 0.001,
        "S_va": 0.001,
        "S_bu": 0.001,
        "S_pro": 0.001,
        "S_ac": 0.001,
        "S_h2": 1e-8,
        "S_ch4": 1e-5,
        "S_IC": 0.48,
        "S_IN": 0.14,
        "S_I": 0.02,
        "X_c": 2,
        "X_ch": 5,
        "X_pr": 20,
        "X_li": 5,
        "X_su": 0.0,
        "X_aa": 0.010,
        "X_fa": 0.010,
        "X_c4": 0.010,
        "X_pro": 0.010,
        "X_ac": 0.010,
        "X_h2": 0.010,
        "X_I": 25,
    }.items():
        unit.inlet.conc_mass_comp[0, comp].fix(conc)
    unit.inlet.cations[0].fix(0.04)
    unit.inlet.anions[0].fix(0.02)
    unit.volume_liquid.fix(3400)
    unit.volume_vapor.fix(300)
    unit.liquid_outlet.temperature.fix(308.15)
    iscale.calculate_scaling_factors(unit)
    iscale.set_scaling_factor(unit.liquid_phase.mass_transfer_term[0, "Liq", "S_h2"], 1e7)
    iscale.set_scaling_factor(unit.liquid_phase.heat[0], 1e3)
    return model


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
        vapor_ch4 = _value(unit.vapor_outlet.conc_mass_comp[0, "S_ch4"])
        vapor_co2 = _value(unit.vapor_outlet.conc_mass_comp[0, "S_co2"])
        vapor_flow = _value(unit.vapor_outlet.flow_vol[0])
        electricity = _value(unit.electricity_consumption[0])
        hrt = _value(unit.hydraulic_retention_time[0])
        liquid_ac = _value(unit.liquid_outlet.conc_mass_comp[0, "S_ac"])
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and vapor_ch4 is not None
            and 1.5 < vapor_ch4 < 1.8
            and vapor_flow is not None
            and vapor_flow > 0
            and electricity is not None
            and electricity > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_anaerobic_digester_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "anaerobic_digester_optimal", "pass": optimal},
                {"name": "anaerobic_digester_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "anaerobic_digester_final_dof_zero", "pass": final_dof == 0},
                {"name": "anaerobic_digester_vapor_ch4_range", "pass": vapor_ch4 is not None and 1.5 < vapor_ch4 < 1.8},
                {"name": "anaerobic_digester_biogas_flow_positive", "pass": vapor_flow is not None and vapor_flow > 0},
                {"name": "anaerobic_digester_electricity_positive", "pass": electricity is not None and electricity > 0},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "vapor_ch4_conc_kg_m3": vapor_ch4,
            "vapor_co2_conc_kg_m3": vapor_co2,
            "vapor_flow_m3_s": vapor_flow,
            "electricity_consumption_kW": electricity,
            "hydraulic_retention_time_s": hrt,
            "liquid_acetate_conc_kg_m3": liquid_ac,
            "stream_values": {
                "inlet": {"flow_vol_m3_s": _value(unit.inlet.flow_vol[0]), "temperature_K": _value(unit.inlet.temperature[0]), "pressure_Pa": _value(unit.inlet.pressure[0])},
                "liquid_outlet": {"flow_vol_m3_s": _value(unit.liquid_outlet.flow_vol[0]), "temperature_K": _value(unit.liquid_outlet.temperature[0]), "pressure_Pa": _value(unit.liquid_outlet.pressure[0])},
                "vapor_outlet": {"flow_vol_m3_s": vapor_flow, "temperature_K": _value(unit.vapor_outlet.temperature[0]), "pressure_Pa": _value(unit.vapor_outlet.pressure[0])},
            },
            "source_summary": {
                "source": "watertap.unit_models.anaerobic_digester.AD",
                "property_package": "watertap.property_models.unit_specific.anaerobic_digestion.ADM1ParameterBlock",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP anaerobic digester did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_anaerobic_digester_unit",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "anaerobic_digester_runner_exception", "pass": False}],
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
