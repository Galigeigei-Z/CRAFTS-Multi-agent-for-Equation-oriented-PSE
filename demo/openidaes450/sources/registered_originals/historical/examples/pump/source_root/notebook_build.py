from pyomo.environ import ConcreteModel, SolverFactory, TerminationCondition, value, units
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.models.properties import iapws95
from idaes.models.properties.helmholtz.helmholtz import PhaseType
from idaes.models.unit_models.pressure_changer import Pump
import idaes.logger as idaeslog


def build_model():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties = iapws95.Iapws95ParameterBlock(phase_presentation=PhaseType.L)
    m.fs.pump_case_1 = Pump(property_package=m.fs.properties)
    return m


def set_operating_conditions(m):
    m.fs.pump_case_1.inlet.flow_mol[0].fix(100)
    m.fs.pump_case_1.inlet.pressure[0].fix(101325)
    hin = value(iapws95.htpx(T=298.15 * units.K, P=101325 * units.Pa))
    m.fs.pump_case_1.inlet.enth_mol[0].fix(hin)
    m.fs.pump_case_1.deltaP.fix(100000)
    m.fs.pump_case_1.efficiency_pump.fix(0.8)


def initialize_model(m):
    m.fs.pump_case_1.initialize(outlvl=idaeslog.INFO)


def solve_model(m, tee=False):
    solver = SolverFactory("ipopt")
    results = solver.solve(m, tee=tee)
    assert results.solver.termination_condition == TerminationCondition.optimal
    return results


def main():
    m = build_model()
    print("dof_before", degrees_of_freedom(m))
    set_operating_conditions(m)
    print("dof_after", degrees_of_freedom(m))
    initialize_model(m)
    results = solve_model(m)
    print("simulation_termination", results.solver.termination_condition)
    print("final_dof", degrees_of_freedom(m))
    return m, results


if __name__ == "__main__":
    main()
