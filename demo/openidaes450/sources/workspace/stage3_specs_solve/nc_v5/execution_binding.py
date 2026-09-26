"""Audit actual candidate consumption after the measured native solve."""

from __future__ import annotations

from typing import Any

from orchestrator.nc_v5.state import canonical_json_sha256


def _consumed_ids(rows: object, key: str) -> tuple[list[object], bool]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return [], False
    return [row.get(key) for row in rows], all(row.get("consumed") is True for row in rows)


def audit_post_solve_binding(
    pre_solve_binding: dict[str, Any], native_solve_report: dict[str, Any]
) -> dict[str, Any]:
    binding = native_solve_report.get("candidate_binding")
    if not isinstance(binding, dict):
        binding = {}
    units, units_consumed = _consumed_ids(binding.get("units"), "candidate_id")
    arcs, arcs_consumed = _consumed_ids(binding.get("arcs"), "candidate_id")
    specs, specs_consumed = _consumed_ids(binding.get("specifications"), "candidate_index")
    sections, sections_consumed = _consumed_ids(binding.get("semantic_sections"), "json_pointer")
    expected_sections = [
        f"/{name}" for name in pre_solve_binding.get("semantic_section_sha256", {})
    ]
    checks = {
        "pre_solve_binding_passed": pre_solve_binding.get("passed") is True,
        "pre_solve_binding_hash_exact": binding.get("pre_solve_binding_sha256")
        == canonical_json_sha256(pre_solve_binding),
        "runner_contract_exact": binding.get("runner_contract_version")
        == "native-candidate-runner/v5",
        "topology_hash_exact": binding.get("topology_sha256")
        == pre_solve_binding.get("topology_sha256"),
        "spec_hash_exact": binding.get("spec_sha256") == pre_solve_binding.get("spec_sha256"),
        "build_plan_hash_exact": binding.get("build_plan_sha256")
        == pre_solve_binding.get("build_plan_sha256"),
        "unit_identity_and_consumption_exact": units == pre_solve_binding.get("unit_ids")
        and units_consumed,
        "arc_identity_and_consumption_exact": arcs == pre_solve_binding.get("arc_ids")
        and arcs_consumed,
        "spec_identity_and_consumption_exact": specs
        == list(range(len(pre_solve_binding.get("spec_record_sha256", []))))
        and specs_consumed,
        "semantic_sections_consumed_exact": sections == expected_sections and sections_consumed,
        "generated_before_solve": binding.get("generated_before_solve") is True,
        "all_candidate_values_applied_before_solve": binding.get(
            "all_candidate_values_applied_before_solve"
        )
        is True,
        "unmapped_fields_absent": binding.get("unmapped_promoted_fields") == [],
        "native_solve_passed": native_solve_report.get("pass") is True,
    }
    return {
        "schema_version": "post-solve-binding/v5",
        "pre_solve_binding_sha256": canonical_json_sha256(pre_solve_binding),
        "runner_id": binding.get("runner_id"),
        "checks": checks,
        "passed": all(checks.values()),
        "failed_checks": sorted(name for name, passed in checks.items() if not passed),
    }
