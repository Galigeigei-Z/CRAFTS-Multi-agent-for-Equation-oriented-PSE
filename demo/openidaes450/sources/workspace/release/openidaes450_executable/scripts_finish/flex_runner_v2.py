import os
from pathlib import Path
def run_case():
    import sys
    sys.modules["gurobipy"] = None  # Optional commercial backend is unused; solve with HiGHS.
    import pyomo.environ as p
    from watertap.flowsheets.flex_desal.tests import test_pricetaker_workflow as source
    os.chdir(os.environ['DEMO_OUTPUT']);test=source.TestPriceTakerWorkflow();frame=test.system_frame.__wrapped__(test);model,prices=frame
    for name in ['test_add_constraints','test_add_useful_expressions','test_add_capacity_limits','test_constrain_water_production']:getattr(test,name)(frame)
    # All skids running, no startup/shutdown during the fixed demonstration window.
    for var in model.component_data_objects(p.Var,descend_into=True):
        if var.is_binary():var.fix(0 if any(x in var.name.lower() for x in ['startup','shutdown','start_up','shut_down']) else 1)
    solver=p.SolverFactory('appsi_highs');solver.options['threads']=1;result=solver.solve(model)
    return {'pass':bool(p.check_optimal_termination(result)),'termination_condition':str(result.solver.termination_condition),'scope':'Original full-horizon model with fixed all-on schedule and nominal recovery; no free-binary scheduling optimum.'}
