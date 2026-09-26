#!/usr/bin/env python3
"""Compare frozen numeric specifications with exported native variables and ports."""
import csv,json,re
from pathlib import Path
import pint
ROOT=Path(__file__).resolve().parents[1];WORKSPACE=ROOT.parents[1]
UNITS=pint.UnitRegistry()
def canonical(s):
    s=re.sub(r'[\s\'\"]','',s)
    return re.sub(r'(?<=[\[,])0\.0(?=[,\]])','0',s)
def unit(s):
    return re.sub(r'\bm([23])\b',r'm**\1',s.replace('^','**'))
def main():
    rows=json.loads((ROOT/'case_status.json').read_text());summary=[]
    for case in rows:
        chosen=case.get('selected_export')
        if not chosen or not chosen['native_export_pass']:continue
        run=ROOT/chosen['path'];observations={}
        def add(name,value,units):
            if value in ('',None):return
            observations.setdefault(canonical(name),[]).append({'name':name,'value':float(value),'units':units})
        for r in csv.DictReader((run/'unit_and_state_variables.csv').open()):add(r['name'],r['value'],r['units'])
        units=json.loads((run/'units.json').read_text());feed_names={u['name'] for u in units if u['class'].endswith(('Feed','FeedData'))}
        for r in csv.DictReader((run/'streams.csv').open()):
            index=r['index'];suffix='' if index=='None' else '['+index.strip('()')+']'
            add(r['port']+'.'+r['member']+suffix,r['value'],r['units'])
            owner=r['port'].rsplit('.',1)[0]
            if owner in feed_names:add(owner+'.'+r['member']+suffix,r['value'],r['units'])
        document=json.loads((WORKSPACE/case['specification_file']).read_text());checks=[]
        for spec in document.get('specs',[]):
            target=canonical('fs.'+spec['target']+'.'+spec['variable']);matches=[]
            if '...' in target:
                pattern=re.escape(target).replace(r'\.\.\.',r'[^\]]+')
                matches=[v for k,vs in observations.items() if re.fullmatch(pattern,k) for v in vs]
            else:
                matches=observations.get(target,[]) or observations.get(target+'[0]',[])
            checked=[]
            for obs in matches:
                try:
                    if obs['units']=='None':raise ValueError('No units declared by model')
                    expected=(float(spec['value'])*UNITS(unit(spec['units']))).to(unit(obs['units'])).magnitude
                    passed=abs(obs['value']-expected)<=1e-14+1e-6*abs(expected)
                    checked.append(dict(obs,expected_in_model_units=expected,pass_match=passed))
                except Exception as exc:checked.append(dict(obs,pass_match=False,error=str(exc)))
            checks.append({'specification':spec,'matches':checked,'pass':bool(checked) and all(x['pass_match'] for x in checked)})
        audit={'case_id':case['case_id'],'run_path':chosen['path'],'specification_sha256':case['specification_sha256'],'method':'Exact model path or explicit Port member; only Feed outlet aliases allowed; dimensional unit conversion; atol 1e-14 plus rtol 1e-6. Missing or nonnumeric values fail closed.','pass':bool(checks) and all(c['pass'] for c in checks),'checks':checks}
        out=ROOT/'results/specification_audits'/case['case_id']/(run.parent.name+'.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(audit,indent=2)+'\n');summary.append({'case_id':case['case_id'],'run_path':chosen['path'],'pass':audit['pass'],'matched':sum(c['pass'] for c in checks),'total':len(checks),'audit':str(out.relative_to(ROOT))})
    (ROOT/'results/specification_audit_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'audited':len(summary),'all_specs_match':sum(x['pass'] for x in summary)}))
if __name__=='__main__':main()
