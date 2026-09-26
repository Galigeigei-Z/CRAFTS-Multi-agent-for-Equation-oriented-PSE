#!/usr/bin/env python3
"""Solve reaction/separation and gas-processing expansion batch C."""

from __future__ import annotations
import argparse,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.runtime_env import configure_py310_runtime
from experiment.scripts.chemical_meaningful_batch_c_v6 import BATCH,BY_KEY
configure_py310_runtime();OUT=ROOT/"validation/VectorEngine_qwen36_validation"

def search(mode):
 rows=[]
 if mode=="methanol_co2":
  for ci in range(21):
   c=ci*.02
   for pi in range(5,31):
    p=pi/100;conv=.55+.20*c-.12*c*c;meoh=.10*conv*(1-.2*p);water=.10*c*conv;recycle=(1-p)*(.10*(1-conv)+.005);obj=meoh-0.08*recycle
    rows.append({"co2_cofeed_fraction":c,"purge_fraction":p,"methanol_kg_s":meoh,"water_knockout_kg_s":water,"recycle_gas_kg_s":recycle,"objective":obj,"feasible":water<=.015 and recycle<=.045})
  b=max((x for x in rows if x["feasible"]),key=lambda x:x["objective"]);return {"co2_cofeed_fraction":b["co2_cofeed_fraction"],"purge_fraction":b["purge_fraction"]},rows
 if mode=="methanol_intercool":
  for ti in range(31):
   t=320+ti*2;conv1=.38;conv2=(1-conv1)*(.52-.0015*(t-320));total=conv1+conv2;duty=2.1*(430-t)
   rows.append({"interstage_temperature_K":t,"first_stage_conversion":conv1,"second_stage_incremental_conversion":conv2,"total_conversion":total,"cooling_duty_index":duty,"feasible":t<=370})
  b=max((x for x in rows if x["feasible"]),key=lambda x:x["total_conversion"]-.0005*x["cooling_duty_index"]);return {"interstage_temperature_K":b["interstage_temperature_K"]},rows
 if mode=="hda_staged_h2":
  for si in range(21):
   s=si*.05;conv=.80+.16*s-.06*s*s;h2=1.05+.15*s;methane=.05/(1+.4*s);purity=.88+.08*conv;obj=h2+.5*methane
   rows.append({"interstage_hydrogen_fraction":s,"toluene_conversion":conv,"hydrogen_ratio":h2,"recycle_methane_fraction":methane,"benzene_purity":purity,"objective":obj,"feasible":conv>=.90 and purity>=.95})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["objective"]);return {"interstage_hydrogen_fraction":b["interstage_hydrogen_fraction"]},rows
 if mode=="hda_heat_pump":
  for i in range(81):
   x=i/100;power=180*x;heat=500*x;steam=900-heat;purity=.97-.01*x
   rows.append({"overhead_heat_pump_fraction":x,"compressor_power_kW":power,"reboiler_steam_kW":steam,"benzene_purity":purity,"feasible":power<=120 and purity>=.965})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["reboiler_steam_kW"]);return {"overhead_heat_pump_fraction":b["overhead_heat_pump_fraction"]},rows
 if mode=="btx_extractive":
  for sri in range(11,41):
   sr=sri/10
   for ri in range(11,20):
    r=ri/20;alpha=2.1+1.3*(1-math.exp(-.7*sr));purity=1-1/(1+alpha**3);loss=.01*(1-r)*sr;duty=300+55*sr+100*(1-r);obj=duty+500*loss
    rows.append({"solvent_to_feed_ratio":sr,"solvent_recycle_fraction":r,"relative_volatility":alpha,"benzene_purity":purity,"solvent_loss_kg_s":loss,"reboiler_index":duty,"objective":obj,"feasible":purity>=.95 and loss<=.02})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["objective"]);return {"solvent_to_feed_ratio":b["solvent_to_feed_ratio"],"solvent_recycle_fraction":b["solvent_recycle_fraction"]},rows
 if mode=="gas_dehydration":
  for i in range(11,61):
   g=i/10;rem=1-math.exp(-.8*g);water=.001*(1-rem);loss=.00002*g;duty=30*g
   rows.append({"teg_circulation_ratio":g,"water_removal":rem,"dry_gas_water_kg_s":water,"teg_loss_kg_s":loss,"regenerator_duty_kW":duty,"feasible":water<=1e-5 and loss<=.00012})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["regenerator_duty_kW"]);return {"teg_circulation_ratio":b["teg_circulation_ratio"]},rows
 if mode=="bfb_fgr":
  for ai in range(5,16):
   a=ai/20
   for fi in range(11):
    f=fi*.05;temp=1100+260*a-300*f;nox=.0002*a*math.exp((temp-1100)/350);conv=.96+.035*a-.01*f
    rows.append({"secondary_air_fraction":a,"flue_gas_recycle_fraction":f,"bed_temperature_K":temp,"nox_proxy":nox,"methane_conversion":conv,"feasible":1050<=temp<=1200 and conv>=.97})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["nox_proxy"]);return {"secondary_air_fraction":b["secondary_air_fraction"],"flue_gas_recycle_fraction":b["flue_gas_recycle_fraction"]},rows
 if mode=="tga_redox":
  for i in range(21):
   ox=.25+i*.025;util=min(.98,.72+.35*ox);fuelconv=.93-.10*max(0,ox-.55);swing=80+100*abs(ox-.5);score=util*fuelconv
   rows.append({"oxidation_time_fraction":ox,"oxygen_carrier_utilization":util,"methane_conversion":fuelconv,"temperature_swing_K":swing,"score":score,"feasible":swing<=110 and fuelconv>=.90})
  b=max((x for x in rows if x["feasible"]),key=lambda x:x["score"]);return {"oxidation_time_fraction":b["oxidation_time_fraction"]},rows
 if mode=="biogas_oxy_fgr":
  for oi in range(21,41):
   o=oi/100
   for fi in range(11):
    f=fi*.05;temp=1450+1800*(o-.21)-700*f;co=max(0,.002-.012*(o-.21)+.001*f);power=40*(o-.21);obj=power+1e4*co
    rows.append({"oxygen_mole_fraction":o,"flue_gas_recycle_fraction":f,"flame_temperature_K":temp,"co_kg_s":co,"oxygen_power_index":power,"objective":obj,"feasible":1400<=temp<=1750 and co<=.001})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["objective"]);return {"oxygen_mole_fraction":b["oxygen_mole_fraction"],"flue_gas_recycle_fraction":b["flue_gas_recycle_fraction"]},rows
 if mode=="co2_membrane_two_stage":
  for ai in range(3,18):
   a=ai/20
   for ri in range(11):
    r=ri*.05;recovery=.68+.25*a+.15*r;purity=.86+.12*(1-a)+.05*r;power=100+120*r+40*a
    rows.append({"stage_one_area_fraction":a,"second_retentate_recycle_fraction":r,"co2_recovery":recovery,"co2_purity":purity,"compression_power_kW":power,"feasible":recovery>=.85 and purity>=.95 and power<=180})
  b=min((x for x in rows if x["feasible"]),key=lambda x:x["compression_power_kW"]);return {"stage_one_area_fraction":b["stage_one_area_fraction"],"second_retentate_recycle_fraction":b["second_retentate_recycle_fraction"]},rows
 raise KeyError(mode)

def build(mode,d):
 from pyomo.environ import ConcreteModel,Constraint,Var,exp
 m=ConcreteModel();q={}
 def fv(name,val):v=Var(initialize=val);setattr(m,name,v);return v
 if mode=="methanol_co2":
  c,p=d.values();m.c=fv("c",c);m.c.fix(c);m.p=fv("p",p);m.p.fix(p);m.conv=fv("conv",.6);m.meoh=fv("meoh",.06);m.water=fv("water",.01);m.recycle=fv("recycle",.03);m.e1=Constraint(expr=m.conv==.55+.20*m.c-.12*m.c**2);m.e2=Constraint(expr=m.meoh==.10*m.conv*(1-.2*m.p));m.e3=Constraint(expr=m.water==.10*m.c*m.conv);m.e4=Constraint(expr=m.recycle==(1-m.p)*(.10*(1-m.conv)+.005));m.cw=Constraint(expr=m.water<=.015);m.cr=Constraint(expr=m.recycle<=.045);q={"co_conversion":m.conv,"methanol_kg_s":m.meoh,"water_knockout_kg_s":m.water,"recycle_gas_kg_s":m.recycle}
 elif mode=="methanol_intercool":
  t=d["interstage_temperature_K"];m.t=fv("t",t);m.t.fix(t);m.c1=fv("c1",.38);m.c2=fv("c2",.3);m.total=fv("total",.7);m.duty=fv("duty",200);m.e1=Constraint(expr=m.c1==.38);m.e2=Constraint(expr=m.c2==(1-m.c1)*(.52-.0015*(m.t-320)));m.e3=Constraint(expr=m.total==m.c1+m.c2);m.e4=Constraint(expr=m.duty==2.1*(430-m.t));q={"first_stage_conversion":m.c1,"second_stage_conversion":m.c2,"total_conversion":m.total,"intercooler_duty_index":m.duty}
 elif mode=="hda_staged_h2":
  s=d["interstage_hydrogen_fraction"];m.s=fv("s",s);m.s.fix(s);m.conv=fv("conv",.9);m.h2=fv("h2",1.1);m.ch4=fv("ch4",.04);m.purity=fv("purity",.95);m.e1=Constraint(expr=m.conv==.80+.16*m.s-.06*m.s**2);m.e2=Constraint(expr=m.h2==1.05+.15*m.s);m.e3=Constraint(expr=m.ch4*(1+.4*m.s)==.05);m.e4=Constraint(expr=m.purity==.88+.08*m.conv);m.q1=Constraint(expr=m.conv>=.90);m.q2=Constraint(expr=m.purity>=.95);q={"toluene_conversion":m.conv,"hydrogen_ratio":m.h2,"recycle_methane_fraction":m.ch4,"benzene_purity":m.purity}
 elif mode=="hda_heat_pump":
  x=d["overhead_heat_pump_fraction"];m.x=fv("x",x);m.x.fix(x);m.power=fv("power",100);m.heat=fv("heat",300);m.steam=fv("steam",600);m.purity=fv("purity",.97);m.e1=Constraint(expr=m.power==180*m.x);m.e2=Constraint(expr=m.heat==500*m.x);m.e3=Constraint(expr=m.steam==900-m.heat);m.e4=Constraint(expr=m.purity==.97-.01*m.x);m.q1=Constraint(expr=m.power<=120);m.q2=Constraint(expr=m.purity>=.965);q={"compressor_power_kW":m.power,"recovered_reboiler_heat_kW":m.heat,"external_steam_kW":m.steam,"benzene_purity":m.purity}
 elif mode=="btx_extractive":
  sr,r=d.values();m.sr=fv("sr",sr);m.sr.fix(sr);m.r=fv("r",r);m.r.fix(r);m.alpha=fv("alpha",3);m.purity=fv("purity",.95);m.loss=fv("loss",.01);m.duty=fv("duty",500);m.e1=Constraint(expr=m.alpha==2.1+1.3*(1-exp(-.7*m.sr)));m.e2=Constraint(expr=(1-m.purity)*(1+m.alpha**3)==1);m.e3=Constraint(expr=m.loss==.01*(1-m.r)*m.sr);m.e4=Constraint(expr=m.duty==300+55*m.sr+100*(1-m.r));m.q1=Constraint(expr=m.purity>=.95);m.q2=Constraint(expr=m.loss<=.02);q={"relative_volatility":m.alpha,"benzene_purity":m.purity,"solvent_loss_kg_s":m.loss,"reboiler_index":m.duty}
 elif mode=="gas_dehydration":
  g=d["teg_circulation_ratio"];m.g=fv("g",g);m.g.fix(g);m.rem=fv("rem",.99);m.water=fv("water",1e-5);m.loss=fv("loss",1e-4);m.duty=fv("duty",150);m.e1=Constraint(expr=m.rem==1-exp(-.8*m.g));m.e2=Constraint(expr=m.water==.001*(1-m.rem));m.e3=Constraint(expr=m.loss==.00002*m.g);m.e4=Constraint(expr=m.duty==30*m.g);m.q1=Constraint(expr=m.water<=1e-5);m.q2=Constraint(expr=m.loss<=.00012);q={"water_removal_fraction":m.rem,"dry_gas_water_kg_s":m.water,"teg_loss_kg_s":m.loss,"regenerator_duty_kW":m.duty}
 elif mode=="bfb_fgr":
  a,f=d.values();m.a=fv("a",a);m.a.fix(a);m.f=fv("f",f);m.f.fix(f);m.temp=fv("temp",1150);m.nox=fv("nox",.0001);m.conv=fv("conv",.98);m.e1=Constraint(expr=m.temp==1100+260*m.a-300*m.f);m.e2=Constraint(expr=m.nox==.0002*m.a*exp((m.temp-1100)/350));m.e3=Constraint(expr=m.conv==.96+.035*m.a-.01*m.f);m.q1=Constraint(expr=m.temp>=1050);m.q2=Constraint(expr=m.temp<=1200);m.q3=Constraint(expr=m.conv>=.97);q={"bed_temperature_K":m.temp,"nox_proxy":m.nox,"methane_conversion":m.conv}
 elif mode=="tga_redox":
  ox=d["oxidation_time_fraction"];util=min(.98,.72+.35*ox);conv=.93-.10*max(0,ox-.55);swing=80+100*abs(ox-.5);m.ox=fv("ox",ox);m.ox.fix(ox);m.util=fv("util",util);m.conv=fv("conv",conv);m.swing=fv("swing",swing);m.e1=Constraint(expr=m.util==util);m.e2=Constraint(expr=m.conv==conv);m.e3=Constraint(expr=m.swing==swing);m.q1=Constraint(expr=m.swing<=110);m.q2=Constraint(expr=m.conv>=.90);q={"oxygen_carrier_utilization":m.util,"methane_conversion":m.conv,"temperature_swing_K":m.swing}
 elif mode=="biogas_oxy_fgr":
  o,f=d.values();m.o=fv("o",o);m.o.fix(o);m.f=fv("f",f);m.f.fix(f);m.temp=fv("temp",1600);m.co=fv("co",.001);m.power=fv("power",3);m.e1=Constraint(expr=m.temp==1450+1800*(m.o-.21)-700*m.f);co=max(0,.002-.012*(o-.21)+.001*f);m.e2=Constraint(expr=m.co==co);m.e3=Constraint(expr=m.power==40*(m.o-.21));m.q1=Constraint(expr=m.temp>=1400);m.q2=Constraint(expr=m.temp<=1750);m.q3=Constraint(expr=m.co<=.001);q={"flame_temperature_K":m.temp,"co_kg_s":m.co,"oxygen_power_index":m.power}
 elif mode=="co2_membrane_two_stage":
  a,r=d.values();m.a=fv("a",a);m.a.fix(a);m.r=fv("r",r);m.r.fix(r);m.rec=fv("rec",.9);m.purity=fv("purity",.95);m.power=fv("power",160);m.e1=Constraint(expr=m.rec==.68+.25*m.a+.15*m.r);m.e2=Constraint(expr=m.purity==.86+.12*(1-m.a)+.05*m.r);m.e3=Constraint(expr=m.power==100+120*m.r+40*m.a);m.q1=Constraint(expr=m.rec>=.85);m.q2=Constraint(expr=m.purity>=.95);m.q3=Constraint(expr=m.power<=180);q={"co2_recovery":m.rec,"co2_purity":m.purity,"compression_power_kW":m.power}
 else:raise KeyError(mode)
 return m,q

def solve_one(meta):
 from idaes.core.util.model_statistics import degrees_of_freedom
 from pyomo.environ import check_optimal_termination,value
 from watertap.core.solvers import get_solver
 try:
  d,rows=search(meta["mode"]);m,objs=build(meta["mode"],d);i=degrees_of_freedom(m);res=get_solver().solve(m);f=degrees_of_freedom(m);opt=bool(check_optimal_termination(res));metrics={k:float(value(v)) for k,v in objs.items()};ok=opt and i==0 and f==0
  return {"pass":ok,"stage":"native_reaction_separation_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":str(res.solver.termination_condition),"checks":[{"name":"native_extension_optimal","pass":opt},{"name":"initial_dof_zero","pass":i==0},{"name":"final_dof_zero","pass":f==0}],"initial_dof":i,"final_dof":f,"decision_variables":d,"metrics":metrics,"search_results":rows,"source_summary":{"source":"native Pyomo reaction/separation extension anchored to active registry parent","parent_case_key":meta["parent"],"chemical_distinction":meta["distinction"]},"error":None if ok else {"message":"native extension checks failed"}}
 except Exception as e:return {"pass":False,"stage":"native_reaction_separation_extension_solve","case_family":meta["mode"],"parent_case_key":meta["parent"],"termination_condition":None,"checks":[{"name":"runner_exception","pass":False}],"error":{"type":type(e).__name__,"message":str(e),"traceback_tail":traceback.format_exc()[-5000:]}}

def main():
 p=argparse.ArgumentParser();p.add_argument("--case",action="append",choices=sorted(BY_KEY));p.add_argument("--reuse-passing",action="store_true");a=p.parse_args();selected=a.case or [x["key"] for x in BATCH];rows=[]
 for key in selected:
  folder=OUT/key;folder.mkdir(parents=True,exist_ok=True);rp=folder/"native_solve_report.json"
  if a.reuse_passing and rp.is_file():
   old=json.loads(rp.read_text());
   if old.get("pass") is True and old.get("final_dof")==0:rows.append({"case_key":key,"pass":True,"reused":True});continue
  rep=solve_one(BY_KEY[key]);rp.write_text(json.dumps(rep,indent=2,ensure_ascii=False)+"\n");(folder/"native_execution.log").write_text(json.dumps({k:v for k,v in rep.items() if k!="search_results"},indent=2,ensure_ascii=False)+"\n");rows.append({"case_key":key,"pass":rep.get("pass") is True,"report":str(rp.relative_to(ROOT))})
 result={"pass":all(x["pass"] for x in rows),"case_count":len(rows),"results":rows};print(json.dumps(result,indent=2));raise SystemExit(0 if result["pass"] else 1)
if __name__=="__main__":main()
