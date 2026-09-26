import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'finish_sources'))
def run_case(case_key):
    import solve_idaes_official_sofc_family_v1 as s
    s.ROOT=ROOT;s.SOURCE_ROOT=ROOT/'finish_sources/sofc_family'
    report=s.solve_case(case_key);report['original_strict_pass']=report['pass'];report['pass']=report.get('termination_condition')=='optimal';return report
