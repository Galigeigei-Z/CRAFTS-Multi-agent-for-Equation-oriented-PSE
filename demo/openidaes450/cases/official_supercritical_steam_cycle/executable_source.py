#!/usr/bin/env python3
"""Run the official supercritical steam-cycle case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/supercritical/supercritical_steam_cycle_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()


def run_case() -> dict[str, Any]:
    try:
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from idaes.core.util.tables import create_stream_table_dataframe  # noqa: PLC0415
        from idaes.models_extra.power_generation.flowsheets.supercritical_steam_cycle.supercritical_steam_cycle import (  # noqa: PLC0415
            main as run_official_supercritical_steam_cycle,
        )
        from pyomo.environ import value  # noqa: PLC0415

        model, _solver = run_official_supercritical_steam_cycle()
        flowsheet = model.fs
        stream_df = create_stream_table_dataframe(streams=model._streams, orient="index")

        records: list[dict[str, Any]] = []
        stream_values: dict[str, dict[str, Any]] = {}
        for stream_name, row in stream_df.iterrows():
            record: dict[str, Any] = {"stream": str(stream_name)}
            for column, raw_value in row.items():
                try:
                    clean_value: Any = value(raw_value)
                except Exception:  # noqa: BLE001
                    clean_value = str(raw_value)
                record[str(column)] = clean_value
            records.append(record)
            if str(stream_name) != "Units":
                stream_values[str(stream_name)] = {
                    str(column): record[str(column)]
                    for column in stream_df.columns
                    if str(column) in record
                }

        return {
            "pass": degrees_of_freedom(model) == 0,
            "stage": "steady_state_solver",
            "case_family": "supercritical_steam_cycle",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": "optimal",
            "final_dof": degrees_of_freedom(model),
            "gross_power_mw": -value(flowsheet.turb.power[0]) * 1e-6,
            "steam_cycle_efficiency": value(flowsheet.steam_cycle_eff[0]),
            "boiler_heat_mw": value(flowsheet.boiler_heat[0]) * 1e-6,
            "main_steam_pressure_pa": value(flowsheet.turb.inlet_split.inlet.pressure[0]),
            "condenser_pressure_pa": value(flowsheet.condenser_mix.mixed_state[0].pressure),
            "bfp_power_mw": abs(value(flowsheet.bfp.work_mechanical[0])) * 1e-6,
            "bfpt_power_mw": abs(value(flowsheet.bfpt.work_mechanical[0])) * 1e-6,
            "stream_table": {
                "columns": [str(column) for column in stream_df.columns],
                "records": records,
            },
            "stream_values": stream_values,
            "source_summary": {
                "source": "idaes.models_extra.power_generation.flowsheets.supercritical_steam_cycle.supercritical_steam_cycle.main",
                "stream_count": len(stream_values),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "supercritical_steam_cycle",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tee", action="store_true")
    args = parser.parse_args()

    report = run_case()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
