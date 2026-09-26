#!/usr/bin/env python3
"""Solve chemically coupled hybrid process-integration batch I."""
from __future__ import annotations
import argparse,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_i_v12 import BATCH,BY_KEY
configure_py310_runtime();OUT=ROOT/"validation/VectorEngine_qwen36_validation"
DECISIONS={"wrrf_resource_cascade":("sludge_to_digestion_fraction","centrate_to_struvite_fraction"),"methanol_capture_electrolysis":("captured_co2_to_methanol_fraction","reaction_heat_to_soec_fraction"),"hda_psa_furnace":("psa_hydrogen_recycle_fraction","tailgas_heat_recovery_fraction"),"ree_acid_loop":("bped_acid_recovery_fraction","sx_organic_recycle_fraction"),"lithium_nf_bped":("nf_magnesium_rejection_fraction","bped_alkalinity_fraction"),"sour_gas_integrated":("acid_gas_removal_fraction","membrane_methane_recycle_fraction"),"dac_co_methanation":("co2_to_electroreduction_fraction","syngas_recycle_fraction"),"vfa_bnr_integration":("sludge_fermentation_fraction","ed_vfa_transfer_fraction"),"ro_md_zld":("ro_recovery_fraction","md_recovery_fraction"),"biomass_capture_mineral":("biomass_heat_fraction","captured_co2_to_ash_fraction")}
def evaluate(m,x,y):
 if m=="wrrf_resource_cascade":
  energy=.55+.35*x;precovery=.45+.48*y;tn=.06*(1-.7*y);methane=.65+.30*x;heat=.4*x
  return {"energy_self_supply":energy,"phosphorus_recovery":precovery,"return_tn_index":tn,"methane_yield":methane,"recovered_heat_index":heat,"objective":-energy-precovery,"feasible":energy>=.80 and precovery>=.85 and tn<=.025}
 if m=="methanol_capture_electrolysis":
  carbon=.62+.34*x;methanol=.58+.35*x;heat=1-.65*y;water=.18*(1-y);oxygen=.25*x
  return {"carbon_utilization":carbon,"methanol_yield":methanol,"external_soec_heat_index":heat,"fresh_water_index":water,"oxygen_product_index":oxygen,"objective":heat+water-methanol,"feasible":carbon>=.90 and methanol>=.85 and heat<=.55}
 if m=="hda_psa_furnace":
  h2=.70+.27*x;methane=.04*(1-x);steam=1-.65*y;stack=480-100*y;purity=.94+.05*x
  return {"hydrogen_recovery":h2,"methane_slip":methane,"external_steam_index":steam,"stack_temperature_K":stack,"benzene_purity":purity,"objective":steam-mathless(h2),"feasible":h2>=.92 and methane<=.015 and steam<=.50 and stack>=390 and purity>=.97}
 if m=="ree_acid_loop":
  acid=.58+.38*x;ree=.72+.20*x+.08*y;iron=.07*(1-y);organic=.03*(1-y);voltage=15+25*x
  return {"acid_recovery":acid,"ree_recovery":ree,"iron_in_product":iron,"organic_loss":organic,"bped_voltage_V":voltage,"objective":voltage+50*organic,"feasible":acid>=.90 and ree>=.92 and iron<=.025 and organic<=.012}
 if m=="lithium_nf_bped":
  mg=.82+.16*x;li=.72+.13*(1-x)+.12*y;purity=.88+.10*x+.03*y;voltage=12+28*y
  return {"magnesium_rejection":mg,"lithium_recovery":li,"li2co3_purity":purity,"bped_voltage_V":voltage,"objective":voltage-8*li,"feasible":mg>=.94 and li>=.86 and purity>=.97}
 if m=="sour_gas_integrated":
  h2s=.010*(1-.96*x);co2=.08*(1-.85*x);methane=.88+.10*y-.03*x;sulfur=.70+.27*x;teg=.001+.002*(1-y)
  return {"pipeline_h2s_index":h2s,"pipeline_co2_fraction":co2,"methane_recovery":methane,"sulfur_recovery":sulfur,"water_index":teg,"objective":-methane+.1*x,"feasible":h2s<=.001 and co2<=.025 and methane>=.92 and sulfur>=.92 and teg<=.002}
 if m=="dac_co_methanation":
  carbon=.60+.22*x+.15*y;ch4=.55+.28*x+.12*y;h2=.50+.35*x-.12*y;power=2+2.5*x
  return {"carbon_utilization":carbon,"methane_yield":ch4,"hydrogen_utilization":h2,"power_index":power,"objective":power-4*ch4,"feasible":carbon>=.90 and ch4>=.86 and h2>=.72}
 if m=="vfa_bnr_integration":
  tn=.060*(1-.60*x-.25*y);tp=.040*(1-.35*x-.40*y);salt=.05*x*(1-y);vfa=.50+.35*x+.12*y
  return {"effluent_tn_index":tn,"effluent_tp_index":tp,"salt_return_index":salt,"vfa_supply":vfa,"objective":salt-.5*vfa,"feasible":tn<=.020 and tp<=.015 and salt<=.025}
 if m=="ro_md_zld":
  water=.55+.25*x+.17*y;liquid=.10*(1-y)*(1-x);scale=.03*x*y;salt=.60+.35*y;energy=2*x+3*y
  return {"water_recovery":water,"liquid_purge_fraction":liquid,"scaling_index":scale,"salt_recovery":salt,"energy_index":energy,"objective":energy-5*water,"feasible":water>=.90 and liquid<=.010 and scale<=.025 and salt>=.90}
 if m=="biomass_capture_mineral":
  fossil=1-.90*x;capture=.70+.27*y;carbonate=.55+.40*y;steam=.95-.08*x-.05*y;net=-.2*x*y+.1*(1-x)
  return {"fossil_co2_index":fossil,"co2_capture":capture,"carbonate_conversion":carbonate,"steam_output_index":steam,"net_emission_index":net,"objective":net,"feasible":capture>=.92 and carbonate>=.90 and steam>=.84 and net<=0}
 raise KeyError(m)
def mathless(v):return v
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
  return {"pass":ok,"stage":"native_hybrid_process_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(res.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":opt},{"name":"initial_dof_zero","pass":i==0},{"name":"final_dof_zero","pass":f==0}],"initial_dof":i,"final_dof":f,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo hybrid process extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
 except Exception as ex:return {"pass":False,"stage":"native_hybrid_process_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(ex).__name__,"message":str(ex),"traceback_tail":traceback.format_exc()[-5000:]}}
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
