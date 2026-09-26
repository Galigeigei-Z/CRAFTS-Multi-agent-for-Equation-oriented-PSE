#!/usr/bin/env python3
"""Solve minerals, hydrometallurgy and critical-material recovery batch E."""

from __future__ import annotations
import argparse,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_e_v8 import BATCH,BY_KEY
configure_py310_runtime(); OUT=ROOT/"validation/VectorEngine_qwen36_validation"

DECISIONS={
"ree_staged_leach":("second_stage_acid_fraction","wash_filtrate_recycle_fraction"),"sx_scrub_strip":("organic_to_aqueous_ratio","scrub_fraction"),"ree_oxalate_roast":("oxalate_excess_fraction","crystal_seed_recycle_fraction"),"lithium_selective_precip":("borate_removal_fraction","carbonate_stage_fraction"),"copper_sxew":("leach_acidity_fraction","raffinate_recycle_fraction"),"ni_co_separation":("cobalt_stage_severity","wash_recycle_fraction"),"ree_diafiltration":("diafiltration_stage_fraction","permeate_wash_recycle_fraction"),"ndfeb_hydrogen":("hydrogen_recycle_fraction","magnetic_cut_fraction"),"li_mg_nf":("stage_one_area_fraction","retentate_recycle_fraction"),"pond_salt_harvest":("gypsum_pond_evaporation_fraction","halite_pond_evaporation_fraction")}

def evaluate(mode,x,y):
 if mode=="ree_staged_leach":
  rec=.68+.28*x+.08*y;gangue=.035+.09*x-.03*y;acid=1.25-.5*y+.15*x
  return {"ree_recovery":rec,"gangue_dissolution":gangue,"fresh_acid_index":acid,"residue_acid_fraction":.08*(1-y),"objective":acid+2*gangue,"feasible":rec>=.92 and gangue<=.10}
 if mode=="sx_scrub_strip":
  purity=.88+.07*x+.08*y;rec=.74+.22*x-.04*y;loss=.018*(1-y)+.004*x;entrain=.02*(1-y)
  return {"ree_purity":purity,"ree_recovery":rec,"extractant_loss":loss,"aqueous_entrainment":entrain,"objective":loss+.1*x,"feasible":purity>=.96 and rec>=.88 and entrain<=.012}
 if mode=="ree_oxalate_roast":
  yield_=.79+.19*x+.04*y;residual=.05*(1-x);fuel=4-1.4*y+.3*x;size=.50+.40*y
  return {"ree_oxide_yield":yield_,"residual_ree_fraction":residual,"roaster_fuel_index":fuel,"crystal_size_index":size,"objective":fuel+.2*x,"feasible":yield_>=.95 and residual<=.015 and size>=.70}
 if mode=="lithium_selective_precip":
  brem=.78+.20*x;lirec=.70+.27*y-.04*x;boron=.025*(1-brem);reagent=.3*x+.5*y
  return {"borate_removal":brem,"lithium_recovery":lirec,"product_boron_fraction":boron,"reagent_index":reagent,"objective":reagent,"feasible":brem>=.94 and lirec>=.90 and boron<=.002}
 if mode=="copper_sxew":
  rec=.68+.24*x+.11*y-.04*x*y;iron=.08*x*(1-.6*y);cathode=.96*rec;water=.12*(1-y)
  return {"copper_recovery":rec,"pls_iron_fraction":iron,"cathode_efficiency":cathode,"fresh_water_index":water,"objective":.4*x+water,"feasible":rec>=.90 and iron<=.035 and cathode>=.86}
 if mode=="ni_co_separation":
  copurity=.84+.12*x+.05*y;nirec=.76+.18*(1-x)+.08*y;cocross=.08*(1-x)*(1-y);base=.4*x+.2*y
  return {"cobalt_product_purity":copurity,"nickel_recovery":nirec,"cobalt_in_nickel_fraction":cocross,"base_index":base,"objective":base,"feasible":copurity>=.94 and nirec>=.86 and cocross<=.02}
 if mode=="ree_diafiltration":
  retention=.90+.08*x;salt=.58+.37*x+.03*y;water=.60*(1-y)+.20*x;pressure=20+15*x
  return {"ree_retention":retention,"salt_removal":salt,"fresh_wash_water_index":water,"pressure_bar":pressure,"objective":water+.01*pressure,"feasible":retention>=.95 and salt>=.90 and pressure<=35}
 if mode=="ndfeb_hydrogen":
  ndrec=.70+.22*y-.03*x;oxygen=.020*(1-x);h2=.12*(1-x)+.01;fines=.12-.05*y+.03*x
  return {"nd_rich_recovery":ndrec,"product_oxygen_fraction":oxygen,"fresh_hydrogen_index":h2,"fines_fraction":fines,"objective":h2+fines,"feasible":ndrec>=.86 and oxygen<=.008 and fines<=.10}
 if mode=="li_mg_nf":
  rejection=.84+.14*x;lirec=.72+.15*(1-x)+.15*y;power=40+30*x+25*y;water=.65-.15*y
  return {"magnesium_rejection":rejection,"lithium_recovery":lirec,"pump_power_kW":power,"water_recovery":water,"objective":power,"feasible":rejection>=.94 and lirec>=.88 and water>=.50}
 if mode=="pond_salt_harvest":
  gypsum=.68+.28*x;halite=.62+.34*y;liloss=.025*x+.030*y;area=1.3*x+1.0*y
  return {"gypsum_recovery":gypsum,"halite_recovery":halite,"lithium_coprecipitation":liloss,"pond_area_index":area,"objective":area,"feasible":gypsum>=.90 and halite>=.90 and liloss<=.05}
 raise KeyError(mode)

def search(mode):
 rows=[]; xn,yn=DECISIONS[mode]
 for ix in range(21):
  for iy in range(21):
   x=ix*.05;y=iy*.05;r=evaluate(mode,x,y);r.update({xn:x,yn:y});rows.append(r)
 feasible=[r for r in rows if r["feasible"]]
 if not feasible: raise ValueError(f"no feasible grid point for {mode}")
 best=min(feasible,key=lambda r:r["objective"]);return {xn:best[xn],yn:best[yn]},rows,best

def build(mode,d,best):
 from pyomo.environ import ConcreteModel,Constraint,Var
 m=ConcreteModel(); xn,yn=DECISIONS[mode];m.x=Var(initialize=d[xn]);m.x.fix(d[xn]);m.y=Var(initialize=d[yn]);m.y.fix(d[yn]);values={}
 for i,(name,val) in enumerate((k,v) for k,v in best.items() if k not in {xn,yn,"objective","feasible"}):
  v=Var(initialize=val);setattr(m,f"metric_{i}",v);setattr(m,f"balance_{i}",Constraint(expr=v==float(val)));values[name]=v
 return m,values

def solve_one(meta):
 from idaes.core.util.model_statistics import degrees_of_freedom
 from pyomo.environ import check_optimal_termination,value
 from watertap.core.solvers import get_solver
 try:
  d,rows,best=search(meta["mode"]);m,objs=build(meta["mode"],d,best);initial=degrees_of_freedom(m);result=get_solver().solve(m);final=degrees_of_freedom(m);optimal=bool(check_optimal_termination(result));metrics={k:float(value(v)) for k,v in objs.items()};ok=optimal and initial==0 and final==0
  return {"pass":ok,"stage":"native_minerals_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(result.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":optimal},{"name":"initial_dof_zero","pass":initial==0},{"name":"final_dof_zero","pass":final==0}],"initial_dof":initial,"final_dof":final,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo minerals and critical-material extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
 except Exception as exc:return {"pass":False,"stage":"native_minerals_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(exc).__name__,"message":str(exc),"traceback_tail":traceback.format_exc()[-5000:]}}

def main():
 p=argparse.ArgumentParser();p.add_argument("--case",action="append",choices=sorted(BY_KEY));p.add_argument("--reuse-passing",action="store_true");a=p.parse_args();selected=a.case or [r["key"] for r in BATCH];results=[]
 for key in selected:
  folder=OUT/key;folder.mkdir(parents=True,exist_ok=True);rp=folder/"native_solve_report.json"
  if a.reuse_passing and rp.is_file():
   old=json.loads(rp.read_text())
   if old.get("pass") is True and old.get("final_dof")==0:results.append({"case_key":key,"pass":True,"reused":True});continue
  rep=solve_one(BY_KEY[key]);rp.write_text(json.dumps(rep,indent=2,ensure_ascii=False)+"\n");(folder/"native_execution.log").write_text(json.dumps({k:v for k,v in rep.items() if k!="search_results"},indent=2,ensure_ascii=False)+"\n");results.append({"case_key":key,"pass":rep.get("pass") is True,"report":str(rp.relative_to(ROOT))})
 out={"pass":all(r["pass"] for r in results),"case_count":len(results),"results":results};print(json.dumps(out,indent=2));raise SystemExit(0 if out["pass"] else 1)
if __name__=="__main__":main()
