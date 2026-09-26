import importlib.util,json,os
from pathlib import Path
def run_case():
    import pandas as pd
    path=Path('/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/full107_official_sources/watertap/watertap/flowsheets/METAB/model_evaluation.py')
    spec=importlib.util.spec_from_file_location('original_metab',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    out=Path(os.environ['DEMO_OUTPUT']);os.chdir(out)
    data=pd.DataFrame({'inf_fr':[5,5,5],'temp':[20,25,30],'hrt':[1,5,10]});data.to_csv(out/'inputs.csv',index=False)
    results=m.run_model(data);assert isinstance(results,pd.DataFrame) and len(results)==3;results.to_csv(out/'external_stream_results.csv',index=False)
    (out/'missing_values.json').write_text(json.dumps({'missing_by_column':results.isna().sum().to_dict(),'note':'Blank cells are retained as unavailable; they are not filled with synthetic values.'},indent=2))
    return {'pass':True,'external_computation':True,'model_fidelity':'EXPOsan_dynamic_BDF','output_file':'external_stream_results.csv','rows':len(results),'columns':list(results.columns),'property_packages':'EXPOsan METAB components; IDAES property packages not applicable','integration_horizon_days':200,'source':str(path)}
