#!/usr/bin/env python3
"""Report imports and optionally solve tiny NLP/LP probes in the active environment."""
import argparse,importlib.metadata as md,json,platform
p=argparse.ArgumentParser();p.add_argument('--solve',action='store_true');a=p.parse_args()
r={'python':platform.python_version(),'packages':{},'solvers':{}}
for name in ['idaes-pse','pyomo','watertap','watertap-solvers','highspy','reaktoro','exposan','qsdsan','scipy']:
 try:r['packages'][name]=md.version(name)
 except md.PackageNotFoundError:r['packages'][name]=None
try:
 import idaes
 import pyomo.environ as pe
 for name in ['ipopt','appsi_highs']:
  try:
   s=pe.SolverFactory(name);item={'available':bool(s.available(exception_flag=False))}
   if item['available'] and a.solve:
    m=pe.ConcreteModel();m.x=pe.Var(bounds=(0,None));m.c=pe.Constraint(expr=m.x>=1);m.obj=pe.Objective(expr=(m.x-2)**2 if name=='ipopt' else m.x)
    res=s.solve(m);item.update(termination=str(res.solver.termination_condition),optimal=bool(pe.check_optimal_termination(res)),x=pe.value(m.x))
   r['solvers'][name]=item
  except Exception as e:r['solvers'][name]={'error':str(e)}
except ImportError as e:r['simulation_import_error']=str(e)
print(json.dumps(r,indent=2))
if a.solve and not all(r['solvers'].get(n,{}).get('optimal',False) for n in ['ipopt','appsi_highs']):raise SystemExit(1)
