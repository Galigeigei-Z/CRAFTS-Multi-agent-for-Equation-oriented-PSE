"""Native WaterTAP single-unit model for ASM1 waste-sludge dewatering."""

from __future__ import annotations

from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.core.util.scaling as iscale
from pyomo.environ import ConcreteModel, units, value
from watertap.core.solvers import get_solver
from watertap.property_models.unit_specific.activated_sludge.asm1_properties import (
    ASM1ParameterBlock,
)
from watertap.unit_models.dewatering import DewateringUnit


PARTICULATE_COMPONENTS = ("X_I", "X_S", "X_BH", "X_BA", "X_P", "X_ND")
FEED_CONCENTRATIONS_MG_L = {
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


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = ASM1ParameterBlock()
    model.fs.dewaterer = DewateringUnit(property_package=model.fs.properties)
    return model


def set_operating_conditions(model):
    unit = model.fs.dewaterer
    unit.inlet.flow_vol.fix(178.4674 * units.m**3 / units.day)
    unit.inlet.temperature.fix(308.15 * units.K)
    unit.inlet.pressure.fix(1 * units.atm)
    for component, concentration in FEED_CONCENTRATIONS_MG_L.items():
        unit.inlet.conc_mass_comp[0, component].fix(
            concentration * units.mg / units.liter
        )
    unit.inlet.alkalinity.fix(97.8459 * units.mol / units.m**3)
    unit.hydraulic_retention_time.fix(1800 * units.s)

    # These are the native BSM2 dewaterer correlations: 98% TSS capture and
    # 28 wt% dry solids in the underflow cake.
    unit.TSS_rem.set_value(0.98)
    unit.p_dewat.set_value(0.28)
    iscale.calculate_scaling_factors(model)

    dof = degrees_of_freedom(model)
    if dof != 0:
        raise RuntimeError(f"ASM1 dewatering specification has {dof} DoF, expected 0")


def initialize_model(model):
    model.fs.dewaterer.initialize()


def solve_model(model, tee=False):
    return get_solver().solve(model, tee=tee)


def _particulate_mass_flow(port):
    return value(
        port.flow_vol[0]
        * sum(port.conc_mass_comp[0, component] for component in PARTICULATE_COMPONENTS)
    )


def metrics(model):
    unit = model.fs.dewaterer
    density = value(model.fs.properties.dens_mass)
    feed_flow = value(unit.inlet.flow_vol[0])
    overflow_flow = value(unit.overflow.flow_vol[0])
    underflow_flow = value(unit.underflow.flow_vol[0])
    feed_particulate = _particulate_mass_flow(unit.inlet)
    overflow_particulate = _particulate_mass_flow(unit.overflow)
    underflow_particulate = _particulate_mass_flow(unit.underflow)
    # ASM1 defines TSS as 0.75 times the particulate component concentration.
    feed_tss = 0.75 * feed_particulate
    overflow_tss = 0.75 * overflow_particulate
    underflow_tss = 0.75 * underflow_particulate
    cake_wet_mass = underflow_flow * density
    return {
        "feed_flow_m3_day": feed_flow * 86400.0,
        "overflow_filtrate_flow_m3_day": overflow_flow * 86400.0,
        "underflow_cake_flow_m3_day": underflow_flow * 86400.0,
        "filtrate_hydraulic_recovery": overflow_flow / feed_flow,
        "tss_feed_kg_day": feed_tss * 86400.0,
        "tss_to_cake_kg_day": underflow_tss * 86400.0,
        "tss_to_filtrate_kg_day": overflow_tss * 86400.0,
        "tss_capture_fraction": underflow_tss / feed_tss,
        "filtrate_tss_rejection": 1.0 - overflow_tss / feed_tss,
        "cake_dry_solids_mass_fraction": underflow_tss / cake_wet_mass,
        "cake_tss_concentration_kg_m3": underflow_tss / underflow_flow,
        "filtrate_tss_concentration_kg_m3": overflow_tss / overflow_flow,
        "electricity_consumption_kw": value(unit.electricity_consumption[0]),
        "specific_electricity_kwh_m3_feed": value(
            unit.energy_electric_flow_vol_inlet[0]
        ),
        "vessel_volume_m3": value(unit.volume[0]),
        "hydraulic_balance_residual_m3_s": feed_flow - overflow_flow - underflow_flow,
        "particulate_balance_residual_kg_s": (
            feed_particulate - overflow_particulate - underflow_particulate
        ),
    }
