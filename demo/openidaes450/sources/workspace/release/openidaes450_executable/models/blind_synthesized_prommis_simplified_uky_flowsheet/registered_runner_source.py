#!/usr/bin/env python3
"""Run official PrOMMiS UKy flowsheet validation for the simplified schematic case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_prommis_uky_reference_solve import CASE_ROOT, run_case as run_uky_case


SOURCE_URL = "https://prommis.readthedocs.io/en/stable/tutorials/uky_flowsheet-solution.html"
SIMPLIFIED_FIGURE = CASE_ROOT / "docs" / "tutorials" / "simplified_uky.png"


def run_case() -> dict:
    report = dict(run_uky_case())
    source_summary = dict(report.get("source_summary") or {})
    source_summary.update(
        {
            "official_reference_figure": str(SIMPLIFIED_FIGURE),
            "source_flowchart": str(SIMPLIFIED_FIGURE),
            "official_notebook": str(CASE_ROOT / "docs" / "tutorials" / "uky_flowsheet-solution.ipynb"),
            "simplified_schematic": True,
        }
    )
    checks = list(report.get("checks") or [])
    checks.insert(
        0,
        {
            "name": "simplified_uky_official_figure_exists",
            "pass": SIMPLIFIED_FIGURE.exists(),
            "actual": str(SIMPLIFIED_FIGURE),
        },
    )
    passed = bool(report.get("pass")) and SIMPLIFIED_FIGURE.exists()
    report.update(
        {
            "pass": passed,
            "case_family": "prommis_simplified_uky_flowsheet",
            "official_reference_url": SOURCE_URL,
            "checks": checks,
            "source_summary": source_summary,
            "error": None if passed else report.get("error") or {"message": "PrOMMiS simplified UKy checks failed"},
        }
    )
    return report


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
