#!/usr/bin/env python3
"""Run the official IDAES NGCC HRSG subflowsheet as a Stage-3 target."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_REPO = ROOT / "experiment" / "runtime_data" / "official_idaes_examples_snapshot_v1"
NGCC_NOTEBOOK_DIR = EXAMPLES_REPO / "idaes_examples" / "notebooks" / "docs" / "power_gen" / "ngcc"
OFFICIAL_REFERENCE_URL = "https://idaes.github.io/examples-pse/latest/Examples/Flowsheets/power_generation/ngcc/ngcc_doc.html"
SOURCE_VARIANT_URL = f"{OFFICIAL_REFERENCE_URL}#hrsg_subflowsheet"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from pyomo.environ import value  # noqa: E402
from stage3_specs_solve.stream_extract import port_stream_values  # noqa: E402
from stage3_specs_solve.native_topology_probe import probe_native_topology  # noqa: E402


HRSG_UNIT_IDS = (
    "fg_inlet", "lp_feedwater", "econ_lp", "evap_lp", "sh_lp", "econ_ip1",
    "econ_ip2", "evap_ip", "sh_ip1", "sh_ip2", "sh_ip3", "econ_hp1",
    "econ_hp2", "econ_hp3", "econ_hp4", "econ_hp5", "evap_hp", "sh_hp1",
    "sh_hp2", "sh_hp3", "sh_hp4", "mixer1", "mixer_soec", "drum_lp",
    "splitter1", "pump_ip", "pump_hp", "splitter_ip1", "mixer_ip1",
    "splitter_ip2", "evap_hp_valve", "split_fg_lp", "mixer_lp2",
    "hp_steam_out", "ip_steam_out", "lp_steam_out", "stack_gas",
)
HRSG_BOUNDARY_UNIT_PATHS = {
    "fg_inlet": "fs.sh_hp4.shell_inlet",
    "lp_feedwater": "fs.econ_lp.tube_inlet",
    "hp_steam_out": "fs.sh_hp4.tube_outlet",
    "ip_steam_out": "fs.sh_ip3.tube_outlet",
    "lp_steam_out": "fs.sh_lp.tube_outlet",
    "stack_gas": "fs.econ_lp.shell_outlet",
}
HRSG_ARCS = {
    "fg_to_sh_hp4": ("fs.sh_hp4.shell_inlet", "fs.sh_hp4.shell_inlet"),
    "lp_feed_to_econ_lp": ("fs.econ_lp.tube_inlet", "fs.econ_lp.tube_inlet"),
    "lp02": ("fs.econ_lp.tube_outlet", "fs.mixer1.econ_lp"),
    "lp04": ("fs.mixer1.outlet", "fs.evap_lp.tube_inlet"),
    "lp05": ("fs.evap_lp.tube_outlet", "fs.mixer_soec.main"),
    "lp13": ("fs.mixer_soec.outlet", "fs.drum_lp.inlet"),
    "lp10": ("fs.drum_lp.vap_outlet", "fs.sh_lp.tube_inlet"),
    "lp_steam_product": ("fs.sh_lp.tube_outlet", "fs.sh_lp.tube_outlet"),
    "lp06": ("fs.drum_lp.liq_outlet", "fs.splitter1.inlet"),
    "lp08": ("fs.splitter1.toIP", "fs.pump_ip.inlet"),
    "lp09": ("fs.splitter1.toHP", "fs.pump_hp.inlet"),
    "ip01": ("fs.pump_ip.outlet", "fs.econ_ip1.tube_inlet"),
    "ip02": ("fs.econ_ip1.tube_outlet", "fs.splitter_ip1.inlet"),
    "ip03": ("fs.splitter_ip1.toIP_ECON2", "fs.econ_ip2.tube_inlet"),
    "ip05": ("fs.econ_ip2.tube_outlet", "fs.evap_ip.tube_inlet"),
    "ip06": ("fs.evap_ip.tube_outlet", "fs.sh_ip1.tube_inlet"),
    "ip07": ("fs.sh_ip1.tube_outlet", "fs.mixer_ip1.sh_ip1"),
    "ip15": ("fs.splitter_ip2.Cold_reheat", "fs.mixer_ip1.Cold_reheat"),
    "ip08": ("fs.mixer_ip1.outlet", "fs.sh_ip2.tube_inlet"),
    "ip09": ("fs.sh_ip2.tube_outlet", "fs.sh_ip3.tube_inlet"),
    "ip_steam_product": ("fs.sh_ip3.tube_outlet", "fs.sh_ip3.tube_outlet"),
    "hp01": ("fs.pump_hp.outlet", "fs.econ_hp1.tube_inlet"),
    "hp02": ("fs.econ_hp1.tube_outlet", "fs.econ_hp2.tube_inlet"),
    "hp03": ("fs.econ_hp2.tube_outlet", "fs.econ_hp3.tube_inlet"),
    "hp04": ("fs.econ_hp3.tube_outlet", "fs.econ_hp4.tube_inlet"),
    "hp05": ("fs.econ_hp4.tube_outlet", "fs.econ_hp5.tube_inlet"),
    "hp06": ("fs.econ_hp5.tube_outlet", "fs.evap_hp_valve.inlet"),
    "hp06b": ("fs.evap_hp_valve.outlet", "fs.evap_hp.tube_inlet"),
    "hp07": ("fs.evap_hp.tube_outlet", "fs.sh_hp1.tube_inlet"),
    "hp08": ("fs.sh_hp1.tube_outlet", "fs.sh_hp2.tube_inlet"),
    "hp09": ("fs.sh_hp2.tube_outlet", "fs.sh_hp3.tube_inlet"),
    "hp10": ("fs.sh_hp3.tube_outlet", "fs.sh_hp4.tube_inlet"),
    "hp_steam_product": ("fs.sh_hp4.tube_outlet", "fs.sh_hp4.tube_outlet"),
    "g09": ("fs.sh_hp4.shell_outlet", "fs.sh_ip3.shell_inlet"),
    "g10": ("fs.sh_ip3.shell_outlet", "fs.sh_hp3.shell_inlet"),
    "g11": ("fs.sh_hp3.shell_outlet", "fs.sh_hp2.shell_inlet"),
    "g12": ("fs.sh_hp2.shell_outlet", "fs.sh_ip2.shell_inlet"),
    "g13": ("fs.sh_ip2.shell_outlet", "fs.sh_hp1.shell_inlet"),
    "g14": ("fs.sh_hp1.shell_outlet", "fs.evap_hp.shell_inlet"),
    "g15": ("fs.evap_hp.shell_outlet", "fs.econ_hp5.shell_inlet"),
    "g16": ("fs.econ_hp5.shell_outlet", "fs.sh_ip1.shell_inlet"),
    "g17": ("fs.sh_ip1.shell_outlet", "fs.econ_hp4.shell_inlet"),
    "g18": ("fs.econ_hp4.shell_outlet", "fs.econ_hp3.shell_inlet"),
    "g19": ("fs.econ_hp3.shell_outlet", "fs.split_fg_lp.inlet"),
    "g20": ("fs.split_fg_lp.toLP_SH", "fs.sh_lp.shell_inlet"),
    "g21": ("fs.sh_lp.shell_outlet", "fs.mixer_lp2.fromLP_SH"),
    "g22": ("fs.split_fg_lp.toMixer", "fs.mixer_lp2.bypass"),
    "g23": ("fs.mixer_lp2.outlet", "fs.evap_ip.shell_inlet"),
    "g24": ("fs.evap_ip.shell_outlet", "fs.econ_ip2.shell_inlet"),
    "g25": ("fs.econ_ip2.shell_outlet", "fs.econ_hp2.shell_inlet"),
    "g26": ("fs.econ_hp2.shell_outlet", "fs.econ_ip1.shell_inlet"),
    "g27": ("fs.econ_ip1.shell_outlet", "fs.econ_hp1.shell_inlet"),
    "g28": ("fs.econ_hp1.shell_outlet", "fs.evap_lp.shell_inlet"),
    "g29": ("fs.evap_lp.shell_outlet", "fs.econ_lp.shell_inlet"),
    "g30": ("fs.econ_lp.shell_outlet", "fs.econ_lp.shell_outlet"),
}


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


def run_case(report_path: Path, tee: bool = False) -> dict[str, Any]:
    try:
        import idaes  # noqa: PLC0415
        import idaes.core.util.scaling as iscale  # noqa: PLC0415
        import pyomo.environ as pyo  # noqa: PLC0415
        from idaes.core.solvers import use_idaes_solver_configuration_defaults  # noqa: PLC0415
        from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
        from pyomo.opt import SolverStatus, TerminationCondition  # noqa: PLC0415

        if not EXAMPLES_REPO.is_dir():
            raise RuntimeError(f"IDAES examples repo not found: {EXAMPLES_REPO}")
        sys.path.insert(0, str(EXAMPLES_REPO))
        from idaes_examples.mod.power_gen import hrsg  # noqa: PLC0415

        work_dir = report_path.parent
        init_source = NGCC_NOTEBOOK_DIR / "hrsg_init.json.gz"
        if not init_source.is_file():
            raise RuntimeError(f"Official HRSG init JSON not found: {init_source}")
        shutil.copy2(init_source, work_dir / "hrsg_init.json.gz")

        use_idaes_solver_configuration_defaults()
        idaes.cfg.ipopt.options.nlp_scaling_method = "user-scaling"
        idaes.cfg.ipopt.options.linear_solver = "ma57"
        idaes.cfg.ipopt.options.OF_ma57_automatic_scaling = "yes"
        idaes.cfg.ipopt.options.ma57_pivtol = 1e-5
        idaes.cfg.ipopt.options.ma57_pivtolmax = 0.1

        model = pyo.ConcreteModel()
        model.fs = hrsg.HrsgFlowsheet(dynamic=False)
        iscale.calculate_scaling_factors(model)
        model.fs.initialize(load_from=str(work_dir / "hrsg_init.json.gz"), save_to=str(work_dir / "hrsg_init.json.gz"))
        results = pyo.SolverFactory("ipopt").solve(model, tee=tee)
        optimal = results.solver.status == SolverStatus.ok and results.solver.termination_condition == TerminationCondition.optimal
        final_dof = degrees_of_freedom(model)
        native_topology_binding = probe_native_topology(
            model,
            units={
                unit_id: HRSG_BOUNDARY_UNIT_PATHS.get(unit_id, f"fs.{unit_id}")
                for unit_id in HRSG_UNIT_IDS
            },
            arcs=HRSG_ARCS,
        )
        heat_duties_mw: dict[str, float | None] = {}
        for unit_name in ("econ_lp", "evap_lp", "sh_lp", "econ_ip1", "econ_ip2", "evap_ip", "sh_ip1", "sh_ip2", "sh_ip3", "econ_hp1", "econ_hp2", "econ_hp3", "econ_hp4", "econ_hp5", "evap_hp", "sh_hp1", "sh_hp2", "sh_hp3", "sh_hp4"):
            unit = getattr(model.fs, unit_name, None)
            heat = getattr(unit, "heat_duty", None) if unit is not None else None
            raw = component_value(heat, 0) if heat is not None else None
            heat_duties_mw[unit_name] = raw * 1e-6 if raw is not None else None
        passed = bool(optimal and final_dof == 0 and native_topology_binding["passed"])
        return {
            "pass": passed,
            "stage": "steady_state_solver",
            "case_family": "ngcc_hrsg_subflowsheet",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "source_variant_url": SOURCE_VARIANT_URL,
            "termination_condition": str(results.solver.termination_condition),
            "solver_status": str(results.solver.status),
            "final_dof": final_dof,
            "heat_duties_mw": heat_duties_mw,
            "stream_values": port_stream_values(model),
            "native_topology_binding": native_topology_binding,
            "source_summary": {
                "source": "idaes_examples.mod.power_gen.hrsg.HrsgFlowsheet",
                "init_json": str(init_source),
                "boundary_projection": HRSG_BOUNDARY_UNIT_PATHS,
            },
            "error": None if passed else {"message": "NGCC HRSG subflowsheet did not satisfy pass checks"},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": False,
            "stage": "steady_state_solver",
            "case_family": "ngcc_hrsg_subflowsheet",
            "official_reference_url": OFFICIAL_REFERENCE_URL,
            "source_variant_url": SOURCE_VARIANT_URL,
            "termination_condition": None,
            "final_dof": None,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]},
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
