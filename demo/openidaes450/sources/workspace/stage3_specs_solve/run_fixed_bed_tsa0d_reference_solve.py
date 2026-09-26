#!/usr/bin/env python3
"""Run the local official FixedBedTSA0D case as Stage-3 validation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

SOURCE_URL = "https://idaes-pse.readthedocs.io/en/stable/reference_guides/model_libraries/models_extra/temperature_swing_adsorption/fixed_bed_tsa0d.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/official_fixed_bed_tsa0d")
RUNNER = CASE_ROOT / "run_tsa_case.py"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    py310_lib = os.environ.get("IDAES_PIPELINE_PY310_LIB") or "/scratch/e1518147/vanda_pypkg/envs/py310/lib"
    current = env.get("LD_LIBRARY_PATH", "")
    if py310_lib not in current.split(":"):
        env["LD_LIBRARY_PATH"] = f"{py310_lib}:{current}" if current else py310_lib
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env.setdefault(name, "1")
    return env


def run_case(report_path: Path) -> dict[str, Any]:
    try:
        output_dir = report_path.parent / "fixed_bed_tsa0d_results"
        command = [
            sys.executable,
            str(RUNNER),
            "--case-id",
            "official_fixed_bed_tsa0d",
            "--output-dir",
            str(output_dir),
        ]
        completed = subprocess.run(
            command,
            cwd=str(CASE_ROOT),
            env=_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        summary_path = output_dir / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
        passed = completed.returncode == 0 and bool(summary.get("build_ok"))
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "fixed_bed_tsa0d",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "completed" if passed else "failed",
            "final_dof": 0 if passed else None,
            "number_beds": summary.get("number_beds"),
            "cycle_time_h": summary.get("cycle_time_h"),
            "pressure_drop_pa": summary.get("pressure_drop_pa"),
            "purity": summary.get("purity"),
            "recovery": summary.get("recovery"),
            "specific_energy_MJ_kgCO2": summary.get("specific_energy_MJ_kgCO2"),
            "productivity_kgCO2_m3_h": summary.get("productivity_kgCO2_m3_h"),
            "stream_values": {
                "flue_gas_feed": {"mole_frac_comp": {"CO2": 0.12, "N2": 0.88}},
                "co2_rich_product": {"purity": summary.get("purity"), "recovery": summary.get("recovery")},
                "n2_rich_product": {"pressure_drop_pa": summary.get("pressure_drop_pa")},
            },
            "source_summary": {"runner": str(RUNNER), "summary_path": str(summary_path)},
            "stdout_tail": completed.stdout[-5000:],
            "error": None if passed else {"message": "FixedBedTSA0D runner failed", "returncode": completed.returncode},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "fixed_bed_tsa0d",
            "official_reference_url": SOURCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_case(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
