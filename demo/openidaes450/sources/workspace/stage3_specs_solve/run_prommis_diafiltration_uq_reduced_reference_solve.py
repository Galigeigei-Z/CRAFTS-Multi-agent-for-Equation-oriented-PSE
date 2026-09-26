#!/usr/bin/env python3
"""Run a reduced official PrOMMiS diafiltration cost-UQ validation."""

from __future__ import annotations

import argparse
import contextlib
import io
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

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import SolverFactory, value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/tutorials/diafiltration_cost_uncertainty_quantification_and_propagation-solution.html"
BASE_FLOWSHEET_URL = "https://prommis.readthedocs.io/en/latest/tutorials/diafiltration.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"
N_SAMPLES = 3
RANDOM_SEED = 7


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


def _finite(values: Any) -> list[float]:
    import numpy as np  # noqa: PLC0415

    arr = np.asarray(values, dtype=float)
    return [float(v) for v in arr[~np.isnan(arr)]]


def _load_lognormal_params(uq: Any, model: Any) -> dict[str, dict[str, float]]:
    import pandas as pd  # noqa: PLC0415

    script_dir = uq.get_script_dir()
    cp = model.fs.costing

    li_df = pd.read_csv(os.path.join(script_dir, "lithium_price_USA_dailymetalprice_yr2021.csv"))
    co_df = pd.read_csv(os.path.join(script_dir, "cobalt_price_USA_tradingeconomics_yr2021.csv"))
    elec_df = pd.read_csv(os.path.join(script_dir, "iea_1990_2025_industry_elec_monthly_price_PA.csv"))

    mu_li, sigma_li = uq.estimate_lognormal_params_from_data(li_df["2021_$/kg"].values)
    mu_co, sigma_co = uq.estimate_lognormal_params_from_data(co_df["2021_$/kg"].values)
    mu_elec, sigma_elec = uq.estimate_lognormal_params_from_data(elec_df["PA_2021_$/kWh"].values)

    return {
        cp.electricity_cost.getname(): {"mu": float(mu_elec), "sigma": float(sigma_elec)},
        cp.Li_price.getname(): {"mu": float(mu_li), "sigma": float(sigma_li)},
        cp.Co_price.getname(): {"mu": float(mu_co), "sigma": float(sigma_co)},
    }


def _run_technology(uq: Any, technology_name: str, sieving_coeffs: tuple[float, float]) -> dict[str, Any]:
    import numpy as np  # noqa: PLC0415

    solver = SolverFactory("ipopt")
    solver.options["max_iter"] = 5000
    solver.options["tol"] = 1e-6
    solver.options["acceptable_tol"] = 1e-5

    model = uq.build_diafiltration_model(sieving_coeffs=sieving_coeffs, technology_name=technology_name)
    uq.decision_variables_bounds(model)
    det_results = solver.solve(model, tee=False)

    uncertain_params = uq.identify_uncertain_params(model)
    lognormal_params = _load_lognormal_params(uq, model)
    income_tax_file = os.path.join(uq.get_script_dir(), "PA_income_tax.csv")
    income_tax_samples = uq.load_income_tax_samples_from_csv(income_tax_file, column_name="2021_tax")
    uncertainty_specs = uq.build_uncertainty_specs(
        model,
        lognormal_params=lognormal_params,
        income_tax_samples=income_tax_samples,
    )

    (
        samples_first_param,
        recovery_cost_samples,
        param_samples,
        stage1_len,
        stage2_len,
        stage3_len,
    ) = uq.run_LHS(
        model,
        uncertain_params,
        uncertainty_specs,
        n_samples=N_SAMPLES,
        solver=solver,
        random_seed=RANDOM_SEED,
    )

    valid_cost = _finite(recovery_cost_samples)
    q05 = q50 = q95 = None
    if valid_cost:
        q05, q50, q95 = [float(v) for v in np.percentile(np.asarray(valid_cost, dtype=float), [5, 50, 95])]

    return {
        "technology": technology_name,
        "sieving_coefficients": list(sieving_coeffs),
        "deterministic_termination_condition": str(det_results.solver.termination_condition),
        "deterministic_cost_of_recovery": scalar(model.fs.costing.cost_of_recovery),
        "final_dof": degrees_of_freedom(model),
        "uncertain_parameter_count": len(uncertain_params),
        "uncertain_parameter_names": [param.getname() for param in uncertain_params],
        "samples_requested": N_SAMPLES,
        "valid_samples": len(valid_cost),
        "cost_of_recovery_samples": valid_cost,
        "cost_of_recovery_q05": q05,
        "cost_of_recovery_q50": q50,
        "cost_of_recovery_q95": q95,
        "stage1_length_samples_m": _finite(stage1_len),
        "stage2_length_samples_m": _finite(stage2_len),
        "stage3_length_samples_m": _finite(stage3_len),
        "first_uncertain_parameter_samples": _finite(samples_first_param),
        "param_sample_shape": list(param_samples.shape),
    }


def run_case() -> dict[str, Any]:
    stdout = io.StringIO()
    try:
        _prepare_imports()
        import prommis.costing.uq.diafiltration_cost_uq as uq  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            technology_results = [
                _run_technology(uq, "Li_sc=1.3, Co_sc=0.5", (1.3, 0.5)),
                _run_technology(uq, "Li_sc=1.5, Co_sc=0.8", (1.5, 0.8)),
            ]

        valid_sample_counts = [int(result["valid_samples"]) for result in technology_results]
        q95_values = [result["cost_of_recovery_q95"] for result in technology_results]

        stream_model = uq.build_diafiltration_model(sieving_coeffs=(1.3, 0.5), technology_name="stream_extract")
        stream_values = port_stream_values(stream_model.fs, max_streams=200)

        passed = bool(
            all(count >= 1 for count in valid_sample_counts)
            and all(q95 is not None and q95 > 0 for q95 in q95_values)
            and all(result["uncertain_parameter_count"] == 10 for result in technology_results)
            and stream_values
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_uq_reduced",
            "official_reference_url": SOURCE_URL,
            "base_flowsheet_reference_url": BASE_FLOWSHEET_URL,
            "termination_condition": "optimal" if passed else None,
            "final_dof": technology_results[0]["final_dof"],
            "design_degrees_of_freedom": technology_results[0]["final_dof"],
            "reduced_sample_count": N_SAMPLES,
            "sampling_method": "latin_hypercube",
            "technology_results": technology_results,
            "stream_values": stream_values,
            "checks": [
                {"name": "diafiltration_uq_two_technologies_evaluated", "pass": len(technology_results) == 2, "actual": len(technology_results)},
                {"name": "diafiltration_uq_uncertain_parameter_count", "pass": all(result["uncertain_parameter_count"] == 10 for result in technology_results), "actual": [result["uncertain_parameter_count"] for result in technology_results]},
                {"name": "diafiltration_uq_valid_lhs_samples", "pass": all(count >= 1 for count in valid_sample_counts), "actual": valid_sample_counts},
                {"name": "diafiltration_uq_quantiles_positive", "pass": all(q95 is not None and q95 > 0 for q95 in q95_values), "actual": q95_values},
                {"name": "diafiltration_uq_stream_values_available", "pass": bool(stream_values), "actual": len(stream_values)},
            ],
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "costing" / "uq" / "diafiltration_cost_uq.py"),
                "base_flowsheet_source": str(SOURCE_ROOT / "prommis" / "nanofiltration" / "diafiltration.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/latest/_images/diafiltration_pfd.png",
                "official_full_sample_count": 200,
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "Reduced PrOMMiS diafiltration UQ checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_uq_reduced",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_summary": {"source_root": str(SOURCE_ROOT), "stdout_tail": stdout.getvalue()[-4000:]},
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
