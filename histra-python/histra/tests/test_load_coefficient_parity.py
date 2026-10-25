"""C# LoadTemplateManager DBNull-cell and absent-row behavior."""
import unittest
from types import SimpleNamespace
from histra.model.load import Analysis,LoadCombination,LoadCombinationItem,LoadCondition
from histra.solver.assembler import _get_load_template_coefficient

class TestMissingCombinationCoefficient(unittest.TestCase):
    def setUp(self):
        self.table=LoadCombination(key=15,items=[LoadCombinationItem(row_key=1,column_key=1,val=0.25)])
        self.model=SimpleNamespace(collections=SimpleNamespace(
            analyses={22:Analysis(key=22,load_combination_key=15)},
            load_combinations={15:self.table},
            load_conditions={1:LoadCondition(id=1),11:LoadCondition(id=11)}))

    def test_empty_cell_in_existing_row_contributes_zero(self):
        self.assertEqual(_get_load_template_coefficient(self.model,22,1,11),0.0)

    def test_present_cell_retains_its_coefficient(self):
        self.assertEqual(_get_load_template_coefficient(self.model,22,1,1),0.25)

    def test_missing_row_is_not_silently_converted_to_zero(self):
        with self.assertRaisesRegex(KeyError,"has no row 2"):
            _get_load_template_coefficient(self.model,22,2,11)

    def test_missing_condition_is_still_rejected(self):
        with self.assertRaisesRegex(KeyError,"Load condition 99 is missing"):
            _get_load_template_coefficient(self.model,22,1,99)
