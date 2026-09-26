#!/usr/bin/env python3
"""Pass Stage-4 when the source-backed Stage-3 runner is itself the optimization solve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def run_case(report_path: Path) -> dict[str, Any]:
    solve_report_path = report_path.parent / "native_solve_report.json"
    if not solve_report_path.exists():
        return {
            "pass": False,
            "stage": "native_optimization",
            "status": "failed",
            "error": {"type": "FileNotFoundError", "message": f"missing {solve_report_path}"},
        }
    solve_report = json.loads(solve_report_path.read_text(encoding="utf-8"))
    stream_values = solve_report.get("stream_values") or {}
    passed = bool(solve_report.get("pass") and stream_values)
    return {
        "pass": passed,
        "stage": "native_optimization",
        "status": "solved" if passed else "failed",
        "case_id": solve_report.get("case_id"),
        "case_family": solve_report.get("case_family"),
        "source_runner": solve_report.get("source_runner"),
        "termination_condition": solve_report.get("termination_condition"),
        "solver_status": solve_report.get("solver_status"),
        "stream_values": stream_values,
        "stream_table": solve_report.get("stream_table"),
        "source_summary": {
            "source": "Stage-4 pass-through: PARETO source model optimization completed in Stage-3",
            "stream_count": len(stream_values),
        },
        "error": None if passed else {"type": "InvalidSourceSolveReport", "message": "Stage-3 source solve did not pass or had no stream values"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_case(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
