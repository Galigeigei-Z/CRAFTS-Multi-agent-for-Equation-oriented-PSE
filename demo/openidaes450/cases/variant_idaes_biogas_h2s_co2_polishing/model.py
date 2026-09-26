#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','variant_idaes_biogas_h2s_co2_polishing']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
