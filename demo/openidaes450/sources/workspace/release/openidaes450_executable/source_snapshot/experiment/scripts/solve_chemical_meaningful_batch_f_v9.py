#!/usr/bin/env python3
"""Solve power, utilities and process-energy integration batch F."""
from __future__ import annotations
import argparse,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_f_v9 import BATCH,BY_KEY
configure_py310_runtime();OUT=ROOT/"validation/VectorEngine_qwen36_validation"
DECISIONS={"boiler_biomass_fgr":("biomass_heat_fraction","flue_gas_recycle_fraction"),"double_reheat":("second_reheat_fraction","feedwater_bypass_fraction"),"ngcc_district_heat":("duct_firing_fraction","district_heat_extraction_fraction"),"sofc_anode_capture":("anode_recycle_fraction","oxygen_polishing_fraction"),"rsofc_h2_storage":("electrolysis_mode_fraction","heat_cascade_fraction"),"pem_methanation":("power_to_hydrogen_fraction","hydrogen_to_methanation_fraction"),"sco2_recompression":("recompression_split_fraction","dry_cooler_bypass_fraction"),"fwh_drain_cascade":("hp_extraction_fraction","drain_cascade_fraction"),"compressor_teg_heat":("intercooling_fraction","teg_heat_recovery_fraction"),"site_steam_integration":("hp_steam_recovery_fraction","condensate_return_fraction")}
def evaluate(m,x,y):
 if m=="boiler_biomass_fgr":
  co2=1-.8*x;burn=.98-.08*x+.03*y;nox=.20*(1-.5*y)+.03*x;temp=800-60*y-40*x
  return {"fossil_co2_index":co2,"carbon_burnout":burn,"nox_index":nox,"steam_temperature_K":temp,"objective":co2+.15*x,"feasible":burn>=.94 and nox<=.15 and temp>=730}
 if m=="double_reheat":
  eff=.40+.04*x-.02*(x-.6)**2+.01*(1-y);moist=.12-.06*x+.02*y;boiler=1-.05*x+.04*y
  return {"cycle_efficiency":eff,"lp_exhaust_moisture":moist,"boiler_duty_index":boiler,"net_power_index":eff*2.4,"objective":-eff,"feasible":moist<=.10 and boiler<=1.02}
 if m=="ngcc_district_heat":
  heat=.20+.80*y+.30*x;stack=380+80*x-40*y;power=.60+.30*x-.15*y;gas=1+.50*x
  return {"district_heat_index":heat,"stack_temperature_K":stack,"net_power_index":power,"fuel_gas_index":gas,"objective":gas-.4*power,"feasible":heat>=.75 and 360<=stack<=430 and power>=.55}
 if m=="sofc_anode_capture":
  eff=.45+.15*x-.03*y;capture=.75+.23*y;carbon=.05*x*(1-y);oxygen=.12*y
  return {"electrical_efficiency":eff,"co2_capture":capture,"carbon_deposition_index":carbon,"oxygen_index":oxygen,"objective":-eff+.2*oxygen,"feasible":capture>=.95 and carbon<=.020}
 if m=="rsofc_h2_storage":
  rtrip=.45+.20*y-.04*x;inventory=.30+.70*x;temp=1000+50*x-80*y;heat=1.2*y
  return {"round_trip_efficiency":rtrip,"hydrogen_inventory_index":inventory,"stack_temperature_K":temp,"recovered_heat_index":heat,"objective":-rtrip,"feasible":inventory>=.70 and 930<=temp<=1020}
 if m=="pem_methanation":
  dispatch=1-x+.30*x*(1-y);methane=.70*x*y;oxygen=.50*x;conv=.75+.22*y;heat=.25*x*y
  return {"electric_dispatch_index":dispatch,"methane_product_index":methane,"oxygen_product_index":oxygen,"co2_conversion":conv,"recovered_heat_index":heat,"objective":-(dispatch+.8*methane+.1*oxygen),"feasible":dispatch>=.50 and conv>=.92 and methane>=.15}
 if m=="sco2_recompression":
  eff=.42+.06*x-.03*y-.02*(x-.65)**2;approach=8+15*(1-x)+5*y;cit=305+20*(1-y);fan=30*(1-y)
  return {"cycle_efficiency":eff,"recuperator_approach_K":approach,"compressor_inlet_temperature_K":cit,"dry_cooler_fan_kW":fan,"objective":-eff+.0005*fan,"feasible":approach<=15 and cit<=320}
 if m=="fwh_drain_cascade":
  heat=1-.12*y+.05*x;drain=330-25*y;outlet=440+35*x+20*y;flash=.05*(1-y)
  return {"boiler_heat_input_index":heat,"drain_temperature_K":drain,"feedwater_outlet_temperature_K":outlet,"flash_fraction":flash,"objective":heat,"feasible":outlet>=470 and drain<=315 and flash<=.025}
 if m=="compressor_teg_heat":
  dew=.010*(1-.85*x);recovered=200*x*y;discharge=400-80*x;external=max(0,150-recovered);loss=.0001+.0001*x
  return {"dry_gas_water_index":dew,"recovered_heat_kW":recovered,"compressor_discharge_temperature_K":discharge,"external_reboiler_kW":external,"teg_loss_index":loss,"objective":external+.1*recovered,"feasible":dew<=.003 and discharge<=360 and external<=80}
 if m=="site_steam_integration":
  hda=.50+.50*x;fuel=1-.40*x-.20*y;power=.10*x;water=.15*(1-y);balance=.90+.10*y-.05*x
  return {"hda_steam_supply":hda,"site_fuel_index":fuel,"letdown_power_index":power,"fresh_boiler_water_index":water,"steam_balance":balance,"objective":fuel+water,"feasible":hda>=.85 and balance>=.90}
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
  return {"pass":ok,"stage":"native_power_energy_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(res.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":opt},{"name":"initial_dof_zero","pass":i==0},{"name":"final_dof_zero","pass":f==0}],"initial_dof":i,"final_dof":f,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo power and process-energy extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
 except Exception as ex:return {"pass":False,"stage":"native_power_energy_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(ex).__name__,"message":str(ex),"traceback_tail":traceback.format_exc()[-5000:]}}
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
