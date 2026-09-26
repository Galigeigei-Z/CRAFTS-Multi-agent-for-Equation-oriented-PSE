import concurrent.futures,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WS=ROOT.parents[1]
name=sys.argv[1];mode=sys.argv[2];out=ROOT/'runs'/name;out.mkdir(parents=True,exist_ok=False)
suite=json.loads((ROOT/'suite.json').read_text())['cases'];bindings=json.loads((ROOT/'registered_demo_bindings.json').read_text())
attempted={p.parent.name for p in (ROOT/'runs').glob('*/*/status.json') if p.parent.parent.name not in {'login_remaining_demo_r001','login_registered_demo_r001'}}
rows=[(k,ROOT/'scripts_demo/registered_runner.py') for k in bindings] if mode=='registered' else [(r['case_id'],WS/r['runner']) for r in suite if r.get('runner') and r['case_id'] not in attempted and (WS/r['runner']).is_file() and r['case_id'] not in bindings]
def work(row):
    k,runner=row
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',LD_LIBRARY_PATH=str(Path(sys.executable).parents[1]/'lib'))
    with (out/(k+'.log')).open('w') as log:
        try:
            p=subprocess.run([sys.executable,str(ROOT/'scripts_demo/run_reference.py'),'--workspace',str(WS),'--runner',str(runner),'--case-id',k,'--output',str(out/k)],stdout=log,stderr=subprocess.STDOUT,env=env,timeout=300)
            return {'case_id':k,'exit_code':p.returncode}
        except subprocess.TimeoutExpired:return {'case_id':k,'timeout':True}
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for r in pool.map(work,rows):
        results.append(r);(out/'batch_progress.json').write_text(json.dumps({'total':len(rows),'finished':len(results),'results':results},indent=2));print(r,flush=True)
