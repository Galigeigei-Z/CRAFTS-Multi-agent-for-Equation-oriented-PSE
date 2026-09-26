#!/usr/bin/env python3
"""Run one packaged case using an already installed compatible environment."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--python',default=sys.executable);p.add_argument('--workspace',type=Path,help='Optional original workspace for site-specific source/data dependencies');args=p.parse_args()
    rows={r['case_id']:r for r in json.loads((ROOT/'catalog.json').read_text())}
    if args.case not in rows:p.error('Unknown case ID')
    if args.output.exists():p.error('Use a new output directory; existing results are never overwritten')
    args.output=args.output.resolve();args.output.parent.mkdir(parents=True,exist_ok=True)
    case=ROOT/'cases'/args.case;binding=json.loads((case/'execution_binding.json').read_text());workspace=args.workspace.resolve() if args.workspace else ROOT/'sources/workspace'
    runner=ROOT/binding['runner_bundled']
    if args.workspace and binding.get('runner_original'):
        candidate=Path(binding['runner_original']);candidate=candidate if candidate.is_absolute() else workspace/candidate
        if candidate.is_file():runner=candidate
    driver=workspace/'release/openidaes450_executable/scripts_finish/run_reference.py'
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',MPLBACKEND='Agg',PYTHONDONTWRITEBYTECODE='1')
    env.update(DEMO_OUTPUT=str(args.output),DEMO_CASE_ID=args.case,DEMO_ROOT=str(workspace/'release/openidaes450_executable'),DEMO_WORKSPACE=str(workspace))
    env['PYTHONPATH']=os.pathsep.join([str(workspace),str(workspace/'release/openidaes450_executable/source_snapshot'),env.get('PYTHONPATH','')])
    # The external METAB workflow has its own environment and no Pyomo model.
    if args.case=='watertap_metab':
        args.output.mkdir();code="import importlib.util,json,os;from pathlib import Path;p=Path(os.environ['DEMO_RUNNER']);s=importlib.util.spec_from_file_location('metab_demo',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);r=m.run_case();Path(os.environ['DEMO_OUTPUT'],'runner_report.json').write_text(json.dumps(r,indent=2))"
        env['DEMO_RUNNER']=str(runner);return subprocess.call([args.python,'-c',code],env=env)
    return subprocess.call([args.python,str(driver),'--workspace',str(workspace),'--runner',str(runner),'--case-id',args.case,'--output',str(args.output)],env=env,cwd=workspace)
if __name__=='__main__':raise SystemExit(main())
