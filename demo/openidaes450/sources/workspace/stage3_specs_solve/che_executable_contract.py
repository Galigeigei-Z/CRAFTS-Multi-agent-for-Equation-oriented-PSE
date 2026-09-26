#!/usr/bin/env python3
"""Deterministic ChE contract between a promoted topology and executable SpecIR.

The case-assisted route is reconstruction, not free-form variable invention.  Its
promoted TopologyIR already declares the simulator-facing inputs.  This module
turns those declarations into an immutable, role-visible contract and rejects a
SpecIR candidate before compilation when it adds, drops, renames, duplicates, or
dimensionally changes an executable input.
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import networkx as nx


SCHEMA_VERSION = "che-executable-contract/1"
REGISTRY_PATH = Path(__file__).with_name("che_adapter_contracts.json")


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _spec_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("target") or ""), str(row.get("variable") or "")


@lru_cache(maxsize=1)
def _adapter_registry() -> dict[str, Any]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "che-native-adapter-contract-registry/1":
        raise ValueError("unsupported ChE native-adapter contract registry")
    contracts = payload.get("contracts")
    if not isinstance(contracts, dict):
        raise ValueError("ChE native-adapter contract registry requires contracts")
    return payload


def adapter_contract_resolution(case_id: str) -> dict[str, Any]:
    """Resolve one exact contract or one explicit, non-chained case alias."""

    registry = _adapter_registry()
    contracts = registry.get("contracts") or {}
    aliases = registry.get("aliases") or {}
    requested = str(case_id or "")
    canonical = str(aliases.get(requested) or requested)
    alias_valid = (
        requested not in aliases
        or (
            canonical != requested
            and canonical not in aliases
            and canonical in contracts
        )
    )
    declaration = contracts.get(canonical) if alias_valid else None
    return {
        "requested_case_id": requested,
        "canonical_contract_id": canonical if declaration is not None else None,
        "resolution": "explicit_alias" if requested in aliases else "exact",
        "alias_valid": alias_valid,
        "declaration": declaration if isinstance(declaration, dict) else None,
    }


def adapter_declaration(case_id: str) -> dict[str, Any] | None:
    value = adapter_contract_resolution(case_id)["declaration"]
    return value if isinstance(value, dict) else None


def _bound_adapter_resolution(
    topology_ir: dict[str, Any],
    contract_case_id: str | None,
    adapter_declaration_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the controller-bound case identity, never the artifact namespace.

    A standardized case-assisted run binds the suite case before model calls.  The
    promoted topology may legitimately retain an official short ``case_id`` (for
    example ``prommis_crusher_unit``), but that identifier must not replace the
    suite-owned adapter-contract identity.
    """

    topology_case_id = str(topology_ir.get("case_id") or "")
    requested = str(contract_case_id or topology_case_id)
    resolution = (
        {
            "requested_case_id": requested,
            "canonical_contract_id": requested,
            "resolution": "frozen_execution_adapter_snapshot",
            "alias_valid": True,
            "declaration": adapter_declaration_override,
        }
        if isinstance(adapter_declaration_override, dict)
        else adapter_contract_resolution(requested)
    )
    if contract_case_id and resolution.get("declaration") is None:
        raise ValueError(
            "controller-bound ChE contract identity has no current-tree adapter "
            f"declaration: {requested!r}"
        )
    return {**resolution, "topology_case_id": topology_case_id}


def _aligned_expected_dof(raw: Any) -> tuple[Any, bool, str]:
    """Canonicalize simulation branches while preserving explicit optimization mode."""

    if isinstance(raw, bool):
        raise ValueError("native adapter expected_dof must not be boolean")
    if isinstance(raw, int):
        if raw != 0:
            raise ValueError("native adapter simulation expected_dof must be zero")
        return raw, False, "integer_zero_final_dof"
    if isinstance(raw, str) and (
        raw.startswith("0 for simulation,")
        or raw == "0 for simulation and final integer-rounded optimization"
    ):
        return 0, True, "steady_state_simulation_branch"
    if raw == "optimization":
        return raw, False, "native_optimization_mode"
    raise ValueError(
        "native adapter expected_dof must be integer zero, explicit optimization "
        "mode, or an explicit '0 for simulation, ...' contract"
    )


def adapter_aligned_topology_ir(
    topology_ir: dict[str, Any],
    *,
    contract_case_id: str | None = None,
    adapter_declaration_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind executable recycle/tear metadata owned by the native adapter.

    The model remains responsible for reconstructing units and connections.  It
    does not own simulator-specific tear selection once the selected native
    adapter declares that structural requirement.
    """

    resolution = _bound_adapter_resolution(
        topology_ir, contract_case_id, adapter_declaration_override
    )
    declaration = resolution.get("declaration")
    # A missing recycle declaration means that the native adapter is acyclic.
    # Keep an explicit non-array value fail-closed so malformed registry entries
    # cannot silently disable a required recycle closure.
    required = declaration.get("recycle_arcs", []) if declaration else []
    if not isinstance(required, list):
        raise ValueError("native adapter recycle_arcs must be an array")
    aligned = json.loads(json.dumps(topology_ir))
    removed_embedded_specifications = sum(
        len(aligned.get(group) or [])
        for group in ("feed_specs", "unit_specs")
        if isinstance(aligned.get(group), list)
    )
    if declaration is not None:
        # Topology owns structure.  Once a current-tree executable adapter is
        # available, only the separately promoted SpecIR may own model inputs.
        # This also removes historical output-like rows from reference topology
        # records before compiler validation.
        aligned["feed_specs"] = []
        aligned["unit_specs"] = []
    raw_expected_dof: Any = None
    expected_dof_normalized = False
    expected_dof_policy = "not_declared"
    solve = aligned.get("solve")
    if declaration is not None and isinstance(solve, dict) and "expected_dof" in solve:
        raw_expected_dof = solve.get("expected_dof")
        if declaration.get("adapter") == "generic_che_conservation_v1":
            solve["expected_dof"] = 0
            expected_dof_normalized = raw_expected_dof != 0
            expected_dof_policy = "generic_conservation_zero_final_dof"
        else:
            (
                solve["expected_dof"],
                expected_dof_normalized,
                expected_dof_policy,
            ) = _aligned_expected_dof(raw_expected_dof)
    arcs = aligned.get("arcs") if isinstance(aligned.get("arcs"), list) else []
    by_id = {
        str(row.get("id") or ""): row
        for row in arcs
        if isinstance(row, dict) and row.get("id")
    }
    bound: list[str] = []
    tear_by_id = {
        str(row.get("arc_id") or ""): row
        for row in aligned.get("tear_streams", []) or []
        if isinstance(row, dict) and row.get("arc_id")
    }
    for index, requirement in enumerate(required):
        if not isinstance(requirement, dict):
            raise ValueError(f"native adapter recycle_arcs[{index}] must be an object")
        arc_id = str(requirement.get("arc_id") or "")
        arc = by_id.get(arc_id)
        if arc is None:
            raise ValueError(f"native adapter recycle arc is absent from promoted topology: {arc_id!r}")
        for endpoint in ("source", "destination"):
            expected = str(requirement.get(endpoint) or "")
            if str(arc.get(endpoint) or "") != expected:
                raise ValueError(
                    f"native adapter recycle arc {arc_id!r} {endpoint} differs: "
                    f"{arc.get(endpoint)!r} != {expected!r}"
                )
        arc["is_recycle"] = True
        arc["tear_candidate"] = True
        tear_by_id[arc_id] = {
            "arc_id": arc_id,
            "destination": arc["destination"],
            "method": str(requirement.get("tear_method") or "direct_substitution"),
            "reason": str(requirement.get("reason") or "native adapter recycle closure"),
        }
        bound.append(arc_id)
    if declaration and declaration.get("adapter") == "generic_che_conservation_v1":
        graph = nx.MultiDiGraph()
        graph.add_nodes_from(
            str(row.get("id") or "")
            for row in aligned.get("units") or []
            if isinstance(row, dict) and row.get("id")
        )
        for arc_id, arc in by_id.items():
            source = str(arc.get("source") or "").split(".", 1)[0]
            destination = str(arc.get("destination") or "").split(".", 1)[0]
            if arc.get("is_recycle") or arc.get("tear_candidate"):
                tear_by_id.setdefault(
                    arc_id,
                    {
                        "arc_id": arc_id,
                        "destination": arc.get("destination"),
                        "method": "direct_substitution",
                        "reason": "registered candidate recycle closure",
                    },
                )
                continue
            graph.add_edge(source, destination, key=arc_id)
        while True:
            try:
                cycle = nx.find_cycle(graph, orientation="original")
            except nx.NetworkXNoCycle:
                break
            cycle_ids = sorted(str(edge[2]) for edge in cycle)
            arc_id = cycle_ids[-1]
            arc = by_id[arc_id]
            arc["is_recycle"] = True
            arc["tear_candidate"] = True
            tear_by_id[arc_id] = {
                "arc_id": arc_id,
                "destination": arc["destination"],
                "method": "direct_substitution",
                "reason": "deterministic generic-adapter directed-cycle tear",
            }
            source = str(arc.get("source") or "").split(".", 1)[0]
            destination = str(arc.get("destination") or "").split(".", 1)[0]
            graph.remove_edge(source, destination, key=arc_id)
    aligned["tear_streams"] = list(tear_by_id.values())
    return aligned, {
        "schema_version": "che-structural-adapter-alignment/1",
        "topology_case_id": resolution["topology_case_id"],
        "requested_contract_case_id": resolution["requested_case_id"],
        "canonical_contract_id": resolution["canonical_contract_id"],
        "contract_resolution": resolution["resolution"],
        "adapter_qualified": declaration is not None,
        "native_adapter": declaration.get("adapter") if declaration else None,
        "required_recycle_arc_ids": [
            str(row.get("arc_id") or "") for row in required if isinstance(row, dict)
        ],
        "bound_recycle_arc_ids": bound,
        "model_controls_tear_selection": False,
        "executable_specification_owner": "promoted_spec_ir",
        "removed_embedded_topology_specification_count": (
            removed_embedded_specifications if declaration is not None else 0
        ),
        "expected_dof_policy": expected_dof_policy,
        "raw_expected_dof": raw_expected_dof,
        "aligned_expected_dof": (
            (aligned.get("solve") or {}).get("expected_dof")
            if isinstance(aligned.get("solve"), dict)
            else None
        ),
        "expected_dof_normalized": expected_dof_normalized,
        "passed": len(bound) == len(required),
    }


def adapter_aligned_spec_ir(
    topology_ir: dict[str, Any],
    baseline_spec_ir: dict[str, Any],
    *,
    contract_case_id: str | None = None,
    adapter_declaration_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Replace historical prompt rows with current native-adapter input declarations."""

    declaration = _bound_adapter_resolution(
        topology_ir, contract_case_id, adapter_declaration_override
    ).get("declaration")
    if declaration is None:
        return baseline_spec_ir, None
    unit_ids = {
        str(row.get("id") or "")
        for row in topology_ir.get("units", []) or []
        if isinstance(row, dict) and row.get("id")
    }
    process_scope_targets = declaration.get("process_scope_targets", []) if declaration else []
    if not isinstance(process_scope_targets, list) or any(
        not isinstance(target, str) or not target.strip()
        for target in process_scope_targets
    ):
        raise ValueError("native adapter process_scope_targets must be an array of names")
    allowed_targets = unit_ids | set(process_scope_targets) | {
        "system",
        "flowsheet",
        "optimization",
    }
    rows: list[dict[str, Any]] = []
    for index, packed in enumerate(declaration.get("specs") or []):
        if not isinstance(packed, list) or len(packed) != 4:
            raise ValueError(f"adapter declaration specs[{index}] must be [target, variable, value, units]")
        target, variable, value, units = packed
        roots = [part.strip().split(".", 1)[0] for part in str(target).split("/") if part.strip()]
        if not roots or any(root not in allowed_targets for root in roots):
            raise ValueError(
                f"adapter declaration specs[{index}] target is absent from promoted topology: {target!r}"
            )
        rows.append(
            {
                "target": str(target),
                "variable": str(variable),
                "value": value,
                "units": str(units),
                "role": "current-tree native adapter independent input",
                "source": "current_tree_native_adapter",
                "source_url": str(topology_ir.get("source_url") or "local://current-tree-native-adapter"),
            }
        )
    aligned = dict(baseline_spec_ir)
    aligned["specs"] = rows
    return aligned, declaration


def _execution_mode(declaration: dict[str, Any] | None) -> str:
    if not declaration:
        return "unqualified"
    explicit = str(declaration.get("execution_mode") or "")
    if explicit:
        return explicit
    return "candidate_parameterized"


def _value_domain(row: dict[str, Any]) -> dict[str, Any]:
    """Return conservative physical bounds without pretending to be a unit package."""

    value = row.get("value")
    variable = str(row.get("variable") or "").casefold()
    units = str(row.get("units") or "").casefold()
    if isinstance(value, bool):
        return {"type": "boolean"}
    domain: dict[str, Any] = {"type": "number", "finite": True}
    if units in {"frac", "fraction"} or any(
        token in variable
        for token in ("efficiency", "fraction", "recovery", "conversion", "porosity")
    ):
        domain.update(minimum=0.0, maximum=1.0)
    elif "temperature" in variable:
        domain.update(exclusive_minimum=0.0)
    elif "pressure" in variable and "deltap" not in variable:
        domain.update(exclusive_minimum=0.0)
    elif any(
        token in variable
        for token in ("flow", "volume", "area", "length", "width", "concentration", "conc_", "cell_pair_num", "cell_triplet_num", "number_columns")
    ):
        domain.update(minimum=0.0)
    if isinstance(value, int) and not isinstance(value, bool) and any(
        token in variable for token in ("_num", "number_", "stages", "columns")
    ):
        domain["integer"] = True
    return domain


def build_che_executable_contract(
    topology_ir: dict[str, Any],
    baseline_spec_ir: dict[str, Any],
    *,
    contract_case_id: str | None = None,
    adapter_declaration_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolution = _bound_adapter_resolution(
        topology_ir, contract_case_id, adapter_declaration_override
    )
    aligned_spec_ir, declaration = adapter_aligned_spec_ir(
        topology_ir,
        baseline_spec_ir,
        contract_case_id=contract_case_id,
        adapter_declaration_override=adapter_declaration_override,
    )
    unit_kinds = {
        str(row.get("id") or ""): str(row.get("kind") or "")
        for row in topology_ir.get("units", []) or []
        if isinstance(row, dict) and row.get("id")
    }
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, source in enumerate(aligned_spec_ir.get("specs", []) or []):
        if not isinstance(source, dict):
            raise ValueError(f"baseline specs[{index}] must be an object")
        key = _spec_key(source)
        if not all(key):
            raise ValueError(f"baseline specs[{index}] has an empty target or variable")
        if key in seen:
            raise ValueError(f"duplicate executable specification key: {key!r}")
        seen.add(key)
        target_root = key[0].split("/", 1)[0].split(".", 1)[0]
        rows.append(
            {
                "contract_id": f"S{index + 1:03d}",
                "target": key[0],
                "target_unit_kind": unit_kinds.get(target_root, "process_scope"),
                "variable": key[1],
                "units": str(source.get("units") or ""),
                "baseline_value": source.get("value"),
                "value_domain": _value_domain(source),
                "classification": (
                    "configuration_option"
                    if isinstance(source.get("value"), bool)
                    else "independent_model_input"
                ),
                "required_for_dof_closure": True,
            }
        )
    semantic = {
        "schema_version": SCHEMA_VERSION,
        "route": "case_assisted_reconstruction",
        "case_id": topology_ir.get("case_id"),
        "topology_case_id": resolution["topology_case_id"],
        "requested_contract_case_id": resolution["requested_case_id"],
        "canonical_contract_id": resolution["canonical_contract_id"],
        "contract_resolution": resolution["resolution"],
        "controller_identity_bound": bool(contract_case_id),
        "topology_sha256": _canonical_sha256(topology_ir),
        "baseline_spec_sha256": _canonical_sha256(aligned_spec_ir),
        "contract_authority": (
            "current_tree_native_adapter_declaration"
            if declaration is not None
            else "topology_declared_unqualified"
        ),
        "adapter_qualified": declaration is not None,
        "native_adapter": declaration.get("adapter") if declaration else None,
        "model_fidelity": declaration.get("model_fidelity") if declaration else None,
        "execution_mode": _execution_mode(declaration),
        "candidate_parameterized_evidence_eligible": bool(
            declaration
            and _execution_mode(declaration) == "candidate_parameterized"
            and rows
        ),
        "adapter_registry_file_sha256": hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest(),
        "selection_policy": "exact_required_key_set",
        "specifications": rows,
        "structural_invariants": {
            "recycle_arc_ids": sorted(
                str(row.get("id"))
                for row in topology_ir.get("arcs", []) or []
                if isinstance(row, dict) and row.get("is_recycle") and row.get("id")
            ),
            "tear_arc_ids": sorted(
                str(row.get("arc_id"))
                for row in topology_ir.get("tear_streams", []) or []
                if isinstance(row, dict) and row.get("arc_id")
            ),
            "expected_final_dof": (baseline_spec_ir.get("solve") or {}).get("expected_dof"),
        },
        "visibility": {
            "allowed_roles": ["specification", "debug"],
            "evaluator_gold_used": False,
            "legacy_runtime_artifact_used": False,
        },
    }
    return {**semantic, "contract_sha256": _canonical_sha256(semantic)}


def _validate_value(value: Any, domain: dict[str, Any], label: str) -> list[str]:
    if domain.get("type") == "boolean":
        return [] if isinstance(value, bool) else [f"{label} must be boolean"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{label} must be numeric"]
    numeric = float(value)
    errors: list[str] = []
    if domain.get("finite") and not math.isfinite(numeric):
        errors.append(f"{label} must be finite")
    if "minimum" in domain and numeric < float(domain["minimum"]):
        errors.append(f"{label} is below the physical minimum {domain['minimum']}")
    if "exclusive_minimum" in domain and numeric <= float(domain["exclusive_minimum"]):
        errors.append(f"{label} must be greater than {domain['exclusive_minimum']}")
    if "maximum" in domain and numeric > float(domain["maximum"]):
        errors.append(f"{label} is above the physical maximum {domain['maximum']}")
    if domain.get("integer") and not numeric.is_integer():
        errors.append(f"{label} must be an integer")
    return errors


def validate_spec_candidate_against_contract(
    candidate_specs: Any, contract: dict[str, Any]
) -> list[str]:
    if not isinstance(candidate_specs, list):
        return ["spec candidate must contain a specs list"]
    allowed_rows = contract.get("specifications") or []
    allowed = {_spec_key(row): row for row in allowed_rows if isinstance(row, dict)}
    received: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    for index, row in enumerate(candidate_specs):
        if not isinstance(row, dict):
            errors.append(f"specs[{index}] must be an object")
            continue
        key = _spec_key(row)
        if key in received:
            errors.append(f"specs[{index}] duplicates executable key {key!r}")
            continue
        received[key] = row
        expected = allowed.get(key)
        if expected is None:
            errors.append(f"specs[{index}] is not an executable contract key: {key!r}")
            continue
        if str(row.get("units") or "") != str(expected.get("units") or ""):
            errors.append(
                f"specs[{index}] units differ from executable contract for {key!r}: "
                f"{row.get('units')!r} != {expected.get('units')!r}"
            )
        errors.extend(
            _validate_value(row.get("value"), expected.get("value_domain") or {}, f"specs[{index}].value")
        )
    missing = sorted(set(allowed).difference(received))
    if missing:
        errors.append(f"missing required executable specification keys: {missing!r}")
    return errors


def materialize_spec_candidate_against_contract(
    candidate: dict[str, Any], contract: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize compiler-owned keys from model-owned contract values."""

    allowed_rows = [
        row for row in contract.get("specifications") or [] if isinstance(row, dict)
    ]
    by_id = {str(row.get("contract_id") or ""): row for row in allowed_rows}
    values = candidate.get("contract_values")
    source_format = "contract_values"
    received: dict[str, Any] = {}
    ignored_legacy_keys: list[list[str]] = []
    if isinstance(values, list):
        for index, row in enumerate(values):
            if not isinstance(row, dict):
                raise ValueError(f"contract_values[{index}] must be an object")
            contract_id = str(row.get("contract_id") or "")
            if contract_id not in by_id:
                raise ValueError(f"contract_values[{index}] has unknown contract_id {contract_id!r}")
            if contract_id in received:
                raise ValueError(f"contract_values[{index}] duplicates {contract_id!r}")
            if "value" not in row:
                raise ValueError(f"contract_values[{index}] must define value")
            received[contract_id] = row["value"]
    elif not allowed_rows:
        source_format = "deterministic_empty_contract"
    else:
        # Compatibility for a fine-tuned role that still emits the historical
        # full-row shape.  Identities outside the compiler contract are inert;
        # only exact contract keys contribute a value.
        source_format = "legacy_full_rows_exact_key_projection"
        specs = candidate.get("specs")
        if not isinstance(specs, list):
            raise ValueError("spec candidate must contain contract_values")
        contract_by_key = {_spec_key(row): row for row in allowed_rows}
        for index, row in enumerate(specs):
            if not isinstance(row, dict):
                raise ValueError(f"specs[{index}] must be an object")
            expected = contract_by_key.get(_spec_key(row))
            if expected is None:
                ignored_legacy_keys.append(list(_spec_key(row)))
                continue
            contract_id = str(expected["contract_id"])
            if contract_id in received:
                raise ValueError(f"specs[{index}] duplicates compiler contract key {contract_id!r}")
            if "value" not in row:
                raise ValueError(f"specs[{index}] must define value")
            received[contract_id] = row["value"]
    missing = sorted(set(by_id).difference(received))
    if missing:
        raise ValueError(f"missing compiler-owned contract values: {missing!r}")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for expected in allowed_rows:
        contract_id = str(expected["contract_id"])
        value = received[contract_id]
        errors.extend(
            _validate_value(
                value,
                expected.get("value_domain") or {},
                f"contract_values[{contract_id}].value",
            )
        )
        rows.append(
            {
                "target": expected["target"],
                "variable": expected["variable"],
                "value": value,
                "units": expected["units"],
                "role": f"model-selected value for compiler-owned {contract_id}",
                "source": "model_contract_value",
            }
        )
    if errors:
        raise ValueError("; ".join(errors))
    return rows, {
        "schema_version": "che-spec-value-materialization/1",
        "source_format": source_format,
        "compiler_owned_fields": ["target", "variable", "units"],
        "model_owned_fields": ["value"],
        "contract_ids": list(by_id),
        "ignored_legacy_keys": ignored_legacy_keys,
        "complete": len(received) == len(by_id),
    }


def model_visible_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Project only role-relevant executable declarations into the model prompt."""

    specifications = contract.get("specifications") or []
    fixed_official = contract.get("execution_mode") == "fixed_official_operating_point"
    return {
        "schema_version": contract.get("schema_version"),
        "contract_sha256": contract.get("contract_sha256"),
        "selection_policy": contract.get("selection_policy"),
        "contract_authority": contract.get("contract_authority"),
        "adapter_qualified": contract.get("adapter_qualified"),
        "native_adapter": contract.get("native_adapter"),
        "model_fidelity": contract.get("model_fidelity"),
        "execution_mode": contract.get("execution_mode"),
        "candidate_parameterized_evidence_eligible": contract.get(
            "candidate_parameterized_evidence_eligible"
        ),
        "instruction": (
            "Return contract_values as an empty array. This official operating-point contract has no model-selected numeric inputs."
            if fixed_official
            else "Return contract_values only, with every contract_id exactly once and a physically admissible value. "
            "The compiler owns target, variable, and units; do not reproduce or edit those identity fields."
        ),
        "specifications": specifications,
        "structural_invariants": contract.get("structural_invariants") or {},
    }
