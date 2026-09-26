import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PREP=ROOT.parent/'openidaes450_demo_preparation'
archive=ROOT.parent/'openidaes450_practical_demo.tar.gz'
rows=json.loads((ROOT/'demo_catalog.json').read_text());selected={r['result_path'] for r in rows if r['evidence']=='fresh_result'}
with tarfile.open(archive,'w:gz') as tar:
    tar.add(PREP,arcname='openidaes450_demo_preparation',filter=lambda x:None if '__pycache__' in x.name else x)
    for name in ['DEMO_README.md','demo_catalog.json','demo_catalog.csv','demo_progress.json','cases','scripts_demo','source_snapshot','source_snapshot_inventory.json','registered_demo_bindings.json','suite.json','experiment.json']:
        tar.add(ROOT/name,arcname='openidaes450_executable/'+name,filter=lambda x:None if '__pycache__' in x.name else x)
    for folder in sorted(ROOT.glob('scripts*')):
        if folder.is_dir() and folder.name!='scripts_demo':tar.add(folder,arcname='openidaes450_executable/'+folder.name,filter=lambda x:None if '__pycache__' in x.name else x)
    for rel in sorted(selected):tar.add(ROOT/rel,arcname='openidaes450_executable/'+rel)
h=hashlib.sha256()
with archive.open('rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
archive.with_suffix(archive.suffix+'.sha256').write_text(h.hexdigest()+'  '+archive.name+'\n')
print(archive,archive.stat().st_size,h.hexdigest())
