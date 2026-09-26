"""Native WaterTAP crystallization with explicit mother-liquor recycle equations."""

from __future__ import annotations

from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.core.util.scaling as iscale
from pyomo.environ import ConcreteModel, Constraint, Param, SolverFactory, value
from watertap.property_models.unit_specific import cryst_prop_pack as props
from watertap.unit_models.crystallizer import Crystallization


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    fs = model.fs
    fs.properties = props.NaClParameterBlock()
    fs.C101 = Crystallization(property_package=fs.properties)
    fs.fresh_nacl = Param(initialize=10.5119)
    fs.fresh_water = Param(initialize=38.9326)
    fs.recycle_fraction = Param(initialize=0.80)

    fs.eq_mother_liquor_recycle_nacl = Constraint(
        expr=fs.C101.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"]
        == fs.fresh_nacl
        + fs.recycle_fraction
        * fs.C101.outlet.flow_mass_phase_comp[0, "Liq", "NaCl"]
    )
    fs.eq_mother_liquor_recycle_water = Constraint(
        expr=fs.C101.inlet.flow_mass_phase_comp[0, "Liq", "H2O"]
        == fs.fresh_water
        + fs.recycle_fraction
        * fs.C101.outlet.flow_mass_phase_comp[0, "Liq", "H2O"]
    )
    return model


def _set_scaling(model):
    fs = model.fs
    fs.properties.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Liq", "H2O"))
    fs.properties.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Liq", "NaCl"))
    fs.properties.set_default_scaling("flow_mass_phase_comp", 1, index=("Vap", "H2O"))
    fs.properties.set_default_scaling("flow_mass_phase_comp", 1e-1, index=("Sol", "NaCl"))
    c = fs.C101
    iscale.set_scaling_factor(c.pressure_operating, 1e-3)
    iscale.set_scaling_factor(c.properties_out[0].pressure, 1e-5)
    iscale.set_scaling_factor(c.properties_solids[0].pressure, 1e-5)
    iscale.set_scaling_factor(c.properties_vapor[0].pressure, 1e-3)
    iscale.set_scaling_factor(c.properties_out[0].flow_vol_phase["Liq"], 1e3)
    iscale.set_scaling_factor(c.properties_out[0].flow_vol_phase["Vap"], 1e8)
    iscale.set_scaling_factor(c.properties_out[0].flow_vol_phase["Sol"], 1e12)
    iscale.set_scaling_factor(c.properties_solids[0].flow_vol_phase["Liq"], 1e11)
    iscale.set_scaling_factor(c.properties_solids[0].flow_vol_phase["Vap"], 1e8)
    iscale.set_scaling_factor(c.properties_vapor[0].flow_vol_phase["Liq"], 1e11)
    iscale.set_scaling_factor(c.properties_vapor[0].flow_vol_phase["Sol"], 1e12)
    iscale.constraint_scaling_transform(fs.eq_mother_liquor_recycle_nacl, 1e-1)
    iscale.constraint_scaling_transform(fs.eq_mother_liquor_recycle_water, 1e-1)
    iscale.calculate_scaling_factors(fs)


def set_operating_conditions(model):
    fs = model.fs
    eps = 1e-6
    fs.C101.inlet.flow_mass_phase_comp[0, "Sol", "NaCl"].fix(eps)
    fs.C101.inlet.flow_mass_phase_comp[0, "Vap", "H2O"].fix(eps)
    fs.C101.inlet.pressure[0].fix(101325)
    fs.C101.inlet.temperature[0].fix(293.15)
    fs.C101.temperature_operating.fix(328.15)
    fs.C101.crystallization_yield["NaCl"].fix(0.40)
    fs.C101.crystal_growth_rate.fix()
    fs.C101.souders_brown_constant.fix()
    fs.C101.crystal_median_length.fix()
    _set_scaling(model)
    dof = degrees_of_freedom(model)
    if dof != 0:
        raise RuntimeError(f"Recycle crystallization specification has {dof} DoF, expected 0")


def initialize_model(model):
    fs = model.fs
    c = fs.C101
    fs.eq_mother_liquor_recycle_nacl.deactivate()
    fs.eq_mother_liquor_recycle_water.deactivate()
    c.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"].fix(20.22)
    c.inlet.flow_mass_phase_comp[0, "Liq", "H2O"].fix(55.0)
    c.initialize()
    c.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"].unfix()
    c.inlet.flow_mass_phase_comp[0, "Liq", "H2O"].unfix()
    fs.eq_mother_liquor_recycle_nacl.activate()
    fs.eq_mother_liquor_recycle_water.activate()


def solve_model(model, tee=False):
    solver = SolverFactory("ipopt")
    solver.options["tol"] = 1e-7
    solver.options["max_iter"] = 800
    return solver.solve(model, tee=tee)


def metrics(model):
    fs = model.fs
    c = fs.C101
    fresh_nacl = value(fs.fresh_nacl)
    crystal_nacl = value(c.solids.flow_mass_phase_comp[0, "Sol", "NaCl"])
    mother_nacl = value(c.outlet.flow_mass_phase_comp[0, "Liq", "NaCl"])
    recycle_nacl = value(fs.recycle_fraction) * mother_nacl
    purge_nacl = (1 - value(fs.recycle_fraction)) * mother_nacl
    c_feed_nacl = value(c.inlet.flow_mass_phase_comp[0, "Liq", "NaCl"])
    return {
        "fresh_feed_nacl_kg_s": fresh_nacl,
        "crystallizer_feed_nacl_kg_s": c_feed_nacl,
        "nacl_crystals_kg_s": crystal_nacl,
        "nacl_purge_kg_s": purge_nacl,
        "nacl_recycle_kg_s": recycle_nacl,
        "single_pass_nacl_recovery": crystal_nacl / c_feed_nacl,
        "overall_fresh_feed_nacl_recovery": crystal_nacl / fresh_nacl,
        "nacl_recycle_ratio": recycle_nacl / fresh_nacl,
        "mother_liquor_purge_fraction": 1 - value(fs.recycle_fraction),
        "steady_state_nacl_balance_error_kg_s": fresh_nacl - crystal_nacl - purge_nacl,
        "water_vapor_kg_s": value(c.vapor.flow_mass_phase_comp[0, "Vap", "H2O"]),
        "crystallizer_heat_duty_kW": value(c.work_mechanical[0]),
        "recycle_conditioner_pressure_rise_Pa": 101325 - value(c.outlet.pressure[0]),
    }
