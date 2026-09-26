import ast,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; WS=ROOT.parents[1]
legacy=Path(json.loads((WS/'release/openidaes450_demo_preparation/provenance/source_bindings.json').read_text())['legacy_artifact_root'])
registry=json.loads((WS/'release/openidaes450_demo_preparation/catalog/registry.original.json').read_text())['cases']
dest=ROOT/'source_snapshot'; pending=[]; bindings={}; inventory=[];seen=set()
for row in registry:
    s=row.get('selection',{}).get('source_manifest_path','')
    if s.startswith('local://experiment/scripts/solve_chemical_meaningful_batch_'):
        s=s.removeprefix('local://');bindings[row['case_key']]=s;pending.append(s)
while pending:
    rel=pending.pop()
    if rel in seen:continue
    seen.add(rel);src=WS/rel
    if not src.is_file():src=legacy/rel
    if not src.is_file():raise FileNotFoundError(rel)
    target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    inventory.append({'path':rel,'source':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
    for n in ast.walk(ast.parse(src.read_text())):
        if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('experiment.scripts.'):
            pending.append(n.module.replace('.','/')+'.py')
(ROOT/'source_snapshot_inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
(ROOT/'registered_demo_bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
print(len(bindings),'cases;',len(inventory),'sources')
