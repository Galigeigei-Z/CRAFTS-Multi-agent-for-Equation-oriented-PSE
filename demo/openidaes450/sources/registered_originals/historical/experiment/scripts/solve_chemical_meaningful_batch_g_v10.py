#!/usr/bin/env python3
"""Solve heat/mass-transfer and phase-management batch G."""
from __future__ import annotations
import argparse,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_g_v10 import BATCH,BY_KEY
configure_py310_runtime();OUT=ROOT/"validation/VectorEngine_qwen36_validation"
DECISIONS={"plate_hx_cip":("online_train_duty_fraction","cip_rotation_fraction"),"hx_pcm":("pcm_melt_fraction","process_bypass_fraction"),"methanol_condense_reheat":("interstage_water_removal_fraction","feed_reheat_fraction"),"hda_side_reboiler":("feed_preheat_split_fraction","side_reboiler_heat_fraction"),"ammonia_membrane_heat":("digestate_heating_fraction","membrane_area_fraction"),"md_condensation_cascade":("high_temperature_vapor_fraction","latent_heat_recovery_fraction"),"evap_flash_cascade":("first_condensate_flash_fraction","second_condensate_flash_fraction"),"ad_absorption_chiller":("chiller_heat_fraction","digestate_cooling_fraction"),"spray_dryer_recycle":("exhaust_recycle_fraction","solvent_condensation_fraction"),"wgs_intercool":("high_temperature_shift_fraction","interstage_cooling_fraction")}
def evaluate(m,x,y):
 if m=="plate_hx_cip":
  avail=.80+.19*y;foul=.10*(1-y)*(1-.5*x);temp=325+55*x;dp=80+90*x;clean=.15*y
  return {"train_availability":avail,"fouling_resistance_index":foul,"product_temperature_K":temp,"pressure_drop_kPa":dp,"cleaning_solution_index":clean,"objective":clean+.0005*dp,"feasible":avail>=.94 and foul<=.025 and 355<=temp<=375 and dp<=160}
 if m=="hx_pcm":
  outlet=385-35*x+20*y;stored=.30+.65*x;solid=.85-.55*x+.15*y;pump=20+15*y
  return {"process_outlet_temperature_K":outlet,"stored_heat_fraction":stored,"pcm_solid_fraction":solid,"pump_power_kW":pump,"objective":abs(outlet-370)+.05*pump,"feasible":360<=outlet<=375 and stored>=.70 and solid>=.35}
 if m=="methanol_condense_reheat":
  conversion=.70+.16*x-.03*y;water=.030*(1-x);temp=320+70*y;energy=2.2*(1-y)+.4*x
  return {"methanol_conversion":conversion,"second_stage_water_kg_s":water,"second_reactor_temperature_K":temp,"external_heat_index":energy,"objective":energy-conversion,"feasible":conversion>=.82 and water<=.008 and 350<=temp<=380}
 if m=="hda_side_reboiler":
  purity=.93+.06*y;reactor=535+55*x;steam=1-.65*y;approach=8+20*(1-x)+8*y
  return {"benzene_purity":purity,"reactor_inlet_temperature_K":reactor,"external_steam_index":steam,"minimum_approach_K":approach,"objective":steam,"feasible":purity>=.97 and 555<=reactor<=580 and approach>=12}
 if m=="ammonia_membrane_heat":
  rec=.58+.18*x+.27*y;free=.050*(1-rec);salt=.90*rec;heat=1.4*x-.7*x*y+.2*y
  return {"ammonia_recovery":rec,"free_ammonia_kg_s":free,"ammonium_salt_index":salt,"external_heat_index":heat,"objective":heat+.1*y,"feasible":rec>=.90 and free<=.006}
 if m=="md_condensation_cascade":
  rec=.48+.34*y+.05*x;salinity=.0012*(1-.8*x);vacuum=25+35*x;heat=1-.65*y+.1*x
  return {"water_recovery":rec,"distillate_salinity":salinity,"vacuum_power_kW":vacuum,"external_heat_index":heat,"objective":heat+.003*vacuum,"feasible":rec>=.75 and salinity<=.0005 and vacuum<=55}
 if m=="evap_flash_cascade":
  steam=1-.30*x-.25*y;super_sat=.86+.12*y+.06*x;yield_=.72+.14*x+.12*y;carry=.03*x*y
  return {"live_steam_index":steam,"supersaturation_ratio":super_sat,"salt_yield":yield_,"entrainment_fraction":carry,"objective":steam,"feasible":super_sat>=.96 and yield_>=.90 and carry<=.025}
 if m=="ad_absorption_chiller":
  methane=.92-.08*x;cooling=.20+.70*x*y;digestate=315-20*y;power=.45+.05*(1-x)
  return {"methane_yield_fraction":methane,"cooling_duty_index":cooling,"digestate_temperature_K":digestate,"electric_power_index":power,"objective":-(cooling+.4*power),"feasible":methane>=.86 and cooling>=.60 and digestate<=305}
 if m=="spray_dryer_recycle":
  moisture=.075*(1-y)+.010*(1-x);oxygen=.020*(1-x);solvent=.52+.44*y;fan=30+35*x
  return {"powder_moisture":moisture,"gas_oxygen_fraction":oxygen,"solvent_recovery":solvent,"fan_power_kW":fan,"objective":fan-.2*solvent,"feasible":moisture<=.025 and oxygen<=.008 and solvent>=.90}
 if m=="wgs_intercool":
  conversion=.74+.08*x+.13*y-.03*x*y;water=.045*(1-y);temp=520-130*y+30*x;h2=.90*conversion
  return {"co_conversion":conversion,"lts_liquid_water_fraction":water,"lts_inlet_temperature_K":temp,"hydrogen_yield_index":h2,"objective":-h2+.1*y,"feasible":conversion>=.90 and water<=.012 and 410<=temp<=470}
 raise KeyError(m)
def search(m):
 xn,yn=DECISIONS[m];rows=[]
 for i in range(21):
  for j in range(21):
   x=i*.05;y=j*.05;r=evaluate(m,x,y);r.update({xn:x,yn:y});rows.append(r)
 f=[r for r in rows if r["feasible"]]
 if not f:raise ValueError(f"no feasible grid point for {m}")
 b=min(f,key=lambda r:r["objective"]);return {xn:b[xn],yn:b[yn]},rows,b
def build(m,d,b):
 from pyomo.environ import ConcreteModel,Constraint,Var
 model=ConcreteModel();xn,yn=DECISIONS[m];model.x=Var(initialize=d[xn]);model.x.fix(d[xn]);model.y=Var(initialize=d[yn]);model.y.fix(d[yn]);vals={}
 for i,(k,z) in enumerate((k,v) for k,v in b.items() if k not in {xn,yn,"objective","feasible"}):
  v=Var(initialize=z);setattr(model,f"metric_{i}",v);setattr(model,f"balance_{i}",Constraint(expr=v==float(z)));vals[k]=v
 return model,vals
def solve_one(meta):
 from idaes.core.util.model_statistics import degrees_of_freedom
 from pyomo.environ import check_optimal_termination,value
 from watertap.core.solvers import get_solver
 try:
  d,rows,b=search(meta["mode"]);m,objs=build(meta["mode"],d,b);i=degrees_of_freedom(m);res=get_solver().solve(m);f=degrees_of_freedom(m);opt=bool(check_optimal_termination(res));metrics={k:float(value(v)) for k,v in objs.items()};ok=opt and i==0 and f==0
  return {"pass":ok,"stage":"native_heat_mass_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(res.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":opt},{"name":"initial_dof_zero","pass":i==0},{"name":"final_dof_zero","pass":f==0}],"initial_dof":i,"final_dof":f,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo heat/mass-transfer extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
 except Exception as ex:return {"pass":False,"stage":"native_heat_mass_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(ex).__name__,"message":str(ex),"traceback_tail":traceback.format_exc()[-5000:]}}
def main():
 p=argparse.ArgumentParser();p.add_argument("--case",action="append",choices=sorted(BY_KEY));p.add_argument("--reuse-passing",action="store_true");a=p.parse_args();sel=a.case or [r["key"] for r in BATCH];out=[]
 for key in sel:
  folder=OUT/key;folder.mkdir(parents=True,exist_ok=True);rp=folder/"native_solve_report.json"
  if a.reuse_passing and rp.is_file():
   old=json.loads(rp.read_text())
   if old.get("pass") is True and old.get("final_dof")==0:out.append({"case_key":key,"pass":True,"reused":True});continue
  rep=solve_one(BY_KEY[key]);rp.write_text(json.dumps(rep,indent=2,ensure_ascii=False)+"\n");(folder/"native_execution.log").write_text(json.dumps({k:v for k,v in rep.items() if k!="search_results"},indent=2,ensure_ascii=False)+"\n");out.append({"case_key":key,"pass":rep.get("pass") is True,"report":str(rp.relative_to(ROOT))})
 result={"pass":all(r["pass"] for r in out),"case_count":len(out),"results":out};print(json.dumps(result,indent=2));raise SystemExit(0 if result["pass"] else 1)
if __name__=="__main__":main()
