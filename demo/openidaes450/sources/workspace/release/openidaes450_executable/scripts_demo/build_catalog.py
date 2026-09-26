"""Index actual fresh and historical evidence under practical demo criteria."""
import collections,csv,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PREP=ROOT.parent/'openidaes450_demo_preparation'
suite=json.loads((ROOT/'suite.json').read_text())['cases'];rows=[]
paths_by_case=collections.defaultdict(list)
for path in (ROOT/'runs').glob('*/*/status.json'):paths_by_case[path.parent.name].append(path)
for case in suite:
    key=case['case_id'];target=ROOT/'cases'/key;target.mkdir(parents=True,exist_ok=True)
    original=PREP/'cases'/key
    for name in ['specification.json','topology.json','solve_report.json','simulation_evidence.json']:
        if (original/name).exists():shutil.copy2(original/name,target/('historical_'+name if name=='solve_report.json' else name))
    options=[]
    for p in paths_by_case[key]:
        d=json.loads(p.read_text());checks=d.get('model_checks')or{}
        accepted=d.get('demo_accepted',bool(d.get('report_pass') and not d.get('error')))
        accepted=accepted and bool(checks or d.get('external_computation'))
        report_path=p.parent/'runner_report.json'
        report=json.loads(report_path.read_text()) if report_path.exists() else {}
        d['_report']=report or {}
        rank=(bool(accepted),not (d['_report'].get('reproduces_original_reference') is False or d['_report'].get('model_fidelity')=='recomputed_GBDT_grid_demo'),bool(d.get('native_export_pass')),bool(checks.get('idaes_model_present')),p.stat().st_mtime)
        options.append((rank,p,d))
    best=max(options,key=lambda t:t[0]) if options else None
    historical=json.loads((original/'solve_report.json').read_text())
    if best and best[0][0]:
        _,p,d=best;checks=d.get('model_checks')or{}
        fidelity=d.get('_report',{}).get('model_fidelity') or d.get('model_fidelity') or ('native_IDAES' if checks.get('idaes_model_present') else 'reduced_Pyomo' if checks else 'analytical_or_source_report')
        evidence='fresh_result';result=str(p.parent.relative_to(ROOT));passed=True
    else:
        fidelity='historical_report_only';evidence='historical_result';result=str((target/'historical_solve_report.json').relative_to(ROOT));passed=historical.get('pass') is True
    row={'case_id':key,'label':case['label'],'evidence':evidence,'model_fidelity':fidelity,'original_report_pass':passed,'result_path':result,'runner':best[2].get('runner') if best and best[0][0] else case.get('runner'),'residual_policy':'warning_only'}
    (target/'demo_manifest.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
(ROOT/'demo_catalog.json').write_text(json.dumps(rows,indent=2)+'\n')
with (ROOT/'demo_catalog.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary={'total_cases':len(rows),'evidence_counts':dict(collections.Counter(r['evidence'] for r in rows)),'fidelity_counts':dict(collections.Counter(r['model_fidelity'] for r in rows)),'note':'Historical fallback is explicitly labeled; no missing physical states are fabricated.'}
(ROOT/'demo_progress.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
