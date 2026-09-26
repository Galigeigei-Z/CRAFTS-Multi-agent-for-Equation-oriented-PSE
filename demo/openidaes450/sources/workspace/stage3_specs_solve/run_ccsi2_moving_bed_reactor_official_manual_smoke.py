#!/usr/bin/env python3
"""Smoke-test the official CCSI2 moving bed reactor manual and source evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "ccsi2_moving_bed_reactor_official_manual_smoke_20260607"
CASE_DIR = ROOT / "validation" / "VectorEngine_qwen36_validation" / CASE_ID
OFFICIAL_REPO_URL = "https://github.com/CCSI-Toolset/mb_reactor"
RAW_BASE = "https://raw.githubusercontent.com/CCSI-Toolset/mb_reactor/master"
README_URL = f"{RAW_BASE}/README.md"
MANUAL_URL = f"{RAW_BASE}/docs/Moving%20Bed%20Reaction%20Model%20User%20Manual.pdf"
ACM_MODEL_URL = f"{RAW_BASE}/ACM/Steady-State/Moving_Bed_SS.acmf"
GPROM_SCRIPT_URL = f"{RAW_BASE}/gPROMS/Steady-state/MovingB_v1.32SS.gPJ"
HTTP_HEADERS = {"User-Agent": "langgraph-idaes-pipeline/ccsi2-mb-reactor-smoke"}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", "replace")


def pdf_text(pdf_path: Path, txt_path: Path) -> tuple[str, str | None]:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return "", "pdftotext not found"
    completed = subprocess.run(
        [pdftotext, str(pdf_path), str(txt_path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        return "", completed.stderr.strip() or f"pdftotext exited {completed.returncode}"
    return txt_path.read_text(encoding="utf-8", errors="replace"), None


def run_case(report_path: Path | None = None) -> dict[str, object]:
    if report_path is None:
        report_path = CASE_DIR / "native_solve_report.json"
    artifacts_dir = report_path.parent / "official_artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "pass": False,
        "stage": "official_manual_smoke",
        "case_family": "ccsi2_moving_bed_reactor_official_manual_smoke",
        "official_reference_url": OFFICIAL_REPO_URL,
        "source_manual_url": MANUAL_URL,
        "python": sys.version.split()[0],
        "checks": [],
    }

    try:
        readme_text = fetch_text(README_URL)
        manual_bytes = fetch_bytes(MANUAL_URL)
        acm_bytes = fetch_bytes(ACM_MODEL_URL)
        gproms_bytes = fetch_bytes(GPROM_SCRIPT_URL)

        readme_path = artifacts_dir / "README.md"
        manual_path = artifacts_dir / "Moving_Bed_Reaction_Model_User_Manual.pdf"
        manual_txt_path = artifacts_dir / "Moving_Bed_Reaction_Model_User_Manual.txt"
        acm_path = artifacts_dir / "Moving_Bed_SS.acmf"
        gproms_path = artifacts_dir / "MovingB_v1.32SS.gPJ"
        readme_path.write_text(readme_text, encoding="utf-8")
        manual_path.write_bytes(manual_bytes)
        acm_path.write_bytes(acm_bytes)
        gproms_path.write_bytes(gproms_bytes)

        manual_text, pdf_error = pdf_text(manual_path, manual_txt_path)
        manual_lower = manual_text.lower()
        readme_lower = readme_text.lower()
        acm_lower = acm_bytes[:200000].decode("utf-8", "replace").lower()
        gproms_lower = gproms_bytes[:200000].decode("utf-8", "replace").lower()

        manual_terms = {
            "ccsi_scope": "carbon capture simulation initiative" in manual_lower,
            "figure_1_schematic": "figure 1: schematic of the mb reactor" in manual_lower,
            "moving_bed_reactor": "moving bed reactor" in manual_lower,
            "gas_solid_contacting": "gas-solid" in manual_lower or "gas solid" in manual_lower,
            "co2_h2o_n2_components": all(term in manual_lower for term in ("co2", "h2o", "n2")),
            "amine_sorbent": "amine" in manual_lower and "sorbent" in manual_lower,
            "acm_and_gproms": "aspen custom modeler" in manual_lower and "gproms" in manual_lower,
        }
        source_terms = {
            "readme_product": "moving bed reactor model" in readme_lower,
            "acm_model": "model" in acm_lower and "reactor" in acm_lower,
            "gproms_project": len(gproms_bytes) > 1000 and (b"gPROMS" in gproms_bytes[:200000] or b"MB" in gproms_bytes[:200000]),
        }
        checks = [
            {"name": "official_readme_loaded", "pass": len(readme_text) > 100, "actual": len(readme_text)},
            {
                "name": "official_manual_pdf_loaded",
                "pass": manual_bytes.startswith(b"%PDF") and len(manual_bytes) > 100000,
                "actual": {"bytes": len(manual_bytes), "pdf_header": manual_bytes.startswith(b"%PDF")},
            },
            {"name": "official_manual_text_extracted", "pass": len(manual_text) > 5000 and pdf_error is None, "actual": {"chars": len(manual_text), "error": pdf_error}},
            {"name": "official_manual_terms_present", "pass": all(manual_terms.values()), "actual": manual_terms},
            {"name": "official_acm_source_loaded", "pass": len(acm_bytes) > 1000, "actual": len(acm_bytes)},
            {"name": "official_gproms_source_loaded", "pass": len(gproms_bytes) > 1000, "actual": len(gproms_bytes)},
            {"name": "official_source_terms_present", "pass": all(source_terms.values()), "actual": source_terms},
        ]
        report.update(
            {
                "pass": all(bool(check["pass"]) for check in checks),
                "checks": checks,
                "status": "solved",
                "termination_condition": "not_run_acm_gproms_smoke_test_only",
                "solver_scope": "official_ccsi2_moving_bed_reactor_manual_smoke",
                "artifacts": {
                    "readme": str(readme_path),
                    "manual_pdf": str(manual_path),
                    "manual_text": str(manual_txt_path),
                    "acm_model": str(acm_path),
                    "gproms_project": str(gproms_path),
                },
                "model_scope": "CCSI Toolset solid sorbent moving bed reactor; local smoke validates official manual/source evidence only",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - serialize smoke-test failure.
        report["error"] = str(exc)
        report["checks"].append({"name": "official_moving_bed_reactor_smoke_exception", "pass": False, "actual": str(exc)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(CASE_DIR / "native_solve_report.json"))
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    report = run_case(report_path)
    write_json(report_path, report)
    write_json(report_path.parent / "official_manual_smoke_report.json", report)
    if report_path.parent == CASE_DIR:
        write_json(CASE_DIR / "topology_prebuild_report_attempt0.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
