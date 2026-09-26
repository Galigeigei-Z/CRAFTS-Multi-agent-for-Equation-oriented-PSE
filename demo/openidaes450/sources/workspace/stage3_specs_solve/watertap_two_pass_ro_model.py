"""Native WaterTAP model for two-pass permeate-polishing reverse osmosis."""

from __future__ import annotations

from idaes.core import FlowsheetBlock
from idaes.core.util.initialization import propagate_state
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.core.util.scaling as iscale
from idaes.models.unit_models import Feed, Product
from pyomo.environ import ConcreteModel, TransformationFactory, value
from pyomo.network import Arc
from watertap.core.solvers import get_solver
import watertap.property_models.NaCl_prop_pack as props
from watertap.unit_models.pressure_changer import Pump
from watertap.unit_models.reverse_osmosis_0D import (
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType,
    ReverseOsmosis0D,
)


def _ro(property_package):
    return ReverseOsmosis0D(
        property_package=property_package,
        has_pressure_change=True,
        pressure_change_type=PressureChangeType.fixed_per_stage,
        mass_transfer_coefficient=MassTransferCoefficient.none,
        concentration_polarization_type=ConcentrationPolarizationType.fixed,
    )


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    fs = model.fs
    fs.properties = props.NaClParameterBlock()

    fs.feed = Feed(property_package=fs.properties)
    fs.P1 = Pump(property_package=fs.properties)
    fs.RO1 = _ro(fs.properties)
    fs.first_pass_brine = Product(property_package=fs.properties)
    fs.P2 = Pump(property_package=fs.properties)
    fs.RO2 = _ro(fs.properties)
    fs.product = Product(property_package=fs.properties)
    fs.second_pass_brine = Product(property_package=fs.properties)

    fs.s01 = Arc(source=fs.feed.outlet, destination=fs.P1.inlet)
    fs.s02 = Arc(source=fs.P1.outlet, destination=fs.RO1.inlet)
    fs.s03 = Arc(source=fs.RO1.retentate, destination=fs.first_pass_brine.inlet)
    fs.s04 = Arc(source=fs.RO1.permeate, destination=fs.P2.inlet)
    fs.s05 = Arc(source=fs.P2.outlet, destination=fs.RO2.inlet)
    fs.s06 = Arc(source=fs.RO2.permeate, destination=fs.product.inlet)
    fs.s07 = Arc(source=fs.RO2.retentate, destination=fs.second_pass_brine.inlet)
    TransformationFactory("network.expand_arcs").apply_to(model)

    for pump in (fs.P1, fs.P2):
        iscale.set_scaling_factor(pump.control_volume.work, 1e-3)
        iscale.set_scaling_factor(pump.work_fluid[0], 1)
    for ro in (fs.RO1, fs.RO2):
        iscale.set_scaling_factor(ro.area, 1e-2)
        iscale.set_scaling_factor(ro.mass_transfer_phase_comp[0, "Liq", "NaCl"], 1e5)
        iscale.set_scaling_factor(ro.feed_side.mass_transfer_term[0, "Liq", "NaCl"], 1e5)
    return model


def set_operating_conditions(
    model,
    flow_vol_m3_s=1e-3,
    feed_nacl_mass_fraction=2e-3,
):
    fs = model.fs
    fs.feed.properties[0].pressure.fix(101325)
    fs.feed.properties[0].temperature.fix(298.15)
    fs.properties.set_default_scaling(
        "flow_mass_phase_comp", 1000 * flow_vol_m3_s, index=("Liq", "H2O")
    )
    fs.properties.set_default_scaling(
        "flow_mass_phase_comp",
        1 / (1000 * flow_vol_m3_s * feed_nacl_mass_fraction),
        index=("Liq", "NaCl"),
    )
    fs.feed.properties[0].flow_vol_phase["Liq"]
    fs.feed.properties[0].mass_frac_phase_comp["Liq", "NaCl"]
    fs.feed.properties.calculate_state(
        var_args={
            ("flow_vol_phase", "Liq"): flow_vol_m3_s,
            ("mass_frac_phase_comp", ("Liq", "NaCl")): feed_nacl_mass_fraction,
        },
        hold_state=True,
    )

    fs.P1.efficiency_pump.fix(0.80)
    fs.P1.control_volume.properties_out[0].pressure.fix(2.0e6)
    fs.P2.efficiency_pump.fix(0.80)
    fs.P2.control_volume.properties_out[0].pressure.fix(1.0e6)

    for ro in (fs.RO1, fs.RO2):
        ro.A_comp.fix(4.2e-12)
        ro.B_comp.fix(3.5e-8)
        ro.permeate.pressure[0].fix(101325)
        ro.feed_side.cp_modulus.fix(1.1)
        ro.deltaP.fix(-1e5)
    fs.RO1.B_comp.fix(3.5e-6)
    fs.RO1.area.fix(70)
    fs.RO2.area.fix(100)

    iscale.calculate_scaling_factors(model)
    if degrees_of_freedom(model) != 0:
        raise RuntimeError(f"Two-pass RO specification has {degrees_of_freedom(model)} DoF, expected 0")


def initialize_model(model, solver=None):
    if solver is None:
        solver = get_solver()
    fs = model.fs
    optarg = solver.options

    fs.feed.initialize(optarg=optarg)
    propagate_state(fs.s01)
    fs.P1.initialize(optarg=optarg)
    propagate_state(fs.s02)
    fs.RO1.initialize(optarg=optarg)
    propagate_state(fs.s04)
    fs.P2.initialize(optarg=optarg)
    propagate_state(fs.s05)
    fs.RO2.initialize(optarg=optarg)


def solve_model(model, solver=None, tee=False):
    if solver is None:
        solver = get_solver()
    return solver.solve(model, tee=tee)


def metrics(model):
    fs = model.fs
    feed_water = value(fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"])
    product_water = value(fs.RO2.mixed_permeate[0].flow_mass_phase_comp["Liq", "H2O"])
    product_flow = value(fs.RO2.mixed_permeate[0].flow_vol_phase["Liq"])
    pump_work = value(fs.P1.work_mechanical[0] + fs.P2.work_mechanical[0])
    first_pass_salinity = value(fs.RO1.mixed_permeate[0].mass_frac_phase_comp["Liq", "NaCl"])
    final_salinity = value(fs.RO2.mixed_permeate[0].mass_frac_phase_comp["Liq", "NaCl"])
    return {
        "feed_nacl_mass_fraction": value(fs.feed.properties[0].mass_frac_phase_comp["Liq", "NaCl"]),
        "first_pass_permeate_nacl_mass_fraction": first_pass_salinity,
        "final_product_nacl_mass_fraction": final_salinity,
        "permeate_polishing_factor": first_pass_salinity / final_salinity,
        "first_pass_water_recovery": value(fs.RO1.recovery_mass_phase_comp[0, "Liq", "H2O"]),
        "second_pass_water_recovery": value(fs.RO2.recovery_mass_phase_comp[0, "Liq", "H2O"]),
        "overall_water_recovery": product_water / feed_water,
        "first_pass_membrane_area_m2": value(fs.RO1.area),
        "second_pass_membrane_area_m2": value(fs.RO2.area),
        "first_pass_pump_work_W": value(fs.P1.work_mechanical[0]),
        "second_pass_pump_work_W": value(fs.P2.work_mechanical[0]),
        "total_pump_work_W": pump_work,
        "specific_energy_consumption_kWh_m3": pump_work / product_flow / 3.6e6,
    }
