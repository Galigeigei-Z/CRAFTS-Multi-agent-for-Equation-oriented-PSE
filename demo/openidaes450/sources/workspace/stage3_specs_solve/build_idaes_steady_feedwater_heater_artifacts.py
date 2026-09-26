#!/usr/bin/env python3
"""Build deterministic IR and SVG artifacts for the steady FWH0D case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.dof_checker import check_dof_proxy  # noqa: E402
from stage3_specs_solve.idaes_steady_feedwater_heater_model import SOURCE_URL  # noqa: E402
from stage3_specs_solve.spec_ir_builder import build_spec_ir, validate_spec_ir  # noqa: E402


CASE_ID = "variant_idaes_steady_feedwater_heater"


def _spec(target: str, variable: str, value: float, units: str, role: str) -> dict[str, Any]:
    return {
        "target": target,
        "variable": variable,
        "value": value,
        "units": units,
        "role": role,
        "source": "official_test_configuration",
        "source_url": SOURCE_URL,
    }


def topology_ir() -> dict[str, Any]:
    return {
        "schema_version": "topology_ir/1",
        "case_id": CASE_ID,
        "family": "family_idaes_feedwater_heater",
        "process_type": "Steady closed feedwater heater with extraction-steam condensation and drain cooling",
        "source_url": SOURCE_URL,
        "source_basis": [
            "Native IDAES FWH0D composite unit with IAPWS95 steam-water properties.",
            "Desuperheating, condensing, drain-cooling, and cascade-drain mixing sections are enabled.",
            "The saturation constraint determines extraction-steam flow instead of prescribing it.",
            "This is a steady thermal-design case, distinct from the registered dynamic transient FWH case.",
        ],
        "property_packages": {
            "iapws95": {
                "components": ["H2O"],
                "phases": ["Liq", "Vap"],
                "source": "idaes.models.properties.iapws95.Iapws95ParameterBlock",
            }
        },
        "components": {"steam_water": ["H2O"]},
        "units": [
            {"id": "extraction_steam", "kind": "Feed", "package": "iapws95", "stage": "steam_supply", "role": "superheated turbine extraction steam", "constructor": {}, "constraint_template": None},
            {"id": "cascade_drain", "kind": "Feed", "package": "iapws95", "stage": "drain_mixing", "role": "higher-pressure heater drain cascade", "constructor": {}, "constraint_template": None},
            {"id": "feedwater", "kind": "Feed", "package": "iapws95", "stage": "feedwater_supply", "role": "cold boiler feedwater", "constructor": {}, "constraint_template": None},
            {"id": "fwh", "kind": "FWH0D", "package": "iapws95", "stage": "heat_recovery", "role": "three-zone closed feedwater heater", "constructor": {"has_desuperheat": True, "has_drain_cooling": True, "has_drain_mixer": True}, "constraint_template": "saturated_liquid_condensate"},
            {"id": "heated_feedwater", "kind": "Product", "package": "iapws95", "stage": "product", "role": "heated boiler feedwater", "constructor": {}, "constraint_template": None},
            {"id": "cooled_drain", "kind": "Product", "package": "iapws95", "stage": "drain_product", "role": "subcooled condensate drain", "constructor": {}, "constraint_template": None},
        ],
        "arcs": [
            {"id": "s01", "source": "extraction_steam.outlet", "destination": "fwh.steam_inlet", "stage": "steam_supply", "role": "extraction steam to desuperheater", "tear_candidate": False},
            {"id": "s02", "source": "cascade_drain.outlet", "destination": "fwh.drain_inlet", "stage": "drain_mixing", "role": "cascade drain to internal mixer", "tear_candidate": False},
            {"id": "s03", "source": "feedwater.outlet", "destination": "fwh.feedwater_inlet", "stage": "feedwater_supply", "role": "cold feedwater to drain cooler", "tear_candidate": False},
            {"id": "s04", "source": "fwh.feedwater_outlet", "destination": "heated_feedwater.inlet", "stage": "product", "role": "heated feedwater product", "tear_candidate": False},
            {"id": "s05", "source": "fwh.drain_outlet", "destination": "cooled_drain.inlet", "stage": "drain_product", "role": "cooled condensed drain", "tear_candidate": False},
        ],
        "feed_specs": [
            _spec("extraction_steam", "pressure", 201325.0, "Pa", "steam pressure"),
            _spec("extraction_steam", "enth_mol", 60000.0, "J/mol", "superheated steam enthalpy"),
            _spec("cascade_drain", "flow_mol", 1.0, "mol/s", "cascade drain flow"),
            _spec("cascade_drain", "pressure", 201325.0, "Pa", "cascade drain pressure"),
            _spec("cascade_drain", "enth_mol", 20000.0, "J/mol", "cascade drain enthalpy"),
            _spec("feedwater", "flow_mol", 400.0, "mol/s", "feedwater flow"),
            _spec("feedwater", "pressure", 101325.0, "Pa", "feedwater pressure"),
            _spec("feedwater", "enth_mol", 3000.0, "J/mol", "feedwater enthalpy"),
        ],
        "unit_specs": [
            _spec("fwh.condense", "area", 1000.0, "m^2", "condensing-zone area"),
            _spec("fwh.condense", "overall_heat_transfer_coefficient", 100.0, "W/m^2/K", "condensing-zone U"),
            _spec("fwh.desuperheat", "area", 1000.0, "m^2", "desuperheating-zone area"),
            _spec("fwh.desuperheat", "overall_heat_transfer_coefficient", 10.0, "W/m^2/K", "desuperheating-zone U"),
            _spec("fwh.cooling", "area", 1000.0, "m^2", "drain-cooling-zone area"),
            _spec("fwh.cooling", "overall_heat_transfer_coefficient", 10.0, "W/m^2/K", "drain-cooling-zone U"),
        ],
        "unconnected_feed_ports": ["extraction_steam.outlet", "cascade_drain.outlet", "feedwater.outlet"],
        "unconnected_product_ports": ["heated_feedwater.inlet", "cooled_drain.inlet"],
        "tear_streams": [],
        "translator_constraint_templates": {},
        "translator_constraints": [],
        "initialization": {"strategy": "native FWH0D staged initializer", "solve_order": ["desuperheat", "drain_mix", "condense", "cooling", "full_unit"]},
        "solve": {"solver": "ipopt", "steady_state": True, "expected_dof": 0},
        "required_entries": ["Feed", "Feed", "Feed", "FWH0D", "Product", "Product"],
        "notes_for_agent_a": ["Do not fix extraction-steam flow; it is determined by the condensing saturation constraint."],
    }


def svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1420" height="520" viewBox="0 0 1420 520">
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#263b50"/></marker></defs>
<style>.l{stroke:#263b50;stroke-width:4;fill:none;marker-end:url(#arrow)}.u{fill:#e8f3fb;stroke:#245c83;stroke-width:3}.f{fill:#fff0dc;stroke:#a65a00;stroke-width:3}.p{fill:#e8f7ef;stroke:#28744b;stroke-width:3}.t{font:700 16px sans-serif;text-anchor:middle;fill:#172533}.s{font:14px sans-serif;fill:#344b60}</style>
<text x="24" y="35" class="t" text-anchor="start">IDAES steady closed feedwater heater (FWH0D)</text>
<text x="24" y="68" class="s">Extraction steam is desuperheated, condensed, and drain-cooled while feedwater flows countercurrently.</text>
<rect x="360" y="115" width="205" height="95" class="u"/><text x="462" y="153" class="t">DESUPERHEAT</text><text x="462" y="181" class="s" text-anchor="middle">UA = 10 kW/K</text>
<rect x="625" y="115" width="205" height="95" class="u"/><text x="727" y="153" class="t">CONDENSE</text><text x="727" y="181" class="s" text-anchor="middle">UA = 100 kW/K</text>
<rect x="890" y="115" width="205" height="95" class="u"/><text x="992" y="153" class="t">DRAIN COOLER</text><text x="992" y="181" class="s" text-anchor="middle">UA = 10 kW/K</text>
<text x="20" y="155" class="s">Extraction steam</text><path d="M145 160 H360" class="l"/><path d="M565 160 H625" class="l"/><path d="M830 160 H890" class="l"/>
<rect x="1150" y="120" width="220" height="80" class="p"/><text x="1260" y="155" class="t">COOLED DRAIN</text><path d="M1095 160 H1150" class="l"/>
<rect x="300" y="330" width="230" height="80" class="p"/><text x="415" y="365" class="t">HEATED FEEDWATER</text>
<path d="M1150 370 H1095" class="l"/><path d="M890 370 H830" class="l"/><path d="M625 370 H530" class="l"/>
<text x="1190" y="355" class="s">Cold feedwater</text><text x="650" y="345" class="s">countercurrent heat recovery</text>
<rect x="625" y="245" width="205" height="65" class="f"/><text x="727" y="283" class="t">DRAIN MIXER</text>
<text x="480" y="275" class="s">Cascade drain</text><path d="M570 275 H625" class="l"/><path d="M727 245 V210" class="l"/>
</svg>\n"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    topology = topology_ir()
    spec = build_spec_ir(topology)
    errors = validate_spec_ir(spec)
    if errors:
        raise SystemExit("spec IR validation failed: " + "; ".join(errors))
    dof_report = check_dof_proxy(topology, spec)
    artifacts = {
        f"{CASE_ID}_topology_ir.json": topology,
        f"{CASE_ID}_spec_ir.json": spec,
        "topology_prebuild_report_attempt0.json": {
            "pass": True,
            "stage": "topology_prebuild",
            "case_id": CASE_ID,
            "unit_count": len(topology["units"]),
            "arc_count": len(topology["arcs"]),
            "required_entries": topology["required_entries"],
        },
        "dof_check_report_attempt0.json": dof_report,
        "source_verified_meta.json": {
            "case_id": CASE_ID,
            "source_kind": "official_idaes_native_model",
            "source_url": SOURCE_URL,
            "source_commit": "eed7cebc3d99be616ee7ead203cecaee9f81ac01",
            "source_path": "idaes/models_extra/power_generation/unit_models/feedwater_heater_0D.py",
            "verification_path": "idaes/models_extra/power_generation/unit_models/tests/test_feedwater_heater.py",
            "model_class": "idaes.models_extra.power_generation.unit_models.FWH0D",
            "property_package": "idaes.models.properties.iapws95.Iapws95ParameterBlock",
            "distinct_from": (
                "Steady three-zone thermal-design solve with extraction-flow calculation; "
                "the existing registered FWH case is a dynamic transient simulation."
            ),
        },
    }
    for filename, payload in artifacts.items():
        (output_dir / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "source_flowchart.svg").write_text(svg(), encoding="utf-8")
    print(json.dumps({"pass": dof_report["pass"], "case_id": CASE_ID, "output_dir": str(output_dir)}, indent=2))
    raise SystemExit(0 if dof_report["pass"] else 1)


if __name__ == "__main__":
    main()
