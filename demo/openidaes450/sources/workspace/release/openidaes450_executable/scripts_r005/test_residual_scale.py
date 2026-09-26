import tempfile,unittest
from pathlib import Path
from pyomo.environ import ConcreteModel,Var,Constraint
from export_actual_model import export
class ResidualScale(unittest.TestCase):
    def run_model(self,offset):
        m=ConcreteModel();m.x=Var(initialize=1);m.y=Var(initialize=1+offset);m.balance=Constraint(expr=1e8*m.x-1e8*m.y==0)
        with tempfile.TemporaryDirectory() as d:return export(m,Path(d))
    def test_cancellation_uses_equation_magnitude(self):
        result=self.run_model(1e-10);self.assertTrue(result['constraints_pass']);self.assertFalse(result['idaes_model_present'])
    def test_material_imbalance_fails(self):self.assertFalse(self.run_model(.01)['constraints_pass'])
if __name__=='__main__':unittest.main()
