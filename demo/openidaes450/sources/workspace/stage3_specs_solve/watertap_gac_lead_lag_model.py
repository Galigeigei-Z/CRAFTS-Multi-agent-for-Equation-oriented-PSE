"""Native WaterTAP lead-lag granular activated carbon adsorption model."""

from __future__ import annotations

import math

from idaes.core import FlowsheetBlock
from idaes.core.util.initialization import propagate_state
from idaes.core.util.model_statistics import degrees_of_freedom
import idaes.core.util.scaling as iscale
from idaes.models.unit_models import Feed, Product
from pyomo.environ import ConcreteModel, TransformationFactory, value
from pyomo.network import Arc
from watertap.core.solvers import get_solver
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
from watertap.unit_models.gac import GAC


def build_model():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.properties = MCASParameterBlock(
        material_flow_basis="molar",
        ignore_neutral_charge=True,
        solute_list=["solute"],
        mw_data={"H2O": 0.018, "solute": 0.08},
        diffus_calculation="HaydukLaudie",
        molar_volume_data={("Liq", "solute"): 1e-4},
    )
    model.fs.feed = Feed(property_package=model.fs.properties)
    model.fs.lead_bed = GAC(
        property_package=model.fs.properties,
        film_transfer_coefficient_type="calculated",
        surface_diffusion_coefficient_type="calculated",
    )
    model.fs.lag_bed = GAC(
        property_package=model.fs.properties,
        film_transfer_coefficient_type="calculated",
        surface_diffusion_coefficient_type="calculated",
    )
    model.fs.product = Product(property_package=model.fs.properties)
    model.fs.lead_adsorbed = Product(property_package=model.fs.properties)
    model.fs.lag_adsorbed = Product(property_package=model.fs.properties)

    model.fs.feed_to_lead = Arc(source=model.fs.feed.outlet, destination=model.fs.lead_bed.inlet)
    model.fs.lead_to_lag = Arc(source=model.fs.lead_bed.outlet, destination=model.fs.lag_bed.inlet)
    model.fs.lag_to_product = Arc(source=model.fs.lag_bed.outlet, destination=model.fs.product.inlet)
    model.fs.lead_to_removed = Arc(source=model.fs.lead_bed.adsorbed, destination=model.fs.lead_adsorbed.inlet)
    model.fs.lag_to_removed = Arc(source=model.fs.lag_bed.adsorbed, destination=model.fs.lag_adsorbed.inlet)
    TransformationFactory("network.expand_arcs").apply_to(model)
    return model


def _fix_bed(unit, *, bed_length, ebct, replacement_ratio):
    unit.freund_k.fix(10)
    unit.freund_ninv.fix(0.9)
    unit.particle_dens_app.fix(750)
    unit.particle_dia.fix(0.001)
    unit.ebct.fix(ebct)
    unit.bed_voidage.fix(0.4)
    unit.bed_length.fix(bed_length)
    unit.conc_ratio_replace.fix(replacement_ratio)
    unit.a0.fix(3.68421)
    unit.a1.fix(13.1579)
    unit.b0.fix(0.784576)
    unit.b1.fix(0.239663)
    unit.b2.fix(0.484422)
    unit.b3.fix(0.003206)
    unit.b4.fix(0.134987)
    unit.shape_correction_factor.fix()
    unit.particle_porosity.fix()
    unit.tort.fix()
    unit.spdfr.fix()


def set_operating_conditions(model):
    fs = model.fs
    feed = fs.feed.properties[0]
    feed.temperature.fix(298.15)
    feed.pressure.fix(101325)
    feed.flow_mol_phase_comp["Liq", "H2O"].fix(2433.81215)
    feed.flow_mol_phase_comp["Liq", "solute"].fix(0.05476625)

    # The lead bed carries most of the service duty; the smaller lag bed is a
    # polishing guard that protects product quality as the lead bed loads.
    _fix_bed(fs.lead_bed, bed_length=6.0, ebct=600.0, replacement_ratio=0.60)
    _fix_bed(fs.lag_bed, bed_length=6.0, ebct=600.0, replacement_ratio=0.20)

    water_sf = 10 ** -math.ceil(math.log10(abs(0.043813 * 1000 / fs.properties.mw_comp["H2O"].value)))
    solute_sf = 10 ** -math.ceil(math.log10(abs(0.043813 * 0.1 / fs.properties.mw_comp["solute"].value)))
    fs.properties.set_default_scaling("flow_mol_phase_comp", water_sf, index=("Liq", "H2O"))
    fs.properties.set_default_scaling("flow_mol_phase_comp", solute_sf, index=("Liq", "solute"))
    iscale.calculate_scaling_factors(model)

    dof = degrees_of_freedom(model)
    if dof != 0:
        raise RuntimeError(f"Lead-lag GAC specification has {dof} DoF, expected 0")


def initialize_model(model):
    fs = model.fs
    fs.feed.initialize()
    propagate_state(fs.feed_to_lead)
    fs.lead_bed.initialize()
    propagate_state(fs.lead_to_lag)
    fs.lag_bed.initialize()
    propagate_state(fs.lag_to_product)
    propagate_state(fs.lead_to_removed)
    propagate_state(fs.lag_to_removed)
    fs.product.initialize()
    fs.lead_adsorbed.initialize()
    fs.lag_adsorbed.initialize()


def solve_model(model, tee=False):
    return get_solver().solve(model, tee=tee)


def metrics(model):
    fs = model.fs
    feed_solute = value(fs.feed.properties[0].flow_mol_phase_comp["Liq", "solute"])
    lead_out = value(fs.lead_bed.outlet.flow_mol_phase_comp[0, "Liq", "solute"])
    product_solute = value(fs.product.properties[0].flow_mol_phase_comp["Liq", "solute"])
    lead_removed = value(fs.lead_adsorbed.properties[0].flow_mol_phase_comp["Liq", "solute"])
    lag_removed = value(fs.lag_adsorbed.properties[0].flow_mol_phase_comp["Liq", "solute"])
    total_removed = lead_removed + lag_removed
    return {
        "feed_solute_mol_s": feed_solute,
        "lead_bed_outlet_solute_mol_s": lead_out,
        "final_product_solute_mol_s": product_solute,
        "lead_bed_solute_removal_fraction": lead_removed / feed_solute,
        "lag_bed_incremental_solute_removal_mol_s": lag_removed,
        "lag_bed_incremental_removal_fraction_of_lead_outlet": lag_removed / lead_out,
        "overall_solute_removal_fraction": total_removed / feed_solute,
        "breakthrough_protection_factor": lead_out / product_solute,
        "final_to_feed_solute_ratio": product_solute / feed_solute,
        "lead_bed_mass_gac_kg": value(fs.lead_bed.bed_mass_gac),
        "lag_bed_mass_gac_kg": value(fs.lag_bed.bed_mass_gac),
        "total_bed_mass_gac_kg": value(fs.lead_bed.bed_mass_gac) + value(fs.lag_bed.bed_mass_gac),
        "lead_bed_operational_time_s": value(fs.lead_bed.operational_time),
        "lag_bed_operational_time_s": value(fs.lag_bed.operational_time),
        "lead_bed_volumes_treated": value(fs.lead_bed.bed_volumes_treated),
        "lag_bed_volumes_treated": value(fs.lag_bed.bed_volumes_treated),
    }
