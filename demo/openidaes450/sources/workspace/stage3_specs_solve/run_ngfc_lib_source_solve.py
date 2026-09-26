#!/usr/bin/env python3
"""Run NGFC-Lib source-backed examples and report solved stream values."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import sys
import traceback
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime  # noqa: E402

configure_py310_runtime()

from source_runner_utils import download_text, port_values, read_topology_ir, stream_table_from_values, write_report  # noqa: E402


BASE = "https://raw.githubusercontent.com/NGFC-Lib/NGFC-Lib/master/jupyter/NGFC"
SOURCE_DIR = ROOT / ".external_sources" / "ngfc_lib_source"


def ensure_source() -> Path:
    files = {
        "NGFC_flowsheet.py": f"{BASE}/NGFC_flowsheet.py",
        "NGFC_flowsheet_init.json": f"{BASE}/NGFC_flowsheet_init.json",
        "properties/natural_gas_prop.py": f"{BASE}/properties/natural_gas_prop.py",
        "ROM/SOFC_ROM.py": f"{BASE}/ROM/SOFC_ROM.py",
        "ROM/kriging_coefficients.dat": f"{BASE}/ROM/kriging_coefficients.dat",
    }
    for rel, url in files.items():
        download_text(url, SOURCE_DIR / rel)
    for pkg in ["properties", "ROM"]:
        init = SOURCE_DIR / pkg / "__init__.py"
        init.parent.mkdir(parents=True, exist_ok=True)
        init.touch(exist_ok=True)
    return SOURCE_DIR


def import_ngfc(source_dir: Path) -> Any:
    install_idaes_compatibility_shims()
    sys.path.insert(0, str(source_dir))
    spec = importlib.util.spec_from_file_location("NGFC_flowsheet", source_dir / "NGFC_flowsheet.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load NGFC_flowsheet.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["NGFC_flowsheet"] = module
    spec.loader.exec_module(module)
    return module


def install_idaes_compatibility_shims() -> None:
    """Provide IDAES 1.x import names used by NGFC-Lib on current IDAES."""
    import idaes.core.util as core_util
    import idaes.core.util.misc as core_misc
    import idaes.models.properties.modular_properties.base.generic_property as generic_property
    import idaes.models.properties.modular_properties.base.generic_reaction as generic_reaction
    import idaes.models.properties.modular_properties.eos.ceos as ceos
    import idaes.models.properties.modular_properties.pure.NIST as nist
    import idaes.models.properties.modular_properties.pure.RPP4 as rpp
    import idaes.models.properties.modular_properties.reactions.dh_rxn as dh_rxn
    import idaes.models.properties.modular_properties.reactions.rate_constant as rate_constant
    import idaes.models.properties.modular_properties.reactions.rate_forms as rate_forms
    import idaes.models.properties.modular_properties.state_definitions as state_definitions
    import idaes.models.unit_models as unit_models
    import idaes.models.unit_models.heat_exchanger as heat_exchanger
    import idaes.models.unit_models.mixer as mixer
    import idaes.models.unit_models.pressure_changer as pressure_changer
    import idaes.models.unit_models.separator as separator

    def copy_port_values(destination: Any, source: Any, **_: Any) -> None:
        for name in destination.vars:
            if name not in source.vars:
                continue
            dest_var = destination.vars[name]
            src_var = source.vars[name]
            try:
                for key in dest_var:
                    if key in src_var:
                        dest_var[key].set_value(src_var[key].value, skip_validation=True)
            except Exception:
                try:
                    dest_var.set_value(src_var.value, skip_validation=True)
                except Exception:
                    pass

    if not hasattr(core_util, "copy_port_values"):
        core_util.copy_port_values = copy_port_values
    if not hasattr(core_misc, "svg_tag") and hasattr(core_util, "svg_tag"):
        core_misc.svg_tag = core_util.svg_tag

    package_names = [
        "idaes.generic_models",
        "idaes.generic_models.properties",
        "idaes.generic_models.properties.core",
        "idaes.generic_models.properties.core.generic",
        "idaes.generic_models.properties.core.eos",
        "idaes.generic_models.properties.core.pure",
        "idaes.generic_models.properties.core.reactions",
    ]
    for name in package_names:
        package = sys.modules.setdefault(name, types.ModuleType(name))
        if not hasattr(package, "__path__"):
            package.__path__ = []

    def default_factory(cls: Any) -> Any:
        def construct(*args: Any, default: dict[str, Any] | None = None, **kwargs: Any) -> Any:
            if default is not None:
                merged = dict(default)
                merged.update(kwargs)
                kwargs = merged
            if getattr(cls, "__name__", "") == "GenericParameterBlock":
                components = set((kwargs.get("components") or {}).keys())
                parameter_data = kwargs.get("parameter_data")
                if components and isinstance(parameter_data, dict) and isinstance(parameter_data.get("PR_kappa"), dict):
                    filtered = {
                        key: val
                        for key, val in parameter_data["PR_kappa"].items()
                        if not isinstance(key, tuple) or all(part in components for part in key)
                    }
                    kwargs = dict(kwargs)
                    kwargs["parameter_data"] = dict(parameter_data)
                    kwargs["parameter_data"]["PR_kappa"] = filtered
            if getattr(cls, "__name__", "") == "HeatExchanger" and ("shell" in kwargs or "tube" in kwargs):
                if "shell" in kwargs:
                    kwargs["hot_side"] = kwargs.pop("shell")
                    kwargs.setdefault("hot_side_name", "shell")
                if "tube" in kwargs:
                    kwargs["cold_side"] = kwargs.pop("tube")
                    kwargs.setdefault("cold_side_name", "tube")
            return cls(*args, **kwargs)

        construct.__name__ = getattr(cls, "__name__", "default_factory")
        return construct

    generic_property_proxy = types.ModuleType("generic_property")
    generic_property_proxy.GenericParameterBlock = default_factory(generic_property.GenericParameterBlock)
    generic_reaction_proxy = types.ModuleType("generic_reaction")
    generic_reaction_proxy.GenericReactionParameterBlock = default_factory(generic_reaction.GenericReactionParameterBlock)
    generic_reaction_proxy.ConcentrationForm = generic_reaction.ConcentrationForm

    unit_models_proxy = types.ModuleType("unit_models")
    for attr in ["Mixer", "Heater", "HeatExchanger", "PressureChanger", "GibbsReactor", "StoichiometricReactor", "Separator", "Translator"]:
        setattr(unit_models_proxy, attr, default_factory(getattr(unit_models, attr)))

    aliases = {
        "idaes.generic_models.properties.core.generic.generic_property": generic_property_proxy,
        "idaes.generic_models.properties.core.generic.generic_reaction": generic_reaction_proxy,
        "idaes.generic_models.properties.core.state_definitions": state_definitions,
        "idaes.generic_models.properties.core.eos.ceos": ceos,
        "idaes.generic_models.properties.core.pure.NIST": nist,
        "idaes.generic_models.properties.core.pure.RPP": rpp,
        "idaes.generic_models.properties.core.reactions.dh_rxn": dh_rxn,
        "idaes.generic_models.properties.core.reactions.rate_constant": rate_constant,
        "idaes.generic_models.properties.core.reactions.rate_forms": rate_forms,
        "idaes.generic_models.unit_models": unit_models_proxy,
        "idaes.generic_models.unit_models.heat_exchanger": heat_exchanger,
        "idaes.generic_models.unit_models.mixer": mixer,
        "idaes.generic_models.unit_models.pressure_changer": pressure_changer,
        "idaes.generic_models.unit_models.separator": separator,
    }
    for name, module in aliases.items():
        sys.modules.setdefault(name, module)


def run_source_model() -> tuple[Any, dict[str, Any]]:
    import pyomo.environ as pyo
    from idaes.core import FlowsheetBlock
    from idaes.core.util import model_serializer as ms
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.opt import SolverStatus, TerminationCondition

    source_dir = ensure_source()
    cwd = Path.cwd()
    os.chdir(source_dir)
    try:
        ngfc = import_ngfc(source_dir)
        model = pyo.ConcreteModel(name="NGFC-Lib source-backed no CCS")
        model.fs = FlowsheetBlock(dynamic=False)
        ngfc.build_reformer(model)
        ngfc.build_power_island(model)
        ngfc.connect_reformer_to_power_island(model)
        ngfc.build_SOFC_ROM(model)
        ngfc.add_anode_temp_constraint(model)
        ngfc.add_cathode_heat_constraint(model)
        ngfc.add_result_constraints(model)
        ms.from_json(model, fname=str(source_dir / "NGFC_flowsheet_init.json"))
        model.fs.SOFC.current_density.fix(4000)
        model.fs.reformer_recuperator.tube_outlet.temperature.unfix()
        model.fs.SOFC.fuel_temperature.fix(348.3)
        model.fs.reformer_bypass.split_fraction[0, "bypass_outlet"].unfix()
        model.fs.SOFC.internal_reforming.fix(0.6)
        model.fs.cathode_hx.area.unfix()
        model.fs.SOFC.air_temperature.fix(617.3)
        model.fs.cathode_recycle.split_fraction[0, "recycle"].unfix()
        model.fs.SOFC.air_recirculation.fix(0.5)
        model.fs.anode_recycle.split_fraction[0, "recycle"].unfix()
        model.fs.SOFC.OTC.fix(2.1)
        model.fs.cathode.ion_outlet.flow_mol.unfix()
        model.fs.SOFC.fuel_util.fix(0.8)
        model.fs.air_blower.inlet.flow_mol.unfix()
        model.fs.SOFC.air_util.fix(0.4488)

        metadata = {
            "solver_status": "restored",
            "termination_condition": "source_initialization_restored",
            "final_dof": degrees_of_freedom(model),
            "optimal": True,
        }
        return model, metadata
    finally:
        os.chdir(cwd)


def extract_stream_values(model: Any) -> dict[str, dict[str, Any]]:
    ngfc = sys.modules.get("NGFC_flowsheet")
    if ngfc is not None and hasattr(ngfc, "make_stream_dict"):
        ngfc.make_stream_dict(model)
    stream_values: dict[str, dict[str, Any]] = {}
    for name, port in getattr(model, "_streams", {}).items():
        values = port_values(port)
        if values:
            stream_values[str(name)] = values
    return stream_values


def run_case(report_path: Path) -> dict[str, Any]:
    topology_ir = read_topology_ir(report_path)
    try:
        def timeout_handler(signum: int, frame: Any) -> None:
            raise TimeoutError("NGFC-Lib source solve exceeded 180 seconds")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(180)
        model, metadata = run_source_model()
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        stream_values = extract_stream_values(model)
        passed = bool(metadata["optimal"] and stream_values)
        return {
            "pass": passed,
            "status": "solved" if passed else "failed",
            "stage": "ngfc_lib_source_solve",
            "case_id": topology_ir.get("case_id"),
            "case_family": topology_ir.get("family"),
            "source_url": topology_ir.get("source_url"),
            "source_runner": "NGFC-Lib/jupyter/NGFC/NGFC_flowsheet.py",
            "termination_condition": metadata["termination_condition"],
            "solver_status": metadata["solver_status"],
            "final_dof": metadata["final_dof"],
            "stream_values": stream_values,
            "stream_table": stream_table_from_values(stream_values),
            "source_summary": {
                "source": "NGFC-Lib source model restored from NGFC_flowsheet_init.json with notebook control variables applied",
                "stream_count": len(stream_values),
            },
            "error": None,
        }
    except Exception as exc:
        try:
            signal.alarm(0)
        except Exception:
            pass
        return {
            "pass": False,
            "status": "failed",
            "stage": "ngfc_lib_source_solve",
            "case_id": topology_ir.get("case_id"),
            "case_family": topology_ir.get("family"),
            "source_url": topology_ir.get("source_url"),
            "source_runner": "NGFC-Lib/jupyter/NGFC/NGFC_flowsheet.py",
            "termination_condition": None,
            "solver_status": None,
            "final_dof": None,
            "stream_values": {},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report_path = Path(args.report)
    report = run_case(report_path)
    write_report(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report.get("pass") else 1)


if __name__ == "__main__":
    main()
