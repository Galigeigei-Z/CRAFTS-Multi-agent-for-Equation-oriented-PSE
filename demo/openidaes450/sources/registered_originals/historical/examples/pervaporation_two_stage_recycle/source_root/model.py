"""Two-stage ethylene-glycol/water pervaporation recycle surrogate.

The permeance constants are anchored to the pinned official IDAES SkeletonUnit
example at 318.15 K.  Unlike the tutorial's composition-independent flux, this
engineering extension multiplies pure-component flux by feed mole fraction so
that staging and recycle alter membrane performance.
"""

from __future__ import annotations

import pyomo.environ as pyo
from idaes.core import FlowsheetBlock


COMPONENTS = ("water", "ethylene_glycol")
PURE_FLUX = {"water": 0.069895, "ethylene_glycol": 0.00006736}  # mol m-2 s-1
LATENT_HEAT = {"water": 40660.0, "ethylene_glycol": 56900.0}  # J mol-1


def _stream(block: pyo.Block, initialize: dict[str, float]) -> None:
    block.flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize=initialize)


def build_model() -> pyo.ConcreteModel:
    model = pyo.ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    fs = model.fs

    fs.WATER = pyo.Block()
    fs.GLYCOL = pyo.Block()
    fs.M101 = pyo.Block()
    fs.PV101 = pyo.Block()
    fs.S101 = pyo.Block()
    fs.PV102 = pyo.Block()
    fs.M201 = pyo.Block()
    fs.PERMEATE = pyo.Block()
    fs.RETENTATE = pyo.Block()

    _stream(fs.WATER, {"water": 0.45, "ethylene_glycol": 1e-6})
    _stream(fs.GLYCOL, {"water": 1e-6, "ethylene_glycol": 0.55})
    _stream(fs.M101, {"water": 0.48, "ethylene_glycol": 0.59})
    fs.M101.recycle_flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize={"water": 0.03, "ethylene_glycol": 0.04})

    for stage, inlet in ((fs.PV101, {"water": 0.48, "ethylene_glycol": 0.59}), (fs.PV102, {"water": 0.32, "ethylene_glycol": 0.44})):
        stage.inlet_flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize=inlet)
        stage.permeate_flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize={"water": 0.08, "ethylene_glycol": 1e-4})
        stage.retentate_flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize={"water": 0.35, "ethylene_glycol": 0.50})
        stage.area = pyo.Var(bounds=(1.0, 9.0), initialize=5.0)
        stage.duty = pyo.Var(bounds=(0, None), initialize=3500.0)

    fs.S101.recycle_fraction = pyo.Var(bounds=(0.02, 0.40), initialize=0.15)
    fs.S101.recycle_flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize={"water": 0.05, "ethylene_glycol": 0.07})
    fs.S101.stage2_flow = pyo.Var(COMPONENTS, bounds=(1e-10, None), initialize={"water": 0.30, "ethylene_glycol": 0.43})
    _stream(fs.M201, {"water": 0.12, "ethylene_glycol": 2e-4})
    _stream(fs.PERMEATE, {"water": 0.12, "ethylene_glycol": 2e-4})
    _stream(fs.RETENTATE, {"water": 0.25, "ethylene_glycol": 0.43})

    fs.WATER.flow["water"].fix(0.45)
    fs.WATER.flow["ethylene_glycol"].fix(1e-6)
    fs.GLYCOL.flow["water"].fix(1e-6)
    fs.GLYCOL.flow["ethylene_glycol"].fix(0.55)
    fs.PV101.area.fix(5.0)
    fs.PV102.area.fix(5.0)
    fs.S101.recycle_fraction.fix(0.15)

    fs.eq_fresh_recycle_mixer = pyo.Constraint(
        COMPONENTS,
        rule=lambda _b, c: fs.M101.flow[c] == fs.WATER.flow[c] + fs.GLYCOL.flow[c] + fs.M101.recycle_flow[c],
    )
    fs.eq_recycle_link = pyo.Constraint(COMPONENTS, rule=lambda _b, c: fs.M101.recycle_flow[c] == fs.S101.recycle_flow[c])
    fs.eq_stage1_inlet = pyo.Constraint(COMPONENTS, rule=lambda _b, c: fs.PV101.inlet_flow[c] == fs.M101.flow[c])

    def flux_rule(_b: pyo.Block, c: str) -> pyo.Constraint:
        total = sum(fs.PV101.inlet_flow[j] for j in COMPONENTS)
        return fs.PV101.permeate_flow[c] == fs.PV101.area * PURE_FLUX[c] * fs.PV101.inlet_flow[c] / total

    fs.eq_stage1_flux = pyo.Constraint(COMPONENTS, rule=flux_rule)
    fs.eq_stage1_balance = pyo.Constraint(
        COMPONENTS,
        rule=lambda _b, c: fs.PV101.retentate_flow[c] == fs.PV101.inlet_flow[c] - fs.PV101.permeate_flow[c],
    )
    fs.eq_split_recycle = pyo.Constraint(
        COMPONENTS,
        rule=lambda _b, c: fs.S101.recycle_flow[c] == fs.S101.recycle_fraction * fs.PV101.retentate_flow[c],
    )
    fs.eq_split_stage2 = pyo.Constraint(
        COMPONENTS,
        rule=lambda _b, c: fs.S101.stage2_flow[c] == (1 - fs.S101.recycle_fraction) * fs.PV101.retentate_flow[c],
    )
    fs.eq_stage2_inlet = pyo.Constraint(COMPONENTS, rule=lambda _b, c: fs.PV102.inlet_flow[c] == fs.S101.stage2_flow[c])

    def stage2_flux_rule(_b: pyo.Block, c: str) -> pyo.Constraint:
        total = sum(fs.PV102.inlet_flow[j] for j in COMPONENTS)
        return fs.PV102.permeate_flow[c] == fs.PV102.area * PURE_FLUX[c] * fs.PV102.inlet_flow[c] / total

    fs.eq_stage2_flux = pyo.Constraint(COMPONENTS, rule=stage2_flux_rule)
    fs.eq_stage2_balance = pyo.Constraint(
        COMPONENTS,
        rule=lambda _b, c: fs.PV102.retentate_flow[c] == fs.PV102.inlet_flow[c] - fs.PV102.permeate_flow[c],
    )
    fs.eq_permeate_mixer = pyo.Constraint(
        COMPONENTS,
        rule=lambda _b, c: fs.M201.flow[c] == fs.PV101.permeate_flow[c] + fs.PV102.permeate_flow[c],
    )
    fs.eq_permeate_product = pyo.Constraint(COMPONENTS, rule=lambda _b, c: fs.PERMEATE.flow[c] == fs.M201.flow[c])
    fs.eq_retentate_product = pyo.Constraint(COMPONENTS, rule=lambda _b, c: fs.RETENTATE.flow[c] == fs.PV102.retentate_flow[c])
    fs.eq_stage1_duty = pyo.Constraint(expr=fs.PV101.duty == sum(LATENT_HEAT[c] * fs.PV101.permeate_flow[c] for c in COMPONENTS))
    fs.eq_stage2_duty = pyo.Constraint(expr=fs.PV102.duty == sum(LATENT_HEAT[c] * fs.PV102.permeate_flow[c] for c in COMPONENTS))
    return model


def add_optimization(model: pyo.ConcreteModel) -> None:
    fs = model.fs
    fs.PV101.area.unfix()
    fs.PV102.area.unfix()
    fs.S101.recycle_fraction.unfix()
    fs.total_area = pyo.Constraint(expr=fs.PV101.area + fs.PV102.area == 10.0)
    fresh_water = fs.WATER.flow["water"] + fs.GLYCOL.flow["water"]
    fresh_glycol = fs.WATER.flow["ethylene_glycol"] + fs.GLYCOL.flow["ethylene_glycol"]
    fs.water_recovery = pyo.Expression(expr=fs.PERMEATE.flow["water"] / fresh_water)
    fs.glycol_loss = pyo.Expression(expr=fs.PERMEATE.flow["ethylene_glycol"] / fresh_glycol)
    fs.glycol_recovery_limit = pyo.Constraint(expr=fs.glycol_loss <= 0.005)
    fs.objective = pyo.Objective(
        expr=fs.water_recovery - 50 * fs.glycol_loss - 1e-6 * (fs.PV101.duty + fs.PV102.duty),
        sense=pyo.maximize,
    )

