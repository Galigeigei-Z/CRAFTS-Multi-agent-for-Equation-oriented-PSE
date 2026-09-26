"""Helpers for extracting lightweight stream values from solved IDAES models."""

from __future__ import annotations

from typing import Any

from pyomo.environ import value


PRIMARY_STREAM_VARS = {
    "flow_mol": "flow_mol",
    "flow_mass": "flow_mass",
    "flow_vol": "volumetric_flow",
    "temperature": "temperature",
    "pressure": "pressure",
    "enth_mol": "enth_mol",
    "enth_mass": "enth_mass",
    "vapor_frac": "vapor_frac",
}

INDEXED_STREAM_VARS = {
    "flow_mass_comp": "flow_mass_comp",
    "flow_mass_phase_comp": "flow_mass_phase_comp",
    "flow_mol_comp": "flow_mol_comp",
    "flow_mol_phase_comp": "flow_mol_phase_comp",
    "flow_vol_phase": "flow_vol_phase",
    "mass_frac_comp": "mass_frac_comp",
    "mass_frac_phase_comp": "mass_frac_phase_comp",
    "mole_frac_comp": "mole_frac_comp",
    "mole_frac_phase_comp": "mole_frac_phase_comp",
    "conc_mass_comp": "conc_mass_comp",
    "conc_mass_phase_comp": "conc_mass_phase_comp",
    "conc_mol_comp": "conc_mol_comp",
    "conc_mol_phase_comp": "conc_mol_phase_comp",
}


def safe_float(expr: Any) -> float | None:
    try:
        return float(value(expr))
    except Exception:
        return None


def first_numeric_value(component: Any) -> float | None:
    if not hasattr(component, "is_indexed") or not component.is_indexed():
        return safe_float(component)
    try:
        for _index, data in component.items():
            numeric = safe_float(data)
            if numeric is not None:
                return numeric
    except Exception:
        return None
    return None


def tail_label(index: Any) -> str:
    if not isinstance(index, tuple):
        parts = [index]
    else:
        parts = list(index)
    if parts and str(parts[0]) in {"0", "0.0"}:
        parts = parts[1:]
    return ".".join(str(part) for part in parts) if parts else "value"


def indexed_numeric_values(component: Any) -> dict[str, float]:
    values: dict[str, float] = {}
    if not hasattr(component, "is_indexed") or not component.is_indexed():
        numeric = safe_float(component)
        return {"value": numeric} if numeric is not None else {}
    try:
        for index, data in component.items():
            numeric = safe_float(data)
            if numeric is not None:
                values[tail_label(index)] = numeric
    except Exception:
        return values
    return values


def matched_output_name(name: str, mapping: dict[str, str]) -> str | None:
    lowered = name.lower()
    for token, output_name in mapping.items():
        if lowered == token or lowered.endswith(f".{token}") or lowered.endswith(f"_{token}"):
            return output_name
    return None


def stream_value_name(raw_name: Any) -> str:
    return str(raw_name).replace(".", "_")


def add_aggregate_values(stream: dict[str, Any], name: str, values: dict[str, float]) -> None:
    if name in {"flow_mass_comp", "flow_mass_phase_comp"}:
        stream["mass_flow"] = sum(values.values())
        stream["flow_kg_s"] = stream["mass_flow"]
        if stream["mass_flow"]:
            frac_key = "mass_frac_comp" if name == "flow_mass_comp" else "mass_frac_phase_comp"
            stream.setdefault(frac_key, {key: value / stream["mass_flow"] for key, value in values.items()})
    elif name in {"flow_mol_comp", "flow_mol_phase_comp"}:
        stream["flow_mol"] = sum(values.values())
        stream["flow_mol_s"] = stream["flow_mol"]
    elif name == "flow_vol_phase":
        stream["volumetric_flow"] = sum(values.values())
        stream["flow_m3_s"] = stream["volumetric_flow"]


def port_stream_values(model: Any, max_streams: int = 120) -> dict[str, dict[str, Any]]:
    try:
        from pyomo.network import Port
    except Exception:
        return {}

    streams: dict[str, dict[str, Any]] = {}
    try:
        ports = model.component_data_objects(Port, descend_into=True)
    except Exception:
        return {}
    for port in ports:
        try:
            port_vars = getattr(port, "vars", {})
        except Exception:
            continue
        if not isinstance(port_vars, dict):
            continue
        stream: dict[str, Any] = {}
        for raw_name, component in port_vars.items():
            name = str(raw_name)
            primary_name = matched_output_name(name, PRIMARY_STREAM_VARS)
            if primary_name is not None:
                numeric = first_numeric_value(component)
                if numeric is not None:
                    stream[primary_name] = numeric
                continue
            indexed_name = matched_output_name(name, INDEXED_STREAM_VARS)
            values = indexed_numeric_values(component)
            if not values:
                continue
            output_name = indexed_name or stream_value_name(raw_name)
            if len(values) == 1 and "value" in values and indexed_name is None:
                stream[output_name] = values["value"]
            else:
                stream[output_name] = values
            add_aggregate_values(stream, output_name, values)
        if stream:
            stream_id = port.getname(fully_qualified=True).replace("fs.", "", 1)
            streams[stream_id] = stream
            if len(streams) >= max_streams:
                break
    return streams
