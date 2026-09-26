#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','variant_reflo_air_stripping_offgas_gac_polishing']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
