#!/usr/bin/env python3
"""Run official PrOMMiS UKy UI flowsheet figure validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_prommis_uky_reference_solve import CASE_ROOT, run_case as run_uky_case  # noqa: E402


SOURCE_URL = "https://github.com/prommis/prommis/blob/main/src/prommis/uky/uky_flowsheet_ui.png"
UKY_UI_FIGURE = CASE_ROOT / "src" / "prommis" / "uky" / "uky_flowsheet_ui.png"


def run_case() -> dict:
    report = dict(run_uky_case())
    source_summary = dict(report.get("source_summary") or {})
    source_summary.update(
        {
            "official_reference_figure": str(UKY_UI_FIGURE),
            "source_flowchart": str(UKY_UI_FIGURE),
            "ui_figure_focus": "official PrOMMiS UKy UI flowsheet uky_flowsheet_ui.png",
        }
    )
    checks = list(report.get("checks") or [])
    checks.insert(0, {"name": "uky_ui_flowsheet_official_figure_exists", "pass": UKY_UI_FIGURE.exists(), "actual": str(UKY_UI_FIGURE)})
    passed = bool(report.get("pass")) and UKY_UI_FIGURE.exists()
    report.update(
        {
            "pass": passed,
            "case_family": "prommis_uky_ui_flowsheet",
            "official_reference_url": SOURCE_URL,
            "checks": checks,
            "source_summary": source_summary,
            "error": None if passed else report.get("error") or {"message": "PrOMMiS UKy UI flowsheet checks failed"},
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
