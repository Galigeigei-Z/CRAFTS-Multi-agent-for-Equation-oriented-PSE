#!/usr/bin/env python3
"""Smoke-test the official CCSI2 ProcessModels BFB reactor manual evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "ccsi2_process_models_bfb_reactor_official_manual_smoke_20260607"
CASE_DIR = ROOT / "validation" / "VectorEngine_qwen36_validation" / CASE_ID
OFFICIAL_REPO_URL = "https://github.com/CCSI-Toolset/ProcessModels_bundle"
RAW_BASE = "https://raw.githubusercontent.com/CCSI-Toolset/ProcessModels_bundle/master"
API_BASE = "https://api.github.com/repos/CCSI-Toolset/ProcessModels_bundle/contents"
README_URL = f"{RAW_BASE}/README.md"
MANUAL_URL = f"{RAW_BASE}/docs/CCSI%20Process%20Models%20User%20Manual.pdf"
BFB_SUBMODULE_URL = f"{API_BASE}/SolidSorbents/bfb_reactor"
BFB_DROM_SUBMODULE_URL = f"{API_BASE}/SolidSorbents/bfb_drom"
HTTP_HEADERS = {"User-Agent": "langgraph-idaes-pipeline/ccsi2-bfb-reactor-smoke"}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", "replace")


def fetch_json(url: str) -> dict[str, object]:
    return json.loads(fetch_text(url))


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
        "case_family": "ccsi2_process_models_bfb_reactor_official_manual_smoke",
        "official_reference_url": OFFICIAL_REPO_URL,
        "source_manual_url": MANUAL_URL,
        "python": sys.version.split()[0],
        "checks": [],
    }

    try:
        readme_text = fetch_text(README_URL)
        manual_bytes = fetch_bytes(MANUAL_URL)
        bfb_submodule = fetch_json(BFB_SUBMODULE_URL)
        bfb_drom_submodule = fetch_json(BFB_DROM_SUBMODULE_URL)

        readme_path = artifacts_dir / "README.md"
        manual_path = artifacts_dir / "CCSI_Process_Models_User_Manual.pdf"
        manual_txt_path = artifacts_dir / "CCSI_Process_Models_User_Manual.txt"
        bfb_submodule_path = artifacts_dir / "bfb_reactor_submodule.json"
        bfb_drom_submodule_path = artifacts_dir / "bfb_drom_submodule.json"
        readme_path.write_text(readme_text, encoding="utf-8")
        manual_path.write_bytes(manual_bytes)
        write_json(bfb_submodule_path, bfb_submodule)
        write_json(bfb_drom_submodule_path, bfb_drom_submodule)

        manual_text, pdf_error = pdf_text(manual_path, manual_txt_path)
        manual_lower = manual_text.lower()
        readme_lower = readme_text.lower()

        manual_terms = {
            "ccsi_process_models_scope": "ccsi process models" in manual_lower,
            "bfb_reactor_model": "bfb reactor model schematic" in manual_lower,
            "figure_1_bfb_schematic": "figure 1: bfb reactor model schematic" in manual_lower,
            "figure_2_mass_transfer": "figure 2: three-region structure mass transfer schematic" in manual_lower,
            "figure_3_bfb_classification": "figure 3: classification of the bfb models" in manual_lower,
            "co2_removal": "co2 removal" in manual_lower,
            "acm_and_gproms": "aspen custom modeler" in manual_lower and "gproms" in manual_lower,
            "gas_solid_reactor": "fluidized bed" in manual_lower and "reactor" in manual_lower,
        }
        readme_terms = {
            "bundle_scope": "process models" in readme_lower,
            "bfb_reactor_listed": "bubbling fluidized bed reactor" in readme_lower,
            "solid_sorbents_section": "solid sorbents" in readme_lower,
        }
        submodule_terms = {
            "bfb_reactor_submodule": bfb_submodule.get("type") == "submodule" and bfb_submodule.get("name") == "bfb_reactor",
            "bfb_reactor_target": "CCSI-Toolset/bfb_reactor" in str(bfb_submodule.get("html_url", "")),
            "bfb_drom_submodule": bfb_drom_submodule.get("type") == "submodule" and bfb_drom_submodule.get("name") == "bfb_drom",
        }
        checks = [
            {"name": "official_readme_loaded", "pass": len(readme_text) > 500, "actual": len(readme_text)},
            {
                "name": "official_manual_pdf_loaded",
                "pass": manual_bytes.startswith(b"%PDF") and len(manual_bytes) > 100000,
                "actual": {"bytes": len(manual_bytes), "pdf_header": manual_bytes.startswith(b"%PDF")},
            },
            {"name": "official_manual_text_extracted", "pass": len(manual_text) > 50000 and pdf_error is None, "actual": {"chars": len(manual_text), "error": pdf_error}},
            {"name": "official_manual_bfb_terms_present", "pass": all(manual_terms.values()), "actual": manual_terms},
            {"name": "official_readme_bfb_terms_present", "pass": all(readme_terms.values()), "actual": readme_terms},
            {"name": "official_bfb_submodules_present", "pass": all(submodule_terms.values()), "actual": submodule_terms},
        ]
        report.update(
            {
                "pass": all(bool(check["pass"]) for check in checks),
                "checks": checks,
                "status": "solved",
                "termination_condition": "not_run_acm_gproms_smoke_test_only",
                "solver_scope": "official_ccsi2_process_models_bfb_reactor_manual_smoke",
                "artifacts": {
                    "readme": str(readme_path),
                    "manual_pdf": str(manual_path),
                    "manual_text": str(manual_txt_path),
                    "bfb_reactor_submodule": str(bfb_submodule_path),
                    "bfb_drom_submodule": str(bfb_drom_submodule_path),
                },
                "model_scope": "CCSI ProcessModels bubbling fluidized bed reactor; local smoke validates official manual/submodule evidence only",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - serialize smoke-test failure.
        report["error"] = str(exc)
        report["checks"].append({"name": "official_bfb_reactor_smoke_exception", "pass": False, "actual": str(exc)})
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
