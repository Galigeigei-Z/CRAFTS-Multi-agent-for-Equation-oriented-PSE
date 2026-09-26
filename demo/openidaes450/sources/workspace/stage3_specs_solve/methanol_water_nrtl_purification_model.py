"""Native IDAES methanol-water flash and partial-condensation rectifier.

The liquid phase uses the original temperature-dependent NRTL form
``tau_ij = b_ij / T``.  The binary parameters are the ChemSep values shipped
with thermo 0.6.0 (CAS 67-56-1 and 7732-18-5).  Pure-component data use the
same public ChEDL correlations, with provenance recorded by the runner.
"""

from __future__ import annotations

from idaes.core import Component, FlowsheetBlock, declare_process_block_class
from idaes.core.solvers import get_solver
from idaes.core.util import scaling as iscale
from idaes.core.util.initialization import propagate_state
from idaes.core.util.misc import extract_data
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.models.properties.activity_coeff_models.activity_coeff_prop_pack import (
    ActivityCoeffParameterData,
    ActivityCoeffStateBlockData,
    _ActivityCoeffStateBlock,
)
from idaes.models.unit_models import Flash
from pyomo.environ import (
    ConcreteModel,
    Constraint,
    Param,
    Set,
    TransformationFactory,
    exp,
    log,
    units as pyunits,
    value,
)
from pyomo.network import Arc


COMPONENTS = ("methanol", "water")
NRTL_B_K = {
    ("methanol", "methanol"): 0.0,
    ("methanol", "water"): -95.13209282738782,
    ("water", "methanol"): 398.95345259688855,
    ("water", "water"): 0.0,
}
NRTL_ALPHA = 0.2999


@declare_process_block_class(
    "MethanolWaterStateBlock", block_class=_ActivityCoeffStateBlock
)
class MethanolWaterStateBlockData(ActivityCoeffStateBlockData):
    """Activity-coefficient state block with temperature-dependent NRTL tau."""

    def build(self):
        super().build()
        # The parent creates its smoothed equilibrium-temperature variable
        # after calling _make_NRTL_eq. Rebuild these equations now so b/T uses
        # exactly the same equilibrium temperature as saturation pressure.
        if hasattr(self, "_temperature_equilibrium"):
            for name in (
                "eq_activity_coeff",
                "eq_B",
                "eq_A",
                "eq_Gij_coeff",
            ):
                self.del_component(getattr(self, name))
            self._use_equilibrium_temperature_for_nrtl = True
            self._make_NRTL_eq()

    def _make_NRTL_eq(self):
        # This mirrors the IDAES activity-coefficient implementation, replacing
        # the global constant tau with ChemSep's state-specific b/T form.
        from pyomo.environ import Var

        comps = self.params.component_list
        if not hasattr(self, "Gij_coeff"):
            self.Gij_coeff = Var(comps, comps, initialize=1.0)
            self.activity_coeff_comp = Var(comps, initialize=1.0, bounds=(1e-6, 50))
            self.A = Var(comps, initialize=0.0)
            self.B = Var(comps, initialize=0.0)

        def tau(i, j):
            temperature = (
                self._temperature_equilibrium
                if getattr(self, "_use_equilibrium_temperature_for_nrtl", False)
                else self.temperature
            )
            return self.params.nrtl_b[i, j] / temperature

        def rule_g(block, i, j):
            if i == j:
                block.Gij_coeff[i, j].fix(1.0)
                return Constraint.Skip
            return block.Gij_coeff[i, j] == exp(-block.params.alpha[i, j] * tau(i, j))

        self.eq_Gij_coeff = Constraint(comps, comps, rule=rule_g)

        def rule_a(block, i):
            numerator = sum(
                block.mole_frac_phase_comp["Liq", j]
                * tau(j, i)
                * block.Gij_coeff[j, i]
                for j in comps
            )
            denominator = sum(
                block.mole_frac_phase_comp["Liq", k] * block.Gij_coeff[k, i]
                for k in comps
            )
            return block.A[i] == numerator / denominator

        self.eq_A = Constraint(comps, rule=rule_a)

        def rule_b(block, i):
            value_b = sum(
                (
                    block.mole_frac_phase_comp["Liq", j]
                    * block.Gij_coeff[i, j]
                    / sum(
                        block.mole_frac_phase_comp["Liq", k] * block.Gij_coeff[k, j]
                        for k in comps
                    )
                )
                * (
                    tau(i, j)
                    - sum(
                        block.mole_frac_phase_comp["Liq", m]
                        * tau(m, j)
                        * block.Gij_coeff[m, j]
                        for m in comps
                    )
                    / sum(
                        block.mole_frac_phase_comp["Liq", k] * block.Gij_coeff[k, j]
                        for k in comps
                    )
                )
                for j in comps
            )
            return block.B[i] == value_b

        self.eq_B = Constraint(comps, rule=rule_b)
        self.eq_activity_coeff = Constraint(
            comps,
            rule=lambda block, i: log(block.activity_coeff_comp[i])
            == block.A[i] + block.B[i],
        )


@declare_process_block_class("MethanolWaterParameterBlock")
class MethanolWaterParameterData(ActivityCoeffParameterData):
    """Two-component ideal-vapor/NRTL-liquid parameter block."""

    def build(self):
        self.component_list_master = Set(initialize=COMPONENTS)
        self.methanol = Component()
        self.water = Component()
        super().build()
        self._state_block_class = MethanolWaterStateBlock

        self.phase_equilibrium_idx_master = Set(initialize=[1, 2])
        self.phase_equilibrium_idx = Set(initialize=[1, 2])
        self.phase_equilibrium_list_master = {
            1: ["methanol", ("Vap", "Liq")],
            2: ["water", ("Vap", "Liq")],
        }
        self.phase_equilibrium_list = dict(self.phase_equilibrium_list_master)

        self.pressure_reference = Param(mutable=True, default=101325, units=pyunits.Pa)
        self.temperature_reference = Param(mutable=True, default=298.15, units=pyunits.K)
        self.pressure_critical = Param(
            self.component_list,
            initialize=extract_data({"methanol": 8.092e6, "water": 22.064e6}),
            units=pyunits.Pa,
        )
        self.temperature_critical = Param(
            self.component_list,
            initialize=extract_data({"methanol": 512.64, "water": 647.096}),
            units=pyunits.K,
        )
        self.mw_comp = Param(
            self.component_list,
            initialize=extract_data({"methanol": 0.03204186, "water": 0.01801528}),
            units=pyunits.kg / pyunits.mol,
        )

        # ChEDL CRC liquid constants and Poling gas heat-capacity polynomials.
        liq_cp = {"methanol": 81.1e3, "water": 75.3e3}  # J/kmol/K
        vap_cp = {
            "A": {"methanol": 39.19437678197438, "water": 36.54206320678348},
            "B": {"methanol": -0.05808483585041853, "water": -0.03480434051958946},
            "C": {"methanol": 0.00035012202085043295, "water": 0.00011681819978505301},
            "D": {"methanol": -3.6941157412454843e-7, "water": -1.3003819534791667e-7},
            "E": {"methanol": 1.2762700118865224e-10, "water": 5.254740374672847e-11},
        }
        for letter, units in (
            ("A", pyunits.J / pyunits.kmol / pyunits.K),
            ("B", pyunits.J / pyunits.kmol / pyunits.K**2),
            ("C", pyunits.J / pyunits.kmol / pyunits.K**3),
            ("D", pyunits.J / pyunits.kmol / pyunits.K**4),
            ("E", pyunits.J / pyunits.kmol / pyunits.K**5),
        ):
            data = liq_cp if letter == "A" else {j: 0.0 for j in COMPONENTS}
            setattr(
                self,
                f"cp_mol_liq_comp_coeff_{letter}",
                Param(self.component_list, initialize=extract_data(data), units=units),
            )
        for letter, units in (
            ("A", pyunits.J / pyunits.mol / pyunits.K),
            ("B", pyunits.J / pyunits.mol / pyunits.K**2),
            ("C", pyunits.J / pyunits.mol / pyunits.K**3),
            ("D", pyunits.J / pyunits.mol / pyunits.K**4),
            ("E", pyunits.J / pyunits.mol / pyunits.K**5),
        ):
            setattr(
                self,
                f"cp_mol_vap_comp_coeff_{letter}",
                Param(self.component_list, initialize=extract_data(vap_cp[letter]), units=units),
            )

        # Methanol uses Wagner-Poling directly. Water coefficients are a
        # least-squares translation of ChEDL's DIPPR-101 correlation into the
        # four-term Wagner equation used by this IDAES package (290-420 K;
        # maximum relative pressure error 2.6e-5).
        pressure_sat = {
            ("methanol", "A"): -8.63571,
            ("methanol", "B"): 1.17982,
            ("methanol", "C"): -2.479,
            ("methanol", "D"): -1.024,
            ("water", "A"): -7.800143505127194,
            ("water", "B"): 1.4977734699531213,
            ("water", "C"): -2.721546767391618,
            ("water", "D"): -1.4956204270323847,
        }
        self.pressure_sat_coeff = Param(
            self.component_list,
            ["A", "B", "C", "D"],
            initialize=extract_data(pressure_sat),
        )

        # Formation enthalpies at 298.15 K (NIST values, J/mol). Entropy is
        # present because it is part of the package metadata; it is not used by
        # this steady-state enthalpy-balance flowsheet.
        dh = {
            ("Liq", "methanol"): -238.66e3,
            ("Vap", "methanol"): -201.0e3,
            ("Liq", "water"): -285.83e3,
            ("Vap", "water"): -241.826e3,
        }
        ds = {(p, j): 0.0 for p in ("Liq", "Vap") for j in COMPONENTS}
        self.dh_form = Param(
            self.phase_list,
            self.component_list,
            initialize=extract_data(dh),
            units=pyunits.J / pyunits.mol,
        )
        self.ds_form = Param(
            self.phase_list,
            self.component_list,
            initialize=extract_data(ds),
            units=pyunits.J / pyunits.mol / pyunits.K,
        )
        self.nrtl_b = Param(
            self.component_list,
            self.component_list,
            initialize=extract_data(NRTL_B_K),
            mutable=True,
            units=pyunits.K,
        )


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = MethanolWaterParameterBlock(
        valid_phase=("Liq", "Vap"), activity_coeff_model="NRTL"
    )
    model.fs.feed_flash = Flash(property_package=model.fs.properties)
    model.fs.vapor_polisher = Flash(property_package=model.fs.properties)
    model.fs.flash_vapor_to_polisher = Arc(
        source=model.fs.feed_flash.vap_outlet,
        destination=model.fs.vapor_polisher.inlet,
    )
    TransformationFactory("network.expand_arcs").apply_to(model)
    return model


def set_operating_conditions(model):
    fs = model.fs
    prop = fs.properties
    for i in COMPONENTS:
        for j in COMPONENTS:
            prop.alpha[i, j].fix(0.0 if i == j else NRTL_ALPHA)
            prop.tau[i, j].fix(0.0)  # legacy variable is replaced by b/T above

    fs.feed_flash.inlet.flow_mol.fix(100.0)
    fs.feed_flash.inlet.mole_frac_comp[0, "methanol"].fix(0.90)
    fs.feed_flash.inlet.mole_frac_comp[0, "water"].fix(0.10)
    fs.feed_flash.inlet.temperature.fix(340.0)
    fs.feed_flash.inlet.pressure.fix(101325.0)
    fs.feed_flash.heat_duty.fix(0.0)
    fs.feed_flash.deltaP.fix(0.0)

    # The first partial condenser rejects a water-rich condensate while its
    # vapor continues as the purified methanol stream.
    fs.vapor_polisher.control_volume.properties_out[0].temperature.fix(333.0)
    fs.vapor_polisher.deltaP.fix(0.0)

    prop.set_default_scaling("flow_mol", 1e-2)
    prop.set_default_scaling("flow_mol_phase", 1e-2)
    prop.set_default_scaling("enth_mol_phase", 1e-4)
    prop.set_default_scaling("enth_mol_phase_comp", 1e-4)
    for unit in (fs.feed_flash, fs.vapor_polisher):
        iscale.set_scaling_factor(unit.control_volume.heat, 1e-5)
    iscale.calculate_scaling_factors(model)
    dof = degrees_of_freedom(model)
    if dof != 0:
        raise RuntimeError(f"Methanol-water purification has {dof} DoF; expected 0")


def initialize_model(model):
    fs = model.fs
    # Initialize the coupled column from the ideal-liquid limit, then restore
    # the full ChemSep interaction parameters by continuation. This changes
    # only the initialization path; the final model and reported solve use the
    # complete temperature-dependent NRTL equations.
    for pair in NRTL_B_K:
        fs.properties.nrtl_b[pair].set_value(0.0)
    fs.feed_flash.initialize()
    propagate_state(fs.flash_vapor_to_polisher)
    fs.vapor_polisher.initialize()
    solver = get_solver()
    for fraction in (0.25, 0.5, 0.75, 1.0):
        for pair, full_value in NRTL_B_K.items():
            fs.properties.nrtl_b[pair].set_value(fraction * full_value)
        result = solver.solve(model)
        if str(result.solver.termination_condition).lower() != "optimal":
            raise RuntimeError(
                f"NRTL continuation failed at fraction {fraction}: "
                f"{result.solver.termination_condition}"
            )


def solve_model(model, tee=False):
    return get_solver().solve(model, tee=tee)


def metrics(model):
    fs = model.fs
    feed_flow = value(fs.feed_flash.inlet.flow_mol[0])
    feed_meoh = feed_flow * value(fs.feed_flash.inlet.mole_frac_comp[0, "methanol"])
    flash_vap_flow = value(fs.feed_flash.vap_outlet.flow_mol[0])
    flash_vap_x = value(fs.feed_flash.vap_outlet.mole_frac_comp[0, "methanol"])
    polished_vap_flow = value(fs.vapor_polisher.vap_outlet.flow_mol[0])
    polished_vap_x = value(fs.vapor_polisher.vap_outlet.mole_frac_comp[0, "methanol"])
    product_meoh = polished_vap_flow * polished_vap_x
    flash_liq_flow = value(fs.feed_flash.liq_outlet.flow_mol[0])
    polisher_liq_flow = value(fs.vapor_polisher.liq_outlet.flow_mol[0])
    return {
        "feed_flow_mol_s": feed_flow,
        "feed_methanol_mol_s": feed_meoh,
        "feed_methanol_mole_fraction": value(fs.feed_flash.inlet.mole_frac_comp[0, "methanol"]),
        "flash_vapor_flow_mol_s": flash_vap_flow,
        "flash_vapor_methanol_mole_fraction": flash_vap_x,
        "flash_liquid_water_mole_fraction": value(fs.feed_flash.liq_outlet.mole_frac_comp[0, "water"]),
        "flash_total_molar_closure": (flash_vap_flow + flash_liq_flow) / feed_flow,
        "polished_vapor_flow_mol_s": polished_vap_flow,
        "polished_vapor_methanol_mole_fraction": polished_vap_x,
        "polisher_condensate_flow_mol_s": polisher_liq_flow,
        "polisher_condensate_water_mole_fraction": value(fs.vapor_polisher.liq_outlet.mole_frac_comp[0, "water"]),
        "purified_product_flow_mol_s": polished_vap_flow,
        "purified_product_methanol_mole_fraction": polished_vap_x,
        "overall_methanol_recovery": product_meoh / feed_meoh,
        "polisher_total_molar_closure": (polished_vap_flow + polisher_liq_flow) / flash_vap_flow,
        "polisher_cooling_duty_kW": value(fs.vapor_polisher.heat_duty[0]) / 1000,
        "nrtl_tau_meoh_water_at_350K": NRTL_B_K[("methanol", "water")] / 350.0,
        "nrtl_tau_water_meoh_at_350K": NRTL_B_K[("water", "methanol")] / 350.0,
    }
