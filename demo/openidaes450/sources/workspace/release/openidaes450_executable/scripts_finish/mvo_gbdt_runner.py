"""Recomputed GBDT demo on the original design grid; not the archived continuous surrogate optimum."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'finish_sources'))
def run_case():
    import build_idaes_mvo_official_v1 as source
    from sklearn.ensemble import HistGradientBoostingRegressor
    import joblib,numpy as np
    from pyomo.environ import SolverFactory,value,check_optimal_termination
    from process_family.type.discretized import DiscretizedProcessFamily
    out=Path(os.environ['DEMO_OUTPUT']);data=source.filtered_data('all_56_variants');features=['Evaporator Area','Condenser Area','Compressor Design Flow','Capacity','Outside Air Temperature']
    feasible=data['Success'].astype(str).str.lower().eq('true');regressor=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=31,random_state=42)
    regressor.fit(data.loc[feasible,features],data.loc[feasible,'Total Annualized Cost']);prediction=regressor.predict(data.loc[feasible,features]);data.loc[feasible,'Total Annualized Cost']=np.maximum(prediction,0)
    csv=out/'fresh_surrogate_grid.csv';data.to_csv(csv,index=False);joblib.dump(regressor,out/'gbdt_model.joblib')
    case=next(c for c in source.CASES if c.case_id=='mvo_official_transcritical_co2_surrogate_gbdt');family=DiscretizedProcessFamily(source.parameters(csv,case));family.build_model();model=family.model
    solver=SolverFactory('appsi_highs');solver.options.update(threads=1,mip_rel_gap=0.01,time_limit=900);result=solver.solve(model)
    return {'pass':bool(check_optimal_termination(result)),'termination_condition':str(result.solver.termination_condition),'objective_value':value(model.obj),'model_fidelity':'recomputed_GBDT_grid_demo','scope':'Original data grid and original feasible alternatives; fresh deterministic GBDT cost surrogate; discrete common-module design optimization. Not a reproduction of the archived continuous surrogate model.','training_rows':int(feasible.sum()),'training_seed':42}
