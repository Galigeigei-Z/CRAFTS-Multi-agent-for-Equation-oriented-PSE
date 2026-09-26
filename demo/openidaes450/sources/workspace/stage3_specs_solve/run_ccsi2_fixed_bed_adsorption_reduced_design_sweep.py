#!/usr/bin/env python3
"""Run a reduced design sweep for the official CCSI2 fixed_bed_adsorption model."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "ccsi2_fixed_bed_adsorption_reduced_design_sweep_20260607"
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
    if os.environ.get("CCSI2_DESIGN_SWEEP_REEXECED") == "1":
        return None
    if not MAMBA_EXE.is_file():
        return None

    env = os.environ.copy()
    env["MAMBA_ROOT_PREFIX"] = str(MAMBA_ROOT_PREFIX)
    env["CCSI2_DESIGN_SWEEP_REEXECED"] = "1"
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


def sweep_points() -> list[dict[str, Any]]:
    return [
        {"name": "base", "temp_feed": 313.15, "temp_bath": 293.15, "y_CO2": 0.15},
        {"name": "warm_feed", "temp_feed": 318.15, "temp_bath": 293.15, "y_CO2": 0.15},
        {"name": "cool_bath", "temp_feed": 313.15, "temp_bath": 288.15, "y_CO2": 0.15},
    ]


def run_case(report_path: Path) -> dict[str, Any]:
    env_prefix = Path(os.environ.get("CONDA_PREFIX", ""))
    idaes_bin = Path.home() / ".idaes" / "bin"
    if idaes_bin.is_dir():
        os.environ["PATH"] = f"{idaes_bin}:{os.environ.get('PATH', '')}"
    if env_prefix.is_dir():
        os.environ["LD_LIBRARY_PATH"] = f"{env_prefix / 'lib'}:{idaes_bin}:{os.environ.get('LD_LIBRARY_PATH', '')}"

    report: dict[str, Any] = {
        "pass": False,
        "stage": "official_reduced_design_sweep",
        "case_family": "ccsi2_fixed_bed_adsorption_reduced_design_sweep",
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
        import pyomo.version  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.environ import Constraint, Objective, SolverFactory, TerminationCondition, TransformationFactory, Var, value  # noqa: PLC0415

        import fixed_bed_model as fb  # noqa: PLC0415

        solver = SolverFactory("ipopt")
        acceptable = {
            TerminationCondition.optimal,
            TerminationCondition.locallyOptimal,
            TerminationCondition.feasible,
        }
        point_reports: list[dict[str, Any]] = []
        model_counts: dict[str, int] | None = None
        for point in sweep_points():
            started = time.time()
            scenario = {
                "scena-name": [0],
                "fitted_transport_coefficient": 212,
                "ua": math.log(5.0e6),
            }
            model = fb.create_model(
                scenario,
                temp_feed=point["temp_feed"],
                temp_bath=point["temp_bath"],
                y=point["y_CO2"],
                doe_model=True,
                k_aug=False,
                opt=False,
                diff=0,
            )
            fb.add_variables(model, timesteps=[0, 1600, 3200], start=0)
            fb.add_equations(model)
            TransformationFactory("dae.finite_difference").apply_to(model, nfe=2, scheme="BACKWARD", wrt=model.t)
            for time_point in model.t:
                model.Q[time_point].fix(0)
            result = solver.solve(model, tee=False, options={"max_iter": 300, "tol": 1e-6})
            termination = str(result.solver.termination_condition)
            status = str(result.solver.status)
            passed = result.solver.termination_condition in acceptable
            counts = {
                "variables": sum(1 for _ in model.component_data_objects(Var, active=True)),
                "constraints": sum(1 for _ in model.component_data_objects(Constraint, active=True)),
                "objectives": sum(1 for _ in model.component_data_objects(Objective, active=True)),
            }
            if model_counts is None:
                model_counts = counts
            point_reports.append(
                {
                    **point,
                    "pass": bool(passed),
                    "solver_status": status,
                    "termination_condition": termination,
                    "degrees_of_freedom": degrees_of_freedom(model),
                    "objective_values": {
                        obj.name: float(value(obj.expr))
                        for obj in model.component_data_objects(Objective, active=True)
                    },
                    "q_profile": {str(time_point): float(value(model.Q[time_point])) for time_point in model.t},
                    "elapsed_seconds": round(time.time() - started, 3),
                    "model_counts": counts,
                }
            )

        ipopt_path = shutil.which("ipopt")
        k_aug_path = shutil.which("k_aug")
        all_points_pass = all(point["pass"] for point in point_reports)
        consistent_counts = all(point["model_counts"] == model_counts for point in point_reports)
        checks = [
            {"name": "official_repo_present", "pass": True},
            {"name": "idaes_2_2_0_loaded", "pass": idaes.__version__ == "2.2.0", "actual": idaes.__version__},
            {"name": "custom_pyomo_branch_loaded", "pass": "6.7.3" in pyomo.version.version or "VOTD" in pyomo.version.version, "actual": pyomo.version.version},
            {"name": "ipopt_available", "pass": bool(ipopt_path), "actual": ipopt_path},
            {"name": "k_aug_available", "pass": bool(k_aug_path), "actual": k_aug_path},
            {"name": "all_design_points_solved", "pass": all_points_pass, "actual": [point["termination_condition"] for point in point_reports]},
            {"name": "consistent_model_counts", "pass": consistent_counts, "actual": model_counts},
            {"name": "three_design_points", "pass": len(point_reports) == 3},
        ]
        artifact_path = report_path.parent / "reduced_design_sweep_points.json"
        write_json(artifact_path, {"points": point_reports})
        report.update(
            {
                "pass": all(bool(check["pass"]) for check in checks),
                "idaes_version": idaes.__version__,
                "pyomo_version": pyomo.version.version,
                "solver_scope": "official_ccsi2_fixed_bed_adsorption_reduced_design_sweep",
                "model_counts": model_counts,
                "design_points": point_reports,
                "design_point_count": len(point_reports),
                "ipopt_path": ipopt_path,
                "k_aug_path": k_aug_path,
                "checks": checks,
                "artifacts": {"reduced_design_sweep_points": str(artifact_path)},
                "status": "solved",
                "termination_condition": "all_design_points_solved" if all_points_pass else "failed",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - serialize reduced sweep failure.
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        report["checks"].append({"name": "reduced_design_sweep_exception", "pass": False, "actual": str(exc)})
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
    write_json(report_path.parent / "reduced_design_sweep_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
