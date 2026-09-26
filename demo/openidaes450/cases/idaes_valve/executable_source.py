import hashlib,importlib.util,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run_case(case_key):
    import pytest
    binding=json.loads((ROOT/'finish_pytest_bindings.json').read_text())[case_key]
    mod=importlib.util.find_spec(binding['module']);path=Path(mod.origin)
    node=str(path)+binding.get('node','')
    out=Path(os.environ['DEMO_OUTPUT'])
    (out/'execution_binding.json').write_text(json.dumps({'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'node':node,'selection':binding.get('selection','')},indent=2))
    args=[node,'-q','--disable-warnings','-p','no:cacheprovider','--confcutdir',str(path.parent),'--basetemp',str(out/'pytest_tmp')]
    if binding.get('selection'):args+=['-k',binding['selection']]
    code=pytest.main(args)
    return {'pass':int(code)==0,'execution':'official source tests','pytest_exit_code':int(code),'case_id':case_key,'source':str(path),'test_selection':binding}
