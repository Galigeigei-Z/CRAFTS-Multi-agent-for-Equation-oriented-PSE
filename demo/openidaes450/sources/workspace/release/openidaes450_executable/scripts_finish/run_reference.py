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
            solver_result=getattr(result,'solver',result)
            termination=getattr(solver_result,'termination_condition',None)
            solver_status=getattr(solver_result,'status',getattr(result,'solution_status',None))
            events.append({'termination_condition':str(termination) if termination is not None else None,'solver_status':str(solver_status) if solver_status is not None else None,'model_id':id(models[0]),'source':frame.f_code.co_filename,'function':frame.f_code.co_name,'optimal':optimal,'solver_class':str(type(local.get('self'))),'options':str(getattr(local.get('self'),'options',None))})
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
        if chosen is not None:export_checks=export(captures[chosen],out)
        else:pass
    except Exception as exc:error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    chosen_events=[e for e in events if e['model_id']==chosen] if export_checks else []
    optimal=bool(chosen_events and chosen_events[-1]['optimal'])
    status={'case_id':args.case_id,'runner':str(args.runner),'elapsed_seconds':round(time.time()-started,3),
      'model_calls':0,'evidence_class':'fresh_registered_reference_model_export','report_pass':isinstance(result,dict) and result.get('pass') is True,
      'solver_optimal_observed':optimal,'selected_model_id':chosen,'termination_condition':chosen_events[-1].get('termination_condition') if chosen_events else None,'model_checks':export_checks,'error':error,
      'case_specific_specification_binding_verified':bool(isinstance(result,dict) and result.get('all_specifications_consumed') is True),'public_reference_complete':False}
    status['native_export_pass']=bool(status['report_pass'] and optimal and export_checks and export_checks['idaes_model_present'] and export_checks['constraints_pass'] and not export_checks['missing_port_values'] and export_checks['port_value_count'])
    status['model_fidelity']='native_IDAES' if export_checks and export_checks['idaes_model_present'] else ('reduced_Pyomo' if export_checks else 'analytical_or_source_report')
    status['demo_accepted']=bool(status['report_pass'] and not error)
    status['residual_checks_are_warnings']=True
    status['streams_applicability']='actual_model_ports' if export_checks and export_checks.get('port_value_count') else 'not_defined_by_original_model'
    from importlib.metadata import version
    import platform
    write(out/'runtime_versions.json',{'python':platform.python_version(),**{k:version(k) for k in ['idaes-pse','pyomo','watertap']}})
    write(out/'status.json',status)
    termination=status.get('termination_condition')
    if isinstance(result,dict):
        if termination is not None:result['termination_condition']=termination
        result['solver_summary_file']='solver_summary.json'
        write(out/'runner_report.json',result)
    write(out/'solver_summary.json',{'case_id':args.case_id,
      'status':termination or ('optimality_confirmed' if optimal else 'termination_not_recorded'),
      'termination_condition':termination,'evidence':'selected model solver result',
      'selected_model_optimality_observed':optimal,'selected_model_id':chosen,
      'solver_calls_recorded':len(events),'selected_model_solver_calls':len(chosen_events),
      'solver_classes':sorted({e['solver_class'] for e in chosen_events if e.get('solver_class')})})
    print(json.dumps({k:v for k,v in status.items() if k not in {'model_checks','error'}}),flush=True)
    return 0 if status['demo_accepted'] else 1
if __name__=='__main__':raise SystemExit(main())
