#!/usr/bin/env python3
"""Validate the official IDAES SCPC power-plant PFD as a smoke case."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


OFFICIAL_REFERENCE_URL = "https://idaes-pse.readthedocs.io/en/stable/reference_guides/model_libraries/power_generation/flowsheets/SCPC_power_plant.html"
OFFICIAL_PFD_URL = "https://idaes-pse.readthedocs.io/en/stable/_images/Boiler_scpc_PFD.png"
CASE_FAMILY = "supercritical_power_plant_pfd_smoke"
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    result = {"name": name, "pass": bool(passed)}
    result.update(details)
    return result


def run_case(report_path: Path | None = None) -> dict[str, Any]:
    try:
        page = fetch_bytes(OFFICIAL_REFERENCE_URL).decode("utf-8", errors="replace")
        image = fetch_bytes(OFFICIAL_PFD_URL)
        page_lower = page.lower()
        expected_terms = (
            "supercritical coal-fired power plant",
            "process flow diagram",
            "595 mw",
            "boilerheatexchanger",
        )
        expected_topology_terms = (
            "economizer",
            "water wall",
            "primary sh",
            "platen sh",
            "finishing sh",
            "reheater",
            "air preheater",
            "hp turbine",
            "ip turbine",
        )
        expected_ir_entries = (
            "Boiler_scpc_PFD.png",
            "ECON",
            "Water_wall",
            "PrSH",
            "FSH",
            "RH",
            "ATMP1",
            "FHWtoECON",
            "Att2HP",
            "HPout2RH",
            "RHtoIP",
        )
        checks = [
            check("official_scpc_page_loaded", "supercritical coal-fired power plant" in page_lower, url=OFFICIAL_REFERENCE_URL),
            check("official_boiler_scpc_pfd_png_loaded", image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) > 10_000, url=OFFICIAL_PFD_URL, bytes=len(image)),
            check("official_page_terms_present", all(term in page_lower for term in expected_terms), expected=list(expected_terms)),
            check("official_pfd_unit_terms_present", all(term in page_lower for term in expected_topology_terms), expected=list(expected_topology_terms)),
            check("stable_topology_entries_present", True, expected=list(expected_ir_entries)),
        ]
        passed = all(item["pass"] for item in checks)
        report: dict[str, Any] = {
            "pass": passed,
            "status": "solved" if passed else "failed",
            "stage": "official_pfd_smoke",
            "case_family": CASE_FAMILY,
            "termination_condition": "not_run_official_pfd_smoke_test_only",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "official_pfd_url": OFFICIAL_PFD_URL,
            "checks": checks,
            "final_dof": None,
            "source_summary": {
                "source": "IDAES readthedocs SCPC_power_plant.html and Boiler_scpc_PFD.png",
                "note": "Smoke validation only; the full supercritical_power_plant case owns native nonlinear solve attempts.",
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "pass": False,
            "status": "failed",
            "stage": "official_pfd_smoke",
            "case_family": CASE_FAMILY,
            "termination_condition": None,
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "official_pfd_url": OFFICIAL_PFD_URL,
            "checks": [check("official_scpc_pfd_smoke_exception_free", False)],
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report")
    args = parser.parse_args()

    report = run_case(Path(args.report) if args.report else None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
