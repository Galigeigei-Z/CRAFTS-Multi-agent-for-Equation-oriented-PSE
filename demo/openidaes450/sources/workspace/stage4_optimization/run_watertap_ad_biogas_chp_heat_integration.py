#!/usr/bin/env python3
"""Solve a heat-led biogas CHP extension of the WaterTAP AD unit model."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

RUNNER_DIR = ROOT / "stage3_specs_solve"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

from run_watertap_anaerobic_digester_unit_reference_solve import build_model  # noqa: E402


SOURCE_URL = "https://watertap.readthedocs.io/en/stable/technical_reference/unit_models/anaerobic_digester.html"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import (  # noqa: PLC0415
            Block,
            Constraint,
            Expression,
            NonNegativeReals,
            Param,
            Var,
            check_optimal_termination,
        )
        from watertap.core.solvers import get_solver  # noqa: PLC0415

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = build_model()
            unit = model.fs.unit

            # The parent fixes both inlet and digester at 35 C.  This extension
            # makes the incoming sludge ambient and closes the 10 K sensible-
            # heat load with useful CHP heat.  ADM1 chemistry and the native AD
            # vapor/liquid balances remain unchanged.
            unit.inlet.temperature[0].fix(298.15)
            unit.initialize()
            parent_results = get_solver().solve(model)

            model.fs.chp = Block()
            chp = model.fs.chp
            chp.methane_lhv_kj_kg = Param(initialize=50_000.0, mutable=False)
            chp.electrical_efficiency = Param(initialize=0.35, mutable=False)
            chp.useful_heat_efficiency = Param(initialize=0.45, mutable=False)
            chp.sludge_density_kg_m3 = Param(initialize=1_000.0, mutable=False)
            chp.sludge_cp_kj_kg_k = Param(initialize=4.18, mutable=False)
            chp.chp_fraction = Var(
                initialize=0.1,
                bounds=(0.0, 1.0),
                domain=NonNegativeReals,
            )
            chp.methane_mass_flow_kg_s = Expression(
                expr=unit.vapor_outlet.conc_mass_comp[0, "S_ch4"]
                * unit.vapor_outlet.flow_vol[0]
            )
            chp.biogas_fuel_power_kw = Expression(
                expr=chp.methane_mass_flow_kg_s * chp.methane_lhv_kj_kg
            )
            chp.gross_electricity_kw = Expression(
                expr=chp.chp_fraction
                * chp.biogas_fuel_power_kw
                * chp.electrical_efficiency
            )
            chp.recovered_heat_kw = Expression(
                expr=chp.chp_fraction
                * chp.biogas_fuel_power_kw
                * chp.useful_heat_efficiency
            )
            chp.feed_heating_duty_kw = Expression(
                expr=unit.inlet.flow_vol[0]
                * chp.sludge_density_kg_m3
                * chp.sludge_cp_kj_kg_k
                * (unit.liquid_outlet.temperature[0] - unit.inlet.temperature[0])
            )
            chp.heat_led_operation = Constraint(
                expr=chp.recovered_heat_kw == chp.feed_heating_duty_kw
            )
            chp.exported_methane_kg_s = Expression(
                expr=(1.0 - chp.chp_fraction) * chp.methane_mass_flow_kg_s
            )
            chp.net_electricity_kw = Expression(
                expr=chp.gross_electricity_kw - unit.electricity_consumption[0]
            )

            initial_dof = degrees_of_freedom(model)
            results = get_solver().solve(model)

        parent_optimal = bool(check_optimal_termination(parent_results))
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        chp_fraction = _value(chp.chp_fraction)
        methane_mass_flow = _value(chp.methane_mass_flow_kg_s)
        recovered_heat = _value(chp.recovered_heat_kw)
        heating_duty = _value(chp.feed_heating_duty_kw)
        gross_electricity = _value(chp.gross_electricity_kw)
        net_electricity = _value(chp.net_electricity_kw)
        heat_gap = None
        if recovered_heat is not None and heating_duty is not None:
            heat_gap = abs(recovered_heat - heating_duty)
        passed = (
            parent_optimal
            and optimal
            and initial_dof == 0
            and final_dof == 0
            and chp_fraction is not None
            and 0.0 < chp_fraction < 1.0
            and methane_mass_flow is not None
            and methane_mass_flow > 0.0
            and heat_gap is not None
            and heat_gap <= 1e-5
            and net_electricity is not None
            and net_electricity > 0.0
        )
        return {
            "pass": passed,
            "stage": "native_energy_integration_solve",
            "case_family": "watertap_ad_biogas_chp_heat_integrated",
            "official_reference_url": SOURCE_URL,
            "parent_termination_condition": str(parent_results.solver.termination_condition),
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "parent_ad_optimal", "pass": parent_optimal},
                {"name": "chp_extension_optimal", "pass": optimal},
                {"name": "initial_dof_zero", "pass": initial_dof == 0},
                {"name": "final_dof_zero", "pass": final_dof == 0},
                {"name": "heat_balance_closed", "pass": heat_gap is not None and heat_gap <= 1e-5},
                {"name": "net_electricity_positive", "pass": net_electricity is not None and net_electricity > 0.0},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "decision_variables": {"chp_biogas_fraction": chp_fraction},
            "metrics": {
                "methane_mass_flow_kg_s": methane_mass_flow,
                "biogas_fuel_power_kw": _value(chp.biogas_fuel_power_kw),
                "feed_heating_duty_kw": heating_duty,
                "recovered_chp_heat_kw": recovered_heat,
                "auxiliary_heat_kw": 0.0,
                "gross_chp_electricity_kw": gross_electricity,
                "ad_electricity_consumption_kw": _value(unit.electricity_consumption[0]),
                "net_electricity_kw": net_electricity,
                "exported_methane_kg_s": _value(chp.exported_methane_kg_s),
                "vapor_flow_m3_s": _value(unit.vapor_outlet.flow_vol[0]),
                "liquid_product_flow_m3_s": _value(unit.liquid_outlet.flow_vol[0]),
                "hydraulic_retention_time_s": _value(unit.hydraulic_retention_time[0]),
            },
            "stream_values": {
                "ambient_sludge_feed": {
                    "flow_vol_m3_s": _value(unit.inlet.flow_vol[0]),
                    "temperature_K": _value(unit.inlet.temperature[0]),
                },
                "heated_digester_liquid": {
                    "flow_vol_m3_s": _value(unit.liquid_outlet.flow_vol[0]),
                    "temperature_K": _value(unit.liquid_outlet.temperature[0]),
                },
                "raw_biogas": {
                    "flow_vol_m3_s": _value(unit.vapor_outlet.flow_vol[0]),
                    "methane_conc_kg_m3": _value(unit.vapor_outlet.conc_mass_comp[0, "S_ch4"]),
                },
                "chp_biogas": {"methane_mass_flow_kg_s": None if methane_mass_flow is None or chp_fraction is None else methane_mass_flow * chp_fraction},
                "export_biogas": {"methane_mass_flow_kg_s": _value(chp.exported_methane_kg_s)},
                "recovered_heat": {"duty_kw": recovered_heat},
                "net_electricity": {"power_kw": net_electricity},
            },
            "source_summary": {
                "source": "watertap.unit_models.anaerobic_digester.AD plus explicit Pyomo CHP material/energy balances",
                "basis": "Methane LHV 50 MJ/kg; 35% electrical and 45% useful-heat efficiencies; heat-led operation without heat rejection.",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "AD CHP heat-integration checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "native_energy_integration_solve",
            "case_family": "watertap_ad_biogas_chp_heat_integrated",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "ad_chp_runner_exception", "pass": False}],
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = run_case()
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
