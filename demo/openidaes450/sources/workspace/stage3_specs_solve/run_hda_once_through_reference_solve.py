#!/usr/bin/env python3
"""Solve HDA once-through single- or two-flash engineering variants."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "examples" / "hda_once_through" / "source_root"
HDA_PROPERTY_ROOT = ROOT / "examples" / "hda_flash" / "source_root"
for path in (ROOT, HDA_PROPERTY_ROOT, SOURCE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: E402
from pyomo.environ import value  # noqa: E402


def port_values(port: Any) -> dict[str, Any]:
    return {
        "flow_mol_phase_comp": {
            f"{phase}:{component}": float(value(port.flow_mol_phase_comp[0, phase, component]))
            for phase in ("Liq", "Vap")
            for component in ("benzene", "toluene", "hydrogen", "methane")
        },
        "temperature_K": float(value(port.temperature[0])),
        "pressure_Pa": float(value(port.pressure[0])),
    }


def btx_metrics(stream: dict[str, Any]) -> dict[str, float]:
    flows = stream["flow_mol_phase_comp"]
    benzene = flows["Liq:benzene"] + flows["Vap:benzene"]
    toluene = flows["Liq:toluene"] + flows["Vap:toluene"]
    return {
        "benzene_mol_s": benzene,
        "toluene_mol_s": toluene,
        "benzene_fraction_in_btx": benzene / (benzene + toluene),
    }


def run_case(*, second_flash: bool, tee: bool = False) -> dict[str, Any]:
    variant = "two_flash" if second_flash else "single_flash"
    try:
        from notebook_build import main  # noqa: PLC0415

        model, result = main(second_flash=second_flash, tee=tee)
        products = {
            "F101_vapor": port_values(model.fs.F101.vap_outlet),
            "F101_liquid": port_values(model.fs.F101.liq_outlet),
        }
        if second_flash:
            products.update(
                {
                    "F102_vapor": port_values(model.fs.F102.vap_outlet),
                    "F102_liquid": port_values(model.fs.F102.liq_outlet),
                }
            )
        crude = btx_metrics(products["F101_liquid"])
        selected_product = btx_metrics(
            products["F102_vapor"] if second_flash else products["F101_liquid"]
        )
        return {
            "pass": True,
            "stage": "steady_state_solver",
            "case_family": f"hda_once_through_{variant}",
            "variant_basis": "topology_distinct_no_recycle",
            "separation_stages": 2 if second_flash else 1,
            "termination_condition": str(result.solver.termination_condition),
            "final_dof": degrees_of_freedom(model),
            "products": products,
            "variant_metrics": {
                "crude_btx_benzene_fraction": crude["benzene_fraction_in_btx"],
                "selected_product_benzene_fraction": selected_product["benzene_fraction_in_btx"],
                "benzene_enrichment_factor": selected_product["benzene_fraction_in_btx"]
                / crude["benzene_fraction_in_btx"],
                "selected_product_benzene_recovery": selected_product["benzene_mol_s"]
                / crude["benzene_mol_s"],
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": f"hda_once_through_{variant}",
            "variant_basis": "topology_distinct_no_recycle",
            "separation_stages": 2 if second_flash else 1,
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("single_flash", "two_flash"), required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()
    report = run_case(second_flash=args.variant == "two_flash", tee=args.tee)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main_cli()
