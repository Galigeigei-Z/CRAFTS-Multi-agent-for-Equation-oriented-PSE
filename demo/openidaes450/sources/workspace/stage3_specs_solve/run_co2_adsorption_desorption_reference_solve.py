#!/usr/bin/env python3
"""Run the official CO2 adsorption/desorption FixedBed1D notebook as Stage-3 validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_REPO = ROOT / "examples" / "github_examples" / "clones" / "examples"
NOTEBOOK_PATH = (
    EXAMPLES_REPO
    / "idaes_examples"
    / "notebooks"
    / "held"
    / "flowsheets"
    / "CO2_adsorption_desorption"
    / "CO2_Adsorption_Desorption_1DFixedBed_doc.ipynb"
)
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/CO2_adsorption_desorption/CO2_Adsorption_Desorption_example_1DFixedBed_doc.html"
for path in (ROOT, PIPELINE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()
from stage3_specs_solve.stream_extract import port_stream_values  # noqa: E402


def reduced_validation_enabled() -> bool:
    return os.environ.get("CO2_ADS_DES_FULL_NOTEBOOK", "").strip().lower() not in {"1", "true", "yes", "on"}


def reduced_settings() -> dict[str, int]:
    return {
        "nxfe": int(os.environ.get("CO2_ADS_DES_NXFE", "5")),
        "adsorption_horizon": int(os.environ.get("CO2_ADS_DES_ADS_HORIZON", "1200")),
        "desorption_horizon": int(os.environ.get("CO2_ADS_DES_DES_HORIZON", "600")),
        "ts_dt": int(os.environ.get("CO2_ADS_DES_TS_DT", "200")),
    }


def transform_source(index: int, source: str) -> str:
    if not reduced_validation_enabled():
        return source
    settings = reduced_settings()
    source = re.sub(r"(?m)^nxfe\s*=\s*50\s*$", f"nxfe = {settings['nxfe']}", source)
    if index == 28:
        source = re.sub(r"(?m)^horizon\s*=\s*108000\s*# s\s*$", f"horizon = {settings['adsorption_horizon']}  # s", source)
    if index == 46:
        source = re.sub(r"(?m)^horizon\s*=\s*7200\s*# s\s*$", f"horizon = {settings['desorption_horizon']}  # s", source)
    source = source.replace('"--ts_dt": 200', f'"--ts_dt": {settings["ts_dt"]}')
    source = source.replace("'--ts_dt': 200", f"'--ts_dt': {settings['ts_dt']}")
    return source


def code_cells(path: Path) -> list[tuple[int, str]]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    cells: list[tuple[int, str]] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", ""))
        if not source.strip():
            continue
        # Keep imports and the full build/init/simulate path, but skip plotting calls in a headless web run.
        stripped = source.strip()
        if (
            ("plot_results_temporal" in source or "plot_results_spatial" in source)
            and not stripped.startswith("from ")
            and not stripped.startswith("import ")
        ):
            continue
        cells.append((index, transform_source(index, source)))
    return cells


def safe_float(value: Any) -> float | None:
    try:
        from pyomo.environ import value as pyomo_value  # noqa: PLC0415

        return float(pyomo_value(value))
    except Exception:
        try:
            return float(value)
        except Exception:
            return None


def run_case(report_path: Path) -> dict[str, Any]:
    try:
        if not NOTEBOOK_PATH.is_file():
            raise RuntimeError(f"official CO2 notebook not found: {NOTEBOOK_PATH}")
        sys.path.insert(0, str(EXAMPLES_REPO))
        work_dir = report_path.parent
        work_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(work_dir)

        namespace: dict[str, Any] = {
            "__name__": "__co2_adsorption_desorption_stage3__",
            "__file__": str(NOTEBOOK_PATH),
        }
        executed: list[int] = []
        for index, source in code_cells(NOTEBOOK_PATH):
            print(f"[co2_stage3] executing official notebook cell {index}", flush=True)
            exec(compile(source, f"{NOTEBOOK_PATH}#cell{index}", "exec"), namespace)  # noqa: S102
            executed.append(index)
            print(f"[co2_stage3] completed official notebook cell {index}", flush=True)

        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415

        m = namespace.get("m")
        fs_ads = getattr(m, "fs_ads", None) if m is not None else None
        fs_des = getattr(m, "fs_des", None) if m is not None else None
        stream_values: dict[str, Any] = {}
        if fs_ads is not None:
            stream_values.update({f"adsorption.{name}": values for name, values in port_stream_values(fs_ads, max_streams=40).items()})
        if fs_des is not None:
            stream_values.update({f"desorption.{name}": values for name, values in port_stream_values(fs_des, max_streams=40).items()})
        return {
            "pass": bool(fs_ads is not None and fs_des is not None),
            "stage": "dynamic_petsc_solver",
            "case_family": "co2_adsorption_desorption",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": "completed_notebook_execution",
            "final_dof": {
                "adsorption": degrees_of_freedom(fs_ads) if fs_ads is not None else None,
                "desorption": degrees_of_freedom(fs_des) if fs_des is not None else None,
            },
            "adsorption_initialization_time_s": safe_float(namespace.get("adsorption_initialization_time")),
            "adsorption_simulation_time_s": safe_float(namespace.get("adsorption_simulation_time")),
            "desorption_initialization_time_s": safe_float(namespace.get("desorption_initialization_time")),
            "desorption_simulation_time_s": safe_float(namespace.get("desorption_simulation_time")),
            "stream_values": stream_values,
            "executed_cells": executed,
            "validation_mode": "reduced_official_dynamic_validation" if reduced_validation_enabled() else "full_official_notebook",
            "reduced_settings": reduced_settings() if reduced_validation_enabled() else None,
            "source_summary": {
                "source": str(NOTEBOOK_PATH),
                "note": "Executed official FixedBed1D adsorption/desorption notebook code cells except plotting cells.",
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "dynamic_petsc_solver",
            "case_family": "co2_adsorption_desorption",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_case(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
