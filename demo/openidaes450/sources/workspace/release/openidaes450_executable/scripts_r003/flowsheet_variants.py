"""Execute registered native multi-unit operating variants, with all parameters bound."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(case_key):
    from idaes.core.util.model_statistics import degrees_of_freedom
    from pyomo.environ import check_optimal_termination
    from stage3_specs_solve import watertap_gac_lead_lag_model as gac
    from stage3_specs_solve import watertap_two_pass_ro_model as ro
    from stage3_specs_solve import watertap_two_stage_crystallization_model as cryst
    manifest=ROOT/'source_bindings/flowsheet_operating_variants_v4.json'
    row=next(x for x in json.loads(manifest.read_text())['cases'] if x['case_id']==case_key);p=row['params']
    canonical=json.dumps({'parent_case_id':row['parent_case_id'],'params':p},sort_keys=True,separators=(',',':'))
    if hashlib.sha256(canonical.encode()).hexdigest()!=row['fingerprint']:raise ValueError('Variant fingerprint mismatch')
    if row['family']=='two_pass_ro':
        expected={'flow_vol_m3_s','feed_nacl_mass_fraction','p1_pressure_Pa','p2_pressure_Pa','ro1_area_m2','ro2_area_m2'}
        if set(p)!=expected:raise ValueError('Unexpected RO parameters')
        module=ro;model=ro.build_model();ro.set_operating_conditions(model,p['flow_vol_m3_s'],p['feed_nacl_mass_fraction']);fs=model.fs
        fs.P1.control_volume.properties_out[0].pressure.fix(p['p1_pressure_Pa']);fs.P2.control_volume.properties_out[0].pressure.fix(p['p2_pressure_Pa']);fs.RO1.area.fix(p['ro1_area_m2']);fs.RO2.area.fix(p['ro2_area_m2'])
    elif row['family']=='two_stage_crystallization':
        expected={'feed_nacl_kg_s','feed_water_kg_s','stage1_temperature_K','stage2_temperature_K','stage1_yield','stage2_yield'}
        if set(p)!=expected:raise ValueError('Unexpected crystallization parameters')
        module=cryst;model=cryst.build_model();cryst.set_operating_conditions(model);fs=model.fs
        fs.C1.inlet.flow_mass_phase_comp[0,'Liq','NaCl'].fix(p['feed_nacl_kg_s']);fs.C1.inlet.flow_mass_phase_comp[0,'Liq','H2O'].fix(p['feed_water_kg_s'])
        fs.C1.temperature_operating.fix(p['stage1_temperature_K']);fs.C2.temperature_operating.fix(p['stage2_temperature_K']);fs.C1.crystallization_yield['NaCl'].fix(p['stage1_yield']);fs.C2.crystallization_yield['NaCl'].fix(p['stage2_yield'])
    elif row['family']=='gac_lead_lag':
        expected={'lead_bed_length_m','lead_ebct_s','lead_replacement_ratio','lag_bed_length_m','lag_ebct_s','lag_replacement_ratio'}
        if set(p)!=expected:raise ValueError('Unexpected GAC parameters')
        module=gac;model=gac.build_model();gac.set_operating_conditions(model);fs=model.fs
        for name in ['lead','lag']:
            bed=getattr(fs,name+'_bed');bed.bed_length.fix(p[name+'_bed_length_m']);bed.ebct.fix(p[name+'_ebct_s']);bed.conc_ratio_replace.fix(p[name+'_replacement_ratio'])
    else:raise ValueError('Unbound family')
    module.initialize_model(model);results=module.solve_model(model)
    return model,{'pass':bool(check_optimal_termination(results) and degrees_of_freedom(model)==0),'case_id':case_key,'termination_condition':str(results.solver.termination_condition),'final_dof':degrees_of_freedom(model),'variant_parameters':p,'variant_fingerprint':row['fingerprint'],'all_registered_variant_parameters_consumed':True,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'metrics':module.metrics(model)}
