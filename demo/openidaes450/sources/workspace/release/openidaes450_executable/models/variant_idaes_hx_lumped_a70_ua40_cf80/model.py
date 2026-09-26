from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from variant_models import solve

def run_case():
    model,report=solve('variant_idaes_hx_lumped_a70_ua40_cf80')
    return report
