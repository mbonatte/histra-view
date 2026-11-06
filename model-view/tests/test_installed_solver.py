"""The viewer must use its installed HiStrA-Python distribution."""
from importlib.metadata import distribution
from pathlib import Path
import unittest


class InstalledSolverTests(unittest.TestCase):
    def test_viewer_imports_installed_solver_after_loading_adapters(self):
        import material_preview
        import csharp_results
        import result_preview
        import solver_api
        import histra

        installed = Path(distribution('histra-python').locate_file('histra')).resolve()
        loaded = Path(histra.__file__).resolve().parent
        self.assertEqual(loaded, installed)
        embedded = Path(__file__).resolve().parents[2] / 'histra-python'
        self.assertFalse(loaded.is_relative_to(embedded.resolve()))

    def test_elastic_support_frame_and_restart_safeguards_are_present(self):
        from histra.preprocessing.restraint_support import validate_elastic_restraint_frame
        from histra.model.restraint import Restraint
        from histra.preprocessing.errors import ModelPreparationError
        from histra.solver.restart import restore_committed_analysis_state
        from histra.io.results_reader import ResultsStateError
        from types import SimpleNamespace

        restraint = Restraint(key=1, k=[-1, 100, -1, -1, -1, -1])
        with self.assertRaisesRegex(ModelPreparationError, 'ReferenceSystem'):
            validate_elastic_restraint_frame(restraint)
        model = SimpleNamespace(collections=SimpleNamespace(restraints={1: restraint}))
        with self.assertRaisesRegex(ResultsStateError, 'elastic restraints'):
            restore_committed_analysis_state(model, '/no/such/file', 1, 1, None, None, None)
