#!/usr/bin/env python3
"""Build a deterministic spec IR from a topology IR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUPPORTED_TOPOLOGY_SCHEMA = "topology_ir/1"
SPEC_SCHEMA = "spec_ir/1"
REQUIRED_SPEC_FIELDS = {"target", "variable", "value", "units", "role", "source", "source_url"}


def build_spec_ir(topology_ir: dict[str, Any]) -> dict[str, Any]:
    if topology_ir.get("schema_version") != SUPPORTED_TOPOLOGY_SCHEMA:
        raise ValueError(f"unsupported topology schema: {topology_ir.get('schema_version')!r}")

    specs: list[dict[str, Any]] = []
    for group_name in ("feed_specs", "unit_specs"):
        for spec in topology_ir.get(group_name, []) or []:
            specs.append(
                {
                    "target": spec["target"],
                    "variable": spec["variable"],
                    "value": spec["value"],
                    "units": spec["units"],
                    "role": spec.get("role", ""),
                    "source": "reference",
                    "source_url": topology_ir.get("source_url", ""),
                }
            )

    return {
        "schema_version": SPEC_SCHEMA,
        "case_id": topology_ir["case_id"],
        "family": topology_ir["family"],
        "source_url": topology_ir["source_url"],
        "topology_schema_version": topology_ir["schema_version"],
        "specs": specs,
        "terminal_feed_ports": topology_ir.get("unconnected_feed_ports", []),
        "terminal_product_ports": topology_ir.get("unconnected_product_ports", []),
        "translator_constraint_templates": topology_ir.get("translator_constraint_templates", {}),
        "initialization": topology_ir.get("initialization", {}),
        "solve": topology_ir.get("solve", {}),
    }


def validate_spec_ir(spec_ir: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if spec_ir.get("schema_version") != SPEC_SCHEMA:
        errors.append(f"unsupported spec schema: {spec_ir.get('schema_version')!r}")
    for field in ("case_id", "family", "source_url", "topology_schema_version"):
        if not isinstance(spec_ir.get(field), str) or not spec_ir.get(field):
            errors.append(f"{field} must be a non-empty string")
    specs = spec_ir.get("specs")
    if not isinstance(specs, list):
        errors.append("specs must be a list")
    else:
        for index, spec in enumerate(specs):
            if not isinstance(spec, dict):
                errors.append(f"specs[{index}] must be an object")
                continue
            missing = sorted(REQUIRED_SPEC_FIELDS - set(spec))
            if missing:
                errors.append(f"specs[{index}] missing fields: {missing}")
            for text_field in ("target", "variable", "units", "source", "source_url"):
                if text_field in spec and not isinstance(spec[text_field], str):
                    errors.append(f"specs[{index}].{text_field} must be a string")
    for field in ("terminal_feed_ports", "terminal_product_ports"):
        if not isinstance(spec_ir.get(field), list):
            errors.append(f"{field} must be a list")
    if not isinstance(spec_ir.get("initialization"), dict):
        errors.append("initialization must be an object")
    if not isinstance(spec_ir.get("solve"), dict):
        errors.append("solve must be an object")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topology_ir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    topology_path = Path(args.topology_ir)
    topology_ir = json.loads(topology_path.read_text(encoding="utf-8"))
    spec_ir = build_spec_ir(topology_ir)
    errors = validate_spec_ir(spec_ir)
    if errors:
        raise SystemExit("spec IR validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec_ir, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"schema_version": SPEC_SCHEMA, "spec_count": len(spec_ir["specs"])}, indent=2))


if __name__ == "__main__":
    main()
