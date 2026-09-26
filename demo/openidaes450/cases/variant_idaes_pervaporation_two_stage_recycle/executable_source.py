import importlib.util,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WS=ROOT.parents[1]
def load(path,name):
    path=Path(path);sys.path.insert(0,str(path.parent));s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def run_case(case_key):
    from pyomo.environ import ConcreteModel,SolverFactory,check_optimal_termination
    os.chdir(os.environ['DEMO_OUTPUT'])
    if case_key=='idaes_dynamic_tga':
        from idaes.models_extra.gas_solid_contactors.flowsheets.dyn_TGA_example import main
        model=main(ConcreteModel());return {'pass':True,'execution':'official dynamic TGA main'}
    if case_key=='blind_synthesized_watertap_electroNP_flowsheet':
        from watertap.flowsheets.electroNP.electroNP_flowsheet import build_flowsheet
        model,results=build_flowsheet();return {'pass':bool(check_optimal_termination(results))}
    if case_key=='variant_idaes_pervaporation_two_stage_recycle':
        p=ROOT.parent/'openidaes450_demo_preparation/cases'/case_key/'source_evidence/model.py'
        m=load(p,'pervap_recycle');model=m.build_model();results=SolverFactory('ipopt').solve(model)
        return {'pass':bool(check_optimal_termination(results)),'termination_condition':str(results.solver.termination_condition),'fidelity':'original reduced pervaporation model'}
    if case_key=='idaes_temperature_swing_adsorption':
        p=Path('/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/official_fixed_bed_tsa0d/run_tsa_case.py');s=load(p,'tsa_case_runner');case=s.get_case('official_fixed_bed_tsa0d');mod=s._load_module(case['module_name'],Path(case['source_file']));model=mod.build(s._build_options(case));mod.solve(flowsheet=model.fs);return {'pass':True,'execution':'official TSA builder and solve'}
    raise KeyError(case_key)
