import importlib.metadata,json,os,platform,traceback
from pathlib import Path
from metab_runner import run_case
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'runs/finish_metab_r002/watertap_metab';out.mkdir(parents=True,exist_ok=False);os.environ['DEMO_OUTPUT']=str(out)
versions={'python':platform.python_version()}
for name in ['exposan','qsdsan','biosteam','scipy','idaes-pse','pyomo']:
 try:versions[name]=importlib.metadata.version(name)
 except importlib.metadata.PackageNotFoundError:versions[name]=None
report=None;error=None
try:report=run_case()
except Exception as exc:error={'message':str(exc),'traceback':traceback.format_exc()}
for name,obj in [('environment.json',versions),('runner_report.json',report),('property_packages.json',{'applicability':'not_IDAES','model':'EXPOsan METAB biochemical components'}),('status.json',{'case_id':'watertap_metab','demo_accepted':bool(report and report.get('pass')),'report_pass':bool(report and report.get('pass')),'model_fidelity':'EXPOsan_dynamic_BDF','external_computation':True,'error':error})]:
 (out/name).write_text(json.dumps(obj,indent=2))
print(report or error)
