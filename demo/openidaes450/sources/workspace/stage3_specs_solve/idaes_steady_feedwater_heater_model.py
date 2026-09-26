"""Native steady-state IDAES closed feedwater-heater model.

The model follows the official FWH0D unit test configuration.  It contains a
desuperheating zone, condensing zone, drain-cooling zone, and a drain mixer.
The condensing constraint determines the required extraction-steam flow.
"""

from __future__ import annotations

from typing import Any


SOURCE_URL = (
    "https://github.com/IDAES/idaes-pse/blob/eed7cebc3d99be616ee7ead203cecaee9f81ac01/"
    "idaes/models_extra/power_generation/unit_models/feedwater_heater_0D.py"
)
VERIFICATION_URL = (
    "https://github.com/IDAES/idaes-pse/blob/eed7cebc3d99be616ee7ead203cecaee9f81ac01/"
    "idaes/models_extra/power_generation/unit_models/tests/test_feedwater_heater.py"
)


def build_model() -> Any:
    """Build and fully specify the official three-zone FWH0D benchmark."""
    import pyomo.environ as pyo
    from idaes.core import FlowsheetBlock
    from idaes.models.properties import iapws95
    from idaes.models_extra.power_generation.unit_models import FWH0D

    model = pyo.ConcreteModel()
    model.fs = FlowsheetBlock(
        dynamic=False,
        default_property_package=iapws95.Iapws95ParameterBlock(),
    )
    model.fs.properties = model.fs.config.default_property_package
    model.fs.fwh = FWH0D(
        has_desuperheat=True,
        has_drain_cooling=True,
        has_drain_mixer=True,
        property_package=model.fs.properties,
    )

    fwh = model.fs.fwh
    # Extraction steam flow is intentionally not fixed: the native condensing
    # constraint calculates the flow required to leave as saturated liquid.
    fwh.desuperheat.hot_side_inlet.flow_mol[:].set_value(100.0)
    fwh.desuperheat.hot_side_inlet.pressure.fix(201325.0)
    fwh.desuperheat.hot_side_inlet.enth_mol.fix(60000.0)

    fwh.drain_mix.drain.flow_mol.fix(1.0)
    fwh.drain_mix.drain.pressure.fix(201325.0)
    fwh.drain_mix.drain.enth_mol.fix(20000.0)

    fwh.cooling.cold_side_inlet.flow_mol.fix(400.0)
    fwh.cooling.cold_side_inlet.pressure.fix(101325.0)
    fwh.cooling.cold_side_inlet.enth_mol.fix(3000.0)

    fwh.condense.area.fix(1000.0)
    fwh.condense.overall_heat_transfer_coefficient.fix(100.0)
    fwh.desuperheat.area.fix(1000.0)
    fwh.desuperheat.overall_heat_transfer_coefficient.fix(10.0)
    fwh.cooling.area.fix(1000.0)
    fwh.cooling.overall_heat_transfer_coefficient.fix(10.0)
    return model


def initialize_and_solve(model: Any, tee: bool = False) -> Any:
    """Run the native composite-unit initializer followed by a full solve."""
    from idaes.core.solvers import get_solver

    model.fs.fwh.initialize(optarg={"max_iter": 50})
    return get_solver(options={"max_iter": 100}).solve(model, tee=tee)

