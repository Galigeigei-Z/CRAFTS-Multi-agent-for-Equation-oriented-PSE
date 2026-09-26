#!/usr/bin/env python3
"""Solve ten topology-distinct native Pyomo water/resource-recovery variants."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime  # noqa: E402
from experiment.scripts.chemical_meaningful_batch_a_v4 import BATCH, BY_KEY  # noqa: E402

configure_py310_runtime()

VALIDATION_ROOT = ROOT / "validation/VectorEngine_qwen36_validation"


def _search(mode: str) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    if mode == "ro_antiscalant":
        for i in range(81):
            r = i / 100
            lw = 0.965 / (1 - 0.55 * r)
            ls = 0.035 / (1 - 0.99 * r)
            bw, bs = 0.55 * lw, 0.99 * ls
            salinity = bs / (bw + bs)
            rows.append({"recycle_fraction": r, "brine_salinity": salinity, "permeate_water_kg_s": 0.45 * lw, "feasible": salinity <= 0.12})
        best = max((row for row in rows if row["feasible"]), key=lambda row: row["permeate_water_kg_s"])
        return {"recycle_fraction": best["recycle_fraction"]}, rows
    if mode == "ro_boron":
        for ph_i in range(31):
            ph = 8.0 + ph_i / 10
            rejection = 0.50 + 0.48 / (1 + math.exp(-2.0 * (ph - 9.2)))
            for f_i in range(1, 21):
                f = f_i / 20
                feed_b = 0.0015
                product_water = (1 - f) + 0.9 * f
                product_b = feed_b * ((1 - f) + f * (1 - rejection))
                concentration = product_b / product_water
                objective = 0.55 * f + 0.025 * (ph - 8) ** 2
                rows.append({"polishing_fraction": f, "interstage_pH": ph, "boron_rejection": rejection, "product_boron_kg_m3": concentration, "objective": objective, "feasible": concentration <= 0.0005})
        best = min((row for row in rows if row["feasible"]), key=lambda row: row["objective"])
        return {"polishing_fraction": best["polishing_fraction"], "interstage_pH": best["interstage_pH"], "boron_rejection": best["boron_rejection"]}, rows
    if mode == "md_bypass":
        for i in range(51):
            b = i / 100
            mixed_t = (1 - b) * 347.0379591455 + b * 291.1492744598
            heater = 4.18 * 8.0718642101 * (363.15 - mixed_t)
            rows.append({"bypass_fraction": b, "mixed_preheat_temperature_K": mixed_t, "heater_duty_kW": heater, "feasible": mixed_t <= 343.15})
        best = min((row for row in rows if row["feasible"]), key=lambda row: row["heater_duty_kW"])
        return {"bypass_fraction": best["bypass_fraction"]}, rows
    if mode == "crystallizer_recycle":
        for i in range(91):
            r = i / 100
            lw = 0.895 / (1 - 0.60 * r)
            ls = 0.100 / (1 - 0.40 * r)
            li = 0.005 / (1 - 0.99 * r)
            mw, ms, mi = 0.60 * lw, 0.40 * ls, 0.99 * li
            impurity = mi / (mw + ms + mi)
            rows.append({"mother_liquor_recycle_fraction": r, "mother_liquor_impurity_mass_fraction": impurity, "salt_crystal_kg_s": 0.60 * ls, "feasible": impurity <= 0.025})
        best = max((row for row in rows if row["feasible"]), key=lambda row: row["salt_crystal_kg_s"])
        return {"mother_liquor_recycle_fraction": best["mother_liquor_recycle_fraction"]}, rows
    if mode == "mec_mvr":
        for i in range(101):
            x = i / 100
            compressor = 150 * x
            steam = max(0.0, 1000 - 500 - 400 * x)
            rows.append({"mvr_vapor_fraction": x, "compressor_power_kW": compressor, "external_steam_duty_kW": steam, "feasible": compressor <= 100})
        best = min((row for row in rows if row["feasible"]), key=lambda row: row["external_steam_duty_kW"])
        return {"mvr_vapor_fraction": best["mvr_vapor_fraction"]}, rows
    if mode == "ed_recycle":
        for i in range(81):
            r = i / 100
            lw = 0.965 / (1 - 0.10 * r)
            ls = 0.035 / (1 - 0.80 * r)
            cw, cs = 0.10 * lw, 0.80 * ls
            salinity = cs / (cw + cs)
            recovery = 0.90 * lw / 0.965
            rows.append({"concentrate_recycle_fraction": r, "concentrate_salinity": salinity, "water_recovery": recovery, "feasible": salinity <= 0.25})
        best = max((row for row in rows if row["feasible"]), key=lambda row: row["water_recovery"])
        return {"concentrate_recycle_fraction": best["concentrate_recycle_fraction"]}, rows
    if mode == "bped_recycle":
        for i in range(76):
            r = i / 100
            acid = 0.07 / (1 - 0.95 * r)
            water = 0.30 / (1 - 0.70 * r)
            impurity = 0.0005 / (1 - r)
            strength = acid / (acid + water + impurity)
            specific_energy = 2.5 + 1.2 * r
            rows.append({"acid_base_recycle_fraction": r, "product_strength_mass_fraction": strength, "impurity_mass_fraction": impurity / (acid + water + impurity), "specific_energy_kWh_kg": specific_energy, "feasible": impurity / (acid + water + impurity) <= 0.01 and specific_energy <= 3.2})
        best = max((row for row in rows if row["feasible"]), key=lambda row: row["product_strength_mass_fraction"])
        return {"acid_base_recycle_fraction": best["acid_base_recycle_fraction"]}, rows
    if mode == "gac_regeneration":
        for n in range(1, 11):
            capacity = 0.30 * (1 - 0.05 * (n - 1))
            carbon_throughput = 0.001 / capacity
            makeup = carbon_throughput * (1 / n + 0.035 * (n - 1))
            regen_energy = 0.45 * carbon_throughput * (n - 1)
            objective = 3.0 * makeup + 0.12 * regen_energy
            rows.append({"carbon_use_cycles": n, "effective_capacity_kg_kg": capacity, "virgin_makeup_kg_s": makeup, "regeneration_energy_kW": regen_energy, "objective": objective, "feasible": capacity >= 0.21})
        best = min((row for row in rows if row["feasible"]), key=lambda row: row["objective"])
        return {"carbon_use_cycles": float(best["carbon_use_cycles"])}, rows
    if mode == "softening_seed":
        for i in range(81):
            r = i / 100
            removal = 0.90 + 0.05 * r
            lime = 0.0015 * (1 - 0.35 * r)
            precipitate = 0.002 * removal
            recycle_solids = r * (precipitate + lime) / (1 - 0.70 * r)
            co2 = 0.44 * max(0.0, lime - 0.0008)
            rows.append({"seed_recycle_fraction": r, "calcium_removal": removal, "lime_kg_s": lime, "seed_solids_kg_s": recycle_solids, "co2_kg_s": co2, "feasible": recycle_solids <= 0.010})
        best = min((row for row in rows if row["feasible"]), key=lambda row: row["lime_kg_s"])
        return {"seed_recycle_fraction": best["seed_recycle_fraction"]}, rows
    if mode == "air_gac":
        for i in range(100):
            capture = 0.90 + i / 1000
            stripped = 0.001 * 0.95
            vent = stripped * (1 - capture)
            energy = 25 + 20 * capture**3
            rows.append({"offgas_gac_capture_fraction": capture, "vent_voc_kg_s": vent, "regeneration_energy_kW": energy, "feasible": vent <= 1e-6})
        best = min((row for row in rows if row["feasible"]), key=lambda row: row["regeneration_energy_kW"])
        return {"offgas_gac_capture_fraction": best["offgas_gac_capture_fraction"]}, rows
    raise KeyError(mode)


def _build(mode: str, decision: dict[str, float]):
    from pyomo.environ import ConcreteModel, Constraint, Param, Var  # noqa: PLC0415

    m = ConcreteModel()
    m.mode = mode
    metrics: dict[str, Any] = {}
    if mode in {"ro_antiscalant", "ed_recycle", "crystallizer_recycle"}:
        if mode == "ro_antiscalant":
            fresh = (0.965, 0.035, 0.55, 0.99); key = "recycle_fraction"; r = decision[key]; cap = 0.12
        elif mode == "ed_recycle":
            fresh = (0.965, 0.035, 0.10, 0.80); key = "concentrate_recycle_fraction"; r = decision[key]; cap = 0.25
        else:
            fresh = (0.895, 0.100, 0.60, 0.40); key = "mother_liquor_recycle_fraction"; r = decision[key]; cap = None
        m.r = Var(initialize=r); m.r.fix(r)
        m.loop_water = Var(initialize=1); m.loop_solute = Var(initialize=.1)
        m.product_water = Var(initialize=.4); m.product_solute = Var(initialize=.05)
        m.residual_water = Var(initialize=.5); m.residual_solute = Var(initialize=.05)
        m.recycle_water = Var(initialize=.1); m.recycle_solute = Var(initialize=.01)
        m.purge_water = Var(initialize=.1); m.purge_solute = Var(initialize=.01)
        fw, fs, rw, rs = fresh
        m.c1 = Constraint(expr=m.loop_water == fw + m.recycle_water)
        m.c2 = Constraint(expr=m.loop_solute == fs + m.recycle_solute)
        m.c3 = Constraint(expr=m.residual_water == rw * m.loop_water)
        m.c4 = Constraint(expr=m.residual_solute == rs * m.loop_solute)
        m.c5 = Constraint(expr=m.product_water == m.loop_water - m.residual_water)
        m.c6 = Constraint(expr=m.product_solute == m.loop_solute - m.residual_solute)
        m.c7 = Constraint(expr=m.recycle_water == m.r * m.residual_water)
        m.c8 = Constraint(expr=m.recycle_solute == m.r * m.residual_solute)
        m.c9 = Constraint(expr=m.purge_water == (1 - m.r) * m.residual_water)
        m.c10 = Constraint(expr=m.purge_solute == (1 - m.r) * m.residual_solute)
        if cap is not None:
            m.quality = Constraint(expr=m.residual_solute <= cap * (m.residual_water + m.residual_solute))
        metrics = {"loop_water_kg_s": m.loop_water, "loop_solute_kg_s": m.loop_solute, "product_water_kg_s": m.product_water, "product_solute_kg_s": m.product_solute, "purge_water_kg_s": m.purge_water, "purge_solute_kg_s": m.purge_solute}
        if mode == "crystallizer_recycle":
            m.impurity_loop = Var(initialize=.01); m.impurity_residual = Var(initialize=.01); m.impurity_recycle = Var(initialize=.001); m.impurity_purge = Var(initialize=.001)
            m.c11 = Constraint(expr=m.impurity_loop == .005 + m.impurity_recycle)
            m.c12 = Constraint(expr=m.impurity_residual == .99 * m.impurity_loop)
            m.c13 = Constraint(expr=m.impurity_recycle == m.r * m.impurity_residual)
            m.c14 = Constraint(expr=m.impurity_purge == (1 - m.r) * m.impurity_residual)
            m.quality = Constraint(expr=m.impurity_residual <= .025 * (m.residual_water + m.residual_solute + m.impurity_residual))
            metrics.update({"salt_crystal_kg_s": m.product_solute, "impurity_purge_kg_s": m.impurity_purge})
        return m, metrics
    if mode == "ro_boron":
        f, ph, rej = decision["polishing_fraction"], decision["interstage_pH"], decision["boron_rejection"]
        m.f = Var(initialize=f); m.f.fix(f); m.ph = Var(initialize=ph); m.ph.fix(ph)
        for name in ["polish_water", "bypass_water", "polish_boron", "bypass_boron", "second_perm_water", "second_perm_boron", "product_water", "product_boron", "brine_water", "brine_boron"]: setattr(m, name, Var(initialize=.1))
        m.c1=Constraint(expr=m.polish_water==m.f); m.c2=Constraint(expr=m.bypass_water==1-m.f); m.c3=Constraint(expr=m.polish_boron==.0015*m.f); m.c4=Constraint(expr=m.bypass_boron==.0015*(1-m.f)); m.c5=Constraint(expr=m.second_perm_water==.9*m.polish_water); m.c6=Constraint(expr=m.brine_water==m.polish_water-m.second_perm_water); m.c7=Constraint(expr=m.second_perm_boron==(1-rej)*m.polish_boron); m.c8=Constraint(expr=m.brine_boron==m.polish_boron-m.second_perm_boron); m.c9=Constraint(expr=m.product_water==m.bypass_water+m.second_perm_water); m.c10=Constraint(expr=m.product_boron==m.bypass_boron+m.second_perm_boron); m.quality=Constraint(expr=m.product_boron<=.0005*m.product_water)
        return m,{"product_water_m3_s":m.product_water,"product_boron_kg_s":m.product_boron,"second_pass_brine_kg_s":m.brine_water+m.brine_boron}
    if mode == "md_bypass":
        b=decision["bypass_fraction"]; m.b=Var(initialize=b);m.b.fix(b);m.mixed_t=Var(initialize=343);m.heater=Var(initialize=600);m.hx=Var(initialize=1800);m.c1=Constraint(expr=m.mixed_t==(1-m.b)*347.0379591455+m.b*291.1492744598);m.c2=Constraint(expr=m.heater==4.18*8.0718642101*(363.15-m.mixed_t));m.c3=Constraint(expr=m.hx==4.18*8.0718642101*(m.mixed_t-291.1492744598));m.quality=Constraint(expr=m.mixed_t<=343.15)
        return m,{"mixed_preheat_temperature_K":m.mixed_t,"heater_duty_kW":m.heater,"recovered_heat_kW":m.hx,"water_recovery":0.5}
    if mode == "mec_mvr":
        x=decision["mvr_vapor_fraction"];m.x=Var(initialize=x);m.x.fix(x);m.compressor=Var(initialize=100);m.steam=Var(initialize=250);m.cascade=Var(initialize=1);m.mvr_heat=Var(initialize=1);m.c1=Constraint(expr=m.compressor==150*m.x);m.c2=Constraint(expr=m.cascade==500*(1-m.x));m.c3=Constraint(expr=m.mvr_heat==400*m.x);m.c4=Constraint(expr=m.steam+m.cascade+m.mvr_heat==1000);m.power=Constraint(expr=m.compressor<=100)
        return m,{"compressor_power_kW":m.compressor,"external_steam_duty_kW":m.steam,"cascade_heat_kW":m.cascade,"mvr_heat_return_kW":m.mvr_heat}
    if mode == "bped_recycle":
        r=decision["acid_base_recycle_fraction"];m.r=Var(initialize=r);m.r.fix(r);m.acid=Var(initialize=.1);m.water=Var(initialize=.3);m.impurity=Var(initialize=.001);m.product_acid=Var(initialize=.03);m.product_water=Var(initialize=.1);m.c1=Constraint(expr=m.acid==.07+.95*m.r*m.acid);m.c2=Constraint(expr=m.water==.30+.70*m.r*m.water);m.c3=Constraint(expr=m.impurity==.0005+m.r*m.impurity);m.c4=Constraint(expr=m.product_acid==(1-m.r)*m.acid);m.c5=Constraint(expr=m.product_water==(1-m.r)*m.water);m.quality=Constraint(expr=m.impurity<=.01*(m.acid+m.water+m.impurity))
        return m,{"acid_loop_kg_s":m.acid,"product_acid_kg_s":m.product_acid,"product_water_kg_s":m.product_water,"loop_impurity_kg_s":m.impurity}
    if mode == "gac_regeneration":
        n=decision["carbon_use_cycles"];m.n=Var(initialize=n);m.n.fix(n);m.capacity=Var(initialize=.25);m.carbon=Var(initialize=.004);m.makeup=Var(initialize=.001);m.energy=Var(initialize=.001);m.c1=Constraint(expr=m.capacity==.30*(1-.05*(m.n-1)));m.c2=Constraint(expr=m.carbon*m.capacity==.001);m.c3=Constraint(expr=m.makeup==m.carbon*(1/m.n+.035*(m.n-1)));m.c4=Constraint(expr=m.energy==.45*m.carbon*(m.n-1));m.quality=Constraint(expr=m.capacity>=.21)
        return m,{"effective_capacity_kg_kg":m.capacity,"carbon_throughput_kg_s":m.carbon,"virgin_makeup_kg_s":m.makeup,"regeneration_energy_kW":m.energy}
    if mode == "softening_seed":
        r=decision["seed_recycle_fraction"];m.r=Var(initialize=r);m.r.fix(r);m.removal=Var(initialize=.93);m.lime=Var(initialize=.001);m.precip=Var(initialize=.002);m.seed=Var(initialize=.005);m.co2=Var(initialize=.0002);m.c1=Constraint(expr=m.removal==.90+.05*m.r);m.c2=Constraint(expr=m.lime==.0015*(1-.35*m.r));m.c3=Constraint(expr=m.precip==.002*m.removal);m.c4=Constraint(expr=m.seed*(1-.70*m.r)==m.r*(m.precip+m.lime));m.c5=Constraint(expr=m.co2==.44*(m.lime-.0008));m.quality=Constraint(expr=m.seed<=.010)
        return m,{"calcium_removal_fraction":m.removal,"lime_kg_s":m.lime,"precipitate_kg_s":m.precip,"seed_solids_kg_s":m.seed,"recarbonation_co2_kg_s":m.co2}
    if mode == "air_gac":
        e=decision["offgas_gac_capture_fraction"];m.e=Var(initialize=e);m.e.fix(e);m.water_voc=Var(initialize=.00005);m.offgas_voc=Var(initialize=.00095);m.captured=Var(initialize=.0009);m.vent=Var(initialize=1e-6);m.energy=Var(initialize=40);m.c1=Constraint(expr=m.water_voc==.001*(1-.95));m.c2=Constraint(expr=m.offgas_voc==.001-m.water_voc);m.c3=Constraint(expr=m.captured==m.e*m.offgas_voc);m.c4=Constraint(expr=m.vent==m.offgas_voc-m.captured);m.c5=Constraint(expr=m.energy==25+20*m.e**3);m.air=Constraint(expr=m.vent<=1e-6)
        return m,{"treated_water_voc_kg_s":m.water_voc,"captured_voc_kg_s":m.captured,"vent_voc_kg_s":m.vent,"regeneration_energy_kW":m.energy}
    raise KeyError(mode)


def solve_one(meta: dict[str, Any]) -> dict[str, Any]:
    from idaes.core.util.model_statistics import degrees_of_freedom  # noqa: PLC0415
    from pyomo.environ import check_optimal_termination, value  # noqa: PLC0415
    from watertap.core.solvers import get_solver  # noqa: PLC0415

    try:
        decision, search = _search(meta["mode"])
        model, metric_objects = _build(meta["mode"], decision)
        initial_dof = degrees_of_freedom(model)
        results = get_solver().solve(model)
        final_dof = degrees_of_freedom(model)
        optimal = bool(check_optimal_termination(results))
        metrics = {name: float(value(obj)) for name, obj in metric_objects.items()}
        passed = optimal and initial_dof == 0 and final_dof == 0
        return {"pass": passed, "stage": "native_process_extension_solve", "case_family": meta["mode"], "parent_case_key": meta["parent"], "termination_condition": str(results.solver.termination_condition), "checks": [{"name": "native_extension_optimal", "pass": optimal}, {"name": "initial_dof_zero", "pass": initial_dof == 0}, {"name": "final_dof_zero", "pass": final_dof == 0}], "initial_dof": initial_dof, "final_dof": final_dof, "decision_variables": decision, "metrics": metrics, "search_results": search, "source_summary": {"source": "native Pyomo material/energy extension anchored to active registry parent", "parent_case_key": meta["parent"], "chemical_distinction": meta["distinction"]}, "error": None if passed else {"message": "native extension checks failed"}}
    except Exception as exc:  # noqa: BLE001
        return {"pass": False, "stage": "native_process_extension_solve", "case_family": meta["mode"], "parent_case_key": meta["parent"], "termination_condition": None, "checks": [{"name": "runner_exception", "pass": False}], "error": {"type": type(exc).__name__, "message": str(exc), "traceback_tail": traceback.format_exc()[-5000:]}}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",action="append",choices=sorted(BY_KEY));parser.add_argument("--reuse-passing",action="store_true");args=parser.parse_args();selected=args.case or [row["key"] for row in BATCH];rows=[]
    for key in selected:
        output=VALIDATION_ROOT/key;output.mkdir(parents=True,exist_ok=True);report_path=output/"native_solve_report.json"
        if args.reuse_passing and report_path.is_file():
            prior=json.loads(report_path.read_text(encoding="utf-8"))
            if prior.get("pass") is True and prior.get("final_dof")==0: rows.append({"case_key":key,"pass":True,"reused":True});continue
        report=solve_one(BY_KEY[key]);report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");(output/"native_execution.log").write_text(json.dumps({k:v for k,v in report.items() if k!="search_results"},indent=2,ensure_ascii=False)+"\n",encoding="utf-8");rows.append({"case_key":key,"pass":report.get("pass") is True,"report":str(report_path.relative_to(ROOT))})
    payload={"pass":all(row["pass"] for row in rows),"case_count":len(rows),"results":rows};print(json.dumps(payload,indent=2));raise SystemExit(0 if payload["pass"] else 1)


if __name__ == "__main__": main()
