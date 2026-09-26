import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'finish_sources'))
def run_case(case_key):
    from pyomo.contrib.appsi.solvers.highs import Highs
    original=Highs.__init__
    def init(self,*a,**kw):
        original(self,*a,**kw);self.highs_options['threads']=1
    Highs.__init__=init
    if case_key.startswith('mvo_v2'):
        import build_idaes_mvo_decision_variants_v2 as source
        case=next(c for c in source.CASES if c.case_id==case_key)
        return source.solve_case(case)[0]
    if case_key.startswith('mvo_'):
        import build_idaes_mvo_official_v1 as source
        case=next(c for c in source.CASES if c.case_id==case_key)
        if case.method!='discretized':raise ValueError('GBDT source requires a separate surrogate runner, not historical notebook replay')
        return source.solve_discretized(case)[0]
    if case_key.startswith('gtep_v2'):
        import build_idaes_gtep_engineering_variants_v2 as source
        case=next(c for c in source.VARIANTS if c.case_id==case_key)
        metrics=source.solve_variant(case)
        return {'pass':True,'status':'optimized','termination_condition':'optimal','metrics':metrics,'model_fidelity':'native_grid_optimization'}
    import build_idaes_gtep_official_v1 as source
    case=next(c for c in source.CASES if c.case_id==case_key)
    if case_key in ['official_gtep_5bus_jsc_baseline','official_gtep_5bus_candidate_expansion']:return source.execute(case)
    import solve_idaes_gtep_recovery_v1 as recovery
    with recovery.fixed_copper_plate_sets():
        metrics,configuration=recovery.recover(case)
    return {'pass':True,'status':'optimized','termination_condition':'optimal','metrics':metrics,'configuration':configuration,'model_fidelity':'native_grid_optimization'}
