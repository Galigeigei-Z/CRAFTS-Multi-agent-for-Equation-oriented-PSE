"""Candidate-bound NC v5 adapter over the stable current-tree IDAES runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback
from typing import Any

from compiler.nc_v5.spec_binding import build_pre_solve_binding
from orchestrator.nc_v5.state import canonical_json_sha256
from stage3_specs_solve.nc_v5.execution_binding import audit_post_solve_binding
from stage3_specs_solve.nc_v5.generic_conservation import solve_generic_candidate_conservation
from stage3_specs_solve.run_native_candidate_case import run_candidate_case


RUNNER_ID = "native_candidate_runner_v5"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _same_spec_boundary(native: dict[str, Any], promoted: list[dict[str, Any]]) -> bool:
    rows = [*(native.get("feed_specs") or []), *(native.get("unit_specs") or [])]
    def keyed(values: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
        return {
            (str(row.get("target") or ""), str(row.get("variable") or "")): canonical_json_sha256(row)
            for row in values
        }
    return keyed(rows) == keyed(promoted)


def _ordered_consumption(
    rows: object, expected_ids: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("stable native consumption ledger must be an array of objects")
    mapped = {str(row.get("candidate_id") or ""): row for row in rows}
    observed = [str(row.get("candidate_id") or "") for row in rows]
    if len(mapped) != len(rows) or set(mapped) != set(expected_ids):
        raise ValueError(
            f"stable native consumption identity differs: expected={expected_ids}, observed={observed}"
        )
    return [
        {"candidate_id": candidate_id, "consumed": mapped[candidate_id].get("consumed") is True}
        for candidate_id in expected_ids
    ]


def run_native_candidate_v5(
    topology_path: Path,
    spec_path: Path,
    build_plan_path: Path,
    adapter_contract_path: Path | None = None,
) -> dict[str, Any]:
    topology = _read(topology_path)
    spec = _read(spec_path)
    plan = _read(build_plan_path)
    pre = build_pre_solve_binding(topology, spec, plan)
    if not pre["passed"]:
        raise ValueError(f"v5 pre-solve binding failed: {pre['failed_checks']}")
    native_plan = plan.get("native_plan")
    if not isinstance(native_plan, dict):
        raise ValueError("BuildPlanIR has no bound native_plan")
    if native_plan.get("source_topology_sha256") != pre["topology_sha256"] or native_plan.get("source_spec_sha256") != pre["spec_sha256"]:
        raise ValueError("native_plan source hashes differ from promoted inputs")
    if not _same_spec_boundary(native_plan, plan["spec_records"]):
        raise ValueError("native_plan specification boundary differs from SpecIR")

    pre_path = build_plan_path.parent / "pre_solve_binding.json"
    native_path = build_plan_path.parent / "native_build_plan.json"
    _write(pre_path, pre)
    _write(native_path, native_plan)
    adapter_contract = _read(adapter_contract_path) if adapter_contract_path else {}
    if adapter_contract.get("adapter") == "generic_che_conservation_v1":
        native = solve_generic_candidate_conservation(topology, spec, plan)
        native["execution_protocol"] = "manuscript-full-workflow/v5"
    else:
        native = run_candidate_case(
            str(topology_path), str(spec_path), str(native_path),
            execution_protocol="manuscript-full-workflow/v5",
        )
    old = native.get("candidate_binding")
    old = old if isinstance(old, dict) else {}
    binding = {
        "pre_solve_binding_sha256": canonical_json_sha256(pre),
        "runner_contract_version": "native-candidate-runner/v5",
        "runner_id": RUNNER_ID,
        "topology_sha256": pre["topology_sha256"],
        "spec_sha256": pre["spec_sha256"],
        "build_plan_sha256": pre["build_plan_sha256"],
        "units": _ordered_consumption(old.get("units"), pre["unit_ids"]),
        "arcs": _ordered_consumption(old.get("arcs"), pre["arc_ids"]),
        "specifications": [{"candidate_index": row["candidate_index"], "consumed": row.get("consumed") is True} for row in old.get("specifications") or []],
        "semantic_sections": [{"json_pointer": f"/{name}", "consumed": native.get("pass") is True} for name in pre["semantic_section_sha256"]],
        "generated_before_solve": old.get("generated_before_solve") is True,
        "all_candidate_values_applied_before_solve": old.get("all_candidate_values_applied_before_solve") is True,
        "unmapped_promoted_fields": old.get("unmapped_promoted_fields"),
    }
    report = {
        "schema_version": "native-solve-report/v5",
        "pass": native.get("pass") is True,
        "execution_protocol": "manuscript-full-workflow/v5",
        "candidate_binding": binding,
        "stable_native_report": native,
    }
    post = audit_post_solve_binding(pre, report)
    report["post_solve_binding"] = post
    report["pass"] = report["pass"] and post["passed"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology-ir", type=Path, required=True)
    parser.add_argument("--spec-ir", type=Path, required=True)
    parser.add_argument("--build-plan", type=Path, required=True)
    parser.add_argument("--adapter-contract", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_native_candidate_v5(
            args.topology_ir.resolve(),
            args.spec_ir.resolve(),
            args.build_plan.resolve(),
            args.adapter_contract.resolve() if args.adapter_contract else None,
        )
    except Exception as exc:  # noqa: BLE001
        report = {"schema_version": "native-solve-report/v5", "pass": False, "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]}}
    _write(args.report.resolve(), report)
    print(json.dumps({"passed": report.get("pass") is True, "report": str(args.report)}))
    return 0 if report.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
