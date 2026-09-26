"""Native two-bed methanol synthesis with interstage cooling."""

from __future__ import annotations

import idaes.logger as idaeslog
from idaes.core import FlowsheetBlock
from idaes.core.util.initialization import propagate_state
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock
from idaes.models.properties.modular_properties.base.generic_reaction import GenericReactionParameterBlock
from idaes.models.unit_models import Compressor, Feed, Flash, Heater, Mixer, Product, StoichiometricReactor, Turbine
from idaes.models.unit_models.mixer import MomentumMixingType
from idaes.models.unit_models.pressure_changer import ThermodynamicAssumption
from idaes_examples.mod.methanol import (
    methanol_ideal_VLE as thermo_props_VLE,
    methanol_ideal_vapor as thermo_props_vapor,
    methanol_reactions as reaction_props,
)
from pyomo.environ import ConcreteModel, Constraint, SolverFactory, TerminationCondition, TransformationFactory, Var, units as pyunits
from pyomo.network import Arc
from pyomo.util.check_units import assert_units_consistent


def add_conversion_constraint(reactor, name: str, initial: float = 0.5):
    conversion = Var(initialize=initial, bounds=(0, 1))
    reactor.add_component(name, conversion)
    inlet_co = reactor.inlet.flow_mol[0] * reactor.inlet.mole_frac_comp[0, "CO"]
    outlet_co = reactor.outlet.flow_mol[0] * reactor.outlet.mole_frac_comp[0, "CO"]
    reactor.add_component(
        f"{name}_constraint",
        Constraint(expr=conversion == (inlet_co - outlet_co) / inlet_co),
    )
    return conversion


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.thermo_params_vapor = GenericParameterBlock(**thermo_props_vapor.config_dict)
    model.fs.thermo_params_VLE = GenericParameterBlock(**thermo_props_VLE.config_dict)
    model.fs.reaction_params = GenericReactionParameterBlock(
        property_package=model.fs.thermo_params_vapor,
        **reaction_props.config_dict,
    )

    model.fs.H2 = Feed(property_package=model.fs.thermo_params_vapor)
    model.fs.CO = Feed(property_package=model.fs.thermo_params_vapor)
    model.fs.M101 = Mixer(
        property_package=model.fs.thermo_params_vapor,
        inlet_list=["H2_feed", "CO_feed"],
        momentum_mixing_type=MomentumMixingType.minimize,
        has_phase_equilibrium=True,
    )
    model.fs.C101 = Compressor(
        property_package=model.fs.thermo_params_vapor,
        thermodynamic_assumption=ThermodynamicAssumption.isothermal,
    )
    model.fs.H101 = Heater(property_package=model.fs.thermo_params_vapor, has_pressure_change=False)
    model.fs.R101 = StoichiometricReactor(
        property_package=model.fs.thermo_params_vapor,
        reaction_package=model.fs.reaction_params,
        has_heat_of_reaction=True,
        has_heat_transfer=True,
        has_pressure_change=False,
    )
    model.fs.H103 = Heater(property_package=model.fs.thermo_params_vapor, has_pressure_change=False)
    model.fs.R102 = StoichiometricReactor(
        property_package=model.fs.thermo_params_vapor,
        reaction_package=model.fs.reaction_params,
        has_heat_of_reaction=True,
        has_heat_transfer=True,
        has_pressure_change=False,
    )
    model.fs.T101 = Turbine(dynamic=False, property_package=model.fs.thermo_params_vapor)
    model.fs.H102 = Heater(property_package=model.fs.thermo_params_vapor, has_pressure_change=False)
    model.fs.F101 = Flash(
        property_package=model.fs.thermo_params_VLE,
        has_heat_transfer=True,
        has_pressure_change=True,
    )
    model.fs.EXHAUST = Product(property_package=model.fs.thermo_params_VLE)
    model.fs.CH3OH = Product(property_package=model.fs.thermo_params_VLE)

    connections = [
        ("s01", model.fs.H2.outlet, model.fs.M101.H2_feed),
        ("s02", model.fs.CO.outlet, model.fs.M101.CO_feed),
        ("s03", model.fs.M101.outlet, model.fs.C101.inlet),
        ("s04", model.fs.C101.outlet, model.fs.H101.inlet),
        ("s05", model.fs.H101.outlet, model.fs.R101.inlet),
        ("s06", model.fs.R101.outlet, model.fs.H103.inlet),
        ("s07", model.fs.H103.outlet, model.fs.R102.inlet),
        ("s08", model.fs.R102.outlet, model.fs.T101.inlet),
        ("s09", model.fs.T101.outlet, model.fs.H102.inlet),
        ("s10", model.fs.H102.outlet, model.fs.F101.inlet),
        ("s11", model.fs.F101.vap_outlet, model.fs.EXHAUST.inlet),
        ("s12", model.fs.F101.liq_outlet, model.fs.CH3OH.inlet),
    ]
    for name, source, destination in connections:
        model.fs.add_component(name, Arc(source=source, destination=destination))
    TransformationFactory("network.expand_arcs").apply_to(model)

    add_conversion_constraint(model.fs.R101, "co_conversion", 0.5)
    add_conversion_constraint(model.fs.R102, "co_conversion", 0.5)
    return model


def set_feed(port, *, flow: float, h2: float, co: float, enthalpy: float):
    port.flow_mol[0].fix(flow)
    port.pressure[0].fix(3_000_000)
    port.enth_mol[0].fix(enthalpy)
    port.mole_frac_comp[0, "H2"].fix(h2)
    port.mole_frac_comp[0, "CO"].fix(co)
    port.mole_frac_comp[0, "CH3OH"].fix(1e-6)
    port.mole_frac_comp[0, "CH4"].fix(1e-6)


def set_operating_conditions(model):
    set_feed(model.fs.H2.outlet, flow=637.2, h2=1.0, co=1e-6, enthalpy=-142.4)
    set_feed(model.fs.CO.outlet, flow=316.8, h2=1e-6, co=1.0, enthalpy=-110676.4)
    model.fs.C101.outlet.pressure[0].fix(5_100_000)

    model.fs.H101.outlet_temperature = Constraint(
        expr=model.fs.H101.control_volume.properties_out[0].temperature == 488.15 * pyunits.K
    )
    model.fs.R101.co_conversion.fix(0.50)
    model.fs.R101.outlet_temperature = Constraint(
        expr=model.fs.R101.control_volume.properties_out[0].temperature == 507.15 * pyunits.K
    )
    model.fs.R101.heat_duty.setub(0)

    model.fs.H103.outlet_temperature = Constraint(
        expr=model.fs.H103.control_volume.properties_out[0].temperature == 488.15 * pyunits.K
    )
    model.fs.R102.co_conversion.fix(0.50)
    model.fs.R102.outlet_temperature = Constraint(
        expr=model.fs.R102.control_volume.properties_out[0].temperature == 507.15 * pyunits.K
    )
    model.fs.R102.heat_duty.setub(0)

    model.fs.T101.deltaP.fix(-2_000_000)
    model.fs.T101.efficiency_isentropic.fix(0.9)
    model.fs.H102.outlet_temperature = Constraint(
        expr=model.fs.H102.control_volume.properties_out[0].temperature == 407.15 * pyunits.K
    )
    model.fs.F101.deltaP.fix(0)
    model.fs.F101.outlet_temperature = Constraint(
        expr=model.fs.F101.control_volume.properties_out[0].temperature == 407.15 * pyunits.K
    )
    return model


def initialize_model(model):
    ordered = [
        (model.fs.H2, model.fs.s01),
        (model.fs.CO, model.fs.s02),
        (model.fs.M101, model.fs.s03),
        (model.fs.C101, model.fs.s04),
        (model.fs.H101, model.fs.s05),
        (model.fs.R101, model.fs.s06),
        (model.fs.H103, model.fs.s07),
        (model.fs.R102, model.fs.s08),
        (model.fs.T101, model.fs.s09),
        (model.fs.H102, model.fs.s10),
        (model.fs.F101, model.fs.s11),
        (model.fs.EXHAUST, None),
    ]
    for unit, outgoing in ordered:
        unit.initialize(outlvl=idaeslog.WARNING)
        if outgoing is not None:
            propagate_state(outgoing)
    propagate_state(model.fs.s12)
    model.fs.CH3OH.initialize(outlvl=idaeslog.WARNING)
    for arc in model.fs.component_data_objects(Arc):
        arc.destination.unfix()
    return model


def solve_model(model, *, tee: bool = False):
    assert_units_consistent(model)
    solver = SolverFactory("ipopt")
    solver.options.update(
        {"tol": 1e-7, "max_iter": 1500, "bound_push": 1e-8, "bound_frac": 1e-8, "mu_init": 1e-6}
    )
    result = solver.solve(model, tee=tee)
    assert result.solver.termination_condition == TerminationCondition.optimal
    return result


def main(*, tee: bool = False):
    model = build_model()
    set_operating_conditions(model)
    initialize_model(model)
    result = solve_model(model, tee=tee)
    return model, result


if __name__ == "__main__":
    main(tee=True)
