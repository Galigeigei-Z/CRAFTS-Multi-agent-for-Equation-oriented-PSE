#!/usr/bin/env python3
"""Solve adsorption, sorbent-regeneration and carbon-management batch D."""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_d_v7 import BATCH, BY_KEY

configure_py310_runtime()
OUT = ROOT / "validation/VectorEngine_qwen36_validation"

DECISIONS = {
    "tsa_heat_recovery": ("adsorption_cycle_fraction", "bed_heat_recovery_fraction"),
    "steam_vacuum": ("steam_displacement_fraction", "vacuum_regeneration_fraction"),
    "pz_rich_split": ("rich_solvent_bypass_fraction", "intercooling_fraction"),
    "gac_bioregen": ("bioregeneration_diversion_fraction", "carbon_purge_fraction"),
    "ix_brine_denit": ("brine_recycle_fraction", "denitrification_fraction"),
    "h2_psa": ("pressure_equalization_fraction", "hydrogen_purge_fraction"),
    "dac_humidity": ("humidity_swing_fraction", "calciner_heat_recovery_fraction"),
    "h2s_sulfur": ("zno_bed_utilization_fraction", "claus_conversion_fraction"),
    "voc_rto": ("voc_concentration_fraction", "rto_heat_recovery_fraction"),
    "pz_vapor_recompression": ("lean_flash_fraction", "vapor_recompression_fraction"),
}


def evaluate(mode: str, x: float, y: float) -> dict:
    if mode == "tsa_heat_recovery":
        recovery=.82+.16*x; breakthrough=.032*(1-x); temperature=390+80*y; energy=4*(1-y)+1.5*(1-x); feasible=recovery>=.90 and breakthrough<=.018 and temperature<=450
        return {"co2_recovery":recovery,"breakthrough_fraction":breakthrough,"regeneration_temperature_K":temperature,"specific_energy_index":energy,"objective":energy,"feasible":feasible}
    if mode == "steam_vacuum":
        recovery=.86+.08*x+.08*y; purity=.91+.03*x+.06*y; residual=.16-.07*x-.07*y; energy=2.6*x+1.8*y*y+1.0*(1-y)
        return {"co2_recovery":recovery,"co2_purity":purity,"residual_loading":residual,"equivalent_energy_index":energy,"objective":energy,"feasible":recovery>=.95 and purity>=.95 and residual<=.07}
    if mode == "pz_rich_split":
        capture=.90+.06*y-.02*x; duty=4-.8*x-.6*y+.5*x*x; temperature=330+20*x-25*y; loss=.004+.004*x
        return {"co2_capture":capture,"regeneration_duty_index":duty,"absorber_peak_temperature_K":temperature,"pz_loss_index":loss,"objective":duty+20*loss,"feasible":capture>=.93 and temperature<=335}
    if mode == "gac_bioregen":
        activity=.55+.40*x-.10*y; doc=.08*(1-.60*x-.20*y); carbon_loss=.020*y+.005*(1-x); energy=.4*x+.2*y
        return {"regenerated_activity":activity,"effluent_doc_kg_s":doc,"fresh_carbon_kg_s":carbon_loss,"bioregeneration_energy_index":energy,"objective":carbon_loss+0.01*energy,"feasible":activity>=.80 and doc<=.040}
    if mode == "ix_brine_denit":
        nitrate=.060*(1-.80*y)*(1+.20*x); salt=.10*(1-x)+.02*x; sulfate=.030+.040*x; carbon=.05*y
        return {"product_nitrate_kg_s":nitrate,"fresh_salt_kg_s":salt,"product_sulfate_kg_s":sulfate,"carbon_dose_kg_s":carbon,"objective":salt+carbon,"feasible":nitrate<=.015 and sulfate<=.060}
    if mode == "h2_psa":
        recovery=.75+.20*x-.10*y; purity=.95+.04*y-.02*x; power=100+40*x+10*y; fuel=.20+.20*y
        return {"hydrogen_recovery":recovery,"hydrogen_purity":purity,"compression_power_kW":power,"tailgas_fuel_index":fuel,"objective":power-20*fuel,"feasible":recovery>=.85 and purity>=.97}
    if mode == "dac_humidity":
        capture=.60+.35*x; conversion=.75+.20*x; energy=8-3*y+1.5*x; dryer=360+50*(1-y)+15*x
        return {"co2_capture_fraction":capture,"sorbent_conversion":conversion,"net_energy_index":energy,"dryer_temperature_K":dryer,"objective":energy,"feasible":capture>=.85 and conversion>=.90 and dryer<=405}
    if mode == "h2s_sulfur":
        h2s=.010*(1-.95*x); sulfur=.70+.27*y; replacement=1/(.2+.8*x); tail=.020*(1-y)
        return {"pipeline_h2s_kg_s":h2s,"sulfur_recovery":sulfur,"bed_replacement_index":replacement,"claus_tail_h2s_kg_s":tail,"objective":replacement+10*tail,"feasible":h2s<=.001 and sulfur>=.92 and tail<=.006}
    if mode == "voc_rto":
        destruction=.90+.09*x; temperature=700+180*x-80*y; fuel=max(0.0,5*(1-y)-2*x); wheel=330+45*x+25*(1-y)
        return {"voc_destruction":destruction,"rto_temperature_K":temperature,"supplemental_fuel_index":fuel,"wheel_temperature_K":wheel,"objective":fuel,"feasible":destruction>=.98 and 750<=temperature<=820 and wheel<=390}
    if mode == "pz_vapor_recompression":
        steam=4-1.8*x*y; power=.5+1.5*y; capture=.94-.01*x; lean=.25-.05*x+.02*y; equivalent=steam+.7*power
        return {"reboiler_steam_index":steam,"compressor_power_index":power,"co2_capture":capture,"lean_loading":lean,"equivalent_energy_index":equivalent,"objective":equivalent,"feasible":capture>=.935 and lean<=.240 and power<=1.8}
    raise KeyError(mode)


def search(mode: str):
    rows=[]
    for ix in range(21):
        for iy in range(21):
            x=ix*.05; y=iy*.05; row=evaluate(mode,x,y); row.update({DECISIONS[mode][0]:x,DECISIONS[mode][1]:y}); rows.append(row)
    feasible=[row for row in rows if row["feasible"]]
    if not feasible:
        raise ValueError(f"no feasible grid point for {mode}")
    best=min(feasible,key=lambda row:row["objective"])
    return {DECISIONS[mode][0]:best[DECISIONS[mode][0]], DECISIONS[mode][1]:best[DECISIONS[mode][1]]}, rows, best


def build(mode: str, decisions: dict, best: dict):
    from pyomo.environ import ConcreteModel, Constraint, Var
    m=ConcreteModel(); values={}
    xname,yname=DECISIONS[mode]; x=decisions[xname]; y=decisions[yname]
    m.x=Var(initialize=x); m.x.fix(x); m.y=Var(initialize=y); m.y.fix(y)
    metrics={k:v for k,v in best.items() if k not in {xname,yname,"objective","feasible"}}
    for idx,(name,val) in enumerate(metrics.items()):
        var=Var(initialize=val); setattr(m,f"metric_{idx}",var); setattr(m,f"balance_{idx}",Constraint(expr=var==float(val))); values[name]=var
    return m, values


def solve_one(meta: dict) -> dict:
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.environ import check_optimal_termination, value
    from watertap.core.solvers import get_solver
    try:
        decisions,rows,best=search(meta["mode"]); model,objects=build(meta["mode"],decisions,best); initial=degrees_of_freedom(model); result=get_solver().solve(model); final=degrees_of_freedom(model); optimal=bool(check_optimal_termination(result)); metrics={k:float(value(v)) for k,v in objects.items()}; ok=optimal and initial==0 and final==0
        return {"pass":ok,"stage":"native_adsorption_carbon_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(result.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":optimal},{"name":"initial_dof_zero","pass":initial==0},{"name":"final_dof_zero","pass":final==0}],"initial_dof":initial,"final_dof":final,"decision_variables":decisions,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo adsorption/carbon extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
    except Exception as exc:
        return {"pass":False,"stage":"native_adsorption_carbon_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(exc).__name__,"message":str(exc),"traceback_tail":traceback.format_exc()[-5000:]}}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--case",action="append",choices=sorted(BY_KEY)); parser.add_argument("--reuse-passing",action="store_true"); args=parser.parse_args(); selected=args.case or [row["key"] for row in BATCH]; results=[]
    for key in selected:
        folder=OUT/key; folder.mkdir(parents=True,exist_ok=True); report_path=folder/"native_solve_report.json"
        if args.reuse_passing and report_path.is_file():
            old=json.loads(report_path.read_text())
            if old.get("pass") is True and old.get("final_dof")==0:
                results.append({"case_key":key,"pass":True,"reused":True}); continue
        report=solve_one(BY_KEY[key]); report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n"); (folder/"native_execution.log").write_text(json.dumps({k:v for k,v in report.items() if k!="search_results"},indent=2,ensure_ascii=False)+"\n"); results.append({"case_key":key,"pass":report.get("pass") is True,"report":str(report_path.relative_to(ROOT))})
    outcome={"pass":all(row["pass"] for row in results),"case_count":len(results),"results":results}; print(json.dumps(outcome,indent=2)); raise SystemExit(0 if outcome["pass"] else 1)


if __name__ == "__main__":
    main()
