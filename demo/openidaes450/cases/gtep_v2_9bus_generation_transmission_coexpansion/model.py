#!/usr/bin/env python3
from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[2]
sys.argv=[str(root/'run_case.py'),'--case','gtep_v2_9bus_generation_transmission_coexpansion']+sys.argv[1:]
runpy.run_path(str(root/'run_case.py'),run_name='__main__')
