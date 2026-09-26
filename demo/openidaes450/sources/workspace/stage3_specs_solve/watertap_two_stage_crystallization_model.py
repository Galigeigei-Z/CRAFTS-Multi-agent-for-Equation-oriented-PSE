"""Native WaterTAP model for staged NaCl crystallization of mother liquor."""

from __future__ import annotations

from idaes.core import FlowsheetBlock
from idaes.core.util.initialization import propagate_state
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.core.util.scaling as iscale
from pyomo.environ import ConcreteModel, TransformationFactory, value
from pyomo.network import Arc
from watertap.core.solvers import get_solver
from watertap.property_models.unit_specific import cryst_prop_pack as props
from watertap.unit_models.crystallizer import Crystallization


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = props.NaClParameterBlock()
    model.fs.C1 = Crystallization(property_package=model.fs.properties)
    model.fs.C2 = Crystallization(property_package=model.fs.properties)
    model.fs.mother_liquor_to_C2 = Arc(source=model.fs.C1.outlet, destination=model.fs.C2.inlet)
    TransformationFactory("network.expand_arcs").apply_to(model)
    return model


def _set_scaling(model):
    prop = model.fs.properties
    prop.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Liq", "H2O"))
    prop.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Liq", "NaCl"))
    prop.set_default_scaling("flow_mass_phase_comp", 1, index=("Vap", "H2O"))
    prop.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Sol", "NaCl"))
    for unit in (model.fs.C1, model.fs.C2):
        iscale.set_scaling_factor(unit.pressure_operating, 1e-3)
        iscale.set_scaling_factor(unit.properties_out[0].pressure, 1e-5)
        iscale.set_scaling_factor(unit.properties_solids[0].pressure, 1e-5)
        iscale.set_scaling_factor(unit.properties_vapor[0].pressure, 1e-3)
        iscale.set_scaling_factor(unit.properties_out[0].flow_vol_phase["Liq"], 1e3)
        iscale.set_scaling_factor(unit.properties_out[0].flow_vol_phase["Vap"], 1e8)
        iscale.set_scaling_factor(unit.properties_out[0].flow_vol_phase["Sol"], 1e12)
        iscale.set_scaling_factor(unit.properties_solids[0].flow_vol_phase["Liq"], 1e11)
        iscale.set_scaling_factor(unit.properties_solids[0].flow_vol_phase["Vap"], 1e8)
        iscale.set_scaling_factor(unit.properties_vapor[0].flow_vol_phase["Liq"], 1e11)
        iscale.set_scaling_factor(unit.properties_vapor[0].flow_vol_phase["Sol"], 1e12)
    iscale.calculate_scaling_factors(model.fs)


def set_operating_conditions(model):
    fs = model.fs
    eps = 1e-6
    fs.C1.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"].fix(10.5119)
    fs.C1.inlet.flow_mass_phase_comp[0, "Liq", "H2O"].fix(38.9326)
    fs.C1.inlet.flow_mass_phase_comp[0, "Sol", "NaCl"].fix(eps)
    fs.C1.inlet.flow_mass_phase_comp[0, "Vap", "H2O"].fix(eps)
    fs.C1.inlet.pressure[0].fix(101325)
    fs.C1.inlet.temperature[0].fix(293.15)

    for unit, temperature in ((fs.C1, 328.15), (fs.C2, 318.15)):
        unit.temperature_operating.fix(temperature)
        unit.crystallization_yield["NaCl"].fix(0.40)
        unit.crystal_growth_rate.fix()
        unit.souders_brown_constant.fix()
        unit.crystal_median_length.fix()

    _set_scaling(model)
    dof = degrees_of_freedom(model)
    if dof != 0:
        raise RuntimeError(f"Two-stage crystallization specification has {dof} DoF, expected 0")


def initialize_model(model):
    model.fs.C1.initialize()
    propagate_state(model.fs.mother_liquor_to_C2)
    model.fs.C2.initialize()


def solve_model(model, tee=False):
    return get_solver().solve(model, tee=tee)


def metrics(model):
    fs = model.fs
    feed_nacl = value(fs.C1.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"])
    c1_solid = value(fs.C1.solids.flow_mass_phase_comp[0, "Sol", "NaCl"])
    c2_solid = value(fs.C2.solids.flow_mass_phase_comp[0, "Sol", "NaCl"])
    c1_liquid_nacl = value(fs.C1.outlet.flow_mass_phase_comp[0, "Liq", "NaCl"])
    c2_liquid_nacl = value(fs.C2.outlet.flow_mass_phase_comp[0, "Liq", "NaCl"])
    return {
        "feed_nacl_kg_s": feed_nacl,
        "stage1_nacl_crystals_kg_s": c1_solid,
        "stage2_incremental_nacl_crystals_kg_s": c2_solid,
        "total_nacl_crystals_kg_s": c1_solid + c2_solid,
        "stage1_nacl_recovery": c1_solid / feed_nacl,
        "stage2_mother_liquor_nacl_recovery": c2_solid / c1_liquid_nacl,
        "overall_nacl_recovery": (c1_solid + c2_solid) / feed_nacl,
        "stage1_mother_liquor_nacl_kg_s": c1_liquid_nacl,
        "final_mother_liquor_nacl_kg_s": c2_liquid_nacl,
        "stage1_vapor_h2o_kg_s": value(fs.C1.vapor.flow_mass_phase_comp[0, "Vap", "H2O"]),
        "stage2_vapor_h2o_kg_s": value(fs.C2.vapor.flow_mass_phase_comp[0, "Vap", "H2O"]),
        "stage1_heat_duty_kW": value(fs.C1.work_mechanical[0]),
        "stage2_heat_duty_kW": value(fs.C2.work_mechanical[0]),
        "stage1_temperature_K": value(fs.C1.temperature_operating),
        "stage2_temperature_K": value(fs.C2.temperature_operating),
    }
