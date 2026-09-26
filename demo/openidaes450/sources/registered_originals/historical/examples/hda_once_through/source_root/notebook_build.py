"""Native IDAES HDA once-through variants with one or two flash stages."""

from __future__ import annotations

import idaes.logger as idaeslog
from idaes.core import FlowsheetBlock
from idaes.core.util.initialization import propagate_state
from idaes.models.unit_models import Flash, Heater, Mixer, StoichiometricReactor
from pyomo.environ import ConcreteModel, Constraint, SolverFactory, TerminationCondition, TransformationFactory, Var
from pyomo.network import Arc
from pyomo.util.check_units import assert_units_consistent

import hda_ideal_VLE as thermo_props
import hda_reaction as reaction_props


def build_model(*, second_flash: bool):
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.thermo_params = thermo_props.HDAParameterBlock()
    model.fs.reaction_params = reaction_props.HDAReactionParameterBlock(
        property_package=model.fs.thermo_params
    )

    model.fs.M101 = Mixer(
        property_package=model.fs.thermo_params,
        inlet_list=["toluene_feed", "hydrogen_feed"],
    )
    model.fs.H101 = Heater(
        property_package=model.fs.thermo_params,
        has_pressure_change=False,
        has_phase_equilibrium=True,
    )
    model.fs.R101 = StoichiometricReactor(
        property_package=model.fs.thermo_params,
        reaction_package=model.fs.reaction_params,
        has_heat_of_reaction=True,
        has_heat_transfer=True,
        has_pressure_change=False,
    )
    model.fs.F101 = Flash(
        property_package=model.fs.thermo_params,
        has_heat_transfer=True,
        has_pressure_change=True,
    )
    if second_flash:
        model.fs.F102 = Flash(
            property_package=model.fs.thermo_params,
            has_heat_transfer=True,
            has_pressure_change=True,
        )

    model.fs.s01 = Arc(source=model.fs.M101.outlet, destination=model.fs.H101.inlet)
    model.fs.s02 = Arc(source=model.fs.H101.outlet, destination=model.fs.R101.inlet)
    model.fs.s03 = Arc(source=model.fs.R101.outlet, destination=model.fs.F101.inlet)
    if second_flash:
        model.fs.s04 = Arc(source=model.fs.F101.liq_outlet, destination=model.fs.F102.inlet)
    TransformationFactory("network.expand_arcs").apply_to(model)

    model.fs.R101.conversion = Var(initialize=0.50, bounds=(0, 1))
    model.fs.R101.conversion_constraint = Constraint(
        expr=model.fs.R101.conversion
        == (
            model.fs.R101.inlet.flow_mol_phase_comp[0, "Vap", "toluene"]
            - model.fs.R101.outlet.flow_mol_phase_comp[0, "Vap", "toluene"]
        )
        / model.fs.R101.inlet.flow_mol_phase_comp[0, "Vap", "toluene"]
    )
    return model


def set_operating_conditions(model, *, second_flash: bool):
    phases = ("Liq", "Vap")
    components = ("benzene", "toluene", "hydrogen", "methane")
    for phase in phases:
        for component in components:
            model.fs.M101.toluene_feed.flow_mol_phase_comp[0, phase, component].fix(1e-5)
            model.fs.M101.hydrogen_feed.flow_mol_phase_comp[0, phase, component].fix(1e-5)

    model.fs.M101.toluene_feed.flow_mol_phase_comp[0, "Liq", "toluene"].fix(0.30)
    model.fs.M101.hydrogen_feed.flow_mol_phase_comp[0, "Vap", "hydrogen"].fix(0.30)
    model.fs.M101.hydrogen_feed.flow_mol_phase_comp[0, "Vap", "methane"].fix(0.02)
    for inlet in (model.fs.M101.toluene_feed, model.fs.M101.hydrogen_feed):
        inlet.temperature[0].fix(303.2)
        inlet.pressure[0].fix(350000)

    model.fs.H101.outlet.temperature[0].fix(600)
    # The once-through reactor uses a conservative per-pass conversion. The
    # recycle cases can sustain the higher 0.75 target because unused hydrogen
    # is returned to the reactor loop.
    model.fs.R101.conversion.fix(0.50)
    model.fs.R101.heat_duty.fix(0)
    model.fs.F101.vap_outlet.temperature[0].fix(325.0)
    model.fs.F101.deltaP.fix(0)
    if second_flash:
        # A deeper pressure let-down and moderate reheat are required for the
        # once-through, toluene-richer liquid. Reusing the recycle case's
        # 375 K/150 kPa condition produces essentially no second-stage vapor.
        model.fs.F102.vap_outlet.temperature[0].fix(375.0)
        model.fs.F102.deltaP.fix(-225000)
    return model


def initialize_model(model):
    def initialize_unit(unit):
        try:
            unit.default_initializer().initialize(unit, output_level=idaeslog.WARNING)
        except Exception:
            SolverFactory("ipopt").solve(unit, tee=False)

    initialize_unit(model.fs.M101)
    propagate_state(model.fs.s01)
    initialize_unit(model.fs.H101)
    propagate_state(model.fs.s02)
    initialize_unit(model.fs.R101)
    propagate_state(model.fs.s03)
    initialize_unit(model.fs.F101)
    if hasattr(model.fs, "F102"):
        propagate_state(model.fs.s04)
        initialize_unit(model.fs.F102)
        model.fs.F102.inlet.unfix()
    # propagate_state fixes destination states for unit initialization. Release
    # those temporary fixes before the simultaneous flowsheet solve; the Arc
    # equalities, not duplicate fixed inlet states, must close the model.
    model.fs.F101.inlet.unfix()
    model.fs.R101.inlet.unfix()
    model.fs.H101.inlet.unfix()
    return model


def solve_model(model, *, tee: bool = False):
    assert_units_consistent(model)
    solver = SolverFactory("ipopt")
    solver.options["tol"] = 1e-7
    solver.options["max_iter"] = 3000
    # Several trace phase-component flows sit close to their lower bounds.
    # Keep IPOPT's initial interior-point perturbation smaller than those
    # physically intentional trace values.
    solver.options["bound_push"] = 1e-8
    solver.options["bound_frac"] = 1e-8
    solver.options["mu_init"] = 1e-6
    result = solver.solve(model, tee=tee)
    assert result.solver.termination_condition == TerminationCondition.optimal
    return result


def main(*, second_flash: bool = False, tee: bool = False):
    model = build_model(second_flash=second_flash)
    set_operating_conditions(model, second_flash=second_flash)
    initialize_model(model)
    result = solve_model(model, tee=tee)
    return model, result


if __name__ == "__main__":
    main(second_flash=False, tee=True)
