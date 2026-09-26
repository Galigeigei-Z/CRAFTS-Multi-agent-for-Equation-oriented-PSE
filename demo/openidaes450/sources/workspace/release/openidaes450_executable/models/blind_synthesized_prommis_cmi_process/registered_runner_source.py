#!/usr/bin/env python3
"""Run the official PrOMMiS CMI process flowsheet as Stage-3 validation."""

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


SOURCE_URL = "https://prommis.readthedocs.io/en/latest/examples/cmi_process.html"
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
        from prommis.examples.cmi_process_flowsheet import cmi_process_flowsheet as cmi  # noqa: PLC0415
        from stage3_specs_solve.stream_extract import port_stream_values  # noqa: PLC0415

        with contextlib.redirect_stdout(stdout):
            model, _ = cmi.main()

        final_dof = degrees_of_freedom(model)
        nd_product = scalar(model.fs.Calcination.flow_mol_comp_product[0, "Nd"])
        s102_solid_nd_oxalate = scalar(model.fs.S102.sol_outlet.flow_mol_phase_comp[0, "Sol", "Nd2(C2O4)3 * 10H2O"])
        stream_values = port_stream_values(model.fs, max_streams=120)
        passed = bool(final_dof == 0 and nd_product is not None and 0.999 <= nd_product <= 1.001)
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "prommis_cmi_process",
            "official_reference_url": SOURCE_URL,
            "termination_condition": "optimal",
            "final_dof": final_dof,
            "checks": [
                {"name": "cmi_degrees_of_freedom_zero", "pass": final_dof == 0, "actual": final_dof},
                {"name": "cmi_nd_product_expected", "pass": bool(nd_product is not None and 0.999 <= nd_product <= 1.001), "actual": nd_product, "expected": 1.0},
                {"name": "cmi_stream_values_available", "pass": bool(stream_values), "actual": len(stream_values)},
            ],
            "nd_product_mol_s": nd_product,
            "s102_solid_nd_oxalate_mol_s": s102_solid_nd_oxalate,
            "stream_values": stream_values,
            "source_summary": {
                "source": str(SOURCE_ROOT / "prommis" / "examples" / "cmi_process_flowsheet" / "cmi_process_flowsheet.py"),
                "source_flowchart": "https://prommis.readthedocs.io/en/latest/_images/cmi_process_pfd.png",
                "stdout_tail": stdout.getvalue()[-4000:],
            },
            "error": None if passed else {"message": "PrOMMiS CMI process checks failed"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "prommis_cmi_process",
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
