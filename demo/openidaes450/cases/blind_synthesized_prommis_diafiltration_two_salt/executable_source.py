#!/usr/bin/env python3
"""Run official PrOMMiS two-salt diafiltration flowsheet validation."""

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
from pyomo.environ import value  # noqa: E402


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/_autosummary/prommis.nanofiltration.diafiltration_flowsheet_two_salt.html"
CASE_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
SOURCE_ROOT = CASE_ROOT / "src"


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


def run_case() -> dict[str, Any]:
    stdout = io.StringIO()
    try:
        _prepare_imports()
        import matplotlib.pyplot as plt  # noqa: PLC0415
        from prommis.nanofiltration import diafiltration_flowsheet_two_salt as case  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            model, overall_plot, boundary_plot, membrane_plot, rejection_plot = case.main()
        for fig in (overall_plot, boundary_plot, membrane_plot, rejection_plot):
            plt.close(fig)

        membrane = model.fs.membrane
        ret_flow = scalar(membrane.retentate_flow_volume[0, 1])
        perm_flow = scalar(membrane.permeate_flow_volume[0, 1])
        ret_li = scalar(membrane.retentate_conc_mol_comp[0, 1, "Li"])
        perm_co = scalar(membrane.permeate_conc_mol_comp[0, 1, "Co"])
        final_dof = degrees_of_freedom(model)
        stream_values = port_stream_values(model.fs, max_streams=100)
        passed = bool(
            final_dof == 0
            and ret_flow is not None and ret_flow > 0
            and perm_flow is not None and perm_flow > 0
            and ret_li is not None and abs(ret_li - 190.89) < 0.5
            and perm_co is not None and abs(perm_co - 222.48) < 0.5
        )
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_two_salt",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "checks": [
                {"name": "two_salt_dof_zero", "pass": final_dof == 0, "actual": final_dof},
                {"name": "two_salt_retentate_flow_positive", "pass": bool(ret_flow is not None and ret_flow > 0), "actual": ret_flow},
                {"name": "two_salt_permeate_flow_positive", "pass": bool(perm_flow is not None and perm_flow > 0), "actual": perm_flow},
                {"name": "two_salt_retentate_li_matches_official_test", "pass": bool(ret_li is not None and abs(ret_li - 190.89) < 0.5), "actual": ret_li},
                {"name": "two_salt_permeate_co_matches_official_test", "pass": bool(perm_co is not None and abs(perm_co - 222.48) < 0.5), "actual": perm_co},
            ],
            "retentate_flow_volume": ret_flow,
            "permeate_flow_volume": perm_flow,
            "retentate_li_mol_m3": ret_li,
            "permeate_co_mol_m3": perm_co,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "nanofiltration" / "diafiltration_flowsheet_two_salt.py"),
                "official_test_source": str(SOURCE_ROOT / "prommis" / "nanofiltration" / "tests" / "test_diafiltration_flowsheet_two_salt.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/latest/_images/diafiltration_pfd.png",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS two-salt diafiltration checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_diafiltration_two_salt",
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
