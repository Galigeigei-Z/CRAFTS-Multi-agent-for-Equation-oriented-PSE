"""ASM1 variant with all bioreactor effluent routed through the clarifier.

The official WaterTAP ASM1 flowsheet recycles both a direct R5 outlet branch and
clarifier underflow.  This variant closes the direct branch and retains only
return activated sludge (RAS) from the clarifier underflow.  Continuation is
used because changing the recycle topology in one solver step is numerically
poorly conditioned.
"""

from __future__ import annotations

from idaes.core.util.model_statistics import degrees_of_freedom
from pyomo.environ import value
from watertap.core.solvers import get_solver
from watertap.flowsheets.activated_sludge import ASM1_flowsheet


DIRECT_RECYCLE_CONTINUATION = (0.50, 0.40, 0.30, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005, 0.001, 0.0)
AERATION_TRANSFER_KG_O2_PER_KWH = 1.8


def _concentration_mg_l(port, component):
    # ASM1 concentration variables use kg/m3, numerically equal to g/L.
    return 1000.0 * value(port.conc_mass_comp[0, component])


def _state_metrics(model):
    fs = model.fs
    treated = fs.Treated.inlet
    feed_flow = value(fs.FeedWater.outlet.flow_vol[0])
    treated_flow = value(treated.flow_vol[0])
    ras_flow = value(fs.SP6.recycle.flow_vol[0])
    waste_flow = value(fs.Sludge.inlet.flow_vol[0])
    oxygen_kg_s = sum(value(getattr(fs, reactor).injection[0, "Liq", "S_O"]) for reactor in ("R3", "R4", "R5"))
    aeration_power_kw = oxygen_kg_s * 3600.0 / AERATION_TRANSFER_KG_O2_PER_KWH
    soluble_inorganic_n = _concentration_mg_l(treated, "S_NO") + _concentration_mg_l(treated, "S_NH")
    soluble_cod = _concentration_mg_l(treated, "S_I") + _concentration_mg_l(treated, "S_S")
    particulate_cod = sum(_concentration_mg_l(treated, c) for c in ("X_I", "X_S", "X_BH", "X_BA", "X_P"))
    total_reactor_volume = sum(value(getattr(fs, reactor).volume[0]) for reactor in ("R1", "R2", "R3", "R4", "R5"))
    return {
        "influent_flow_m3_s": feed_flow,
        "treated_flow_m3_s": treated_flow,
        "waste_sludge_flow_m3_s": waste_flow,
        "hydraulic_balance_residual_m3_s": feed_flow - treated_flow - waste_flow,
        "clarifier_ras_flow_m3_s": ras_flow,
        "clarifier_ras_to_influent_ratio": ras_flow / feed_flow,
        "nominal_bioreactor_hrt_h": total_reactor_volume / feed_flow / 3600.0,
        "effluent_ammonium_n_mg_l": _concentration_mg_l(treated, "S_NH"),
        "effluent_nitrate_n_mg_l": _concentration_mg_l(treated, "S_NO"),
        "effluent_soluble_inorganic_n_mg_l": soluble_inorganic_n,
        "effluent_soluble_cod_states_mg_l": soluble_cod,
        "effluent_particulate_cod_states_mg_l": particulate_cod,
        "oxygen_transfer_kg_s": oxygen_kg_s,
        "estimated_aeration_power_kw": aeration_power_kw,
        "estimated_specific_aeration_energy_kwh_m3": aeration_power_kw / (feed_flow * 3600.0),
        "aeration_transfer_assumption_kg_o2_per_kwh": AERATION_TRANSFER_KG_O2_PER_KWH,
    }


def build_initialized_model():
    """Build and solve the official baseline, returning its initialized state."""
    model, baseline_results = ASM1_flowsheet.build_flowsheet()
    if degrees_of_freedom(model) != 0:
        raise RuntimeError("Official ASM1 baseline does not have zero degrees of freedom")
    return model, baseline_results, _state_metrics(model)


def solve_clarifier_only_ras(model, tee=False):
    """Close the direct reactor recycle by continuation and solve at zero flow."""
    solver = get_solver(options={"max_iter": 1000})
    continuation = []
    results = None
    for direct_recycle_fraction in DIRECT_RECYCLE_CONTINUATION:
        model.fs.SP5.split_fraction[:, "underflow"].fix(direct_recycle_fraction)
        results = solver.solve(model, tee=tee)
        continuation.append(
            {
                "direct_reactor_recycle_fraction": direct_recycle_fraction,
                "termination_condition": str(results.solver.termination_condition),
            }
        )
    return results, continuation


def variant_metrics(model, baseline_metrics):
    current = _state_metrics(model)
    current.update(
        {
            "baseline_direct_reactor_recycle_fraction": 0.60,
            "variant_direct_reactor_recycle_fraction": value(model.fs.SP5.split_fraction[0, "underflow"]),
            "baseline_effluent_ammonium_n_mg_l": baseline_metrics["effluent_ammonium_n_mg_l"],
            "baseline_effluent_nitrate_n_mg_l": baseline_metrics["effluent_nitrate_n_mg_l"],
            "baseline_effluent_soluble_inorganic_n_mg_l": baseline_metrics["effluent_soluble_inorganic_n_mg_l"],
            "baseline_estimated_aeration_power_kw": baseline_metrics["estimated_aeration_power_kw"],
        }
    )
    return current
