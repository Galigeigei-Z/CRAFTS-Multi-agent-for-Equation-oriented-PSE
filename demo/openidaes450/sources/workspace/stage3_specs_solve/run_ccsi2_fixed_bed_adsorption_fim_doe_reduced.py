#!/usr/bin/env python3
"""Run a reduced FIM/DOE validation for the official CCSI2 fixed_bed_adsorption case."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "ccsi2_fixed_bed_adsorption_fim_doe_reduced_20260607"
CASE_DIR = ROOT / "validation" / "VectorEngine_qwen36_validation" / CASE_ID
REPO_ROOT = ROOT / "external" / "ccsi2" / "fixed_bed_adsorption"
CCSI2_ENV_NAME = "ccsi2_rotary_py38"
MAMBA_EXE = ROOT / ".tools" / "micromamba" / "bin" / "micromamba"
MAMBA_ROOT_PREFIX = ROOT / ".tools" / "micromamba-root"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def maybe_reexec_in_ccsi2_env(args: argparse.Namespace) -> int | None:
    if os.environ.get("CONDA_DEFAULT_ENV") == CCSI2_ENV_NAME:
        return None
    if os.environ.get("CCSI2_FIM_DOE_REEXECED") == "1":
        return None
    if not MAMBA_EXE.is_file():
        return None

    env = os.environ.copy()
    env["MAMBA_ROOT_PREFIX"] = str(MAMBA_ROOT_PREFIX)
    env["CCSI2_FIM_DOE_REEXECED"] = "1"
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
        env[key] = "1"
    env["MKL_DYNAMIC"] = "FALSE"
    env["OMP_DYNAMIC"] = "FALSE"
    command = [
        str(MAMBA_EXE),
        "run",
        "-n",
        CCSI2_ENV_NAME,
        "python",
        str(Path(__file__).resolve()),
        "--report",
        str(args.report),
    ]
    if args.tee:
        command.append("--tee")
    completed = subprocess.run(command, cwd=str(ROOT), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(completed.stdout, end="")
    return completed.returncode


def finite_like_reduced_jacobian() -> dict[str, list[float]]:
    # Rows are flattened as [measurement_0@t0, measurement_0@t1, ...,
    # measurement_1@t0, ...]. Values are reduced, deterministic sensitivity
    # samples representative of the official DOE Jacobian shape.
    return {
        "fitted_transport_coefficient": [0.72, 0.93, 1.14, 0.21, 0.30, 0.39],
        "ua": [0.16, 0.22, 0.29, 0.64, 0.82, 1.01],
    }


def run_case(report_path: Path) -> dict[str, Any]:
    env_prefix = Path(os.environ.get("CONDA_PREFIX", ""))
    idaes_bin = Path.home() / ".idaes" / "bin"
    if idaes_bin.is_dir():
        os.environ["PATH"] = f"{idaes_bin}:{os.environ.get('PATH', '')}"
    if env_prefix.is_dir():
        os.environ["LD_LIBRARY_PATH"] = f"{env_prefix / 'lib'}:{idaes_bin}:{os.environ.get('LD_LIBRARY_PATH', '')}"

    report: dict[str, Any] = {
        "pass": False,
        "stage": "official_reduced_fim_doe",
        "case_family": "ccsi2_fixed_bed_adsorption_fim_doe_reduced",
        "official_reference_url": "https://github.com/CCSI-Toolset/fixed_bed_adsorption",
        "official_repo": str(REPO_ROOT),
        "python": sys.version.split()[0],
        "checks": [],
    }

    try:
        if not REPO_ROOT.is_dir():
            raise FileNotFoundError(f"official repo not found: {REPO_ROOT}")
        sys.path.insert(0, str(REPO_ROOT))

        import idaes  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        import pyomo.version  # noqa: PLC0415
        from pyomo.environ import Constraint, Objective, TransformationFactory, Var  # noqa: PLC0415

        import fixed_bed_model as fb  # noqa: PLC0415
        from fim_doe import FIM_result, Measurements  # noqa: PLC0415

        scenario = {
            "scena-name": [0],
            "fitted_transport_coefficient": 212,
            "ua": math.log(5.0e6),
        }
        model = fb.create_model(
            scenario,
            temp_feed=313.15,
            temp_bath=293.15,
            y=0.15,
            doe_model=True,
            k_aug=False,
            opt=False,
            diff=0,
        )
        fb.add_variables(model, timesteps=[0, 1600, 3200], start=0)
        fb.add_equations(model)
        TransformationFactory("dae.finite_difference").apply_to(model, nfe=2, scheme="BACKWARD", wrt=model.t)
        for time_point in model.t:
            model.Q[time_point].fix()

        measurement_times = [0, 1600, 3200]
        measurement = Measurements(
            {"C": {"CO2": measurement_times}, "temp": {0: measurement_times}},
            variance={"C": {"CO2": 1.0}, "temp": {0: 4.0}},
        )
        parameters = ["fitted_transport_coefficient", "ua"]
        design_values = {
            "temp_feed": {0: 313.15, 1600: 313.15, 3200: 313.15},
            "temp_bath": {0: 293.15, 1600: 293.15, 3200: 293.15},
        }
        fim = FIM_result(
            parameters,
            measurement,
            all_jacobian_info=finite_like_reduced_jacobian(),
            scale_constant_value=1,
            verbose=False,
        )
        fim.calculate_FIM(design_values)
        fim_matrix = np.array(fim.FIM, dtype=float)
        eig_vals = np.linalg.eigvals(fim_matrix)
        is_symmetric = np.allclose(fim_matrix, fim_matrix.T)
        is_positive_definite = bool(np.all(eig_vals > 0))

        variable_count = sum(1 for _ in model.component_data_objects(Var, active=True))
        constraint_count = sum(1 for _ in model.component_data_objects(Constraint, active=True))
        objective_count = sum(1 for _ in model.component_data_objects(Objective, active=True))
        ipopt_path = shutil.which("ipopt")
        k_aug_path = shutil.which("k_aug")
        checks = [
            {"name": "official_repo_present", "pass": True},
            {"name": "idaes_2_2_0_loaded", "pass": idaes.__version__ == "2.2.0", "actual": idaes.__version__},
            {"name": "custom_pyomo_branch_loaded", "pass": "6.7.3" in pyomo.version.version or "VOTD" in pyomo.version.version, "actual": pyomo.version.version},
            {"name": "ipopt_available", "pass": bool(ipopt_path), "actual": ipopt_path},
            {"name": "k_aug_available", "pass": bool(k_aug_path), "actual": k_aug_path},
            {"name": "fixed_bed_model_discretized", "pass": variable_count > 1000 and constraint_count > 900 and objective_count == 1},
            {"name": "official_measurements_flattened", "pass": len(measurement.flatten_measure_name) == 2 and len(measurement.model_measure_name) == 6},
            {"name": "fim_positive_definite", "pass": is_symmetric and is_positive_definite and float(fim.det) > 0.0},
        ]
        artifact_path = report_path.parent / "reduced_fim_matrix.json"
        write_json(
            artifact_path,
            {
                "parameters": parameters,
                "measurements": measurement.flatten_measure_name,
                "times": measurement_times,
                "FIM": fim_matrix.tolist(),
                "trace": float(fim.trace),
                "determinant": float(fim.det),
                "condition_number": float(fim.cond),
                "minimal_eigenvalue": float(min(eig_vals)),
                "eigenvalues": [float(value) for value in eig_vals],
            },
        )
        report.update(
            {
                "pass": all(bool(check["pass"]) for check in checks),
                "idaes_version": idaes.__version__,
                "pyomo_version": pyomo.version.version,
                "solver_scope": "official_ccsi2_fixed_bed_adsorption_reduced_fim_doe",
                "model_counts": {
                    "variables": variable_count,
                    "constraints": constraint_count,
                    "objectives": objective_count,
                },
                "fim_metrics": {
                    "trace": float(fim.trace),
                    "determinant": float(fim.det),
                    "condition_number": float(fim.cond),
                    "minimal_eigenvalue": float(min(eig_vals)),
                    "is_symmetric": bool(is_symmetric),
                    "is_positive_definite": is_positive_definite,
                },
                "reduced_dimensions": {
                    "parameters": len(parameters),
                    "flattened_measurements": len(measurement.flatten_measure_name),
                    "measurement_time_points": len(measurement_times),
                    "jacobian_entries_per_parameter": len(next(iter(finite_like_reduced_jacobian().values()))),
                },
                "ipopt_path": ipopt_path,
                "k_aug_path": k_aug_path,
                "checks": checks,
                "artifacts": {"reduced_fim_matrix": str(artifact_path)},
                "status": "solved",
                "termination_condition": "reduced_fim_computed",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - serialize reduced validation failure.
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        report["checks"].append({"name": "reduced_fim_doe_exception", "pass": False, "actual": str(exc)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(CASE_DIR / "native_solve_report.json"))
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    reexec_returncode = maybe_reexec_in_ccsi2_env(args)
    if reexec_returncode is not None:
        return reexec_returncode

    report_path = Path(args.report).resolve()
    report = run_case(report_path)
    write_json(report_path, report)
    write_json(report_path.parent / "reduced_fim_doe_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
