"""Export solved model state and check actual constraints; never invent outputs."""
import csv
import hashlib
import importlib.metadata
import inspect
import json
import math
import platform
import sys
from pathlib import Path


def write(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False,default=str)+'\n')


def export(model, output):
    from pyomo.environ import Var,Param,Constraint,Block,value,units as pyunits
    from pyomo.network import Port,Arc
    from pyomo.core.expr.numeric_expr import SumExpression
    from idaes.core import PhysicalParameterBlock,ReactionParameterBlock,UnitModelBlockData
    from idaes.core.util.model_statistics import degrees_of_freedom
    output=Path(output)
    def num(x):
        if x is None:return None
        try:
            v=float(value(x,exception=False));return v if math.isfinite(v) else None
        except (ValueError,TypeError,OverflowError,ZeroDivisionError):return None
    def config(x):
        if x is None or isinstance(x,(str,bool,int)):return x
        if isinstance(x,float):return x if math.isfinite(x) else None
        if isinstance(x,dict) or (type(x).__module__.startswith('pyomo.common.config') and hasattr(x,'items')):return {str(k):config(v) for k,v in x.items()}
        if isinstance(x,(tuple,list)):return [config(v) for v in x]
        if hasattr(x,'name') and isinstance(x.name,str):return {'component':x.name}
        if hasattr(x,'__module__') and hasattr(x,'__qualname__'):return x.__module__+'.'+x.__qualname__
        return {'type':type(x).__module__+'.'+type(x).__qualname__,'requires_source_definition':True}
    variables=[]
    for v in model.component_data_objects(Var,descend_into=True):
        variables.append({'name':v.name,'value':num(v),'units':str(v.get_units()),'fixed':v.fixed,'lower_bound':num(v.lb),'upper_bound':num(v.ub)})
    with (output/'unit_and_state_variables.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['name','value','units','fixed','lower_bound','upper_bound']);w.writeheader();w.writerows(variables)
    parameters=[]
    for component in model.component_objects(Param,descend_into=True):
        for index,item in component.items():
            name=component.name if index is None else component.name+'['+str(index)+']'
            parameters.append({'name':name,'value':num(item),'units':str(component.get_units())})
    write(output/'parameters.json',parameters)
    ports=[]
    for port in model.component_data_objects(Port,descend_into=True):
        for member,var in port.vars.items():
            for index,item in var.items():ports.append({'port':port.name,'member':member,'index':str(index),'model_variable':item.name,'value':num(item),'units':str(pyunits.get_units(item))})
    with (output/'streams.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['port','member','index','model_variable','value','units']);w.writeheader();w.writerows(ports)
    write(output/'arcs.json',[{'name':a.name,'source':getattr(a.source,'name',None),'destination':getattr(a.destination,'name',None)} for a in model.component_data_objects(Arc,descend_into=True)])
    packages=[];source_modules=set()
    for b in model.component_objects(descend_into=True):
        if not isinstance(b,(PhysicalParameterBlock,ReactionParameterBlock)):continue
        definitions=[]
        for cls in type(b).__mro__:
            if cls.__module__.startswith(('pyomo.','idaes.core.','builtins')) or cls.__name__.startswith('_'):
                continue
            source_modules.add(cls.__module__)
            definitions.append({'class':cls.__module__+'.'+cls.__name__})
        constructor=next((d['class'] for d in definitions if d['class'].endswith('ParameterBlock')),next((d['class'] for d in reversed(definitions) if not d['class'].endswith('Data')),None))
        data_class=next((d['class'] for d in definitions if d['class'].endswith('Data')),None)
        packages.append({'name':b.name,'class':constructor or data_class or type(b).__module__+'.'+type(b).__name__,
          'module':(constructor or data_class or type(b).__module__+'.'+type(b).__name__).rsplit('.',1)[0],
          'data_class':data_class,'identity_evidence':'runtime class hierarchy',
          'implementation':definitions,'configuration':{str(k):config(v) for k,v in getattr(b,'config',{}).items()}})
    write(output/'property_packages.json',packages)
    write(output/'property_summary.json',{'applicability':'model_parameter_packages' if packages else 'no_IDAES_parameter_packages_defined','package_count':len(packages),'packages':[{'name':p['name'],'class':p['class'],'module':p['module'],'configuration_file':'property_packages.json'} for p in packages]})
    units=[]
    for b in model.component_data_objects(Block,descend_into=True):
        if isinstance(b,UnitModelBlockData):
            units.append({'name':b.name,'class':type(b).__module__+'.'+type(b).__name__,'configuration':{str(k):config(v) for k,v in getattr(b,'config',{}).items()}})
    write(output/'units.json',units)
    violations=[];unknown=[];max_scaled=0.;count=0
    for c in model.component_data_objects(Constraint,active=True,descend_into=True):
        count+=1;body=num(c.body);lower=num(c.lower);upper=num(c.upper)
        if body is None:unknown.append(c.name);continue
        delta=max(0.,(lower-body) if lower is not None else 0.,(body-upper) if upper is not None else 0.)
        term_scale=sum(abs(num(arg) or 0.) for arg in c.body.args) if isinstance(c.body,SumExpression) else abs(body)
        scale=max(1.,term_scale,abs(body),abs(lower or 0.),abs(upper or 0.));ratio=delta/scale;max_scaled=max(max_scaled,ratio)
        if ratio>1e-6:violations.append({'name':c.name,'absolute_violation':delta,'relative_violation':ratio,'normalization_scale':scale})
    sources=[]
    for name,module in sorted(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if not filename or not str(filename).endswith('.py'):continue
        if not name.startswith(('idaes','pyomo','watertap','prommis','dispatches','reference_case','stage3','sandbox_solver')):continue
        p=Path(filename)
        if p.is_file():sources.append({'module':name,'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    write(output/'loaded_source_inventory.json',sources)
    versions={}
    for name in ['idaes-pse','pyomo','watertap','watertap-solvers','prommis','dispatches']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    write(output/'environment.json',{'python':platform.python_version(),'platform':platform.platform(),'versions':versions,'executable':sys.executable})
    checks={'variable_count':len(variables),'missing_variable_values':sum(v['value'] is None for v in variables),'port_value_count':len(ports),'missing_port_values':sum(v['value'] is None for v in ports),
      'unit_count':len(units),'property_package_count':len(packages),'degrees_of_freedom':degrees_of_freedom(model),'constraint_count':count,
      'constraint_residual_convention':'equation-terms/v2: violation/max(1,sum(abs(additive body terms)),abs(body),abs(bounds)); tolerance 1e-6; raw violations retained; not a substitute for engineering conservation audits',
      'maximum_relative_constraint_violation':max_scaled,'violations':violations[:100],'unevaluable_constraints':unknown[:100],
      'constraints_pass':not violations and not unknown,'idaes_model_present':bool(units and packages)}
    write(output/'model_checks.json',checks)
    return checks
