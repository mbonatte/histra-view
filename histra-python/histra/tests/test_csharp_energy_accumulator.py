import json
from pathlib import Path
import struct
import unittest
import numpy as np
from histra.solver import hysteretic_runtime as rt


class NativeEnergyAccumulatorTests(unittest.TestCase):
    def test_original_running_total_binary_outputs(self):
        fixture = Path(__file__).with_name("fixtures") / "csharp_energy_accumulator_2026_1_1.json"
        q = np.zeros((3, rt.QUAD_STATE_SIZE))
        q[:,rt.QTSTRESS] = 1.0
        q[:,rt.QTSTRAIN] = 4.0
        for case in json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]:
            with self.subTest(seed=case["seed"]):
                actual = rt._managed_elastic_energy(
                    np.zeros(0),np.zeros((0,9)),np.zeros((0,9)),np.full(3,0.5),q,
                    np.zeros(0,dtype=np.int64),np.zeros(0,dtype=np.int64),
                    np.zeros((0,1)),np.zeros((0,rt.COULOMB_STATE_SIZE)),
                    np.zeros(0,dtype=np.int64),np.zeros(0,dtype=np.int64),np.zeros(0,dtype=np.int64),
                    case["seed"],case["seed"],
                )
                for value,key in zip(actual,("elastic_bits","plastic_bits")):
                    self.assertEqual(struct.unpack("<q",struct.pack("<d",value))[0],int(case[key]))
