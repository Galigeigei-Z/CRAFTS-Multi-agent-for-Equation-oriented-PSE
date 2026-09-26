import json,tempfile,unittest
from pathlib import Path
from pyomo.environ import ConcreteModel,Var,Param,Constraint
from export_actual_model import export

class ExportChecks(unittest.TestCase):
    def test_immutable_parameter_and_violated_constraint(self):
        model=ConcreteModel();model.x=Var(initialize=2);model.constant=Param(initialize=3);model.balance=Constraint(expr=model.x==1)
        with tempfile.TemporaryDirectory() as directory:
            result=export(model,Path(directory))
            self.assertFalse(result['constraints_pass'])
            self.assertFalse(result['idaes_model_present'])
            self.assertEqual(json.loads((Path(directory)/'parameters.json').read_text())[0]['value'],3)
    def test_unevaluated_state_is_not_converged_data(self):
        model=ConcreteModel();model.x=Var();model.balance=Constraint(expr=model.x==1)
        with tempfile.TemporaryDirectory() as directory:
            result=export(model,Path(directory))
            self.assertEqual(result['missing_variable_values'],1)
            self.assertFalse(result['constraints_pass'])
            self.assertEqual(result['unevaluable_constraints'],['balance'])

if __name__=='__main__':unittest.main()
