#!/usr/bin/env python3
"""Run official PrOMMiS CMI process PFD figure validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_prommis_cmi_process_reference_solve import CASE_ROOT, run_case as run_cmi_case  # noqa: E402


SOURCE_URL = "https://github.com/prommis/prommis/blob/main/docs/examples/cmi_process_pfd.png"
CMI_PFD = CASE_ROOT / "docs" / "examples" / "cmi_process_pfd.png"


def run_case() -> dict:
    report = dict(run_cmi_case())
    source_summary = dict(report.get("source_summary") or {})
    source_summary.update(
        {
            "official_reference_figure": str(CMI_PFD),
            "source_flowchart": str(CMI_PFD),
            "pfd_focus": "official PrOMMiS CMI process cmi_process_pfd.png",
        }
    )
    checks = list(report.get("checks") or [])
    checks.insert(0, {"name": "cmi_process_pfd_official_figure_exists", "pass": CMI_PFD.exists(), "actual": str(CMI_PFD)})
    passed = bool(report.get("pass")) and CMI_PFD.exists()
    report.update(
        {
            "pass": passed,
            "case_family": "prommis_cmi_process_pfd",
            "official_reference_url": SOURCE_URL,
            "checks": checks,
            "source_summary": source_summary,
            "error": None if passed else report.get("error") or {"message": "PrOMMiS CMI process PFD checks failed"},
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
