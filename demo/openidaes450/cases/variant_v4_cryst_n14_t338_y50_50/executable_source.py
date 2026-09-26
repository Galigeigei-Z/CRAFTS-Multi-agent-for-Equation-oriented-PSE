from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts_r003"))
from flowsheet_variants import run

def run_case():
    model,report=run('variant_v4_cryst_n14_t338_y50_50')
    return report
