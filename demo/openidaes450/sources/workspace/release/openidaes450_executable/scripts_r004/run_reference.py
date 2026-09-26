#!/usr/bin/env python3
"""Instrument an actual reference runner; retain failed exports as diagnostics."""
import argparse,hashlib,importlib.util,inspect,json,sys,time,traceback
from pathlib import Path
from export_actual_model import export,write


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--runner',type=Path,required=True);parser.add_argument('--case-id',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(args.workspace));sys.path.insert(0,str(args.runner.parent))
    from pyomo.core.base.block import BlockData
    from pyomo.environ import check_optimal_termination
    captures={};events=[];preferred=[]
    def model_from(obj):
        if isinstance(obj,BlockData):return obj.model()
        return None
    def profile(frame,event,result):
        if event!='return' or frame.f_code.co_name not in {'solve','run_case','solve_one','solve_variant'}:return
        local=frame.f_locals;models=[]
        for name in ['model','m','instance','block','blk']:
            model=model_from(local.get(name))
            if model is not None:models.append(model)
        for obj in local.get('args',()) if isinstance(local.get('args',()),tuple) else ():
            model=model_from(obj)
            if model is not None:models.append(model)
        if not models:return
        for model in models:captures[id(model)]=model
        if frame.f_code.co_name=='solve':
            if result is None or isinstance(result,(tuple,list,str,bool,int,float)) or not (hasattr(result,'solver') or hasattr(result,'termination_condition')):
                return
            try:optimal=bool(check_optimal_termination(result))
            except Exception:optimal=False
            events.append({'model_id':id(models[0]),'source':frame.f_code.co_filename,'function':frame.f_code.co_name,'optimal':optimal,'solver_class':str(type(local.get('self'))),'options':str(getattr(local.get('self'),'options',None))})
        else:
            preferred.extend(id(m) for m in models)
    result=None;error=None
    started=time.time()
    try:
        spec=importlib.util.spec_from_file_location('reference_case',args.runner);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        fn=module.run_case;sig=inspect.signature(fn);kwargs={}
        for name,param in sig.parameters.items():
            if name=='case_key':kwargs[name]=args.case_id
            elif name=='report_path':kwargs[name]=out/'native_report.json'
            elif param.default is inspect.Parameter.empty:raise ValueError('Runner requires an explicit binding for argument '+name)
        sys.setprofile(profile)
        result=fn(**kwargs)
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:sys.setprofile(None)
    write(out/'runner_report.json',result)
    write(out/'solver_events.json',events)
    export_checks=None
    try:
        chosen=preferred[-1] if preferred else (events[-1]['model_id'] if events else None)
        if chosen is not None:
            model=captures[chosen]
            export_checks=export(model,out)
            if isinstance(result,dict) and result.get('pass') is True and export_checks['idaes_model_present']:
                from pyomo.environ import Var
                if any(v.is_integer() or v.is_binary() for v in model.component_data_objects(Var,descend_into=True)):
                    raise ValueError('IPOPT polishing refuses discrete variables')
                from idaes.core.solvers import get_solver
                solver=get_solver(options={'tol':1e-10,'constr_viol_tol':1e-9,'acceptable_tol':1e-10,'max_iter':1500})
                polished=solver.solve(model)
                result={'original_runner_report':result,'pass':bool(check_optimal_termination(polished)),'termination_condition':str(polished.solver.termination_condition),'stage':'fresh_native_model_polish','options':dict(solver.options)}
                write(out/'polish_report.json',result)
                events.append({'model_id':chosen,'source':'explicit_native_model_polish','function':'solve','optimal':bool(check_optimal_termination(polished)),'solver_class':str(type(solver)),'options':str(solver.options)})
                write(out/'solver_events.json',events)
                export_checks=export(model,out)
        else:error=error or {'type':'MissingModel','message':'Runner did not expose an actual solved model.'}
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    chosen_events=[e for e in events if e['model_id']==chosen] if export_checks else []
    optimal=bool(chosen_events and chosen_events[-1]['optimal'])
    status={'case_id':args.case_id,'runner':str(args.runner),'runner_sha256':hashlib.sha256(args.runner.read_bytes()).hexdigest(),'elapsed_seconds':round(time.time()-started,3),
      'model_calls':0,'evidence_class':'fresh_registered_reference_model_export','report_pass':isinstance(result,dict) and result.get('pass') is True,
      'solver_optimal_observed':optimal,'model_checks':export_checks,'error':error,
      'case_specific_specification_binding_verified':bool(isinstance(result,dict) and result.get('all_specifications_consumed') is True),'public_reference_complete':False}
    status['native_export_pass']=bool(status['report_pass'] and optimal and export_checks and export_checks['idaes_model_present'] and export_checks['constraints_pass'] and not export_checks['missing_port_values'] and export_checks['port_value_count'])
    write(out/'status.json',status)
    print(json.dumps({k:v for k,v in status.items() if k not in {'model_checks','error'}}),flush=True)
    return 0 if status['native_export_pass'] else 1
if __name__=='__main__':raise SystemExit(main())
