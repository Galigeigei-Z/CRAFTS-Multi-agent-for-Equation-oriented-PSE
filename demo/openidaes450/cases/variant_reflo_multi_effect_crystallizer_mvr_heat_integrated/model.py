#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','variant_reflo_multi_effect_crystallizer_mvr_heat_integrated']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
