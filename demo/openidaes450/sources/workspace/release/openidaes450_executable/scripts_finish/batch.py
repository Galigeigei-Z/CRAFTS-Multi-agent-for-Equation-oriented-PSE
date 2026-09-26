import concurrent.futures,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WS=ROOT.parents[1]
manifest=Path(sys.argv[1]);name=sys.argv[2];workers=int(sys.argv[3]) if len(sys.argv)>3 else 6
rows=json.loads(manifest.read_text());out=ROOT/'runs'/name;out.mkdir(parents=True,exist_ok=False)
def work(row):
    k=row['case_id'];runner=Path(row['runner']).resolve();python=row.get('python','/scratch/e1518147/vanda_pypkg/envs/py310/bin/python')
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',MPLBACKEND='Agg',LD_LIBRARY_PATH=str(Path(python).parents[1]/'lib'))
    env['DEMO_CASE_ID']=k;env['DEMO_OUTPUT']=str(out/k);env['DEMO_ROOT']=str(ROOT);env['DEMO_WORKSPACE']=str(WS)
    with (out/(k+'.log')).open('w') as log:
        p=subprocess.Popen([python,str(ROOT/'scripts_finish/run_reference.py'),'--workspace',str(WS),'--runner',str(runner),'--case-id',k,'--output',str(out/k)],stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try:p.wait(timeout=row.get('timeout',1200));result={'case_id':k,'exit_code':p.returncode}
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait();result={'case_id':k,'timeout':True}
    return result
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
 for fut in concurrent.futures.as_completed([pool.submit(work,row) for row in rows]):
    r=fut.result();results.append(r);(out/'batch_progress.json').write_text(json.dumps({'total':len(rows),'finished':len(results),'results':results},indent=2));print(r,flush=True)
