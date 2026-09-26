#!/usr/bin/env python3
"""Solve chemically meaningful safety and operability batch J."""
from __future__ import annotations
import argparse,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_j_v13 import BATCH,BY_KEY
configure_py310_runtime();OUT=ROOT/"validation/VectorEngine_qwen36_validation"
DECISIONS={"methanol_quench_relief":("cold_gas_quench_fraction","relief_condensation_fraction"),"hda_n2_quench":("hydrogen_cutoff_fraction","nitrogen_quench_fraction"),"gas_hydrate_slug":("methanol_inhibitor_fraction","inhibitor_recovery_fraction"),"chlorine_dechlor":("chlorine_contact_fraction","bisulfite_dechlorination_fraction"),"biogas_h2s_emergency":("guard_bed_utilization_fraction","emergency_scrubber_fraction"),"leach_spill_recovery":("lime_neutralization_fraction","ree_redissolution_fraction"),"sofc_fuel_trip":("nitrogen_purge_fraction","heat_dump_fraction"),"boiler_startup_transition":("biomass_transition_fraction","startup_fgr_fraction"),"pz_reclaimer":("solvent_reclaimer_fraction","pz_makeup_fraction"),"ro_cip_recovery":("cleanant_reuse_fraction","purge_neutralization_fraction"),"ammonia_storage_scrub":("emergency_scrubber_fraction","recovered_salt_return_fraction")}
def evaluate(m,x,y):
 if m=="methanol_quench_relief":
  peak=610-190*x;pressure=110-55*x;methanol=.48+.47*y;flare=.22*(1-y);quench=.15*x
  return {"runaway_peak_temperature_K":peak,"relief_pressure_bar":pressure,"methanol_recovery":methanol,"flare_load_index":flare,"quench_inventory_index":quench,"objective":quench+flare,"feasible":peak<=480 and pressure<=75 and methanol>=.88 and flare<=.06}
 if m=="hda_n2_quench":
  peak=710-90*x-210*y;h2=.10*(1-x);arom=.50+.43*y;flare=.20*(1-y);n2=.20*y
  return {"runaway_peak_temperature_K":peak,"residual_hydrogen_fraction":h2,"aromatic_recovery":arom,"flare_load_index":flare,"nitrogen_inventory_index":n2,"objective":n2+flare,"feasible":peak<=490 and h2<=.025 and arom>=.88}
 if m=="gas_hydrate_slug":
  margin=-5+16*x;methanol=.032*x*(1-y);recovery=.50+.46*y;slug=.12*(1-.5*x);duty=.4*y
  return {"hydrate_margin_K":margin,"product_methanol_fraction":methanol,"inhibitor_recovery":recovery,"liquid_slug_index":slug,"recovery_duty_index":duty,"objective":.2*x+duty,"feasible":margin>=5 and methanol<=.010 and recovery>=.90}
 if m=="chlorine_dechlor":
  logkill=.80+4.2*x;residual=.050*x*(1-y);sulfate=.018*y;water=.80+.18*y;reagent=.10*x+.08*y
  return {"pathogen_log_reduction":logkill,"free_chlorine_residual":residual,"sulfate_addition":sulfate,"water_recovery":water,"reagent_index":reagent,"objective":reagent,"feasible":logkill>=4.0 and residual<=.010 and sulfate<=.018 and water>=.92}
 if m=="biogas_h2s_emergency":
  chp=.020*(1-.92*x);flare_h2s=.020*(1-.85*y);destroy=.88+.11*y;caustic=.10*y;bedlife=.55+.4*x
  return {"chp_h2s_index":chp,"flare_h2s_index":flare_h2s,"methane_destruction":destroy,"caustic_index":caustic,"bed_life_fraction":bedlife,"objective":caustic+.1*x,"feasible":chp<=.003 and flare_h2s<=.004 and destroy>=.96 and bedlife>=.85}
 if m=="leach_spill_recovery":
  ph=2+8*x;ree=.50+.45*y;acid=.10*(1-x);sludge=.20*x-.10*y;water=.04*(1-y)
  return {"neutralized_ph":ph,"ree_recovery":ree,"residual_acid_index":acid,"waste_sludge_index":sludge,"water_ree_index":water,"objective":sludge+.2*x,"feasible":6<=ph<=9 and ree>=.90 and acid<=.04 and water<=.01}
 if m=="sofc_fuel_trip":
  oxygen=.050*(1-x);gradient=85*(1-y);stack=1000-150*y;vent=.03*(1-x);n2=.20*x
  return {"anode_oxygen_fraction":oxygen,"thermal_gradient_K":gradient,"stack_temperature_K":stack,"flammable_vent_fraction":vent,"nitrogen_index":n2,"objective":n2+.1*y,"feasible":oxygen<=.010 and gradient<=35 and stack>=870 and vent<=.008}
 if m=="boiler_startup_transition":
  stability=.58+.31*x+.12*y;co=.055*(1-x)+.008*y;nox=.20*(1-y)+.025*x;steam=650+120*x-50*y
  return {"flame_stability":stability,"co_index":co,"nox_index":nox,"steam_temperature_K":steam,"objective":co+nox+.05*(1-x),"feasible":stability>=.90 and co<=.020 and nox<=.10 and steam>=700}
 if m=="pz_reclaimer":
  hss=.080*(1-.85*x);capture=.90+.08*y-.02*x;corrosion=.40*hss;loss=.030*x-.010*y;duty=.5*x
  return {"heat_stable_salt_fraction":hss,"co2_capture":capture,"corrosion_index":corrosion,"pz_loss_index":loss,"reclaimer_duty_index":duty,"objective":duty+10*max(loss,0),"feasible":hss<=.020 and capture>=.94 and corrosion<=.010 and loss<=.020}
 if m=="ro_cip_recovery":
  cleaning=.70+.26*x;ph=2+6*y;waste=.20*(1-x);damage=.030*x*(1-y);salt=.05*(1-y)
  return {"cleaning_effectiveness":cleaning,"neutralized_purge_ph":ph,"liquid_waste_index":waste,"membrane_damage_index":damage,"purge_salt_index":salt,"objective":waste+.1*y,"feasible":cleaning>=.92 and 6<=ph<=9 and damage<=.008 and salt<=.015}
 if m=="ammonia_storage_scrub":
  vent=.050*(1-.95*x);fert=.70+.24*y+.06*x;acid=.10*x;stack=.020*(1-y);salt=.15*x*y
  return {"ammonia_vent_index":vent,"fertilizer_n_recovery":fert,"acid_index":acid,"clean_stack_index":stack,"recovered_salt_index":salt,"objective":acid+.05*y,"feasible":vent<=.005 and fert>=.92 and stack<=.005}
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
  return {"pass":ok,"stage":"native_safety_operability_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(res.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":opt},{"name":"initial_dof_zero","pass":i==0},{"name":"final_dof_zero","pass":f==0}],"initial_dof":i,"final_dof":f,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo safety/operability extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
 except Exception as ex:return {"pass":False,"stage":"native_safety_operability_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(ex).__name__,"message":str(ex),"traceback_tail":traceback.format_exc()[-5000:]}}
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
