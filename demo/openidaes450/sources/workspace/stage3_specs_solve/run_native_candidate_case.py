#!/usr/bin/env python3
"""Execute promoted TopologyIR, SpecIR, and BuildPlanIR as the native v3 input."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler.compile import validate_build_plan  # noqa: E402
from orchestrator.runtime_environment import runtime_environment  # noqa: E402


CANDIDATE_RUNNER_CONTRACT_VERSION = "native-candidate-runner/1"
NON_SEMANTIC_PLAN_KEYS = {
    "schema_version",
    "case_id",
    "family",
    "source_url",
    "source_topology_sha256",
    "source_spec_sha256",
    "specification_source",
    "compiler",
    "plan_sha256",
    "units",
    "arcs",
    "feed_specs",
    "unit_specs",
}


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pre_solve_binding(
    topology_path: Path,
    spec_path: Path,
    plan_path: Path,
    topology: dict[str, Any],
    spec: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_build_plan(plan)
    if errors:
        raise ValueError("invalid promoted BuildPlanIR: " + "; ".join(errors))
    topology_sha = _canonical_sha256(topology)
    spec_sha = _canonical_sha256(spec)
    plan_sha = _canonical_sha256({key: value for key, value in plan.items() if key != "plan_sha256"})
    if plan.get("source_topology_sha256") != topology_sha:
        raise ValueError("BuildPlanIR is not bound to the promoted TopologyIR")
    if plan.get("source_spec_sha256") != spec_sha:
        raise ValueError("BuildPlanIR is not bound to the promoted SpecIR")
    if plan.get("plan_sha256") != plan_sha:
        raise ValueError("BuildPlanIR plan_sha256 differs from its semantic bytes")
    plan_specs = [*(plan.get("feed_specs") or []), *(plan.get("unit_specs") or [])]
    spec_rows = spec.get("specs") or []

    def keyed(rows: list[Any], label: str) -> dict[tuple[str, str], str]:
        result: dict[tuple[str, str], str] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{label}[{index}] must be an object")
            key = (str(row.get("target") or ""), str(row.get("variable") or ""))
            if not all(key):
                raise ValueError(f"{label}[{index}] has an empty specification key")
            if key in result:
                raise ValueError(f"{label} duplicates specification key {key!r}")
            result[key] = _canonical_sha256(row)
        return result

    # The compiler groups feed and unit specifications into separate BuildPlan
    # sections.  Order is therefore non-semantic; exact unique keys and the
    # canonical bytes at each key remain mandatory.
    if keyed(plan_specs, "BuildPlanIR specifications") != keyed(
        spec_rows, "promoted SpecIR specifications"
    ):
        raise ValueError("BuildPlanIR specifications differ from promoted SpecIR")
    return {
        "schema_version": "native-candidate-pre-solve-binding/1",
        "runner_contract_version": CANDIDATE_RUNNER_CONTRACT_VERSION,
        "topology_file_sha256": _file_sha256(topology_path),
        "spec_file_sha256": _file_sha256(spec_path),
        "build_plan_file_sha256": _file_sha256(plan_path),
        "topology_sha256": topology_sha,
        "spec_sha256": spec_sha,
        "build_plan_sha256": plan_sha,
        "units": plan.get("units") or [],
        "arcs": plan.get("arcs") or [],
        "specifications": spec.get("specs") or [],
        "semantic_sections": {
            key: value for key, value in plan.items() if key not in NON_SEMANTIC_PLAN_KEYS
        },
        "generated_before_solve": True,
    }


def _candidate_binding(
    pre: dict[str, Any],
    report: dict[str, Any],
    pre_path: Path,
    consumed_spec_keys: set[tuple[str, str]],
    looked_up_spec_keys: set[tuple[str, str]],
) -> dict[str, Any]:
    match = report.get("template_match_audit")
    match = match if isinstance(match, dict) else {}
    mapping = match.get("candidate_to_template_unit_mapping")
    mapping = mapping if isinstance(mapping, dict) else {}
    explicit_required = report.get("requires_explicit_native_topology_binding") is True
    native_probe = report.get("native_topology_binding")
    native_probe = native_probe if isinstance(native_probe, dict) else {}
    probed_units = native_probe.get("units")
    probed_units = probed_units if isinstance(probed_units, dict) else {}
    probed_arcs = native_probe.get("arcs")
    probed_arcs = probed_arcs if isinstance(probed_arcs, dict) else {}
    expected_unit_ids = {
        str(row.get("id") or "") for row in pre["units"] if isinstance(row, dict)
    }
    expected_arc_ids = {
        str(row.get("id") or "") for row in pre["arcs"] if isinstance(row, dict)
    }
    explicit_topology_exact = (
        not explicit_required
        or (
            native_probe.get("schema_version") == "native-topology-probe/1"
            and native_probe.get("passed") is True
            and set(probed_units) == expected_unit_ids
            and set(probed_arcs) == expected_arc_ids
        )
    )
    units = []
    for row in pre["units"]:
        candidate_id = str(row.get("id") or "")
        native_id = str(mapping.get(candidate_id) or candidate_id)
        probe = probed_units.get(candidate_id)
        probe = probe if isinstance(probe, dict) else {}
        units.append(
            {
                "candidate_id": candidate_id,
                "model_component": (
                    str(probe.get("model_component") or "")
                    if explicit_required
                    else f"fs.{native_id}"
                ),
                "candidate_record_sha256": _canonical_sha256(row),
                "consumed": report.get("pass") is True and (
                    not explicit_required or probe.get("exists") is True
                ),
            }
        )
    arcs = []
    for row in pre["arcs"]:
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        destination = row.get("destination") if isinstance(row.get("destination"), dict) else {}
        source_unit = str(mapping.get(source.get("unit")) or source.get("unit") or "")
        destination_unit = str(
            mapping.get(destination.get("unit")) or destination.get("unit") or ""
        )
        candidate_id = str(row.get("id") or "")
        probe = probed_arcs.get(candidate_id)
        probe = probe if isinstance(probe, dict) else {}
        arcs.append(
            {
                "candidate_id": candidate_id,
                "model_connection": (
                    str(probe.get("model_connection") or "")
                    if explicit_required
                    else (
                        f"fs.{source_unit}.{source.get('port')}->"
                        f"fs.{destination_unit}.{destination.get('port')}"
                    )
                ),
                "candidate_record_sha256": _canonical_sha256(row),
                "consumed": report.get("pass") is True and (
                    not explicit_required
                    or (
                        probe.get("source_exists") is True
                        and probe.get("destination_exists") is True
                    )
                ),
            }
        )
    specifications = []
    for index, row in enumerate(pre["specifications"]):
        target = str(row.get("target") or "")
        target_unit, separator, suffix = target.partition(".")
        native_target = str(mapping.get(target_unit) or target_unit)
        mapped_target = f"{native_target}.{suffix}" if separator else native_target
        spec_key = (str(row.get("target") or ""), str(row.get("variable") or ""))
        specifications.append(
            {
                "candidate_index": index,
                "target": row.get("target"),
                "variable": row.get("variable"),
                "applied_value": row.get("value"),
                "applied_units": row.get("units"),
                "model_variable": f"fs.{mapped_target}.{row.get('variable')}",
                "candidate_record_sha256": _canonical_sha256(row),
                "consumed": spec_key in consumed_spec_keys,
            }
        )
    semantic_sections = [
        {
            "json_pointer": f"{chr(47)}{key}",
            "candidate_section_sha256": _canonical_sha256(value),
            "native_evidence": (
                f"solver_scope={report.get('solver_scope')};"
                f"template_match={match.get('mode')}"
            ),
            "consumed": report.get("pass") is True,
        }
        for key, value in pre["semantic_sections"].items()
    ]
    fingerprint_input = {
        "solver_scope": report.get("solver_scope"),
        "template_match_audit": match,
        "units": units,
        "arcs": arcs,
    }
    declared_spec_keys = {
        (str(row.get("target") or ""), str(row.get("variable") or ""))
        for row in pre["specifications"]
    }
    defaulted_spec_keys = looked_up_spec_keys - consumed_spec_keys
    exact_spec_boundary = (
        declared_spec_keys == looked_up_spec_keys
        and declared_spec_keys == consumed_spec_keys
    )
    return {
        "schema_version": "native-candidate-binding/1",
        "runner_contract_version": CANDIDATE_RUNNER_CONTRACT_VERSION,
        **{
            key: pre[key]
            for key in (
                "topology_file_sha256",
                "spec_file_sha256",
                "build_plan_file_sha256",
                "topology_sha256",
                "spec_sha256",
                "build_plan_sha256",
            )
        },
        "pre_solve_binding_file_sha256": _file_sha256(pre_path),
        "runner_sha256": _file_sha256(Path(__file__)),
        "runtime_environment_sha256": runtime_environment()["environment_sha256"],
        "native_model_fingerprint_sha256": _canonical_sha256(fingerprint_input),
        "solver_input_fingerprint_sha256": _canonical_sha256(pre),
        "units": units,
        "arcs": arcs,
        "specifications": specifications,
        "semantic_sections": semantic_sections,
        "generated_before_solve": pre.get("generated_before_solve") is True,
        "all_candidate_values_applied_before_solve": all(
            row["consumed"] for row in specifications
        ),
        "promoted_specification_count": len(specifications),
        "solver_spec_lookup_keys": [list(key) for key in sorted(looked_up_spec_keys)],
        "defaulted_solver_spec_lookup_keys": [list(key) for key in sorted(defaulted_spec_keys)],
        "all_solver_spec_lookups_declared": looked_up_spec_keys == declared_spec_keys,
        "exact_specification_boundary": exact_spec_boundary,
        "explicit_native_topology_binding_required": explicit_required,
        "explicit_native_topology_binding_exact": explicit_topology_exact,
        "native_topology_probe_schema_version": native_probe.get("schema_version"),
        "unmapped_promoted_fields": [],
    }


def run_candidate_case(
    topology_ir: str,
    spec_ir: str,
    build_plan: str,
    *,
    execution_protocol: str = "manuscript-full-workflow/v3",
) -> dict[str, Any]:
    """Run one candidate-bound native model; the signature is a frozen contract."""

    topology_path, spec_path, plan_path = map(Path, (topology_ir, spec_ir, build_plan))
    topology, spec, plan = map(_object, (topology_path, spec_path, plan_path))
    pre = _pre_solve_binding(topology_path, spec_path, plan_path, topology, spec, plan)
    pre_path = plan_path.parent / "native_candidate_pre_solve_binding.json"
    pre_path.write_text(json.dumps(pre, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    from sandbox_solver.solve_build_plan import (  # noqa: PLC0415
        begin_spec_consumption_audit,
        end_spec_consumption_audit_details,
        solve_plan,
    )

    runtime_plan = dict(plan)
    runtime_plan["build_plan_path"] = str(plan_path.resolve())
    begin_spec_consumption_audit()
    try:
        report = solve_plan(runtime_plan)
    finally:
        spec_audit = end_spec_consumption_audit_details()
    if not isinstance(report, dict):
        raise TypeError("candidate solver did not return an object report")
    report["template_match_audit"] = runtime_plan.get("_template_match_audit")
    report["candidate_binding"] = _candidate_binding(
        pre,
        report,
        pre_path,
        spec_audit["consumed"],
        spec_audit["looked_up"],
    )
    if report.get("pass") is True and not report["candidate_binding"][
        "exact_specification_boundary"
    ]:
        report["pass"] = False
        report["error"] = {
            "message": "native solver specification lookups differ from the promoted ChE contract"
        }
    if report.get("pass") is True and not report["candidate_binding"][
        "explicit_native_topology_binding_exact"
    ]:
        report["pass"] = False
        report["error"] = {
            "message": "native topology probe does not exactly cover promoted units and arcs"
        }
    report["execution_protocol"] = execution_protocol
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology-ir", required=True)
    parser.add_argument("--spec-ir", required=True)
    parser.add_argument("--build-plan", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--execution-protocol",
        default="manuscript-full-workflow/v3",
        choices=("manuscript-full-workflow/v3", "manuscript-full-workflow/v4"),
    )
    args = parser.parse_args()
    try:
        report = run_candidate_case(
            args.topology_ir,
            args.spec_ir,
            args.build_plan,
            execution_protocol=args.execution_protocol,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "pass": False,
            "stage": "native_candidate_solve",
            "candidate_binding": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") is True else 1)


if __name__ == "__main__":
    main()
