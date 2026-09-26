from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts_r003"))
from flowsheet_variants import run

def run_case():
    model,report=run('variant_v4_ro_f10_s30_p22_11_a80_120')
    return report
