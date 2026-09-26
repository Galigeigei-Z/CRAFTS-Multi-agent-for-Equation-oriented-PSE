#!/usr/bin/env python3
"""Run official PrOMMiS nanofiltration membrane schematic validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_prommis_multi_component_diafiltration_unit_reference_solve import (  # noqa: E402
    NANOFILTRATION_ROOT,
    run_case as run_multi_component_case,
)


SOURCE_URL = "https://github.com/prommis/prommis/blob/main/src/prommis/nanofiltration/membrane_schematic.png"
MEMBRANE_SCHEMATIC = NANOFILTRATION_ROOT / "membrane_schematic.png"


def run_case() -> dict:
    report = dict(run_multi_component_case())
    source_summary = dict(report.get("source_summary") or {})
    source_summary.update(
        {
            "official_reference_figure": str(MEMBRANE_SCHEMATIC),
            "source_flowchart": str(MEMBRANE_SCHEMATIC),
            "schematic_focus": "official PrOMMiS nanofiltration membrane_schematic.png",
        }
    )
    checks = list(report.get("checks") or [])
    checks.insert(
        0,
        {
            "name": "nanofiltration_membrane_schematic_official_figure_exists",
            "pass": MEMBRANE_SCHEMATIC.exists(),
            "actual": str(MEMBRANE_SCHEMATIC),
        },
    )
    passed = bool(report.get("pass")) and MEMBRANE_SCHEMATIC.exists()
    report.update(
        {
            "pass": passed,
            "case_family": "prommis_nanofiltration_membrane_schematic",
            "official_reference_url": SOURCE_URL,
            "checks": checks,
            "source_summary": source_summary,
            "error": None if passed else report.get("error") or {"message": "PrOMMiS nanofiltration membrane schematic checks failed"},
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
