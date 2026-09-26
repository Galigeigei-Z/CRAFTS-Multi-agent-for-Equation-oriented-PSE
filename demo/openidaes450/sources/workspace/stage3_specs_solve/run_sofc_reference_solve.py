#!/usr/bin/env python3
"""Run the official archive SOFC power-plant case as a Stage-3 validation target."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_REPO = ROOT / "examples" / "github_examples" / "clones" / "examples"
SOFC_DIR = EXAMPLES_REPO / "idaes_examples" / "archive" / "power_gen" / "sofc"
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/sofc/sofc_doc.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402
from stream_extract import port_stream_values  # noqa: E402


def component_value(obj: Any, *index: Any) -> float | None:
    if index:
        try:
            return float(value(obj[index]))
        except Exception:
            pass
    try:
        if hasattr(obj, "is_indexed") and obj.is_indexed():
            return float(value(obj[next(iter(obj))]))
    except Exception:
        pass
    try:
        return float(value(obj))
    except Exception:
        return None


def tag_values(tag_group: Any) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    try:
        keys = list(tag_group.keys())
    except Exception:
        return rows
    for key in keys:
        try:
            rows[str(key)] = float(value(tag_group[key].expression))
        except Exception:
            try:
                rows[str(key)] = float(tag_group[key].value)
            except Exception:
                rows[str(key)] = None
    return rows


def run_case(report_path: Path, tee: bool = False) -> dict[str, Any]:
    try:
        import idaes  # noqa: PLC0415
        import idaes.core.util as iutil  # noqa: PLC0415
        import pyomo.environ as pyo  # noqa: PLC0415
        from pyomo.environ import units as pyunits  # noqa: PLC0415
        from idaes.core.solvers import use_idaes_solver_configuration_defaults  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.opt import SolverStatus, TerminationCondition  # noqa: PLC0415

        if not SOFC_DIR.is_dir():
            raise RuntimeError(f"SOFC official example directory not found: {SOFC_DIR}")
        sys.path.insert(0, str(EXAMPLES_REPO))
        sys.path.insert(0, str(SOFC_DIR))
        import sofc  # noqa: PLC0415
        from sofc_costing import get_capital_cost, get_fixed_costs, get_variable_costs  # noqa: PLC0415

        work_dir = report_path.parent
        for filename in ("sofc_init.json.gz", "sofc_rom_data.json"):
            source = SOFC_DIR / filename
            if source.is_file():
                shutil.copy2(source, work_dir / filename)
        init_source = SOFC_DIR / "sofc_init.json.gz"
        os.chdir(work_dir)

        use_idaes_solver_configuration_defaults()
        idaes.cfg.ipopt.options.nlp_scaling_method = "user-scaling"
        idaes.cfg.ipopt.options.linear_solver = "ma57"
        idaes.cfg.ipopt.options.OF_ma57_automatic_scaling = "yes"
        idaes.cfg.ipopt.options.ma57_pivtol = 1e-5
        idaes.cfg.ipopt.options.ma57_pivtolmax = 0.1
        idaes.cfg.ipopt.options.bound_push = 1e-20

        model = sofc.get_model()
        if (work_dir / "sofc_init.json.gz").is_file():
            iutil.from_json(model, fname=str(work_dir / "sofc_init.json.gz"), wts=iutil.StoreSpec(suffix=False))
        else:
            sofc.initialize(model)
            iutil.to_json(model, fname=str(work_dir / "sofc_init.json.gz"))
        solver = pyo.SolverFactory("ipopt")
        base_results = solver.solve(model, tee=tee)

        get_capital_cost(model)
        get_fixed_costs(model)
        get_variable_costs(model)
        model.fs.obj = pyo.Objective(
            expr=model.fs.costing.annualized_tasc
            + model.fs.costing.total_fixed_OM_cost
            + model.fs.costing.total_variable_OM_cost[0]
        )
        model.fs.anode_hx.area.unfix()
        model.fs.cathode_hx.area.unfix()
        model.fs.air_blower.inlet.flow_mol.unfix()
        model.fs.cathode_recycle.split_fraction[0, "recycle_outlet"].unfix()
        model.fs.sofc.OTC.unfix()
        model.fs.sofc.OTC.setlb(2.099)
        model.fs.sofc.OTC.setub(2.2)

        @model.fs.Constraint()
        def maximum_cell_temperature(fs):
            return model.fs.sofc.max_cell_temperature <= 750

        @model.fs.Constraint()
        def maximum_cell_temperature_change(fs):
            return model.fs.sofc.deltaT_cell <= 100

        model.fs.net_power_MW = pyo.Var(
            model.fs.time,
            initialize=650,
            bounds=(100, 900),
            units=pyunits.MW,
        )

        @model.fs.Constraint(model.fs.time)
        def net_power_constraint(fs, t):
            return fs.net_power_MW[t] == pyunits.convert(fs.net_power[t], pyunits.MW)

        model.fs.anode_mix.feed_inlet.flow_mol.unfix()
        model.fs.net_power_MW.fix(650)

        results = solver.solve(model, tee=tee)
        sofc.add_tags(model)
        tags = tag_values(getattr(model, "_tags_output", {}))
        optimal = (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )
        return {
            "pass": bool(optimal),
            "stage": "design_optimization_solver",
            "case_family": "sofc",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "base_termination_condition": str(base_results.solver.termination_condition),
            "base_solver_status": str(base_results.solver.status),
            "final_dof": degrees_of_freedom(model),
            "stream_values": port_stream_values(model),
            "tag_values": tags,
            "net_power_w": component_value(model.fs.net_power, 0) if hasattr(model.fs, "net_power") else None,
            "annualized_tasc": component_value(model.fs.costing.annualized_tasc),
            "total_fixed_om_cost": component_value(model.fs.costing.total_fixed_OM_cost),
            "total_variable_om_cost": component_value(model.fs.costing.total_variable_OM_cost, 0),
            "source_summary": {
                "source": "idaes_examples.archive.power_gen.sofc.sofc.get_model + sofc_costing official design optimization block",
                "init_json": str(init_source),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "sofc",
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

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = run_case(report_path, tee=args.tee)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
