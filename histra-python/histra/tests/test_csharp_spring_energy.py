"""Native C# energy oracle, including compression and unloading."""
import json
from pathlib import Path
import unittest
import numpy as np
from histra.springs.energy import spring_energy_increment
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.elastic import SpringElastic
from histra.springs.coulomb03 import SpringCoulomb03
from histra.solver import hysteretic_runtime as rt

class TestOriginalCSharpSpringEnergy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=json.loads((Path(__file__).parent/'fixtures/csharp_spring_energy_2026_1_1.json').read_text())['cases']

    def test_compiled_increment_equals_original_csharp(self):
        for index,c in enumerate(self.cases):
            with self.subTest(case=index):
                actual=spring_energy_increment(c['K'],c['CommitStress'],c['TrialStress'],c['CommitStrain'],c['TrialStrain'])
                self.assertEqual(actual,(c['Elastic'],c['Plastic'],c['Total']))

    def test_all_masonry_spring_objects_equal_original_csharp(self):
        for cls in (SpringElastic,SpringHysteretic,SpringCoulomb03):
            for index,c in enumerate(self.cases):
                with self.subTest(spring=cls.__name__,case=index):
                    s=cls(k=c['K']);s._cstress=c['CommitStress'];s._tstress=c['TrialStress']
                    s._cstrain=c['CommitStrain'];s._tstrain=c['TrialStrain']
                    self.assertEqual(s.compute_energy(),(c['Elastic'],c['Plastic'],c['Total']))

    def test_dense_accumulator_includes_quad_and_every_interface_group(self):
        case_ids=[0,1,2,3,4,5]
        q=np.zeros((1,rt.QUAD_STATE_SIZE));committed=np.zeros((2,9));trial=np.zeros((2,9))
        coulomb=np.zeros((3,rt.COULOMB_STATE_SIZE));params=np.ones((3,1))*100.
        for position,index in enumerate(case_ids):
            c=self.cases[index]
            if position==0:
                q[0,rt.QCSTRESS]=c['CommitStress'];q[0,rt.QTSTRESS]=c['TrialStress']
                q[0,rt.QCSTRAIN]=c['CommitStrain'];q[0,rt.QTSTRAIN]=c['TrialStrain']
            elif position<3:
                committed[position-1,6:8]=[c['CommitStress'],c['CommitStrain']]
                trial[position-1,6:8]=[c['TrialStress'],c['TrialStrain']]
            else:
                coulomb[position-3,rt.CCSTRESS]=c['CommitStress'];coulomb[position-3,rt.CTSTRESS]=c['TrialStress']
                coulomb[position-3,rt.CCSTRAIN]=c['CommitStrain'];coulomb[position-3,rt.CTSTRAIN]=c['TrialStrain']
        actual=rt._managed_elastic_energy(np.array([100.,100.]),committed,trial,np.array([100.]),q,
                     np.array([0]),np.array([2]),params,coulomb,np.array([0]),np.array([1]),np.array([2]))
        self.assertEqual(actual,(sum(self.cases[i]['Elastic'] for i in case_ids),sum(self.cases[i]['Plastic'] for i in case_ids)))

if __name__=='__main__':unittest.main()
