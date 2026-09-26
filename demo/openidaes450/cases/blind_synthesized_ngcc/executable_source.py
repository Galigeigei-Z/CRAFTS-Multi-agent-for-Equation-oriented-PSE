#!/usr/bin/env python3
"""Run the official NGCC case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ARTIFACT_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/"
    "langgraph_idaes_pipeline"
)
EXAMPLES_REPO_RELATIVE = Path("examples/github_examples/clones/examples")
EXAMPLES_REPO = LEGACY_ARTIFACT_ROOT / EXAMPLES_REPO_RELATIVE
NGCC_NOTEBOOK_DIR = EXAMPLES_REPO / "idaes_examples" / "notebooks" / "docs" / "power_gen" / "ngcc"
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/ngcc/ngcc_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402
from stream_extract import port_stream_values  # noqa: E402


def component_value(obj: Any, *index: Any) -> float | None:
    if index:
        try:
            return float(value(obj[index]))
        except Exception:
            pass
    try:
        if hasattr(obj, "is_indexed") and obj.is_indexed():
            return float(value(obj[next(iter(obj))]))
    except Exception:
        pass
    try:
        return float(value(obj))
    except Exception:
        return None


def tag_values(tag_group: Any) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    try:
        keys = list(tag_group.keys())
    except Exception:
        return rows
    for key in keys:
        try:
            rows[str(key)] = float(value(tag_group[key].expression))
        except Exception:
            try:
                rows[str(key)] = float(tag_group[key].value)
            except Exception:
                rows[str(key)] = None
    return rows


def run_case(report_path: Path, tee: bool = False) -> dict[str, Any]:
    try:
        import idaes  # noqa: PLC0415
        import idaes.core.util.scaling as iscale  # noqa: PLC0415
        import pyomo.environ as pyo  # noqa: PLC0415
        from idaes.core.solvers import use_idaes_solver_configuration_defaults  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.opt import SolverStatus, TerminationCondition  # noqa: PLC0415

        if not EXAMPLES_REPO.is_dir():
            raise RuntimeError(f"IDAES examples repo not found: {EXAMPLES_REPO}")
        sys.path.insert(0, str(EXAMPLES_REPO))
        from idaes_examples.mod.power_gen import ngcc  # noqa: PLC0415

        work_dir = report_path.parent
        init_source = NGCC_NOTEBOOK_DIR / "ngcc_init.json.gz"
        if init_source.is_file():
            shutil.copy2(init_source, work_dir / "ngcc_init.json.gz")

        use_idaes_solver_configuration_defaults()
        idaes.cfg.ipopt.options.nlp_scaling_method = "user-scaling"
        idaes.cfg.ipopt.options.linear_solver = "ma57"
        idaes.cfg.ipopt.options.OF_ma57_automatic_scaling = "yes"
        idaes.cfg.ipopt.options.ma57_pivtol = 1e-5
        idaes.cfg.ipopt.options.ma57_pivtolmax = 0.1

        model = pyo.ConcreteModel()
        model.fs = ngcc.NgccFlowsheet(dynamic=False)
        iscale.calculate_scaling_factors(model)
        model.fs.initialize(load_from=str(work_dir / "ngcc_init.json.gz"), save_to=str(work_dir / "ngcc_init.json.gz"))
        solver = pyo.SolverFactory("ipopt")
        results = solver.solve(model, tee=tee)
        optimal = (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )
        return {
            "pass": bool(optimal and degrees_of_freedom(model) == 0),
            "stage": "steady_state_solver",
            "case_family": "ngcc",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "final_dof": degrees_of_freedom(model),
            "stream_values": port_stream_values(model),
            "tag_values": tag_values(model.fs.tags_output),
            "net_power_mw": component_value(model.fs.net_power_mw, 0),
            "source_summary": {
                "source": "idaes_examples.mod.power_gen.ngcc.NgccFlowsheet",
                "init_json": str(init_source),
            },
            "source_binding": {
                "kind": "explicit_legacy_artifact_root",
                "artifact_root": str(LEGACY_ARTIFACT_ROOT),
                "relative_path": str(EXAMPLES_REPO_RELATIVE),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "ngcc",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "source_binding": {
                "kind": "explicit_legacy_artifact_root",
                "artifact_root": str(LEGACY_ARTIFACT_ROOT),
                "relative_path": str(EXAMPLES_REPO_RELATIVE),
            },
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

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_case(report_path, tee=args.tee)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
