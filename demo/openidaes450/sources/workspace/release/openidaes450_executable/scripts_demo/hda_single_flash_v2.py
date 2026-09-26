import importlib.util,sys
from stage3_specs_solve import run_hda_once_through_reference_solve as runner
def run_case():
    spec=importlib.util.spec_from_file_location('notebook_build',runner.SOURCE_ROOT/'notebook_build.py')
    module=importlib.util.module_from_spec(spec);sys.modules['notebook_build']=module;spec.loader.exec_module(module)
    return runner.run_case(second_flash=False)
