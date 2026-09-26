#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','blind_synthesized_boron_removal_unit']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
