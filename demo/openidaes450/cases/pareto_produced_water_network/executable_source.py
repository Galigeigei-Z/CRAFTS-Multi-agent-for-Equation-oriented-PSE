import importlib.util,inspect,json,os,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WS=ROOT.parents[1]
def run_case(case_key):
    suite={x['case_id']:x for x in json.loads((ROOT/'suite.json').read_text())['cases']}
    special={'variant_methanol_water_nrtl_partial_condensation':'stage3_specs_solve/run_methanol_water_nrtl_partial_condensation_reference_solve.py','variant_watertap_two_pass_permeate_polishing_ro':'stage3_specs_solve/run_watertap_two_pass_ro_reference_solve.py'}
    p=WS/special.get(case_key,suite[case_key]['runner']);sys.path.insert(0,str(p.parent))
    out=Path(os.environ['DEMO_OUTPUT']);shutil.copy2(ROOT.parent/'openidaes450_demo_preparation/cases'/case_key/'topology.json',out/(case_key+'_topology_ir.json'))
    spec=importlib.util.spec_from_file_location('existing_case',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    kwargs={}
    for name,param in inspect.signature(m.run_case).parameters.items():
        if name=='report_path':kwargs[name]=out/'native_report.json'
        if name=='case_key':kwargs[name]=case_key
    return m.run_case(**kwargs)
