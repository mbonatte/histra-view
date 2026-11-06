import base64
import unittest
from pathlib import Path
from lxml import etree
from builder_api import export
from lateral_soil import strip_soil_supports

MODEL = Path(__file__).resolve().parents[2] / 'modal_models/foundation_lateral_Kx_2200000_Ky_4200000.hrx'

@unittest.skipUnless(MODEL.exists(), 'local modal benchmark is not present')
class LateralSoilRegenerationTests(unittest.TestCase):
    def test_mesh_and_arch_edits_keep_soil_moduli_on_new_faces(self):
        source = base64.b64encode(MODEL.read_bytes()).decode()
        changes = [
            {'collection':'wizard_definition','index':0,'node':[], 'attribute':'Nl','value':'150'},
            {'collection':'wizard_span','index':0,'node':[], 'attribute':'HiStrAArchLayers','value':'2'},
        ]
        result = export({'mode':'edit','source':source,'changes':changes,'rebuild_geometry':True})
        root = etree.fromstring(result)
        self.assertEqual(root.find('./WizardData/Span').get('HiStrAArchLayers'), '2')
        settings, targets = strip_soil_supports(root)
        self.assertEqual(settings, {'X': 2.2, 'Y': 4.2})
        self.assertEqual({axis: len(faces) for axis, faces in targets.items()}, {'X': 168, 'Y': 72})
        again = export({'mode':'edit','source':base64.b64encode(result).decode(),'changes':[], 'rebuild_geometry':True})
        checked = etree.fromstring(again)
        self.assertEqual(strip_soil_supports(checked)[0], settings)

    def test_modified_soil_stiffness_is_rejected(self):
        root=etree.parse(str(MODEL)).getroot()
        glr=next(e for e in root.findall('GeometryLineRestraint') if e.get('Name','').startswith('X soil face '))
        glr.set('K2','123')
        with self.assertRaisesRegex(ValueError, 'modified soil stiffness'):
            strip_soil_supports(root)
