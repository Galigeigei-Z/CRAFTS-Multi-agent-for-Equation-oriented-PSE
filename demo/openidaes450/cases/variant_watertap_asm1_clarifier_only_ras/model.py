#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','variant_watertap_asm1_clarifier_only_ras']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
