"""Modal HRX defaults taken from Analysis.cs in C# 2026.1.1."""
import tempfile
import unittest
from pathlib import Path
from histra.io.hr_loader import load_model
from histra.model.load import Analysis

class TestModal2026Configuration(unittest.TestCase):
    def load_analysis(self, attributes=""):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "modal.hrx"
            path.write_text(f'<HiStrA><Analysis Key="30" AnalysisType="5" {attributes}/></HiStrA>', encoding="utf-8")
            return load_model(path).collections.analyses[30]

    def test_new_analysis_uses_csharp_defaults(self):
        analysis = Analysis(key=30, analysis_type=5)
        self.assertEqual(analysis.modal_procedure, "InverseIterations")
        self.assertEqual(analysis.residual_vector_tolerance, 0.5)

    def test_omitted_hrx_fields_use_csharp_defaults(self):
        analysis = self.load_analysis()
        self.assertEqual(analysis.modal_procedure, "InverseIterations")
        self.assertEqual(analysis.residual_vector_tolerance, 0.5)

    def test_explicit_old_procedure_and_new_residual_tolerance_are_preserved(self):
        analysis = self.load_analysis('ModalProcedure="SubspaceIterations" ResidualVectorTolerance="0.0025"')
        self.assertEqual(analysis.modal_procedure, "SubspaceIterations")
        self.assertEqual(analysis.residual_vector_tolerance, 0.0025)

    def test_nonpositive_tolerance_is_preserved_for_csharp_solver_defaulting(self):
        analysis = self.load_analysis('ResidualVectorTolerance="0"')
        self.assertEqual(analysis.residual_vector_tolerance, 0.0)
