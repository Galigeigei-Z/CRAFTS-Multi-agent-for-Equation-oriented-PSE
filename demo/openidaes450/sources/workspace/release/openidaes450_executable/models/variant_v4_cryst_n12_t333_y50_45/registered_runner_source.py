#!/usr/bin/env python3
"""Execute a whitelisted registry case source and emit one current solve report."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SOURCE_ROOT = Path(
    "/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/prompt/2026-05-31/langgraph_idaes_pipeline"
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from case_registry import find_case, load_registry  # noqa: E402
from core.runtime_env import configure_py310_runtime  # noqa: E402


configure_py310_runtime()


def _load_script(relative_path: str) -> Any:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts or relative.parts[:2] != ("experiment", "scripts"):
        raise ValueError(f"registered source is not an approved experiment script: {relative_path}")
    candidates = [(ROOT / relative).resolve(), (LEGACY_SOURCE_ROOT / relative).resolve()]
    path = next(
        (
            candidate
            for candidate in candidates
            if candidate.is_file()
            and any(base.resolve() in candidate.parents for base in (ROOT, LEGACY_SOURCE_ROOT))
        ),
        None,
    )
    if path is None:
        raise ValueError(f"registered source is outside the workspace or missing: {relative_path}")
    # The legacy tree supplies executable source only. It is imported read-only;
    # no legacy Case Log or validation directory is copied into this release.
    spec = importlib.util.spec_from_file_location(f"registered_case_source_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import registered source: {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_batch_source(case_key: str, source_path: str) -> dict[str, Any]:
    module = _load_script(source_path)
    if not hasattr(module, "BY_KEY") or not hasattr(module, "solve_one") or case_key not in module.BY_KEY:
        raise ValueError(f"registered batch source does not expose case {case_key}")
    return module.solve_one(module.BY_KEY[case_key])


def _run_flowsheet_variant(case_key: str) -> dict[str, Any]:
    module = _load_script("experiment/scripts/build_flowsheet_operating_variants_v4.py")
    row = next((item for item in module.ALL_VARIANTS if item.case_id == case_key), None)
    if row is None:
        raise ValueError(f"flowsheet variant manifest does not contain {case_key}")
    metrics, termination, final_dof = module.solve_variant(row)
    passed = termination.lower() == "optimal" and final_dof == 0
    return {
        "pass": passed,
        "status": "solved",
        "stage": "steady_state_solver",
        "case_key": case_key,
        "case_family": row.family,
        "parent_case_id": row.parent_case_id,
        "variant_fingerprint": row.fingerprint,
        "variant_parameters": row.params,
        "variant_metrics": metrics,
        "final_dof": final_dof,
        "termination_condition": termination,
        "error": None if passed else f"termination={termination}; final_dof={final_dof}",
    }


def run_case(case_key: str) -> dict[str, Any]:
    record = find_case(load_registry(), case_key)
    if record is None:
        raise ValueError(f"unregistered case key: {case_key}")
    selection = record.get("selection") if isinstance(record.get("selection"), dict) else {}
    source = str(selection.get("source_manifest_path") or "")
    if source == "experiment/case_variants/flowsheet_operating_variants_v4.json":
        return _run_flowsheet_variant(case_key)
    if source.startswith("local://experiment/scripts/solve_chemical_meaningful_batch_") and source.endswith(".py"):
        report = _run_batch_source(case_key, source.removeprefix("local://"))
        report.setdefault("case_key", case_key)
        return report
    raise ValueError(f"case source is not approved for registered execution: {source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-key", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run_case(args.case_key)
    except Exception as exc:  # noqa: BLE001
        report = {
            "pass": False,
            "stage": "registered_case_source_solve",
            "case_key": args.case_key,
            "termination_condition": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
