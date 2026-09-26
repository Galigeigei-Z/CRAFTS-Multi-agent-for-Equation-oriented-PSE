"""Probe candidate topology bindings against components on a live Pyomo model."""

from __future__ import annotations

from typing import Any


def probe_native_topology(
    model: Any,
    *,
    units: dict[str, str],
    arcs: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    unit_rows: dict[str, dict[str, Any]] = {}
    for candidate_id, component_path in units.items():
        exists = model.find_component(component_path) is not None
        unit_rows[candidate_id] = {
            "model_component": component_path,
            "exists": exists,
        }
    arc_rows: dict[str, dict[str, Any]] = {}
    for candidate_id, (source_path, destination_path) in arcs.items():
        source_exists = model.find_component(source_path) is not None
        destination_exists = model.find_component(destination_path) is not None
        arc_rows[candidate_id] = {
            "source_component": source_path,
            "destination_component": destination_path,
            "source_exists": source_exists,
            "destination_exists": destination_exists,
            "model_connection": f"{source_path}->{destination_path}",
        }
    passed = all(row["exists"] for row in unit_rows.values()) and all(
        row["source_exists"] and row["destination_exists"]
        for row in arc_rows.values()
    )
    return {
        "schema_version": "native-topology-probe/1",
        "units": unit_rows,
        "arcs": arc_rows,
        "passed": passed,
    }
