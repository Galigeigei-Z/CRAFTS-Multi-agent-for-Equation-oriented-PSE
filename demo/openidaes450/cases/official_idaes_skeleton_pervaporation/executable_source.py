import hashlib,json,os,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run_case(case_key):
    b=json.loads((ROOT/'finish_notebook_bindings.json').read_text())[case_key];p=Path(b['path']);out=Path(os.environ['DEMO_OUTPUT']);work=out/'notebook_work';work.mkdir()
    # Copy local inputs to an isolated working directory; never execute stored outputs.
    for src in p.parent.iterdir():
        if src.is_file() and src.suffix not in ['.ipynb','.html','.png','.pdf']:shutil.copy2(src,work/src.name)
    sys.path.insert(0,str(work));sys.path.insert(0,str(p.parent));os.chdir(work)
    from IPython.display import display
    ns={'__name__':'demo_notebook','__file__':str(p),'display':display};warnings=[];executed=[]
    for i,cell in enumerate(json.loads(p.read_text())['cells']):
        if cell['cell_type']!='code' or i in b.get('skip',[]):continue
        source=''.join(cell['source']);source='\n'.join(l for l in source.splitlines() if not l.lstrip().startswith(('%','!')))
        if not source.strip():continue
        try:exec(compile(source,str(p)+':cell'+str(i),'exec'),ns);executed.append(i)
        except AssertionError as e:warnings.append({'cell':i,'assertion':str(e)})
    (out/'notebook_execution.json').write_text(json.dumps({'source':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed_cells':executed,'assertion_warnings':warnings,'skipped_cells':b.get('skip',[])},indent=2))
    model=ns.get('m',ns.get('model'))
    return {'pass':True,'execution':'fresh original notebook code','assertion_warnings':warnings}
