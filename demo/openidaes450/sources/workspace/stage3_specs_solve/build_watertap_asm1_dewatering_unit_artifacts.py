#!/usr/bin/env python3
"""Generate validation artifacts for the WaterTAP ASM1 dewatering unit case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stage3_specs_solve.run_watertap_asm1_dewatering_unit_reference_solve import (  # noqa: E402
    SOURCE_URL,
    run_case,
)
from stage3_specs_solve.spec_ir_builder import build_spec_ir, validate_spec_ir  # noqa: E402


CASE_ID = "variant_watertap_asm1_dewatering_unit"
FAMILY = "family_watertap_sludge_dewatering"


def topology_ir():
    feed_specs = [
        ("inlet.flow_vol[0]", 178.4674, "m^3/day", "waste activated sludge flow"),
        ("inlet.temperature[0]", 308.15, "K", "feed temperature"),
        ("inlet.pressure[0]", 101325.0, "Pa", "feed pressure"),
        ("inlet.alkalinity[0]", 97.8459, "mol/m^3", "feed alkalinity"),
    ]
    concentrations = {
        "S_I": 130.867,
        "S_S": 258.5789,
        "X_I": 17216.2434,
        "X_S": 2611.4843,
        "X_BH": 1e-6,
        "X_BA": 1e-6,
        "X_P": 626.0652,
        "S_O": 1e-6,
        "S_NO": 1e-6,
        "S_NH": 1442.7882,
        "S_ND": 0.54323,
        "X_ND": 100.8668,
    }
    feed_specs.extend(
        (f"inlet.conc_mass_comp[0,'{component}']", value, "mg/L", f"feed {component}")
        for component, value in concentrations.items()
    )

    def spec(variable, value, unit, role):
        return {
            "target": "dewaterer",
            "variable": variable,
            "value": value,
            "units": unit,
            "role": role,
            "source": "official_bsm2_benchmark_configuration",
            "source_url": SOURCE_URL,
        }

    return {
        "schema_version": "topology_ir/1",
        "case_id": CASE_ID,
        "family": FAMILY,
        "process_type": "Single-unit ASM1 waste activated sludge dewatering",
        "source_url": SOURCE_URL,
        "source_basis": [
            "Uses the official WaterTAP DewateringUnit and ASM1ParameterBlock.",
            "The official BSM2 benchmark feed is separated into clarified overflow and concentrated underflow cake.",
            "Native correlations specify 98% suspended-solids capture and nominal 28 wt% cake dry solids.",
        ],
        "property_packages": {
            "ASM1": {
                "components": list(concentrations),
                "phases": ["Liq"],
                "source": "watertap.property_models.unit_specific.activated_sludge.asm1_properties",
            }
        },
        "components": {
            "soluble": ["S_I", "S_S", "S_O", "S_NO", "S_NH", "S_ND"],
            "particulate": ["X_I", "X_S", "X_BH", "X_BA", "X_P", "X_ND"],
        },
        "units": [
            {"id": "waste_sludge_feed", "kind": "Feed", "package": "ASM1", "stage": "feed", "role": "waste activated sludge", "constructor": {}, "constraint_template": None},
            {"id": "dewaterer", "kind": "DewateringUnit", "package": "ASM1", "stage": "separation", "role": "empirical BSM2 sludge dewaterer", "constructor": {"activated_sludge_model": "ASM1", "split_basis": "componentFlow"}, "constraint_template": None},
            {"id": "filtrate", "kind": "Product", "package": "ASM1", "stage": "product", "role": "clarified liquid overflow", "constructor": {}, "constraint_template": None},
            {"id": "sludge_cake", "kind": "Product", "package": "ASM1", "stage": "product", "role": "captured-solids underflow cake", "constructor": {}, "constraint_template": None},
        ],
        "arcs": [
            {"id": "s01", "source": "waste_sludge_feed.outlet", "destination": "dewaterer.inlet", "stage": "feed", "role": "waste activated sludge", "tear_candidate": False},
            {"id": "s02", "source": "dewaterer.overflow", "destination": "filtrate.inlet", "stage": "product", "role": "clarified filtrate", "tear_candidate": False},
            {"id": "s03", "source": "dewaterer.underflow", "destination": "sludge_cake.inlet", "stage": "product", "role": "dewatered cake", "tear_candidate": False},
        ],
        "feed_specs": [spec(*item) for item in feed_specs],
        "unit_specs": [
            spec("TSS_rem", 0.98, "dimensionless", "suspended-solids capture fraction"),
            spec("p_dewat", 0.28, "dimensionless", "nominal cake dry-solids mass fraction"),
            spec("hydraulic_retention_time[0]", 1800.0, "s", "dewaterer residence time"),
            spec("energy_electric_flow_vol_inlet[0]", 0.026, "kWh/m^3", "specific electricity intensity"),
        ],
        "unconnected_feed_ports": ["waste_sludge_feed.outlet"],
        "unconnected_product_ports": ["filtrate.inlet", "sludge_cake.inlet"],
        "translator_constraint_templates": {},
        "initialization": {"strategy": "initialize the native separator-based DewateringUnit", "solve_order": ["dewaterer"]},
        "solve": {"solver": "ipopt", "steady_state": True, "expected_dof": 0},
    }


def flowchart_svg():
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430" role="img" aria-label="ASM1 sludge dewatering process flow diagram">
<style>.line{stroke:#263b50;stroke-width:4;fill:none}.unit{fill:#e8f3fb;stroke:#245c83;stroke-width:3}.liquid{fill:#e7f6f1;stroke:#28744b;stroke-width:3}.solid{fill:#f5e9dc;stroke:#8a5525;stroke-width:3}.title{font:700 18px sans-serif;text-anchor:middle;fill:#172533}.label{font:15px sans-serif;fill:#344b60}.metric{font:700 15px sans-serif;fill:#172533}</style>
<text x="28" y="210" class="label">ASM1 waste sludge</text><text x="28" y="235" class="label">178.47 m3/day</text><path d="M180 220 H330" class="line"/>
<rect x="330" y="145" width="240" height="150" class="unit"/><text x="450" y="205" class="title">DewateringUnit</text><text x="450" y="235" class="label" text-anchor="middle">98% TSS capture</text><text x="450" y="260" class="label" text-anchor="middle">0.026 kWh/m3</text>
<path d="M570 185 H795" class="line"/><rect x="795" y="125" width="350" height="120" class="liquid"/><text x="970" y="168" class="title">Clarified filtrate</text><text x="970" y="198" class="metric" text-anchor="middle">94.63% hydraulic recovery</text><text x="970" y="224" class="label" text-anchor="middle">0.326 kg TSS/m3</text>
<path d="M450 295 V350 H795" class="line"/><rect x="795" y="305" width="350" height="105" class="solid"/><text x="970" y="347" class="title">Dewatered sludge cake</text><text x="970" y="378" class="metric" text-anchor="middle">28.22 wt% dry solids</text>
<text x="28" y="405" class="label">Native WaterTAP empirical BSM2 dewatering model; steady state, DoF = 0.</text>
</svg>\n"""


def write_artifacts(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    topology = topology_ir()
    spec = build_spec_ir(topology)
    errors = validate_spec_ir(spec)
    if errors:
        raise RuntimeError("spec IR validation failed: " + "; ".join(errors))
    report = run_case()
    paths = {
        "topology": output_dir / f"{CASE_ID}_topology_ir.json",
        "spec": output_dir / f"{CASE_ID}_spec_ir.json",
        "report": output_dir / "native_solve_report.json",
        "svg": output_dir / "source_flowchart.svg",
    }
    paths["topology"].write_text(json.dumps(topology, indent=2) + "\n", encoding="utf-8")
    paths["spec"].write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    paths["report"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    paths["svg"].write_text(flowchart_svg(), encoding="utf-8")
    return report, paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report, paths = write_artifacts(Path(args.output_dir))
    print(json.dumps({"pass": report["pass"], "files": {key: str(path) for key, path in paths.items()}}, indent=2))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
