"""Golden trial traces executed from the actual 2026.1.1 C# search classes."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from histra.solver.line_search import RegulaFalsiLineSearch
from histra.types.linear_system import LinearSystem


class TestCSharpRegulaFalsiTraces(unittest.TestCase):
    def test_trial_state_increment_and_failures_match_csharp(self):
        fixture=Path(__file__).parent/"fixtures/regula-falsi-csharp-2026.1.1.json"
        cases=json.loads(fixture.read_text(encoding="utf-8-sig"))["cases"]
        for case in cases:
            with self.subTest(algorithm=case["Algorithm"],case=case["Case"]):
                system=LinearSystem(1,backend="superlu")
                system.x[:]=case["Direction"]
                program=SimpleNamespace(ls=system)
                class Integrator:
                    def __init__(self):
                        self.position=case["Direction"]
                        self.corrections=[]
                        self.index=0
                    def update(self,model,p,analysis):
                        self.corrections.append(float(p.ls.x[0]))
                        if case["Failure"]<0:
                            return case["Failure"]
                        self.position+=float(p.ls.x[0])
                        return 0
                    def form_unbalance(self,p,model,analysis):
                        residuals=case["Residuals"]
                        p.ls.b[:]=residuals[min(self.index,len(residuals)-1)]
                        self.index+=1
                integrator=Integrator()
                search=RegulaFalsiLineSearch()
                search.tolerance=case["Tolerance"]
                search.min_eta=case["MinEta"]
                search.max_eta=case["MaxEta"]
                search.max_iter=case["MaxIterations"]
                # A constrained integrator can change LS.x after the raw
                # Newton direction was saved. C# reads the current LS.x.
                search.new_step(program,system)
                result=search.search(None,program,system,integrator,None,np.array([1.0]),case["S0"],case["S1"])
                self.assertEqual(integrator.corrections,case["Corrections"])
                self.assertEqual(integrator.position,case["FinalPosition"])
                self.assertEqual(float(system.x[0]),case["FinalIncrement"])
                if case["ReturnCode"]<0:
                    self.assertEqual(result,case["ReturnCode"])
                else:
                    self.assertGreaterEqual(result,0.0)
