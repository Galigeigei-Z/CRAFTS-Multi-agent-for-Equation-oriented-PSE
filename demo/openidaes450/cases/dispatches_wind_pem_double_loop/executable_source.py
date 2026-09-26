"""Explicit engineering demonstrations for sources without a usable full solve.
These are new reduced models, not reproductions of original benchmark results.
Every numerical assumption is emitted with the outputs.
"""
import json,math,os
from pathlib import Path
import pyomo.environ as p
from pyomo.network import Port
ROOT=Path(__file__).resolve().parents[1]
def run_case(case_key):
    m=p.ConcreteModel();m.balance=p.ConstraintList();assumptions={};units=[]
    def v(name,units_=None,lb=0):
        x=p.Var(bounds=(lb,None),initialize=1,units=units_);setattr(m,name,x);return x
    def fix(name,val,unit=None):
        x=v(name,unit);x.fix(val);assumptions[name]={'value':val,'units':str(unit),'basis':'explicit demo assumption, not a recovered reference value'};return x
    def stream(name,components,T=298.15,P=101325):
        b=p.Block();setattr(m,name,b);b.comp=p.Set(initialize=list(components));b.flow_mol_comp=p.Var(b.comp,bounds=(0,None),initialize=1,units=p.units.mol/p.units.s)
        for c,expr in components.items():m.balance.add(b.flow_mol_comp[c]==expr)
        b.temperature=p.Var(initialize=T,units=p.units.K);b.temperature.fix(T);b.pressure=p.Var(initialize=P,units=p.units.Pa);b.pressure.fix(P);b.outlet=Port();b.outlet.add(b.flow_mol_comp,'flow_mol_comp');b.outlet.add(b.temperature,'temperature');b.outlet.add(b.pressure,'pressure');units.append({'name':name,'kind':'reduced material stream'});return b
    if case_key in {'dispatches_usc_tes_integrated','dispatches_usc_tes_charge_superstructure','dispatches_usc_tes_discharge_superstructure','dispatches_grid_integrated_rankine_surrogate'}:
        heat=fix('boiler_heat_MW',1000);eta=fix('steam_cycle_efficiency',0.436);charge=fix('charge_heat_MW',50 if 'charge_superstructure' in case_key or 'integrated' in case_key else 0);discharge=fix('discharge_heat_MW',40 if 'discharge_superstructure' in case_key or 'integrated' in case_key else 0)
        loss=fix('storage_loss_fraction',0.02);saltcp=fix('salt_heat_capacity_kJ_kg_K',1.5);delta=fix('salt_temperature_rise_K',260)
        power=v('net_power_MW');salt=v('charge_salt_kg_s');saltout=v('discharge_salt_kg_s');store=v('storage_change_MWh',lb=None)
        m.balance.add(power==eta*(heat-charge+discharge));m.balance.add(salt*saltcp*delta==charge*1000);m.balance.add(saltout*saltcp*delta==discharge*1000);m.balance.add(store==charge*(1-loss)-discharge/(1-loss))
        stream('steam_cycle_water',{'H2O':fix('steam_flow_mol_s',20000)},T=823.15,P=25000000);scope='Lumped steam-cycle and molten-salt energy balances at an explicit fixed design; no GDP topology optimization.'
    elif case_key in {'reflo_kbhdp_zld','reaktoro_softening_acid_ro'}:
        water=fix('feed_water_mol_s',1000);salt=fix('feed_NaCl_mol_s',10);calcium=fix('feed_CaCO3_equivalent_mol_s',1);removal=fix('softening_fraction',0.95);ro=fix('RO_water_recovery',0.8);md=fix('MD_water_recovery',0.7 if case_key=='reflo_kbhdp_zld' else 0);cryst=fix('crystal_salt_fraction',0.9 if case_key=='reflo_kbhdp_zld' else 0)
        stream('feed',{'H2O':water,'NaCl':salt,'CaCO3_equivalent':calcium});stream('softener_solids',{'CaCO3_equivalent':calcium*removal});stream('RO_permeate',{'H2O':water*ro});stream('MD_distillate',{'H2O':water*(1-ro)*md});stream('salt_crystals',{'NaCl':salt*cryst});stream('final_brine',{'H2O':water*(1-ro)*(1-md),'NaCl':salt*(1-cryst),'CaCO3_equivalent':calcium*(1-removal)});power=v('RO_power_kW');heat=v('MD_heat_kW');m.balance.add(power==water*0.018*ro*3.6*3);m.balance.add(heat==water*(1-ro)*md*0.018*2300);scope='Component-conserving softening/RO/MD/crystallization split model; fixed recoveries, ideal salt rejection, no equilibrium speciation or detailed membrane model.'
    elif case_key in {'official_idaes_pz_afs_carbon_capture','official_co2_adsorption_desorption'}:
        gas=fix('flue_gas_mol_s',1000);co2=fix('inlet_CO2_fraction',0.12);capture=fix('capture_fraction',0.90);duty=fix('regeneration_energy_kJ_mol_CO2',150 if 'pz_' in case_key else 100)
        stream('flue_gas',{'CO2':gas*co2,'N2':gas*(1-co2)},T=313.15);stream('treated_gas',{'CO2':gas*co2*(1-capture),'N2':gas*(1-co2)},T=313.15);stream('CO2_product',{'CO2':gas*co2*capture},T=393.15);q=v('regeneration_heat_kW');m.balance.add(q==gas*co2*capture*duty)
        if 'adsorption' in case_key:
            period=fix('cycle_seconds',1800);capacity=fix('working_capacity_mol_kg',2);mass=v('adsorbent_mass_kg');m.balance.add(mass*capacity==gas*co2*capture*period)
        else:
            cyclic=fix('PZ_working_loading_mol_CO2_mol_PZ',0.25);solvent=v('PZ_circulation_mol_s');m.balance.add(solvent*cyclic==gas*co2*capture)
        scope='Cyclic material and regeneration-energy balance at an assumed capture target; no rate-based column, isotherm, or transient bed solution.'
    elif case_key=='official_idaes_rsofc_soec_mode':
        h2=fix('H2_production_mol_s',2500);conversion=fix('steam_single_pass_conversion',0.7);voltage=fix('cell_voltage_V',1.3);faraday=fix('faraday_C_mol',96485.33212);feed=v('steam_feed_mol_s');power=v('electrical_power_MW');m.balance.add(feed*conversion==h2);m.balance.add(power==2*faraday*h2*voltage/1e6);stream('steam_feed',{'H2O':feed},T=1073.15);stream('fuel_outlet',{'H2':h2,'H2O':feed-h2},T=1073.15);stream('oxygen_outlet',{'O2':h2/2},T=1073.15);scope='Stoichiometric steam electrolysis and Faraday-law power balance at fixed voltage; no cell transport or integrated heat recovery model.'
    elif case_key=='dispatches_wind_pem_double_loop':
        m.t=p.RangeSet(0,23);wind={t:50+20*math.sin(2*math.pi*t/24) for t in m.t};prices={t:40+20*math.cos(2*math.pi*(t-18)/24) for t in m.t};m.wind=p.Param(m.t,initialize=wind);m.price=p.Param(m.t,initialize=prices);m.pem=p.Var(m.t,bounds=(0,30));m.grid=p.Var(m.t,bounds=(0,None));m.h2=p.Var(m.t,bounds=(0,None));m.alloc=p.Constraint(m.t,rule=lambda _,t:m.pem[t]+m.grid[t]==m.wind[t]);m.hydrogen=p.Constraint(m.t,rule=lambda _,t:m.h2[t]*50==m.pem[t]*1000);m.obj=p.Objective(expr=sum(m.grid[t]*m.price[t]+m.h2[t]*3 for t in m.t),sense=p.maximize);assumptions.update({'wind_MW':wind,'electricity_price_USD_MWh':prices,'PEM_kWh_kg_H2':50,'hydrogen_price_USD_kg':3,'basis':'explicit synthetic 24-hour demonstration inputs'});scope='24-hour wind/grid/PEM linear dispatch with explicit synthetic inputs; not Prescient day-ahead/real-time double-loop simulation.'
    else:raise KeyError(case_key)
    solver=p.SolverFactory('ipopt');results=solver.solve(m,options={'tol':1e-8,'max_iter':300})
    out=Path(os.environ['DEMO_OUTPUT']);(out/'demo_assumptions.json').write_text(json.dumps({'scope':scope,'assumptions':assumptions,'original_case_preserved':True,'reproduces_original_reference':False},indent=2));(out/'reduced_units.json').write_text(json.dumps(units,indent=2))
    model=m
    return {'pass':bool(p.check_optimal_termination(results)),'termination_condition':str(results.solver.termination_condition),'model_fidelity':'new_reduced_engineering_demo','reproduces_original_reference':False,'scope':scope,'assumptions_file':'demo_assumptions.json','case_id':case_key}
