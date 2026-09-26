#!/usr/bin/env python3
"""Run official PrOMMiS diafiltration PFD figure validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_prommis_diafiltration_reference_solve import run_case as run_diafiltration_case  # noqa: E402


SOURCE_URL = "https://github.com/prommis/prommis/blob/main/docs/tutorials/diafiltration_pfd.png"
PROMMIS_OFFICIAL_ROOT = Path("/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/prommis_official_source/prommis")
DIAFILTRATION_PFD = PROMMIS_OFFICIAL_ROOT / "docs" / "tutorials" / "diafiltration_pfd.png"


def run_case() -> dict:
    report = dict(run_diafiltration_case())
    source_summary = dict(report.get("source_summary") or {})
    source_summary.update(
        {
            "official_reference_figure": str(DIAFILTRATION_PFD),
            "source_flowchart": str(DIAFILTRATION_PFD),
            "pfd_focus": "official PrOMMiS diafiltration tutorial diafiltration_pfd.png",
        }
    )
    checks = list(report.get("checks") or [])
    checks.insert(0, {"name": "diafiltration_pfd_official_figure_exists", "pass": DIAFILTRATION_PFD.exists(), "actual": str(DIAFILTRATION_PFD)})
    passed = bool(report.get("pass")) and DIAFILTRATION_PFD.exists()
    report.update(
        {
            "pass": passed,
            "case_family": "prommis_diafiltration_pfd",
            "official_reference_url": SOURCE_URL,
            "checks": checks,
            "source_summary": source_summary,
            "error": None if passed else report.get("error") or {"message": "PrOMMiS diafiltration PFD checks failed"},
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
