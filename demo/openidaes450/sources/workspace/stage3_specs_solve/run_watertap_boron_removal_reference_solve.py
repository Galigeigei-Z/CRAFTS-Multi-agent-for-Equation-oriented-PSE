#!/usr/bin/env python3
"""Run the official WaterTAP boron removal unit model solve."""

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

SOURCE_URL = "local://watertap/unit_models/boron_removal"


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
    from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock  # noqa: PLC0415
    from watertap.unit_models.boron_removal import BoronRemoval  # noqa: PLC0415

    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    ion_dict = {
        "solute_list": ["B[OH]3", "B[OH]4_-", "Na_+"],
        "mw_data": {
            "H2O": 18e-3,
            "B[OH]3": 61.83e-3,
            "B[OH]4_-": 78.83e-3,
            "Na_+": 23e-3,
        },
        "charge": {"B[OH]4_-": -1, "Na_+": 1, "B[OH]3": 0},
    }
    model.fs.properties = MCASParameterBlock(**ion_dict)
    chemical_mapping = {
        "boron_name": "B[OH]3",
        "borate_name": "B[OH]4_-",
        "caustic_additive": {
            "cation_name": "Na_+",
            "mw_additive": (40, pyunits.g / pyunits.mol),
            "moles_cation_per_additive": 1,
        },
    }
    model.fs.unit = BoronRemoval(property_package=model.fs.properties, chemical_mapping_data=chemical_mapping)
    state = {
        "H2O": 100,
        "H_+": 1e-7,
        "OH_-": 1e-7,
        "B[OH]3": 2e-4,
        "B[OH]4_-": 1e-6,
        "Na_+": 1e-5,
    }
    model.fs.unit.inlet.pressure.fix(101325)
    model.fs.unit.inlet.temperature.fix(298.15)
    for species, flow in state.items():
        idx = (0, "Liq", species)
        if idx in model.fs.unit.inlet.flow_mol_phase_comp:
            model.fs.unit.inlet.flow_mol_phase_comp[idx].fix(flow)
            model.fs.properties.set_default_scaling("flow_mol_phase_comp", 1 / flow, index=("Liq", species))
    model.fs.unit.caustic_dose_rate.fix(0.9e-5)
    model.fs.unit.reactor_volume.fix(1)
    model.fs.unit.outlet.flow_mol_phase_comp[(0, "Liq", "B[OH]3")].fix(1.98677e-5)
    model.fs.unit.caustic_dose_rate.unfix()
    iscale.calculate_scaling_factors(model.fs)
    return model


def _streams(model: Any) -> dict[str, Any]:
    unit = model.fs.unit
    streams: dict[str, Any] = {}
    for label, port in {"inlet": unit.inlet, "outlet": unit.outlet}.items():
        row: dict[str, Any] = {
            "temperature_K": _value(port.temperature[0]),
            "pressure_Pa": _value(port.pressure[0]),
        }
        for species in ["H2O", "B[OH]3", "B[OH]4_-", "Na_+"]:
            idx = (0, "Liq", species)
            if idx in port.flow_mol_phase_comp:
                row[f"flow_mol_Liq_{species}"] = _value(port.flow_mol_phase_comp[idx])
        streams[label] = row
    return streams


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            model = build_model()
            initial_dof = degrees_of_freedom(model)
            results = solver.solve(model)
        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        outlet_boron = _value(model.fs.unit.outlet.flow_mol_phase_comp[0, "Liq", "B[OH]3"])
        outlet_borate = _value(model.fs.unit.outlet.flow_mol_phase_comp[0, "Liq", "B[OH]4_-"])
        outlet_ph = _value(model.fs.unit.outlet_pH())
        outlet_poh = _value(model.fs.unit.outlet_pOH())
        caustic_dose_rate = _value(model.fs.unit.caustic_dose_rate[0])
        stream_values = _streams(model)
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and outlet_boron is not None
            and abs(outlet_boron - 1.98677e-5) < 1e-8
            and outlet_ph is not None
            and 10.0 < outlet_ph < 10.4
            and caustic_dose_rate is not None
            and caustic_dose_rate > 0
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_boron_removal",
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "boron_removal_optimal", "pass": optimal},
                {"name": "boron_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "boron_final_dof_zero", "pass": final_dof == 0},
                {"name": "outlet_boron_target_met", "pass": outlet_boron is not None and abs(outlet_boron - 1.98677e-5) < 1e-8},
                {"name": "outlet_ph_expected_range", "pass": outlet_ph is not None and 10.0 < outlet_ph < 10.4},
                {"name": "caustic_dose_positive", "pass": caustic_dose_rate is not None and caustic_dose_rate > 0},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            "outlet_boron_mol_s": outlet_boron,
            "outlet_borate_mol_s": outlet_borate,
            "outlet_pH": outlet_ph,
            "outlet_pOH": outlet_poh,
            "caustic_dose_rate_mol_s": caustic_dose_rate,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.unit_models.boron_removal.BoronRemoval",
                "property_package": "watertap.property_models.multicomp_aq_sol_prop_pack.MCASParameterBlock",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "WaterTAP BoronRemoval did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_boron_removal",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "boron_removal_runner_exception", "pass": False}],
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
