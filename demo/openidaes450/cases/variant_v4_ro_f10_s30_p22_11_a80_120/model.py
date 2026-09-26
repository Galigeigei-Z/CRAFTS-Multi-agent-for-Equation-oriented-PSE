#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','variant_v4_ro_f10_s30_p22_11_a80_120']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
