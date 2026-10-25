"""Original LoadTemplateItem.Dir switches and XML direction selection."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from histra.io.hr_loader import load_model
from histra.model.load import LoadTemplateItem


class NativeLoadDirectionTests(unittest.TestCase):
    def test_all_original_direction_codes_and_single_normalization(self):
        data = json.loads((Path(__file__).parent/'fixtures/csharp_load_direction_2026_1_1.json').read_text(encoding='utf-8-sig'))
        for case in data['cases']:
            with self.subTest(direction=case['direction'],axes=case['axes']):
                element = SimpleNamespace(**dict(zip(('reference_e1','reference_e2','reference_e3'),case['axes'])))
                item = LoadTemplateItem(load_direction=case['direction'],dir_x=case['custom'][0],dir_y=case['custom'][1],dir_z=case['custom'][2])
                expected = np.array([int(v) for v in case['expected_bits']],dtype=np.int64).view(np.float64)
                np.testing.assert_array_equal(item.direction_for(element),expected)

    def test_xml_code_overrides_stale_stored_vector(self):
        # The horizontal reference has precisely this stale -Z vector with
        # IdLoadDirection=2. C# resolves the selected code to global +Y.
        xml = '<HiStrA><LoadTemplateItem Key="1" IdLoadTemplate="1" IdLoadDirection="2" DirX="0" DirY="0" DirZ="-1"/><LoadTemplateItem Key="2" IdLoadTemplate="2" DirX="1" DirY="0" DirZ="0"/><Template Key="1" PurposeType="LineLoad"/><Template Key="2" PurposeType="LineLoad"/></HiStrA>'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'direction.hrx';path.write_text(xml)
            model=load_model(path)
        first=model.collections.load_templates[1].items[0]
        self.assertEqual(first.direction,(0.,0.,-1.))
        self.assertEqual(first.direction_for(None),(0.,1.,0.))
        self.assertEqual(model.collections.load_templates[2].items[0].direction_for(None),(0.,0.,-1.))

    def test_invalid_direction_and_missing_local_axes_fail_explicitly(self):
        for item in [LoadTemplateItem(load_direction=8),LoadTemplateItem(load_direction=7),LoadTemplateItem(load_direction=4)]:
            with self.assertRaises(ValueError):
                item.direction_for(None)
