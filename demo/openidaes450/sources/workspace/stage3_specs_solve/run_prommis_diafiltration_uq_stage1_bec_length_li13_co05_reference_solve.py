#!/usr/bin/env python3
"""Run official PrOMMiS diafiltration UQ stage-1 BEC/length Li1.3 Co0.5 figure validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_prommis_diafiltration_uq_reduced_reference_solve import (  # noqa: E402
    CASE_ROOT,
    run_case as run_uq_case,
)


SOURCE_URL = "https://github.com/prommis/prommis/blob/main/src/prommis/costing/uq/stage1_membrane_BEC_vs_length(_Li_sc1.3_Co_sc0.5).png"
STAGE1_BEC_LENGTH = CASE_ROOT / "src" / "prommis" / "costing" / "uq" / "stage1_membrane_BEC_vs_length(_Li_sc1.3_Co_sc0.5).png"


def run_case() -> dict:
    report = dict(run_uq_case())
    source_summary = dict(report.get("source_summary") or {})
    source_summary.update(
        {
            "official_reference_figure": str(STAGE1_BEC_LENGTH),
            "source_flowchart": str(STAGE1_BEC_LENGTH),
            "uq_figure_focus": "official PrOMMiS diafiltration UQ stage1_membrane_BEC_vs_length(_Li_sc1.3_Co_sc0.5).png",
        }
    )
    checks = list(report.get("checks") or [])
    checks.insert(
        0,
        {
            "name": "diafiltration_uq_stage1_bec_length_li13_co05_official_figure_exists",
            "pass": STAGE1_BEC_LENGTH.exists(),
            "actual": str(STAGE1_BEC_LENGTH),
        },
    )
    passed = bool(report.get("pass")) and STAGE1_BEC_LENGTH.exists()
    report.update(
        {
            "pass": passed,
            "case_family": "prommis_diafiltration_uq_stage1_bec_length_li13_co05",
            "official_reference_url": SOURCE_URL,
            "checks": checks,
            "source_summary": source_summary,
            "error": None if passed else report.get("error") or {"message": "PrOMMiS diafiltration UQ stage-1 BEC/length Li1.3 Co0.5 figure checks failed"},
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
