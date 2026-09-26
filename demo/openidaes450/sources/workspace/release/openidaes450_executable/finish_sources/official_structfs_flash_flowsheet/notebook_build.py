import importlib.util
from pathlib import Path

from pyomo.environ import value
from idaes.core.util.model_statistics import degrees_of_freedom

_SOURCE = Path(__file__).resolve().parent / "flash_flowsheet.py"
_SPEC = importlib.util.spec_from_file_location("_official_structfs_flash_source", _SOURCE)
_FLASH = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_FLASH)

build_model = _FLASH.build_model
set_operating_conditions = _FLASH.set_operating_conditions
initialize_model = _FLASH.initialize_model
solve_model = _FLASH.solve_model


def report(m):
    print(f"vapor_flow_mol_s={value(m.fs.flash.vap_outlet.flow_mol[0])}")
    print(f"liquid_flow_mol_s={value(m.fs.flash.liq_outlet.flow_mol[0])}")
    print(f"vapor_benzene_frac={value(m.fs.flash.vap_outlet.mole_frac_comp[0, 'benzene'])}")
    print(f"liquid_benzene_frac={value(m.fs.flash.liq_outlet.mole_frac_comp[0, 'benzene'])}")


def main():
    m = build_model()
    set_operating_conditions(m)
    print(f"initial_dof={degrees_of_freedom(m)}")
    initialize_model(m)
    results = solve_model(m)
    print(f"termination_condition={results.solver.termination_condition}")
    print(f"final_dof={degrees_of_freedom(m)}")
    print("strict_official_structfs_flash_in_process=True")
    report(m)
    return m, results


if __name__ == "__main__":
    main()
