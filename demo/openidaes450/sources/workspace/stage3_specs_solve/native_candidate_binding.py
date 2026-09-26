"""Production v3 audit proving a native solve consumed promoted artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _exact_consumed_mapping(
    records: Any,
    *,
    expected_ids: set[str],
    id_field: str,
    model_field: str,
) -> bool:
    if not isinstance(records, list):
        return False
    observed: list[str] = []
    model_objects: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            return False
        observed.append(str(record.get(id_field) or ""))
        model_objects.append(str(record.get(model_field) or ""))
        if record.get("consumed") is not True:
            return False
    return (
        set(observed) == expected_ids
        and len(observed) == len(expected_ids)
        and all(model_objects)
        and len(set(model_objects)) == len(model_objects)
    )


def _records_by_id(records: Any, id_field: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            return {}
        identifier = str(record.get(id_field) or "")
        if not identifier or identifier in result:
            return {}
        result[identifier] = record
    return result


def _record_hashes_match(
    expected_records: Any, binding_records: Any, *, expected_id: str, binding_id: str
) -> bool:
    if not isinstance(expected_records, list) or not isinstance(binding_records, list):
        return False
    if not expected_records or not binding_records:
        return expected_records == [] and binding_records == []
    expected = _records_by_id(expected_records, expected_id)
    observed = _records_by_id(binding_records, binding_id)
    if not expected or set(expected) != set(observed):
        return False
    return all(
        observed[identifier].get("candidate_record_sha256")
        == canonical_sha256(expected[identifier])
        and observed[identifier].get("consumed") is True
        for identifier in expected
    )


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


def audit_native_candidate_binding(
    topology_path: Path,
    spec_path: Path,
    build_plan_path: Path,
    solve_report_path: Path,
) -> dict[str, Any]:
    topology = _object(topology_path)
    spec = _object(spec_path)
    plan = _object(build_plan_path)
    solve = _object(solve_report_path)
    binding = solve.get("candidate_binding")
    binding = binding if isinstance(binding, dict) else {}

    topology_hash = canonical_sha256(topology)
    spec_hash = canonical_sha256(spec)
    plan_hash = str(plan.get("plan_sha256") or "")
    expected_units = {
        str(record.get("id") or "")
        for record in plan.get("units") or []
        if isinstance(record, dict)
    }
    expected_arcs = {
        str(record.get("id") or "")
        for record in plan.get("arcs") or []
        if isinstance(record, dict)
    }
    expected_specs = spec.get("specs") if isinstance(spec.get("specs"), list) else []
    plan_specs = [
        *(plan.get("feed_specs") if isinstance(plan.get("feed_specs"), list) else []),
        *(plan.get("unit_specs") if isinstance(plan.get("unit_specs"), list) else []),
    ]
    spec_mappings = binding.get("specifications")
    spec_mapping_valid = isinstance(spec_mappings, list) and len(spec_mappings) == len(
        expected_specs
    )
    if spec_mapping_valid:
        by_index = {
            record.get("candidate_index"): record
            for record in spec_mappings
            if isinstance(record, dict)
        }
        spec_mapping_valid = set(by_index) == set(range(len(expected_specs)))
        for index, expected in enumerate(expected_specs):
            record = by_index.get(index) or {}
            spec_mapping_valid = spec_mapping_valid and all(
                (
                    record.get("target") == expected.get("target"),
                    record.get("variable") == expected.get("variable"),
                    record.get("applied_value") == expected.get("value"),
                    record.get("applied_units") == expected.get("units"),
                    record.get("candidate_record_sha256") == canonical_sha256(expected),
                    bool(str(record.get("model_variable") or "")),
                    record.get("consumed") is True,
                )
            )

    expected_sections = {
        key: value
        for key, value in plan.items()
        if key not in NON_SEMANTIC_PLAN_KEYS
    }
    section_records = binding.get("semantic_sections")
    section_mapping_valid = isinstance(section_records, list)
    by_section = (
        {
            str(record.get("json_pointer") or ""): record
            for record in section_records
            if isinstance(record, dict)
        }
        if section_mapping_valid
        else {}
    )
    expected_pointers = {f"/{key}" for key in expected_sections}
    section_mapping_valid = (
        section_mapping_valid
        and len(by_section) == len(section_records)
        and set(by_section) == expected_pointers
    )
    if section_mapping_valid:
        section_mapping_valid = all(
            by_section[f"/{key}"].get("candidate_section_sha256")
            == canonical_sha256(value)
            and by_section[f"/{key}"].get("consumed") is True
            and bool(str(by_section[f"/{key}"].get("native_evidence") or ""))
            for key, value in expected_sections.items()
        )

    checks = {
        "binding_contract_version": binding.get("schema_version")
        == "native-candidate-binding/1"
        and binding.get("runner_contract_version") == "native-candidate-runner/1",
        "exact_input_file_bytes_bound": binding.get("topology_file_sha256")
        == file_sha256(topology_path)
        and binding.get("spec_file_sha256") == file_sha256(spec_path)
        and binding.get("build_plan_file_sha256") == file_sha256(build_plan_path),
        "runner_and_environment_bound": _digest(binding.get("runner_sha256"))
        and _digest(binding.get("runtime_environment_sha256")),
        "native_model_fingerprints_bound": _digest(
            binding.get("native_model_fingerprint_sha256")
        )
        and _digest(binding.get("solver_input_fingerprint_sha256")),
        "solve_passed": solve.get("pass") is True,
        "topology_hash_bound": plan.get("source_topology_sha256") == topology_hash
        and binding.get("topology_sha256") == topology_hash,
        "spec_hash_bound": plan.get("source_spec_sha256") == spec_hash
        and binding.get("spec_sha256") == spec_hash,
        "build_plan_hash_bound": bool(plan_hash)
        and canonical_sha256({key: value for key, value in plan.items() if key != "plan_sha256"})
        == plan_hash
        and binding.get("build_plan_sha256") == plan_hash,
        "all_units_bound_once": bool(expected_units)
        and "" not in expected_units
        and _exact_consumed_mapping(
            binding.get("units"),
            expected_ids=expected_units,
            id_field="candidate_id",
            model_field="model_component",
        ),
        "all_unit_records_bound_exactly": _record_hashes_match(
            plan.get("units"),
            binding.get("units"),
            expected_id="id",
            binding_id="candidate_id",
        ),
        "all_arcs_bound_once": "" not in expected_arcs
        and _exact_consumed_mapping(
            binding.get("arcs"),
            expected_ids=expected_arcs,
            id_field="candidate_id",
            model_field="model_connection",
        ),
        "all_arc_records_bound_exactly": _record_hashes_match(
            plan.get("arcs"),
            binding.get("arcs"),
            expected_id="id",
            binding_id="candidate_id",
        ),
        "all_specifications_applied": spec_mapping_valid,
        "build_plan_spec_records_match_promoted_spec": [canonical_sha256(record) for record in plan_specs]
        == [canonical_sha256(record) for record in expected_specs],
        "all_semantic_plan_sections_consumed": bool(expected_sections)
        and section_mapping_valid,
        "binding_precedes_solve": binding.get("generated_before_solve") is True,
        "candidate_values_applied_before_solve": binding.get(
            "all_candidate_values_applied_before_solve"
        )
        is True,
        "all_solver_spec_lookups_declared": binding.get(
            "all_solver_spec_lookups_declared"
        )
        is True,
        "no_solver_spec_defaults_used": binding.get(
            "defaulted_solver_spec_lookup_keys"
        )
        == [],
        "exact_specification_boundary": binding.get(
            "exact_specification_boundary"
        )
        is True,
        "explicit_native_topology_binding_exact_when_required": (
            binding.get("explicit_native_topology_binding_required") is not True
            or binding.get("explicit_native_topology_binding_exact") is True
        ),
        "no_unmapped_promoted_fields": binding.get("unmapped_promoted_fields") == [],
    }
    return {
        "schema_version": "native-candidate-binding-audit/1",
        "topology_sha256": topology_hash,
        "spec_sha256": spec_hash,
        "build_plan_sha256": plan_hash or None,
        "expected_unit_count": len(expected_units),
        "expected_arc_count": len(expected_arcs),
        "expected_specification_count": len(expected_specs),
        "checks": checks,
        "passed": all(checks.values()),
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
    }
