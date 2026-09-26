import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run_case(case_key):
    bindings=json.loads((ROOT/'registered_demo_bindings.json').read_text())
    scripts=ROOT/'source_snapshot/experiment/scripts'
    import experiment
    pkg=types.ModuleType('experiment.scripts');pkg.__path__=[str(scripts)];sys.modules['experiment.scripts']=pkg
    path=ROOT/'source_snapshot'/bindings[case_key]
    spec=importlib.util.spec_from_file_location('snapshot_registered_case',path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    return m.solve_one(m.BY_KEY[case_key])
