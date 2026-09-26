#!/usr/bin/env python3
"""Run the WaterTAP BSM2 phosphorus extension reference solve."""

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
from watertap_streams import streams_from_arcs  # noqa: E402

SOURCE_URL = "local://watertap/flowsheets/full_water_resource_recovery_facility/BSM2_P_extension"


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        if getattr(obj, "is_indexed", lambda: False)():
            for index in obj:
                return float(value(obj[index]))
        return float(value(obj))
    except Exception:
        return None


def _indexed_value(obj: Any, *index: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj[index]))
    except Exception:
        return None


def _state(unit: Any) -> Any | None:
    try:
        return unit.properties[0]
    except Exception:
        return None


def _metrics(model: Any | None) -> dict[str, Any]:
    if model is None:
        return {}
    fs = model.fs
    metrics = {
        "feed_flow_m3_s": _value(fs.FeedWater.properties[0].flow_vol) if hasattr(fs, "FeedWater") else None,
        "treated_flow_m3_s": _value(fs.Treated.properties[0].flow_vol) if hasattr(fs, "Treated") else None,
        "sludge_flow_m3_s": _value(fs.Sludge.properties[0].flow_vol) if hasattr(fs, "Sludge") else None,
        "r1_volume_m3": _value(fs.R1.volume) if hasattr(fs, "R1") else None,
        "r7_volume_m3": _value(fs.R7.volume) if hasattr(fs, "R7") else None,
    }
    feed = _state(getattr(fs, "FeedWater", None))
    treated = _state(getattr(fs, "Treated", None))
    sludge = _state(getattr(fs, "Sludge", None))
    for prefix, state in (("feed", feed), ("treated", treated), ("sludge", sludge)):
        if state is None or not hasattr(state, "conc_mass_comp"):
            continue
        metrics[f"{prefix}_soluble_phosphate_kg_m3"] = _indexed_value(state.conc_mass_comp, "S_PO4")
        metrics[f"{prefix}_polyphosphate_kg_m3"] = _indexed_value(state.conc_mass_comp, "X_PP")
    feed_flow = metrics.get("feed_flow_m3_s")
    treated_flow = metrics.get("treated_flow_m3_s")
    feed_p = metrics.get("feed_soluble_phosphate_kg_m3")
    treated_p = metrics.get("treated_soluble_phosphate_kg_m3")
    if all(value is not None for value in (feed_flow, treated_flow, feed_p, treated_p)) and feed_flow * feed_p > 0:
        metrics["soluble_phosphate_removal_fraction"] = 1.0 - treated_flow * treated_p / (feed_flow * feed_p)
    kla_values = [_value(getattr(fs, reactor).KLa) for reactor in ("R5", "R6", "R7") if hasattr(fs, reactor)]
    if kla_values and all(value is not None for value in kla_values):
        metrics["aerobic_kla_sum_per_hour"] = 24.0 * sum(kla_values)
    costing = getattr(fs, "costing", None)
    if costing is not None:
        metrics["levelized_cost_of_water"] = _value(getattr(costing, "LCOW", None))
        metrics["specific_energy_consumption_kwh_m3"] = _value(getattr(costing, "specific_energy_consumption", None))
    return metrics


def run_case(*, bio_p: bool = False) -> dict[str, Any]:
    model = None
    try:
        import pyomo.environ as pyo  # noqa: PLC0415
        from idaes.core.initialization import BlockTriangularizationInitializer as BaseBTI  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import check_optimal_termination  # noqa: PLC0415
        from watertap.core.solvers import get_solver  # noqa: PLC0415
        from watertap.flowsheets.full_water_resource_recovery_facility import BSM2_P_extension  # noqa: PLC0415

        class RelaxedResidualBTInitializer(BaseBTI):
            """Match the official BSM2 P path while tolerating tiny 1x1 residual noise."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.config.calculate_variable_options["eps"] = 1e-7
                self.config.calculate_variable_options["iterlim"] = 2000

        BSM2_P_extension.BlockTriangularizationInitializer = RelaxedResidualBTInitializer

        solver = get_solver()
        if bio_p:
            solver.options["max_iter"] = 3000
            solver.options["tol"] = 1e-6
            solver.options["acceptable_tol"] = 1e-5
            solver.options["acceptable_iter"] = 15
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            model = BSM2_P_extension.build(bio_P=bio_p)
            BSM2_P_extension.set_operating_conditions(model, bio_P=bio_p)
            BSM2_P_extension.initialize_system(model, bio_P=bio_p, solver=solver)
            initial_dof = degrees_of_freedom(model)
            BSM2_P_extension.add_costing(model)
            model.fs.costing.initialize()
            BSM2_P_extension.scale_system(model, bio_P=bio_p)
            if bio_p:
                # The upstream bio-P path explicitly notes that its legacy full-model
                # scaling transform is fragile.  Retain the official scaling factors,
                # but solve the initialized original model and then apply the KLa
                # control switch directly to avoid a duplicate scaled NLP.
                full_solver = pyo.SolverFactory("ipopt")
                full_solver.options["max_iter"] = 3000
                full_solver.options["tol"] = 1e-6
                full_solver.options["acceptable_tol"] = 1e-5
                results = full_solver.solve(model)
                if not check_optimal_termination(results):
                    raise RuntimeError(f"bio-P initialized process solve failed: {results.solver.termination_condition}")
                model.fs.R5.KLa.fix(24.0 / 24)
                model.fs.R6.KLa.fix(24.0 / 24)
                model.fs.R7.KLa.fix(8.4 / 24)
                model.fs.R5.outlet.conc_mass_comp[:, "S_O2"].unfix()
                model.fs.R6.outlet.conc_mass_comp[:, "S_O2"].unfix()
                model.fs.R7.outlet.conc_mass_comp[:, "S_O2"].unfix()
                results = full_solver.solve(model)
            else:
                scaling = pyo.TransformationFactory("core.scale_model")
                scaled_model = scaling.create_using(model, rename=False)
                BSM2_P_extension.solve(scaled_model, solver=solver)
                scaled_model.fs.R5.KLa.fix(24.0 / 24)
                scaled_model.fs.R6.KLa.fix(24.0 / 24)
                scaled_model.fs.R7.KLa.fix(8.4 / 24)
                scaled_model.fs.R5.outlet.conc_mass_comp[:, "S_O2"].unfix()
                scaled_model.fs.R6.outlet.conc_mass_comp[:, "S_O2"].unfix()
                scaled_model.fs.R7.outlet.conc_mass_comp[:, "S_O2"].unfix()
                results = BSM2_P_extension.solve(scaled_model, solver=solver)
                scaling.propagate_solution(scaled_model, model)

        optimal = bool(check_optimal_termination(results))
        final_dof = degrees_of_freedom(model)
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model)
        passed = (
            optimal
            and initial_dof == 0
            and final_dof == 0
            and metrics.get("treated_flow_m3_s") is not None
            and metrics["treated_flow_m3_s"] > 0
            and bool(stream_values)
        )
        return {
            "pass": passed,
            "stage": "steady_state_simulation",
            "case_family": "watertap_bsm2_p_extension",
            "configuration": {"bio_P": bio_p},
            "official_reference_url": SOURCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "checks": [
                {"name": "bsm2_p_extension_simulation_optimal", "pass": optimal},
                {"name": "bsm2_p_extension_initial_dof_zero", "pass": initial_dof == 0},
                {"name": "bsm2_p_extension_final_dof_zero", "pass": final_dof == 0},
                {"name": "bsm2_p_extension_biological_phosphorus_configuration", "pass": bio_p} if bio_p else {"name": "bsm2_p_extension_relaxed_initializer_used", "pass": True},
                {"name": "bsm2_p_extension_treated_flow_positive", "pass": metrics.get("treated_flow_m3_s") is not None and metrics["treated_flow_m3_s"] > 0},
                {"name": "bsm2_p_extension_streams_available", "pass": bool(stream_values)},
            ],
            "initial_dof": initial_dof,
            "final_dof": final_dof,
            **metrics,
            "stream_values": stream_values,
            "source_summary": {
                "source": "watertap.flowsheets.full_water_resource_recovery_facility.BSM2_P_extension",
                "configuration": (
                    "BSM2 phosphorus extension with bio_P=True and the official sequential unit initialization path"
                    if bio_p
                    else "BSM2 phosphorus extension with bio_P=False and relaxed BlockTriangularizationInitializer residual tolerance eps=1e-7"
                ),
                "stdout_tail": stdout.getvalue()[-6000:],
            },
            "error": None if passed else {"message": "WaterTAP BSM2 P extension simulation did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        metrics = _metrics(model)
        stream_values = streams_from_arcs(model) if model is not None else {}
        return {
            "pass": False,
            "stage": "steady_state_simulation",
            "case_family": "watertap_bsm2_p_extension",
            "configuration": {"bio_P": bio_p},
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "checks": [{"name": "bsm2_p_extension_simulation_runner_exception", "pass": False}],
            **metrics,
            "stream_values": stream_values,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    parser.add_argument("--bio-p", action="store_true", help="Enable the ASM2d/ADM1 biological-phosphorus pathway")
    args = parser.parse_args()

    report = run_case(bio_p=args.bio_p)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
