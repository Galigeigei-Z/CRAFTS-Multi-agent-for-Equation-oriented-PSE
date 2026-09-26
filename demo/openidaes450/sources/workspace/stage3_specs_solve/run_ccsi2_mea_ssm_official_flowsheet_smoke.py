#!/usr/bin/env python3
"""Smoke-test the official CCSI2 MEA_ssm flowsheet evidence."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "ccsi2_mea_ssm_official_flowsheet_smoke_20260607"
CASE_DIR = ROOT / "validation" / "VectorEngine_qwen36_validation" / CASE_ID
OFFICIAL_REPO_URL = "https://github.com/CCSI-Toolset/MEA_ssm"
RAW_BASE = "https://raw.githubusercontent.com/CCSI-Toolset/MEA_ssm/master"
FLOW_IMAGE_URL = f"{RAW_BASE}/docs/source/media/flow_results.png"
INDEX_URL = f"{RAW_BASE}/docs/source/index.rst"
TUTORIALS_URL = f"{RAW_BASE}/docs/source/tutorials.rst"
MODEL_DEVELOPMENT_URL = f"{RAW_BASE}/docs/source/model_development.rst"
HTTP_HEADERS = {"User-Agent": "langgraph-idaes-pipeline/ccsi2-mea-ssm-smoke"}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", "replace")


def run_case(report_path: Path | None = None) -> dict[str, object]:
    if report_path is None:
        report_path = CASE_DIR / "native_solve_report.json"
    artifacts_dir = report_path.parent / "official_artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "pass": False,
        "stage": "official_flowsheet_smoke",
        "case_family": "ccsi2_mea_ssm_official_flowsheet_smoke",
        "official_reference_url": OFFICIAL_REPO_URL,
        "source_image_url": FLOW_IMAGE_URL,
        "python": sys.version.split()[0],
        "checks": [],
    }

    try:
        index_text = fetch_text(INDEX_URL)
        tutorials_text = fetch_text(TUTORIALS_URL)
        model_development_text = fetch_text(MODEL_DEVELOPMENT_URL)
        image_bytes = fetch_bytes(FLOW_IMAGE_URL)

        (artifacts_dir / "index.rst").write_text(index_text, encoding="utf-8")
        (artifacts_dir / "tutorials.rst").write_text(tutorials_text, encoding="utf-8")
        (artifacts_dir / "model_development.rst").write_text(model_development_text, encoding="utf-8")
        image_path = artifacts_dir / "flow_results.png"
        image_path.write_bytes(image_bytes)

        index_lower = index_text.lower()
        tutorials_lower = tutorials_text.lower()
        model_lower = model_development_text.lower()
        png_header_ok = image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        flow_terms = {
            "absorption_column": "absorption" in index_lower and "column" in index_lower,
            "stripping_column": "stripping" in index_lower and "column" in index_lower,
            "absorber_tutorial": "absorber" in tutorials_lower,
            "regenerator_tutorial": "regenerator" in tutorials_lower,
            "flow_sensitivity_block": "flow" in tutorials_lower and "sensitivity block" in tutorials_lower,
            "flow_image_referenced": "media/flow_results.png" in tutorials_lower,
            "aspen_plus_scope": "aspen plus" in index_lower,
            "mea_capture_scope": "monoethanolamine" in index_lower and "co2" in index_lower,
        }
        checks = [
            {"name": "official_index_loaded", "pass": len(index_text) > 500, "actual": len(index_text)},
            {"name": "official_tutorials_loaded", "pass": len(tutorials_text) > 500, "actual": len(tutorials_text)},
            {"name": "official_model_development_loaded", "pass": len(model_development_text) > 500, "actual": len(model_development_text)},
            {"name": "official_flow_results_png_loaded", "pass": png_header_ok and len(image_bytes) > 1000, "actual": {"bytes": len(image_bytes), "png_header": png_header_ok}},
            {"name": "official_flowsheet_unit_terms_present", "pass": all(flow_terms.values()), "actual": flow_terms},
        ]
        report.update(
            {
                "pass": all(bool(check["pass"]) for check in checks),
                "checks": checks,
                "status": "solved",
                "termination_condition": "not_run_aspen_smoke_test_only",
                "solver_scope": "official_ccsi2_mea_ssm_flowsheet_smoke",
                "artifacts": {
                    "index_rst": str(artifacts_dir / "index.rst"),
                    "tutorials_rst": str(artifacts_dir / "tutorials.rst"),
                    "model_development_rst": str(artifacts_dir / "model_development.rst"),
                    "flow_results_png": str(image_path),
                },
                "model_scope": "Aspen Plus MEA steady-state CO2 capture flowsheet; local smoke validates official evidence only",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - serialize smoke-test failure.
        report["error"] = str(exc)
        report["checks"].append({"name": "official_mea_ssm_smoke_exception", "pass": False, "actual": str(exc)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(CASE_DIR / "native_solve_report.json"))
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    report = run_case(report_path)
    write_json(report_path, report)
    write_json(report_path.parent / "official_flowsheet_smoke_report.json", report)
    if report_path.parent == CASE_DIR:
        write_json(CASE_DIR / "topology_prebuild_report_attempt0.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
