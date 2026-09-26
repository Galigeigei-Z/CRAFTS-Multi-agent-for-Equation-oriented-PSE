#!/usr/bin/env python3
"""Generated from flash_paragraph_polished_complete.txt using encyclopedia patterns."""

from __future__ import annotations

from pyomo.environ import ConcreteModel, SolverFactory, TerminationCondition

from idaes.core import FlowsheetBlock
import idaes.logger as idaeslog
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.models.properties.activity_coeff_models.BTX_activity_coeff_VLE import (
    BTXParameterBlock,
)
from idaes.models.unit_models import Flash


def build_model():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties = BTXParameterBlock(
        valid_phase=("Liq", "Vap"),
        activity_coeff_model="Ideal",
        state_vars="FTPz",
    )
    m.fs.flash = Flash(property_package=m.fs.properties)
    return m


def set_operating_conditions(m):
    m.fs.flash.inlet.flow_mol.fix(1)
    m.fs.flash.inlet.temperature.fix(368)
    m.fs.flash.inlet.pressure.fix(101325)
    m.fs.flash.inlet.mole_frac_comp[0, "benzene"].fix(0.5)
    m.fs.flash.inlet.mole_frac_comp[0, "toluene"].fix(0.5)
    m.fs.flash.heat_duty.fix(0)
    m.fs.flash.deltaP.fix(0)


def initialize_model(m):
    m.fs.flash.initialize(outlvl=idaeslog.INFO)


def solve_model(m, tee=False):
    solver = SolverFactory("ipopt")
    results = solver.solve(m, tee=tee)
    assert results.solver.termination_condition == TerminationCondition.optimal
    return results


def main():
    m = build_model()
    print("dof_after_build", degrees_of_freedom(m))
    set_operating_conditions(m)
    print("dof_after_specs", degrees_of_freedom(m))
    initialize_model(m)
    results = solve_model(m)
    print("simulation_termination", results.solver.termination_condition)
    print("final_dof", degrees_of_freedom(m))


if __name__ == "__main__":
    main()
