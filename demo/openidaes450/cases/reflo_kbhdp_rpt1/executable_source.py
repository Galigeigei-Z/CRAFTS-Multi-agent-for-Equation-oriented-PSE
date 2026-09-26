import hashlib,importlib,importlib.util,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run_case(case_key):
    b=json.loads((ROOT/'finish_module_bindings.json').read_text())[case_key]
    out=Path(os.environ['DEMO_OUTPUT']);os.chdir(out)
    if b.get('path'):
        path=Path(b['path']);sys.path.insert(0,str(path.parent));spec=importlib.util.spec_from_file_location('source_case_'+case_key,path);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    else:
        mod=importlib.import_module(b['module']);path=Path(mod.__file__)
    (out/'execution_binding.json').write_text(json.dumps({'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'binding':b},indent=2))
    fn=getattr(mod,b.get('function','main'));result=fn(**b.get('kwargs',{}))
    from pyomo.core.base.block import BlockData
    model=result if isinstance(result,BlockData) else next((x for x in result if isinstance(x,BlockData)),None) if isinstance(result,tuple) else None
    return {'pass':True,'execution':'original source callable completed','case_id':case_key,'binding':b,'returned_type':str(type(result))}
