#!/usr/bin/env python3
"""Bounded native-reference batch. Leaves every unsatisfied case explicit."""
import argparse,concurrent.futures,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--timeout',type=int,default=600);p.add_argument('--limit',type=int);args=p.parse_args()
 base=OUT/'runs'/args.run;base.mkdir(parents=True,exist_ok=False)
 suite=json.loads((OUT/'variant_suite_v2.json').read_text());rows=suite['cases'];candidates=[r for r in rows if r['preflight_status']=='native_runner_candidate'];candidates=candidates[:args.limit] if args.limit else candidates
 def execute(row):
  key=row['case_id'];runner=ROOT/row['runner'];path=base/key
  if hashlib.sha256(runner.read_bytes()).hexdigest()!=row['runner_sha256']:return {'case_id':key,'state':'source_changed','public_reference_complete':False}
  env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
  cmd=[sys.executable,str(OUT/'scripts_r002/run_reference.py'),'--workspace',str(ROOT),'--runner',str(runner),'--case-id',key,'--output',str(path)]
  with (base/(key+'.log')).open('w') as log:
   proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:rc=proc.wait(timeout=args.timeout)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    rc=124
  if (path/'status.json').is_file():result=json.loads((path/'status.json').read_text())
  else:result={'case_id':key,'state':'timeout' if rc==124 else 'runner_failed','returncode':rc,'public_reference_complete':False}
  print(json.dumps({'case_id':key,'returncode':rc,'native_export_pass':result.get('native_export_pass',False)}),flush=True)
  return result
 results=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
  for result in pool.map(execute,candidates):
   results.append(result);(base/'progress.json').write_text(json.dumps({'attempted':len(results),'scheduled':len(candidates),'native_export_pass':sum(r.get('native_export_pass',False) for r in results),'complete_reference_cases':sum(r.get('public_reference_complete',False) for r in results)},indent=2)+'\n')
 (base/'results.json').write_text(json.dumps(results,indent=2)+'\n')
 (base/'coverage.json').write_text(json.dumps({'catalog_denominator':450,'attempted':len(results),'not_scheduled':[{'case_id':r['case_id'],'reason':r['preflight_status']} for r in rows if r not in candidates],'complete_reference_cases':sum(r.get('public_reference_complete',False) for r in results)},indent=2)+'\n')
 return 0
if __name__=='__main__':raise SystemExit(main())
