#!/usr/bin/env python3
"""Shared utilities for source-backed Stage-3 runners."""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path
from typing import Any

from pyomo.environ import value


def read_topology_ir(report_path: Path) -> dict[str, Any]:
    case_dir = report_path.parent
    for candidate in sorted(case_dir.glob("*topology_ir.json")):
        data = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("case_id") and data.get("arcs"):
            return data
    raise FileNotFoundError(f"no topology IR JSON found in {case_dir}")


def download_text(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())


def safe_value(obj: Any, *index: Any) -> float | None:
    try:
        target = obj[index] if index else obj
        val = value(target)
        if val is None:
            return None
        val = float(val)
        if math.isfinite(val):
            return val
    except Exception:
        return None
    return None


def port_values(port: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if hasattr(port, "flow_mol"):
        out["flow_mol"] = safe_value(port.flow_mol, 0)
    if hasattr(port, "flow_mass_phase_comp"):
        comps: dict[str, float] = {}
        total = 0.0
        try:
            for key in port.flow_mass_phase_comp:
                val = safe_value(port.flow_mass_phase_comp, *(key if isinstance(key, tuple) else (key,)))
                if val is None:
                    continue
                comp = str(key[-1] if isinstance(key, tuple) else key)
                comps[comp] = comps.get(comp, 0.0) + val
                total += val
        except Exception:
            comps = {}
            total = 0.0
        if total:
            out["flow_mass"] = total
            out["mass_frac_comp"] = {name: val / total for name, val in comps.items()}
    if hasattr(port, "mole_frac_comp"):
        mole_frac: dict[str, float] = {}
        try:
            for key in port.mole_frac_comp:
                val = safe_value(port.mole_frac_comp, *(key if isinstance(key, tuple) else (key,)))
                if val is not None:
                    mole_frac[str(key[-1] if isinstance(key, tuple) else key)] = val
        except Exception:
            mole_frac = {}
        if mole_frac:
            out["mole_frac_comp"] = mole_frac
    if hasattr(port, "temperature"):
        out["temperature"] = safe_value(port.temperature, 0)
    if hasattr(port, "pressure"):
        out["pressure"] = safe_value(port.pressure, 0)
    if hasattr(port, "enth_mol"):
        out["enth_mol"] = safe_value(port.enth_mol, 0)
    return {key: val for key, val in out.items() if val is not None and val != {}}


def stream_table_from_values(stream_values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    preferred = ["flow_mol", "flow_mass", "flow_bbl_per_day", "temperature", "pressure", "enth_mol", "mole_frac_comp", "mass_frac_comp"]
    observed = {key for values in stream_values.values() for key in values}
    keys = [key for key in preferred if key in observed] + sorted(observed - set(preferred))
    return {
        "columns": keys,
        "index": list(stream_values.keys()),
        "data": [[values.get(key) for key in keys] for values in stream_values.values()],
    }


def write_report(report_path: Path, report: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
