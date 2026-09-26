#!/usr/bin/env python3
"""Run the WaterTAP multi-stage OARO reference design optimization solve."""

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

RUNNER_DIR = Path(__file__).resolve().parent
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))
from watertap_streams import merge_named_streams, streams_from_arcs  # noqa: E402

SOURCE_URL = "local://watertap/flowsheets/oaro/oaro_multi"
NUMBER_OF_STAGES = 3
SYSTEM_RECOVERY = 0.5


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _maximum_constraint_residual(model: Any) -> float:
    """Return the largest active constraint violation at the loaded solution."""

    from pyomo.environ import Constraint, value  # noqa: PLC0415

    maximum = 0.0
    for constraint in model.component_data_objects(Constraint, active=True, descend_into=True):
        body = float(value(constraint.body))
        if constraint.equality:
            residual = abs(body - float(value(constraint.lower)))
        else:
            residual = 0.0
            if constraint.has_lb():
                residual = max(residual, float(value(constraint.lower)) - body)
            if constraint.has_ub():
                residual = max(residual, body - float(value(constraint.upper)))
        maximum = max(maximum, residual)
    return maximum


def _metrics(model: Any) -> dict[str, Any]:
    fs = model.fs
    total_oaro_area = sum((_value(unit.area) or 0.0) for unit in fs.OAROUnits.values())
    return {
        "feed_flow_m3_s": _value(fs.feed.properties[0].flow_vol_phase["Liq"]),
        "product_flow_m3_s": _value(fs.product.properties[0].flow_vol_phase["Liq"]),
        "disposal_flow_m3_s": _value(fs.disposal.properties[0].flow_vol_phase["Liq"]),
        "water_recovery": _value(fs.water_recovery),
        "mass_water_recovery": _value(fs.mass_water_recovery),
        "system_salt_rejection": _value(fs.system_salt_rejection),
        "levelized_cost_of_water": _value(fs.costing.LCOW),
        "specific_energy_consumption": _value(fs.costing.specific_energy_consumption),
        "total_oaro_membrane_area_m2": total_oaro_area,
        "ro_membrane_area_m2": _value(fs.RO.area),
        "total_membrane_area_m2": total_oaro_area + (_value(fs.RO.area) or 0.0),
        "product_nacl_mass_fraction": _value(fs.product.properties[0].mass_frac_phase_comp["Liq", "NaCl"]),
        "disposal_nacl_mass_fraction": _value(fs.disposal.properties[0].mass_frac_phase_comp["Liq", "NaCl"]),
    }


def _freeze_terminal_design(model: Any, degrees_of_freedom: Any) -> dict[str, float]:
    """Fix a deterministic independent subset of the optimized design at its solution."""

    fs = model.fs
    candidates = []
    candidates.extend(
        pump.control_volume.properties_out[0].pressure
        for pump in fs.PrimaryPumps.values()
    )
    candidates.extend(
        pump.control_volume.properties_out[0].pressure
        for pump in fs.RecyclePumps.values()
    )
    for stage in fs.OAROUnits.values():
        candidates.extend(
            (
                stage.recovery_mass_phase_comp[0, "Liq", "H2O"],
                stage.area,
                stage.width,
                stage.feed_side.velocity[0, 0],
                stage.permeate_outlet.pressure[0],
            )
        )
    candidates.extend(
        (
            fs.RO.recovery_mass_phase_comp[0, "Liq", "H2O"],
            fs.RO.width,
        )
    )
    candidates.extend(
        separator.split_fraction[0, "treat"] for separator in fs.Separators.values()
    )
    candidates.extend(
        fs.ProductSeparator.split_fraction[0, f"makeup{stage}"]
        for stage in range(2, NUMBER_OF_STAGES + 1)
    )

    current_dof = int(degrees_of_freedom(model))
    frozen: dict[str, float] = {}
    for variable in candidates:
        if current_dof <= 0:
            break
        if variable.fixed:
            continue
        numeric_value = _value(variable)
        if numeric_value is None:
            continue
        variable.fix(numeric_value)
        next_dof = int(degrees_of_freedom(model))
        if next_dof < current_dof:
            frozen[str(variable.name)] = numeric_value
            current_dof = next_dof
        else:
            variable.unfix()
    if current_dof != 0:
        raise RuntimeError(
            f"could not freeze optimized OARO design to zero DoF; remaining DoF={current_dof}"
        )
    return frozen


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.oaro import oaro_multi  # noqa: PLC0415

        solver = get_solver()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = oaro_multi.build(number_of_stages=NUMBER_OF_STAGES)
            oaro_multi.set_operating_conditions(model)
            oaro_multi.initialize_system(
                model,
                NUMBER_OF_STAGES,
                solvent_multiplier=0.5,
                solute_multiplier=0.7,
                solver=solver,
            )
            oaro_multi.optimize_set_up(model, number_of_stages=NUMBER_OF_STAGES, water_recovery=SYSTEM_RECOVERY)
            optimization_results = oaro_multi.solve(model, solver=solver)
            optimization_dof = degrees_of_freedom(model)
            frozen_design_variables = _freeze_terminal_design(model, degrees_of_freedom)
            model.fs.objective.deactivate()

        optimization_optimal = bool(check_optimal_termination(optimization_results))
        termination = str(optimization_results.solver.termination_condition)
        final_dof = degrees_of_freedom(model)
        maximum_constraint_residual = _maximum_constraint_residual(model)
        metrics = _metrics(model)
        stream_values = merge_named_streams(
            streams_from_arcs(model),
            {
                "feed": model.fs.feed.outlet,
                "product": model.fs.product.inlet,
                "disposal": model.fs.disposal.inlet,
            },
        )
        passed = (
            optimization_optimal
            and final_dof == 0
            and maximum_constraint_residual <= 1e-4
            and metrics["product_flow_m3_s"] is not None
            and metrics["product_flow_m3_s"] > 0
            and metrics["levelized_cost_of_water"] is not None
            and metrics["specific_energy_consumption"] is not None
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "design_optimization_solver",
            "case_family": "watertap_oaro_multi",
            "official_reference_url": SOURCE_URL,
            "optimization_termination_condition": str(
                optimization_results.solver.termination_condition
            ),
            "termination_condition": termination,
            "checks": [
                {"name": "oaro_multi_design_optimization_optimal", "pass": optimization_optimal},
                {"name": "oaro_multi_terminal_solution_loaded", "pass": optimization_optimal},
                {"name": "oaro_multi_terminal_design_dof_zero", "pass": final_dof == 0},
                {"name": "oaro_multi_terminal_constraint_residual", "pass": maximum_constraint_residual <= 1e-4},
                {"name": "oaro_multi_product_flow_positive", "pass": metrics["product_flow_m3_s"] is not None and metrics["product_flow_m3_s"] > 0},
                {"name": "oaro_multi_lcow_available", "pass": metrics["levelized_cost_of_water"] is not None},
                {"name": "oaro_multi_sec_available", "pass": metrics["specific_energy_consumption"] is not None},
                {"name": "oaro_multi_streams_available", "pass": bool(stream_values)},
            ],
            "number_of_stages": NUMBER_OF_STAGES,
            "target_system_recovery": SYSTEM_RECOVERY,
            "optimization_dof_before_terminal_freeze": optimization_dof,
            "frozen_design_variables": frozen_design_variables,
            "final_dof": final_dof,
            "maximum_constraint_residual": maximum_constraint_residual,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.oaro.oaro_multi",
                "configuration": "3-stage OARO design optimization at 50% system recovery",
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP OARO multi optimization did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "design_optimization_solver",
            "case_family": "watertap_oaro_multi",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "oaro_multi_optimization_runner_exception", "pass": False}],
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
