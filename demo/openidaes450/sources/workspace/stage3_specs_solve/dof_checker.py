#!/usr/bin/env python3
"""Deterministic pre-solve checks for native topology/spec IR."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from stage3_specs_solve.spec_ir_builder import validate_spec_ir  # noqa: E402


def check_dof_proxy(topology_ir: dict[str, Any], spec_ir: dict[str, Any]) -> dict[str, Any]:
    errors = validate_spec_ir(spec_ir)
    warnings: list[str] = []

    unit_ids = {unit.get("id") for unit in topology_ir.get("units", []) if isinstance(unit, dict)}
    terminal_ports = set(topology_ir.get("unconnected_feed_ports", [])) | set(topology_ir.get("unconnected_product_ports", []))
    topology_family = topology_ir.get("family")
    if spec_ir.get("family") != topology_family:
        errors.append(f"spec family {spec_ir.get('family')!r} does not match topology family {topology_family!r}")
    if spec_ir.get("case_id") != topology_ir.get("case_id"):
        errors.append(f"spec case_id {spec_ir.get('case_id')!r} does not match topology case_id {topology_ir.get('case_id')!r}")

    for index, spec in enumerate(spec_ir.get("specs", []) if isinstance(spec_ir.get("specs"), list) else []):
        target = spec.get("target")
        if not isinstance(target, str):
            continue
        unit_id = target.split(".", 1)[0]
        if "." in target and unit_id not in unit_ids and target not in terminal_ports:
            errors.append(f"specs[{index}] target unit is not declared in topology: {target}")
        if "." not in target and target not in unit_ids and target != str(topology_family).removeprefix("family_"):
            warnings.append(f"specs[{index}] target is a flowsheet-level pseudo target: {target}")

    solve = spec_ir.get("solve") if isinstance(spec_ir.get("solve"), dict) else {}
    expected_dof = solve.get("expected_dof")
    return {
        "pass": not errors,
        "stage": "dof_check",
        "kind": "dof_proxy",
        "case_id": spec_ir.get("case_id"),
        "family": spec_ir.get("family"),
        "spec_count": len(spec_ir.get("specs", [])) if isinstance(spec_ir.get("specs"), list) else None,
        "expected_dof": expected_dof,
        "errors": errors,
        "warnings": warnings,
        "note": "This is a deterministic pre-solve IR consistency check; authoritative DOF remains the family Stage-3 solve runner.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology-ir", required=True)
    parser.add_argument("--spec-ir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    topology_ir = json.loads(Path(args.topology_ir).read_text(encoding="utf-8"))
    spec_ir = json.loads(Path(args.spec_ir).read_text(encoding="utf-8"))
    report = check_dof_proxy(topology_ir, spec_ir)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
