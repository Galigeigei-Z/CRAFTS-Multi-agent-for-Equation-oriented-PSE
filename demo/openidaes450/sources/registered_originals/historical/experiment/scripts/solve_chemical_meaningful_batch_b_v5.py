#!/usr/bin/env python3
"""Solve ten native biological wastewater/resource-recovery extensions."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime  # noqa: E402
from experiment.scripts.chemical_meaningful_batch_b_v5 import BATCH,BY_KEY  # noqa: E402
configure_py310_runtime()
VALIDATION_ROOT=ROOT/"validation/VectorEngine_qwen36_validation"


def search(mode:str)->tuple[dict[str,float],list[dict[str,Any]]]:
    rows=[]
    if mode=="asm1_step_feed":
        for fi in range(1,8):
            f=fi/10
            for ri in range(17):
                r=ri/4
                removal=min(.92,.55+.25*f+.12*r/(1+r)); eff=.001*(1-removal); energy=100*(1-.2*f)+2*r
                rows.append({"step_feed_fraction":f,"nitrate_recycle_ratio":r,"tn_effluent_kg_s":eff,"aeration_and_pump_index":energy,"feasible":eff<=.00020})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["aeration_and_pump_index"]);return {"step_feed_fraction":b["step_feed_fraction"],"nitrate_recycle_ratio":b["nitrate_recycle_ratio"]},rows
    if mode in {"asm2d_struvite","centrate_struvite"}:
        for di in range(41):
            d=.6+di*.02
            for ri in range(11 if mode=="centrate_struvite" else 1):
                seed=ri*.05 if mode=="centrate_struvite" else 0
                recovery=min(.98,.82*d+.12*seed); residual=.0005*(1-recovery); mg_res=max(0,.0005*d-.0005*recovery); objective=d+.15*seed
                rows.append({"magnesium_stoichiometric_ratio":d,"seed_recycle_fraction":seed,"phosphorus_recovery":recovery,"residual_phosphate_kg_s":residual,"residual_magnesium_kg_s":mg_res,"objective":objective,"feasible":residual<=5e-5 and mg_res<=1e-4})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["objective"]);return {"magnesium_stoichiometric_ratio":b["magnesium_stoichiometric_ratio"],"seed_recycle_fraction":b["seed_recycle_fraction"]},rows
    if mode=="adm1_two_stage":
        for i in range(21):
            f=.2+i*.025;vfa=.01*(.55+.5*f);meth_conv=.72+.22*(1-f);methane=vfa*meth_conv*.35;residual=vfa*(1-meth_conv)
            rows.append({"acidogenic_hrt_fraction":f,"vfa_production_kg_s":vfa,"methane_kg_s":methane,"residual_vfa_kg_s":residual,"feasible":residual<=.0012})
        b=max((x for x in rows if x["feasible"]),key=lambda x:x["methane_kg_s"]);return {"acidogenic_hrt_fraction":b["acidogenic_hrt_fraction"]},rows
    if mode=="uconn_anammox":
        for i in range(21):
            s=i*.05;rem=.60*(1-s)+.90*s;eff=.001*(1-rem);energy=80*(1-s)+20*s
            rows.append({"sidestream_fraction":s,"nitrogen_removal":rem,"tn_return_kg_s":eff,"aeration_index":energy,"feasible":eff<=.0002})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["aeration_index"]);return {"sidestream_fraction":b["sidestream_fraction"]},rows
    if mode=="asm2d_fermentation":
        for i in range(21):
            f=i*.04;vfa=.003*f*.30;boost=min(1,vfa/.0006);nrem=.60+.22*boost;prem=.70+.20*boost;solids=.003*f*.50;score=nrem+prem-.1*f
            rows.append({"sludge_fermentation_fraction":f,"vfa_return_kg_s":vfa,"nitrogen_removal":nrem,"phosphorus_removal":prem,"solids_loss_kg_s":solids,"score":score,"feasible":solids<=.0012})
        b=max((x for x in rows if x["feasible"]),key=lambda x:x["score"]);return {"sludge_fermentation_fraction":b["sludge_fermentation_fraction"]},rows
    if mode=="adm1_scrub":
        for i in range(29):
            p=3+i*.25;co2_rem=1-math.exp(-.35*(p-1));ch4_loss=.006+.001*p;ch4=.0527*(1-ch4_loss);co2=.0055*(1-co2_rem);purity=ch4/(ch4+co2);power=12*p
            rows.append({"scrubber_pressure_bar":p,"co2_removal":co2_rem,"methane_loss_fraction":ch4_loss,"biomethane_purity":purity,"compression_power_kW":power,"feasible":purity>=.95})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["compression_power_kW"]+.0527*x["methane_loss_fraction"]*1e4);return {"scrubber_pressure_bar":b["scrubber_pressure_bar"]},rows
    if mode=="bsm2_equalization":
        for i in range(25):
            h=i*.5;peak=1+1/(1+h/2);volume=170*h;energy=.5*h
            rows.append({"equalization_hours":h,"peak_load_factor":peak,"tank_volume_m3":volume,"pumping_index":energy,"feasible":peak<=1.20})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["tank_volume_m3"]);return {"equalization_hours":b["equalization_hours"]},rows
    if mode=="digestate_strip":
        for ti in range(9):
            t=40+ti*5
            for pi in range(9):
                ph=9+pi*.25;free=1/(1+10**(9.25-ph));temp_boost=min(1,.45+.012*(t-40));rem=.98*free*temp_boost;eff=.001*(1-rem);energy=4*(t-35)+15*(ph-9)
                rows.append({"strip_temperature_C":t,"strip_pH":ph,"ammonia_recovery":rem,"effluent_ammonium_kg_s":eff,"energy_reagent_index":energy,"feasible":eff<=.00015})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["energy_reagent_index"]);return {"strip_temperature_C":b["strip_temperature_C"],"strip_pH":b["strip_pH"]},rows
    if mode=="coag_seed":
        for ri in range(17):
            r=ri*.05
            for di in range(21):
                d=.5+di*.05;rem=1-math.exp(-2*d*(1+.8*r));eff=.01*(1-rem);metal=.0001*d*(1-.2*r);objective=d+.15*r
                rows.append({"sludge_seed_recycle_fraction":r,"coagulant_relative_dose":d,"turbidity_solids_effluent_kg_s":eff,"residual_metal_kg_s":metal,"objective":objective,"feasible":eff<=.0005 and metal<=.00015})
        b=min((x for x in rows if x["feasible"]),key=lambda x:x["objective"]);return {"sludge_seed_recycle_fraction":b["sludge_seed_recycle_fraction"],"coagulant_relative_dose":b["coagulant_relative_dose"]},rows
    raise KeyError(mode)


def build(mode:str,d:dict[str,float]):
    from pyomo.environ import ConcreteModel,Constraint,Var,exp
    m=ConcreteModel();metrics={}
    if mode=="asm1_step_feed":
        f,r=d["step_feed_fraction"],d["nitrate_recycle_ratio"];m.f=Var(initialize=f);m.f.fix(f);m.r=Var(initialize=r);m.r.fix(r);m.rem=Var(initialize=.85);m.eff=Var(initialize=.0001);m.energy=Var(initialize=100);m.c1=Constraint(expr=m.rem==.55+.25*m.f+.12*m.r/(1+m.r));m.c2=Constraint(expr=m.eff==.001*(1-m.rem));m.c3=Constraint(expr=m.energy==100*(1-.2*m.f)+2*m.r);m.q=Constraint(expr=m.eff<=.00020);metrics={"tn_removal_fraction":m.rem,"tn_effluent_kg_s":m.eff,"aeration_and_pump_index":m.energy}
    elif mode in {"asm2d_struvite","centrate_struvite"}:
        dose,seed=d["magnesium_stoichiometric_ratio"],d["seed_recycle_fraction"];m.d=Var(initialize=dose);m.d.fix(dose);m.s=Var(initialize=seed);m.s.fix(seed);m.rec=Var(initialize=.9);m.p=Var(initialize=5e-5);m.mg=Var(initialize=5e-5);m.c1=Constraint(expr=m.rec==.82*m.d+.12*m.s);m.c2=Constraint(expr=m.p==.0005*(1-m.rec));m.c3=Constraint(expr=m.mg==.0005*(m.d-m.rec));m.q1=Constraint(expr=m.p<=5e-5);m.q2=Constraint(expr=m.mg<=1e-4);metrics={"phosphorus_recovery_fraction":m.rec,"struvite_phosphorus_kg_s":.0005*m.rec,"residual_phosphate_kg_s":m.p,"residual_magnesium_kg_s":m.mg}
    elif mode=="adm1_two_stage":
        f=d["acidogenic_hrt_fraction"];m.f=Var(initialize=f);m.f.fix(f);m.vfa=Var(initialize=.008);m.conv=Var(initialize=.8);m.ch4=Var(initialize=.002);m.res=Var(initialize=.001);m.c1=Constraint(expr=m.vfa==.01*(.55+.5*m.f));m.c2=Constraint(expr=m.conv==.72+.22*(1-m.f));m.c3=Constraint(expr=m.ch4==.35*m.vfa*m.conv);m.c4=Constraint(expr=m.res==m.vfa*(1-m.conv));m.q=Constraint(expr=m.res<=.0012);metrics={"vfa_production_kg_s":m.vfa,"methanogenic_conversion":m.conv,"methane_kg_s":m.ch4,"residual_vfa_kg_s":m.res}
    elif mode=="uconn_anammox":
        s=d["sidestream_fraction"];m.s=Var(initialize=s);m.s.fix(s);m.rem=Var(initialize=.8);m.eff=Var(initialize=.0002);m.energy=Var(initialize=30);m.c1=Constraint(expr=m.rem==.60*(1-m.s)+.90*m.s);m.c2=Constraint(expr=m.eff==.001*(1-m.rem));m.c3=Constraint(expr=m.energy==80*(1-m.s)+20*m.s);m.q=Constraint(expr=m.eff<=.0002);metrics={"nitrogen_removal_fraction":m.rem,"tn_return_kg_s":m.eff,"aeration_index":m.energy}
    elif mode=="asm2d_fermentation":
        f=d["sludge_fermentation_fraction"];m.f=Var(initialize=f);m.f.fix(f);m.vfa=Var(initialize=.0005);m.nrem=Var(initialize=.8);m.prem=Var(initialize=.85);m.solids=Var(initialize=.001);m.c1=Constraint(expr=m.vfa==.003*m.f*.30);m.c2=Constraint(expr=m.nrem==.60+.22*m.vfa/.0006);m.c3=Constraint(expr=m.prem==.70+.20*m.vfa/.0006);m.c4=Constraint(expr=m.solids==.003*m.f*.50);m.q=Constraint(expr=m.solids<=.0012);metrics={"vfa_return_kg_s":m.vfa,"nitrogen_removal_fraction":m.nrem,"phosphorus_removal_fraction":m.prem,"fermented_solids_kg_s":m.solids}
    elif mode=="adm1_scrub":
        p=d["scrubber_pressure_bar"];m.p=Var(initialize=p);m.p.fix(p);m.co2rem=Var(initialize=.8);m.loss=Var(initialize=.01);m.ch4=Var(initialize=.05);m.co2=Var(initialize=.001);m.purity=Var(initialize=.95);m.power=Var(initialize=60);m.c1=Constraint(expr=m.co2rem==1-exp(-.35*(m.p-1)));m.c2=Constraint(expr=m.loss==.006+.001*m.p);m.c3=Constraint(expr=m.ch4==.0527*(1-m.loss));m.c4=Constraint(expr=m.co2==.0055*(1-m.co2rem));m.c5=Constraint(expr=m.purity*(m.ch4+m.co2)==m.ch4);m.c6=Constraint(expr=m.power==12*m.p);m.q=Constraint(expr=m.purity>=.95);metrics={"co2_removal_fraction":m.co2rem,"methane_loss_fraction":m.loss,"biomethane_purity":m.purity,"compression_power_kW":m.power}
    elif mode=="bsm2_equalization":
        h=d["equalization_hours"];m.h=Var(initialize=h);m.h.fix(h);m.peak=Var(initialize=1.2);m.volume=Var(initialize=1000);m.energy=Var(initialize=3);m.c1=Constraint(expr=m.peak==1+1/(1+m.h/2));m.c2=Constraint(expr=m.volume==170*m.h);m.c3=Constraint(expr=m.energy==.5*m.h);m.q=Constraint(expr=m.peak<=1.2);metrics={"peak_load_factor":m.peak,"equalization_volume_m3":m.volume,"pumping_index":m.energy}
    elif mode=="digestate_strip":
        t,ph=d["strip_temperature_C"],d["strip_pH"];free=1/(1+10**(9.25-ph));boost=min(1,.45+.012*(t-40));rem=.98*free*boost;m.t=Var(initialize=t);m.t.fix(t);m.ph=Var(initialize=ph);m.ph.fix(ph);m.rem=Var(initialize=rem);m.eff=Var(initialize=.0001);m.fert=Var(initialize=.0008);m.energy=Var(initialize=150);m.c1=Constraint(expr=m.rem==rem);m.c2=Constraint(expr=m.eff==.001*(1-m.rem));m.c3=Constraint(expr=m.fert==.001*m.rem);m.c4=Constraint(expr=m.energy==4*(m.t-35)+15*(m.ph-9));m.q=Constraint(expr=m.eff<=.00015);metrics={"ammonia_recovery_fraction":m.rem,"effluent_ammonium_kg_s":m.eff,"ammonium_sulfate_n_kg_s":m.fert,"energy_reagent_index":m.energy}
    elif mode=="coag_seed":
        r,dose=d["sludge_seed_recycle_fraction"],d["coagulant_relative_dose"];m.r=Var(initialize=r);m.r.fix(r);m.d=Var(initialize=dose);m.d.fix(dose);m.rem=Var(initialize=.95);m.eff=Var(initialize=.0005);m.metal=Var(initialize=.0001);m.sludge=Var(initialize=.01);m.c1=Constraint(expr=m.rem==1-exp(-2*m.d*(1+.8*m.r)));m.c2=Constraint(expr=m.eff==.01*(1-m.rem));m.c3=Constraint(expr=m.metal==.0001*m.d*(1-.2*m.r));m.c4=Constraint(expr=m.sludge==.01*m.rem+.0001*m.d);m.q1=Constraint(expr=m.eff<=.0005);m.q2=Constraint(expr=m.metal<=.00015);metrics={"turbidity_removal_fraction":m.rem,"effluent_solids_kg_s":m.eff,"residual_metal_kg_s":m.metal,"sludge_kg_s":m.sludge}
    else: raise KeyError(mode)
    return m,metrics


def solve_one(meta):
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.environ import check_optimal_termination,value
    from watertap.core.solvers import get_solver
    try:
        d,rows=search(meta["mode"]);m,objs=build(meta["mode"],d);initial=degrees_of_freedom(m);res=get_solver().solve(m);final=degrees_of_freedom(m);optimal=bool(check_optimal_termination(res));metrics={k:float(value(v)) for k,v in objs.items()};passed=optimal and initial==0 and final==0
        return {"pass":passed,"stage":"native_biological_process_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(res.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":optimal},{"name":"initial_dof_zero","pass":initial==0},{"name":"final_dof_zero","pass":final==0}],"initial_dof":initial,"final_dof":final,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo biological reaction/resource-recovery extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if passed else {"message":"native extension checks failed"}}
    except Exception as e:
        return {"pass":False,"stage":"native_biological_process_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(e).__name__,"message":str(e),"traceback_tail":traceback.format_exc()[-5000:]}}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--case",action="append",choices=sorted(BY_KEY));p.add_argument("--reuse-passing",action="store_true");a=p.parse_args();selected=a.case or [x["key"] for x in BATCH];out=[]
    for key in selected:
        folder=VALIDATION_ROOT/key;folder.mkdir(parents=True,exist_ok=True);rp=folder/"native_solve_report.json"
        if a.reuse_passing and rp.is_file():
            old=json.loads(rp.read_text());
            if old.get("pass") is True and old.get("final_dof")==0:out.append({"case_key":key,"pass":True,"reused":True});continue
        report=solve_one(BY_KEY[key]);rp.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n");(folder/"native_execution.log").write_text(json.dumps({k:v for k,v in report.items() if k!="search_results"},indent=2,ensure_ascii=False)+"\n");out.append({"case_key":key,"pass":report.get("pass") is True,"report":str(rp.relative_to(ROOT))})
    result={"pass":all(x["pass"] for x in out),"case_count":len(out),"results":out};print(json.dumps(result,indent=2));raise SystemExit(0 if result["pass"] else 1)


if __name__=="__main__":main()
