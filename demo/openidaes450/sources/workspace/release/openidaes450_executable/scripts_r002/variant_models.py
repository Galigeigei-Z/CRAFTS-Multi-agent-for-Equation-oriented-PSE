"""Full native IDAES pump and heat-exchanger variants with explicit spec binding."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
PREP=ROOT/'release/openidaes450_demo_preparation/cases'


def build(case_key):
    from pyomo.environ import ConcreteModel,TransformationFactory,value,units as u
    from pyomo.network import Arc
    from idaes.core import FlowsheetBlock
    from idaes.models.unit_models import Feed,Product,Pump
    from idaes.models.properties import iapws95
    spec=json.loads((PREP/case_key/'specification.json').read_text())
    family=spec['family']; bindings=[]
    if family=='family_iapws_pump_canary':
        model=ConcreteModel();model.fs=FlowsheetBlock(dynamic=False);model.fs.properties=iapws95.Iapws95ParameterBlock()
        model.fs.pump=Pump(property_package=model.fs.properties)
        pump=model.fs.pump
        defaults={('feed','flow_mol'):100.,('feed','temperature'):298.15,('feed','pressure'):101325.,('pump','deltaP'):500000.,('pump','efficiency_pump'):0.85}
        expected={('feed','flow_mol'):'mol/s',('feed','temperature'):'K',('feed','pressure'):'Pa',('pump','deltaP'):'Pa',('pump','efficiency_pump'):'dimensionless'}
        for row in spec['specs']:
            key=(row['target'],row['variable'])
            if key not in expected or row['units']!=expected[key]:raise ValueError('Unbound pump specification: '+str(row))
            defaults[key]=float(row['value']);bindings.append({'specification':row,'target':str(key),'value':float(row['value'])})
        pump.inlet.flow_mol[0].fix(defaults['feed','flow_mol']);pump.inlet.pressure[0].fix(defaults['feed','pressure'])
        pump.inlet.enth_mol[0].fix(iapws95.htpx(T=defaults['feed','temperature']*u.K,P=defaults['feed','pressure']*u.Pa))
        pump.deltaP[0].fix(defaults['pump','deltaP']);pump.efficiency_pump[0].fix(defaults['pump','efficiency_pump'])
        branches=[('feed','pressurized_water',model.fs.properties,pump.inlet,pump.outlet,'feed_to_pump','pump_to_product')];unit=pump
    elif family=='family_idaes_hx_ntu':
        from stage3_specs_solve.run_hx_ntu_reference_solve import build_model
        model=build_model();unit=model.fs.heat_exchanger
        targets={('hot_feed','temperature'):(unit.hot_side_inlet.temperature[0],'K'),('cold_feed','temperature'):(unit.cold_side_inlet.temperature[0],'K'),('heat_exchanger','area'):(unit.area,'m^2'),('heat_exchanger','heat_transfer_coefficient'):(unit.heat_transfer_coefficient,'W/m^2/K'),('heat_exchanger','effectiveness'):(unit.effectiveness,'dimensionless')}
        for row in spec['specs']:
            key=(row['target'],row['variable'])
            if key not in targets or row['units']!=targets[key][1]:raise ValueError('Unbound NTU specification: '+str(row))
            obj=targets[key][0];obj.fix(row['value']);bindings.append({'specification':row,'target':obj.name,'value':{str(i):value(v) for i,v in obj.items()} if obj.is_indexed() else value(obj)})
        branches=[('hot_feed','hot_product',model.fs.hotside_properties,unit.hot_side_inlet,unit.hot_side_outlet,'hot_feed_to_hx','hx_to_hot_product'),('cold_feed','cold_product',model.fs.coldside_properties,unit.cold_side_inlet,unit.cold_side_outlet,'cold_feed_to_hx','hx_to_cold_product')]
    elif family=='family_idaes_hx_lumped_capacitance':
        from stage3_specs_solve.run_hx_lumped_capacitance_reference_solve import build_model,set_operating_conditions
        model=build_model();set_operating_conditions(model);unit=model.fs.heat_exchanger
        targets={('cold_feed','temperature'):(unit.tube_inlet.temperature[0],'K'),('heat_exchanger','area'):(unit.area,'m^2'),('heat_exchanger','ua_hot_side'):(unit.ua_hot_side,'W/K'),('heat_exchanger','ua_cold_side'):(unit.ua_cold_side,'W/K'),('heat_exchanger','crossflow_factor'):(unit.crossflow_factor,'dimensionless')}
        for row in spec['specs']:
            key=(row['target'],row['variable'])
            if key==('hot_feed','temperature') and row['units']=='K':
                unit.shell_inlet.enth_mol.fix(iapws95.htpx(T=row['value']*u.K,P=101325*u.Pa));bindings.append({'specification':row,'target':'shell_inlet.enth_mol from IAPWS T,P','value':row['value']});continue
            if key not in targets or row['units']!=targets[key][1]:raise ValueError('Unbound lumped specification: '+str(row))
            obj=targets[key][0];obj.fix(row['value']);bindings.append({'specification':row,'target':obj.name,'value':{str(i):value(v) for i,v in obj.items()} if obj.is_indexed() else value(obj)})
        branches=[('hot_feed','hot_product',model.fs.properties_shell,unit.shell_inlet,unit.shell_outlet,'steam_feed_to_hx','hx_to_steam_product'),('cold_feed','cold_product',model.fs.properties_tube,unit.tube_inlet,unit.tube_outlet,'btx_feed_to_hx','hx_to_btx_product')]
    else:raise ValueError('Unsupported native variant family '+family)
    # Materialize terminal Feed/Product units rather than synthesizing terminal result rows.
    for feed_name,product_name,properties,inlet,outlet,in_arc,out_arc in branches:
        model.fs.add_component(feed_name,Feed(property_package=properties));feed=getattr(model.fs,feed_name)
        model.fs.add_component(product_name,Product(property_package=properties));product=getattr(model.fs,product_name)
        for name,variable in inlet.vars.items():
            for index,item in variable.items():feed.outlet.vars[name][index].fix(value(item));item.unfix()
        model.fs.add_component(in_arc,Arc(source=feed.outlet,destination=inlet));model.fs.add_component(out_arc,Arc(source=outlet,destination=product.inlet))
    TransformationFactory('network.expand_arcs').apply_to(model)
    return model,unit,branches,bindings


def solve(case_key):
    from pyomo.environ import check_optimal_termination
    from idaes.core.solvers import get_solver
    from idaes.core.util.initialization import propagate_state
    from idaes.core.util.model_statistics import degrees_of_freedom
    model,unit,branches,bindings=build(case_key)
    for feed,product,props,inlet,outlet,a,b in branches:
        getattr(model.fs,feed).initialize();propagate_state(getattr(model.fs,a))
    unit.initialize()
    for feed,product,props,inlet,outlet,a,b in branches:
        propagate_state(getattr(model.fs,b));getattr(model.fs,product).initialize()
    results=get_solver().solve(model)
    report={'pass':bool(check_optimal_termination(results) and degrees_of_freedom(model)==0),'case_id':case_key,'termination_condition':str(results.solver.termination_condition),'final_dof':degrees_of_freedom(model),'specification_binding':bindings,'all_specifications_consumed':True,'fidelity':'native IDAES unit equations with physical Feed/Product boundaries'}
    return model,report
