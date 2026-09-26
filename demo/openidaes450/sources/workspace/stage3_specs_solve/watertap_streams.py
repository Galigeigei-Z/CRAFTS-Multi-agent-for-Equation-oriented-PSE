"""Utilities for exporting WaterTAP stream values from solved Pyomo ports."""

from __future__ import annotations

from typing import Any


def _value(obj: Any) -> float | None:
    try:
        from pyomo.environ import value  # noqa: PLC0415

        return float(value(obj))
    except Exception:
        return None


def _is_time_index(value: Any) -> bool:
    return value in (0, 0.0, "0", "0.0")


def _component_label(index: Any) -> str:
    if isinstance(index, tuple):
        parts = list(index)
        if parts and _is_time_index(parts[0]):
            parts = parts[1:]
        return "/".join(str(part) for part in parts)
    if _is_time_index(index):
        return "value"
    return str(index)


def _var_entries(var: Any) -> dict[str, float]:
    entries: dict[str, float] = {}
    if getattr(var, "is_indexed", lambda: False)():
        for index in var:
            value = _value(var[index])
            if value is not None:
                entries[_component_label(index)] = value
    else:
        value = _value(var)
        if value is not None:
            entries["value"] = value
    return entries


def stream_from_port(port: Any) -> dict[str, Any]:
    """Return a JSON-safe stream record from a Pyomo/IDAES Port."""

    stream: dict[str, Any] = {}
    variables = getattr(port, "vars", None)
    if not isinstance(variables, dict):
        return stream

    scalar_names = {"temperature", "pressure", "flow_vol", "flow_mass", "flow_mol"}
    aggregate_names = {
        "flow_vol_phase",
        "flow_mass_comp",
        "flow_mass_phase_comp",
        "flow_mol_comp",
        "flow_mol_phase_comp",
    }
    for name, var in variables.items():
        if name in scalar_names:
            values = list(_var_entries(var).values())
            if values:
                target = {"flow_mass": "mass_flow", "flow_mol": "flow_mol", "flow_vol": "volumetric_flow"}.get(name, name)
                stream[target] = values[0]
            continue

        entries = _var_entries(var)
        if not entries:
            continue
        if len(entries) == 1 and "value" in entries and name not in aggregate_names:
            stream[name] = entries["value"]
        else:
            stream[name] = entries
        if name in {"flow_mass_comp", "flow_mass_phase_comp"}:
            stream["mass_flow"] = sum(entries.values())
            stream["flow_kg_s"] = stream["mass_flow"]
            total = stream["mass_flow"]
            if total:
                frac_key = "mass_frac_comp" if name == "flow_mass_comp" else "mass_frac_phase_comp"
                stream[frac_key] = {key: value / total for key, value in entries.items()}
        elif name in {"flow_mol_comp", "flow_mol_phase_comp"}:
            stream["flow_mol"] = sum(entries.values())
        elif name == "flow_vol_phase":
            stream["volumetric_flow"] = sum(entries.values())
            stream["flow_m3_s"] = stream["volumetric_flow"]

    return stream


def streams_from_arcs(model: Any, aliases: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Export all Pyomo network Arc source-port streams from a solved model."""

    from pyomo.network import Arc  # noqa: PLC0415

    streams: dict[str, dict[str, Any]] = {}
    aliases = aliases or {}
    used_labels: set[str] = set()
    for arc in model.component_data_objects(Arc, descend_into=True):
        source = getattr(arc, "source", None)
        if source is None:
            continue
        arc_name = arc.getname(fully_qualified=False)
        qualified_name = arc.getname(fully_qualified=True)
        label = aliases.get(qualified_name, aliases.get(arc_name, arc_name))
        if label in used_labels and qualified_name not in aliases:
            label = qualified_name
        record = stream_from_port(source)
        if record:
            used_labels.add(label)
            record["source_port"] = source.getname(fully_qualified=True)
            destination = getattr(arc, "destination", None)
            if destination is not None:
                record["destination_port"] = destination.getname(fully_qualified=True)
            streams[label] = record
    return streams


def merge_named_streams(base: dict[str, dict[str, Any]], named_ports: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Add or replace selected named streams from explicit ports."""

    merged = dict(base)
    for name, port in named_ports.items():
        record = stream_from_port(port)
        if record:
            record["source_port"] = port.getname(fully_qualified=True)
            merged[name] = record
    return merged
