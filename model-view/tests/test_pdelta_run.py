import unittest
from types import SimpleNamespace
from lxml import etree
from solver_api import _apply_pdelta_effect, start_job


class PdeltaRunTests(unittest.TestCase):
    def test_static_chain_override_is_recorded_without_changing_modal(self):
        source = b'<Model><Analysis Key="1" PdeltaEffect="None"/><Analysis Key="2" PdeltaEffect="None"/><Analysis Key="3" PdeltaEffect="None"/></Model>'
        chain = [SimpleNamespace(key=1, analysis_type=1, pdelta_effect='None'),
                 SimpleNamespace(key=2, analysis_type=1, pdelta_effect='None'),
                 SimpleNamespace(key=3, analysis_type=5, pdelta_effect='None')]
        result = etree.fromstring(_apply_pdelta_effect(source, chain, 'EachStep'))
        self.assertEqual([e.get('PdeltaEffect') for e in result], ['EachStep', 'EachStep', 'None'])
        self.assertEqual([a.pdelta_effect for a in chain], ['EachStep', 'EachStep', 'None'])
        self.assertIn(b'PdeltaEffect="None"', source)

    def test_invalid_setting_rejected(self):
        with self.assertRaisesRegex(ValueError, 'P-Delta'):
            start_job(b'<Model/>', 'x', 1, pdelta_effect='bad')
