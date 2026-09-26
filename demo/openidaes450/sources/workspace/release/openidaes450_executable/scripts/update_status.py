#!/usr/bin/env python3
"""Build a case-level reference worklist without merging benchmark scores."""
import csv,datetime,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNS=['login_native_export_r002','login_recovered_export_r001','login_unit_variants_r003','login_unit_variants_repair_r001','login_unit_variants_residual_r001','login_flowsheet_variants_r001','login_native_polish_r001']

def main():
    suite=json.loads((ROOT/'suite.json').read_text());cases={r['case_id']:dict(r,attempts=[]) for r in suite['cases']}
    for run in RUNS:
        for p in (ROOT/'runs'/run).glob('*/status.json'):
            d=json.loads(p.read_text());key=d['case_id']
            if key not in cases:continue
            cases[key]['attempts'].append({'path':str(p.parent.relative_to(ROOT)),'native_export_pass':d.get('native_export_pass',False),'case_specific_specification_binding_verified':d.get('case_specific_specification_binding_verified',False),'error':(d.get('error')or{}).get('message'),'report_pass':d.get('report_pass'), 'runner':d.get('runner')})
    rows=[]
    for c in cases.values():
        passing=[a for a in c['attempts'] if a['native_export_pass']]
        chosen=passing[-1] if passing else (c['attempts'][-1] if c['attempts'] else None)
        c['selected_export']=chosen
        c['native_export_available']=bool(passing)
        c['case_specification_bound']=bool(chosen and chosen['case_specific_specification_binding_verified'])
        c['public_ready']=False
        rows.append(c)
    count={'total_cases':450,'attempted_cases':sum(bool(c['attempts']) for c in rows),'cases_with_native_export':sum(c['native_export_available'] for c in rows),'native_exports_with_explicit_spec_binding':sum(c['native_export_available'] and c['case_specification_bound'] for c in rows),'public_ready':0,'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'note':'Reference preparation only. Separate attempts remain intact; this index is not a benchmark score.'}
    (ROOT/'case_status.json').write_text(json.dumps(rows,indent=2)+'\n');(ROOT/'progress.json').write_text(json.dumps(count,indent=2)+'\n')
    with (ROOT/'case_status.csv').open('w',newline='') as f:
        fields=['case_id','label','preflight_status','native_export_available','case_specification_bound','public_ready'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    print(json.dumps(count),flush=True)
if __name__=='__main__':main()
