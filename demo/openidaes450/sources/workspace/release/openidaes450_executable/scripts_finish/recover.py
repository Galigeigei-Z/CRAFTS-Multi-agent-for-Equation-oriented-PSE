import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WS=ROOT.parents[1]
legacy=Path(json.loads((WS/'release/openidaes450_demo_preparation/provenance/source_bindings.json').read_text())['legacy_artifact_root'])
names=['build_idaes_gtep_official_v1','build_idaes_gtep_engineering_variants_v2','solve_idaes_gtep_recovery_v1','build_idaes_mvo_official_v1','build_idaes_mvo_decision_variants_v2']
out=ROOT/'finish_sources';out.mkdir(exist_ok=True);inv=[]
for name in names:
 src=legacy/'experiment/scripts'/f'{name}.py';s=src.read_text();lines=s.splitlines(keepends=True)
 for n in ast.walk(ast.parse(s)):
  if isinstance(n,ast.ImportFrom) and n.module in ['run_three_stage_case','web.server']:
   for i in range(n.lineno-1,n.end_lineno):lines[i]='\n'
 s=''.join(lines).replace('from experiment.scripts import build_idaes_mvo_official_v1 as v1','import build_idaes_mvo_official_v1 as v1')
 (out/(name+'.py')).write_text(s)
 inv.append({'file':name+'.py','original_source':str(src),'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'adapted_sha256':hashlib.sha256(s.encode()).hexdigest(),'edits':'Removed unused visualization imports; localized MVO helper import. Numerical formulations unchanged.'})
(ROOT/'finish_source_inventory.json').write_text(json.dumps(inv,indent=2)+'\n')
