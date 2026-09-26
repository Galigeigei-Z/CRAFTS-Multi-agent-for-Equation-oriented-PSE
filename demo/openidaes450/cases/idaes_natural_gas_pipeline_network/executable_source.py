import ast,inspect,os,textwrap
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run_case(case_key):
    import pyomo.environ as pyo
    os.chdir(os.environ['DEMO_OUTPUT'])
    if case_key=='dispatches_ultra_supercritical_plant':
        from dispatches.case_studies.fossil_case.ultra_supercritical_plant import ultra_supercritical_powerplant as source
        model=source.build_plant_model();source.initialize(model);results=pyo.SolverFactory('ipopt').solve(model)
    elif case_key=='idaes_natural_gas_pipeline_network':
        from idaes.models_extra.gas_distribution.unit_models.tests import test_flowsheet as source
        fn=source.TestConstructFlowsheets.test_four_nodes_linear
        tree=ast.parse(textwrap.dedent(inspect.getsource(fn)));tree.body[0].body.append(ast.Return(value=ast.Name(id='m',ctx=ast.Load())));ast.fix_missing_locations(tree)
        ns=dict(source.__dict__);exec(compile(tree,source.__file__,'exec'),ns);model=ns[fn.__name__](source.TestConstructFlowsheets())
        for variable in model.component_data_objects(pyo.Var,descend_into=True):
            if variable.value is None:
                variable.set_value(5400 if 'flow_mass' in variable.name else 0 if 'dt' in variable.name else 1)
        results=pyo.SolverFactory('ipopt').solve(model,options={'max_iter':2000,'tol':1e-6})
    elif case_key=='idaes_ngcc_soec':
        import sys,importlib.util
        source_dir=Path('/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/netl_ngcc_soec/source_root/ngcc')
        sys.path.insert(0,str(source_dir))
        import ngcc_soec
        NgccSoecFlowsheet=ngcc_soec.NgccSoecFlowsheet
        model=pyo.ConcreteModel();model.fs=NgccSoecFlowsheet(dynamic=False)
        checkpoint='/scratch/projects/CFP04/CFP04-CF-050/idaes/agentB/cases/mfs_refactored_cases/netl_ngcc_soec/source_root/ngcc/ngcc_soec_init.json.gz'
        model.fs.initialize(load_from=checkpoint,save_to=None)
        results=pyo.SolverFactory('ipopt').solve(model,options={'max_iter':1000,'linear_solver':'ma57','nlp_scaling_method':'user-scaling'})
    else:raise KeyError(case_key)
    return {'pass':bool(pyo.check_optimal_termination(results)),'termination_condition':str(results.solver.termination_condition)}
