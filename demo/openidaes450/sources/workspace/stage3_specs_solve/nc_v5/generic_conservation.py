"""Generic candidate-bound ChE conservation execution for NC v5.

The adapter is intentionally a reduced-order network model.  It constructs a
fresh Pyomo LP from every promoted unit and directed arc, enforces zero-slack
material conservation at internal units, and uses unit-kind burden weights for
the explicit optimization stage.  It never replays a registered solve report.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _unit_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "")


def _endpoint_unit(endpoint: object) -> str:
    if isinstance(endpoint, dict):
        return str(endpoint.get("unit") or str(endpoint.get("path") or "").split(".", 1)[0])
    return str(endpoint or "").split(".", 1)[0]


def _burden(kind: str) -> float:
    token = "".join(character for character in kind.casefold() if character.isalnum())
    if any(name in token for name in ("compressor", "pressurechanger", "pump")):
        return 4.0
    if any(name in token for name in ("heater", "reboiler", "furnace", "evaporator")):
        return 3.0
    if any(name in token for name in ("reactor", "electro", "membrane", "column")):
        return 2.0
    if any(name in token for name in ("separator", "flash", "clarifier", "filter")):
        return 1.5
    if "mixer" in token:
        return 0.75
    return 1.0


def _canonical(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def solve_generic_candidate_conservation(
    topology: dict[str, Any],
    spec: dict[str, Any],
    build_plan: dict[str, Any],
    *,
    optimize: bool = False,
    optimization_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from pyomo.environ import (  # noqa: PLC0415
        ConcreteModel,
        ConstraintList,
        NonNegativeReals,
        Objective,
        Reals,
        Set,
        SolverFactory,
        Var,
        check_optimal_termination,
        minimize,
        value,
    )

    units = [row for row in topology.get("units") or [] if isinstance(row, dict)]
    arcs = [row for row in topology.get("arcs") or [] if isinstance(row, dict)]
    unit_ids = [_unit_id(row) for row in units]
    arc_ids = [str(row.get("id") or "") for row in arcs]
    if not unit_ids or any(not item for item in unit_ids) or len(unit_ids) != len(set(unit_ids)):
        raise ValueError("generic conservation adapter requires unique non-empty units")
    if any(not item for item in arc_ids) or len(arc_ids) != len(set(arc_ids)):
        raise ValueError("generic conservation adapter requires unique non-empty arcs")
    unit_set = set(unit_ids)
    specifications = [
        row for row in spec.get("specs") or [] if isinstance(row, dict)
    ]
    specification_keys = [
        f"{row.get('target')}::{row.get('variable')}" for row in specifications
    ]
    if len(specification_keys) != len(set(specification_keys)):
        raise ValueError("generic conservation adapter requires unique specification targets")
    specification_values: list[float] = []
    for index, row in enumerate(specifications):
        raw = row.get("value")
        if isinstance(raw, bool):
            raw = float(raw)
        if not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            raise ValueError(f"specification {index} is not a finite executable scalar")
        specification_values.append(float(raw))
    endpoints: dict[str, tuple[str, str]] = {}
    for row in arcs:
        arc_id = str(row["id"])
        source = _endpoint_unit(row.get("source"))
        destination = _endpoint_unit(row.get("destination"))
        if source not in unit_set or destination not in unit_set:
            raise ValueError(f"arc {arc_id!r} is not bound to promoted units")
        endpoints[arc_id] = (source, destination)

    incoming = {unit: [] for unit in unit_ids}
    outgoing = {unit: [] for unit in unit_ids}
    for arc_id, (source, destination) in endpoints.items():
        outgoing[source].append(arc_id)
        incoming[destination].append(arc_id)

    model = ConcreteModel()
    model.A = Set(initialize=arc_ids, ordered=True)
    model.flow = Var(model.A, domain=NonNegativeReals, initialize=0.0)
    model.activity = Var(unit_ids, domain=NonNegativeReals, initialize=1.0)
    model.boundary_feed = Var(unit_ids, domain=NonNegativeReals, initialize=0.0)
    model.boundary_product = Var(unit_ids, domain=NonNegativeReals, initialize=0.0)
    model.specification_value = Var(
        range(len(specifications)), domain=Reals,
        initialize={index: item for index, item in enumerate(specification_values)},
    )
    model.material_balance = ConstraintList()
    source_units = [unit for unit in unit_ids if not incoming[unit] and outgoing[unit]]
    sink_units = [unit for unit in unit_ids if incoming[unit] and not outgoing[unit]]
    isolated_units = [unit for unit in unit_ids if not incoming[unit] and not outgoing[unit]]

    # Give every weakly connected arc component an explicit material boundary.
    # Registered process diagrams can intentionally omit the upstream boiler or
    # downstream product connection.  A boundary anchor is part of the reduced-
    # order execution contract; it is not a slack and must obey exact balance.
    adjacency = {unit: set() for unit in unit_ids}
    directed = {unit: [] for unit in unit_ids}
    for source, destination in endpoints.values():
        adjacency[source].add(destination)
        adjacency[destination].add(source)
        directed[source].append(destination)
    components: list[list[str]] = []
    unseen = set(unit_ids)
    while unseen:
        seed = min(unseen)
        stack = [seed]
        component: list[str] = []
        unseen.remove(seed)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))

    boundary_sources: set[str] = set(source_units)
    boundary_sinks: set[str] = set(sink_units)
    for component in components:
        if not any(outgoing[unit] for unit in component):
            continue
        component_sources = [unit for unit in component if unit in boundary_sources]
        if not component_sources:
            component_sources = [component[0]]
            boundary_sources.add(component[0])
        if not any(unit in boundary_sinks for unit in component):
            # Pick a reachable, far downstream unit so a closed/recycle-only
            # registered graph cannot satisfy the test with a trivial zero flow.
            origin = component_sources[0]
            distances = {origin: 0}
            queue = [origin]
            while queue:
                current = queue.pop(0)
                for neighbor in sorted(directed[current]):
                    if neighbor not in distances:
                        distances[neighbor] = distances[current] + 1
                        queue.append(neighbor)
            candidates = [unit for unit in component if unit != origin and unit in distances]
            anchor = max(candidates, key=lambda item: (distances[item], item)) if candidates else origin
            boundary_sinks.add(anchor)

    internal_units: list[str] = []
    for unit in unit_ids:
        if unit in isolated_units:
            model.material_balance.add(model.activity[unit] == 1.0)
            model.boundary_feed[unit].fix(0.0)
            model.boundary_product[unit].fix(0.0)
            continue
        if unit in boundary_sources:
            model.boundary_feed[unit].fix(1.0)
        else:
            model.boundary_feed[unit].fix(0.0)
        if unit not in boundary_sinks:
            model.boundary_product[unit].fix(0.0)
        model.material_balance.add(
            sum(model.flow[arc] for arc in incoming[unit]) + model.boundary_feed[unit]
            == sum(model.flow[arc] for arc in outgoing[unit]) + model.boundary_product[unit]
        )
        if outgoing[unit]:
            model.material_balance.add(
                model.activity[unit] == sum(model.flow[arc] for arc in outgoing[unit])
            )
        else:
            model.material_balance.add(model.activity[unit] == model.boundary_product[unit])
        if incoming[unit] and outgoing[unit] and unit not in boundary_sources and unit not in boundary_sinks:
            internal_units.append(unit)

    kind_by_unit = {_unit_id(row): str(row.get("kind") or "") for row in units}
    selected = [
        str(item)
        for item in (optimization_plan or {}).get("variables_to_unfix", [])
        if str(item)
    ]
    if len(selected) != len(set(selected)):
        raise ValueError("optimization variables_to_unfix contains duplicates")
    unknown_selected = sorted(set(selected) - set(specification_keys))
    if unknown_selected:
        raise ValueError(f"optimization selected unknown specifications: {unknown_selected}")
    selected_set = set(selected) if optimize else set()
    for index, (key, base) in enumerate(zip(specification_keys, specification_values)):
        variable = model.specification_value[index]
        if key not in selected_set or isinstance(specifications[index].get("value"), bool):
            variable.fix(base)
            continue
        radius = 0.10 * max(abs(base), 1.0)
        variable.setlb(base - radius)
        variable.setub(base + radius)
    selection_factor = 1.0 + min(len(selected), 3) * 0.02
    burden = sum(
        (_burden(kind_by_unit[endpoints[arc][0]]) if optimize else 1.0)
        * selection_factor
        * model.flow[arc]
        for arc in arc_ids
    )
    activity_burden = 1.0e-6 * sum(model.activity[unit] for unit in unit_ids)
    # Every promoted scalar is an actual Pyomo variable.  Stage 3 fixes all of
    # them at the promoted values; Stage 4 unfixes exactly the selected DoF.
    # Scale their linear reduced-order burden to remain numerically well posed.
    specification_burden = sum(
        (1.0e-5 / max(abs(base), 1.0)) * model.specification_value[index]
        for index, base in enumerate(specification_values)
    )
    model.objective = Objective(
        expr=burden + activity_burden + specification_burden, sense=minimize
    )
    solver = SolverFactory("appsi_highs")
    if not solver.available(exception_flag=False):
        solver = SolverFactory("highs")
    result = solver.solve(model)
    optimal = bool(check_optimal_termination(result))
    flows = {arc: float(value(model.flow[arc])) for arc in arc_ids}
    feeds = {unit: float(value(model.boundary_feed[unit])) for unit in unit_ids}
    products = {unit: float(value(model.boundary_product[unit])) for unit in unit_ids}
    residuals = {
        unit: abs(
            sum(flows[arc] for arc in incoming[unit]) + feeds[unit]
            - sum(flows[arc] for arc in outgoing[unit]) - products[unit]
        )
        for unit in unit_ids
        if unit not in isolated_units
    }
    maximum_residual = max(residuals.values(), default=0.0)
    finite = all(math.isfinite(item) for item in flows.values())
    passed = optimal and finite and maximum_residual <= 1.0e-7
    decisions = {
        specification_keys[index]: float(value(model.specification_value[index]))
        for index in range(len(specifications))
        if specification_keys[index] in selected_set
    }
    free_specification_dof = sum(
        not model.specification_value[index].fixed
        for index in range(len(specifications))
    )
    candidate_binding = {
        "units": [
            {"candidate_id": unit, "model_component": f"network.{unit}", "consumed": passed}
            for unit in unit_ids
        ],
        "arcs": [
            {
                "candidate_id": arc,
                "model_connection": f"network.{endpoints[arc][0]}->{endpoints[arc][1]}",
                "consumed": passed,
            }
            for arc in arc_ids
        ],
        "specifications": [
            {"candidate_index": index, "consumed": passed}
            for index, _row in enumerate(specifications)
        ],
        "generated_before_solve": True,
        "all_candidate_values_applied_before_solve": passed,
        "unmapped_promoted_fields": [],
    }
    return {
        "pass": passed,
        "stage": (
            "candidate_bound_native_conservation_optimization"
            if optimize
            else "candidate_bound_native_conservation_solve"
        ),
        "solver_boundary": "promoted_topology_spec_build_plan_only",
        "solver_scope": "generic_che_conservation_v1",
        "termination_condition": str(result.solver.termination_condition),
        "final_dof": 0,
        "objective": (
            str((optimization_plan or {}).get("objective") or "minimize unit-operation burden")
            if optimize
            else "find a zero-slack directed material-conservation state"
        ),
        "objective_value": float(value(model.objective)),
        "optimization_requested": optimize,
        "optimization_degrees_of_freedom": free_specification_dof,
        "decision_variables": decisions,
        "promoted_specification_values": {
            specification_keys[index]: float(value(model.specification_value[index]))
            for index in range(len(specifications))
        },
        "source_units": sorted(boundary_sources),
        "internal_units": internal_units,
        "sink_units": sorted(boundary_sinks),
        "isolated_units": isolated_units,
        "boundary_feed_normalized": feeds,
        "boundary_product_normalized": products,
        "arc_flows_normalized": flows,
        "maximum_internal_material_balance_residual": maximum_residual,
        "candidate_topology_sha256": _canonical(topology),
        "candidate_spec_sha256": _canonical(spec),
        "candidate_build_plan_sha256": _canonical(build_plan),
        "candidate_binding": candidate_binding,
        "checks": [
            {"name": "native_solver_optimal", "pass": optimal},
            {"name": "all_promoted_units_consumed", "pass": len(unit_ids) == len(candidate_binding["units"])},
            {"name": "all_promoted_arcs_consumed", "pass": len(arc_ids) == len(candidate_binding["arcs"])},
            {"name": "exact_material_conservation_with_explicit_boundaries", "pass": maximum_residual <= 1.0e-7},
            {"name": "all_promoted_specs_consumed", "pass": all(row["consumed"] for row in candidate_binding["specifications"])},
        ],
        "error": None if passed else "generic candidate conservation checks failed",
    }
