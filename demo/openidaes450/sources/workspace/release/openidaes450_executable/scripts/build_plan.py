#!/usr/bin/env python3
import ast,collections,datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parents[1];PREP=ROOT/'release/openidaes450_demo_preparation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n')
runners={r['case_id']:r for r in json.loads((PREP/'catalog/runner_bindings.json').read_text())}
registry=json.loads((PREP/'catalog/registry.original.json').read_text());rows=[]
for c in registry['cases']:
 key=c['case_key'];r=runners[key];ev=json.loads((PREP/'cases'/key/'simulation_evidence.json').read_text());runner=r.get('runner');p=ROOT/runner.replace('implementation/current/','') if runner else None
 status='native_runner_candidate';required=[]
 if not p or not p.exists():status='missing_runner'
 elif ev['reduced_or_proxy_scope_detected'] or p.name=='run_registered_case_source.py':status='requires_model_reconstruction'
 elif key.startswith('variant_'):status='variant_binding_required'
 else:
  f=next((n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='run_case'),None)
  if f is None:status='no_run_case_function'
  else:
   required=[x.arg for x in f.args.args[:len(f.args.args)-len(f.args.defaults)]]
   if any(name not in {'report_path'} for name in required):status='explicit_arguments_required'
 row={'index':c['order']+1,'case_id':key,'label':c['label'],'family':c['family'],'request':c.get('display_prompt'),'preflight_status':status,'runner':str(p.relative_to(ROOT)) if p else None,'runner_sha256':sha(p) if p and p.is_file() else None,'required_arguments':required,'specification_file':str((PREP/'cases'/key/'specification.json').relative_to(ROOT)),'specification_sha256':sha(PREP/'cases'/key/'specification.json'),'topology_file':str((PREP/'cases'/key/'topology.json').relative_to(ROOT)),'topology_sha256':sha(PREP/'cases'/key/'topology.json'),'public_reference_complete':False}
 rows.append(row);write(OUT/'models'/key/'binding.json',row)
 if p and p.is_file():
  target=OUT/'models'/key/'registered_runner_source.py';target.write_bytes(p.read_bytes())
write(OUT/'suite.json',{'schema_version':'reference-model-suite/1','suite_id':'openidaes450_reference_export_r001','fixed_denominator':450,'cases':rows})
write(OUT/'preflight.json',{'counts':dict(collections.Counter(r['preflight_status'] for r in rows)),'model_calls':0,'model_visible_context':[],'fidelity_policy':'Full IDAES reference models required; no reduced substitution counted as completion.'})
write(OUT/'experiment.json',{'schema_version':'standardized-experiment/1','experiment_id':'openidaes450_reference_export_r001','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'planned','workflow_protocol':'reference-model-export/1','route':'case_assisted_reconstruction','evidence_class':'reference_model_qualification_not_agent_evaluation','execution_protocol':'actual-model-export/1','scoring_protocol':'numerical-reference-completeness/1','suite':{'path':'suite.json','suite_id':'openidaes450_reference_export_r001','sha256':sha(OUT/'suite.json'),'case_count':450,'fixed_denominator':450},'providers':['deterministic_no_model'],'namespace':{'axes':['workflow_protocol','provider_profile','suite_sha256','run_namespace'],'artifact_reuse_between_cells':False,'root':'.'},'paths':{'runs':'runs','results':'results','indexes':'indexes'}})
print(collections.Counter(r['preflight_status'] for r in rows))
