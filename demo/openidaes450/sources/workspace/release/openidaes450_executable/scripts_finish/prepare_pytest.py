import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
b={}
def add(key,module,node='',selection=''):
 b[key]={'module':module,'node':node,'selection':selection}
base='idaes.models.unit_models.tests.'
add('idaes_feed_flash',base+'test_feed_flash','::TestBTXIdeal')
add('idaes_pipe',base+'test_pipe','::TestSaponification')
add('idaes_valve',base+'test_valve','::TestLinearValveLegacyScaling')
add('idaes_mscontactor',base+'test_mscontactor',selection='solve or initialize')
base='idaes.models_extra.power_generation.unit_models.tests.'
for key,mod in [('idaes_heat_exchanger_2d','test_heat_exchanger2D'),('idaes_dynamic_feedwater_heater','test_feedwater_heater_dynamic'),('idaes_drum_1d','test_drum1D')]:add(key,base+mod)
add('idaes_co2_membrane_1d','idaes.models_extra.co2_capture_and_utilization.unit_models.tests.test_membrane_1d','::TestMembrane')
base='watertap_contrib.reflo.'
add('reflo_fo_trevi',base+'flowsheets.FO.tests.test_fo_trevi_flowsheet','::TestTreviFO')
add('reflo_ltmed_vagmd_semibatch',base+'flowsheets.LTMED_VAGMD_semibatch.tests.test_LTMED_VAGMD_semibatch','::TestVAGMDbatch')
add('reflo_vagmd_multiperiod',base+'flowsheets.VAGMD_batch.tests.test_VAGMD_batch','::TestVAGMDbatchAS7C15L_Closed')
for key,mod,node in [('air_stripping_0d','test_air_stripping_0D','TestAirStripping0D'),('chemical_softening','test_chemical_softening','TestChemSoft_ExcessLimeSodaSilicaRemoval'),('crystallizer_effect','test_crystallizer_effect','TestCrystallizerEffect'),('deep_well_injection','test_deep_well_injection','TestDeepWellInjection_BLMCosting'),('multi_effect_crystallizer','test_multi_effect_crystallizer','TestMultiEffectCrystallizer_3Effects'),('solar_still','test_solar_still','TestSolarStill'),('waiv','test_waiv','TestWAIV')]:add('reflo_'+key,base+'unit_models.tests.'+mod,'::'+node)
(ROOT/'finish_pytest_bindings.json').write_text(json.dumps(b,indent=2))
rows=[{'case_id':k,'runner':str(ROOT/'scripts_finish/pytest_runner.py'),'timeout':900} for k in b]
(ROOT/'finish_pytest.json').write_text(json.dumps(rows,indent=2));print(len(rows))
