import unittest

from hrx_model import parse_hrx


SOURCE = b"""<HiStrA version="2026.1.0">
  <Template Key="18" Name="Masonry" TypeOf="HiStrA.Objects.MasonryMaterial" Color="#CC9966"/>
  <Node Key="1" Point="0;0;0"/>
  <Node Key="2" Point="10;0;0"/>
  <Node Key="3" Point="10;0;10"/>
  <Node Key="4" Point="0;0;10"/>
  <Quad Key="1" NodeKey1="1" NodeKey2="2" NodeKey3="3" NodeKey4="4" MaterialKey="18"/>
  <ModelPoint Key="1" Name="Crown" ElementType="Node" ElementKey="1" Point="0;0;10"/>
  <ModelPoint Key="2" Description="SpanQuarter" ElementType="Quad" ElementKey="1" IdVertex="4" Point="10;0;10"/>
  <LoadCondition Id="1" Name="G1" GammaUnfavSTR="1.35" GammaFavSTR="1.0"/>
  <LoadCondition Id="2" Name="Q" GammaUnfavSTR="1.5"/>
  <LoadCombination Key="6" Name="SEISMIC" LimitState="Seismic" Description="Seismic combo">
    <Item LoadCombinationKey="6" ColumnKey="1" RowKey="1" Name="1" Schema="NoSchema" Position="0" Combination="1" TypeData="GammaUnfavSTR" SecondaryTypeData="Number" Val="1"/>
    <Item LoadCombinationKey="6" ColumnKey="2" RowKey="1" Name="1" Schema="NoSchema" Position="0" Combination="1" TypeData="Psi0" SecondaryTypeData="Number" Val="0.6"/>
  </LoadCombination>
  <LoadFunction key="1" typeDiscr="false" DiscrVal="0.2"/>
  <LoadFunctionItem key="1" loadFunctionKey="1" pseudoTime="0" multiplier="0"/>
  <LoadFunctionItem key="2" loadFunctionKey="1" pseudoTime="1" multiplier="1"/>
  <Analysis Key="1" Name="Vert" AnalysisType="2" Description="Base analysis"
            InitialAnalysisKey="-100" LoadCombinationKey="6" LoadFunctionKey="1"
            MasterPoint="1" Mult="1" AdapticConvergenceCriteria="ForceMoment"
            Method="StandardSecantLineSearch" Dr2="0.25" DirX="1" DirY="0" DirZ="0">
    <States>
      <State Id="1" Key="1" Combination="1" Step="5" State="ExecutedCompleted"
             Fo="214.7" Exit="Converged" ExitDescription="5 steps converged"/>
    </States>
    <ActiveModelPoints><ActiveModelPoint Key="1" Value="true"/><ActiveModelPoint Key="2" Value="false"/></ActiveModelPoints>
    <DisplModelPoints><DisplModelPoint Key="1" Value="0"/><DisplModelPoint Key="2" Value="1.5"/></DisplModelPoints>
  </Analysis>
  <Analysis Key="2" Name="Modal_0" AnalysisType="5" Description="Modal analysis"
            InitialAnalysisKey="1" LoadCombinationKey="6" LoadFunctionKey="1"
            MasterPoint="-10" PushModal_ModalAnalysisKey="1">
    <States><State Key="2" Step="0" State="NotExecutedNotToBeExecuted" Exit="NotExecuted"/></States>
    <ActiveModelPoints/><DisplModelPoints/>
  </Analysis>
</HiStrA>"""


class AnalysisProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = parse_hrx(SOURCE, "analyses.hrx")
        cls.vert = cls.model["analyses"][0]
        cls.modal = cls.model["analyses"][1]

    def test_analyses_are_projected_with_type_and_labels(self):
        self.assertEqual([analysis["name"] for analysis in self.model["analyses"]],
                         ["Vert", "Modal_0"])
        self.assertEqual(self.vert["type"], "Static nonlinear")
        self.assertEqual(self.modal["type"], "Modal")
        self.assertEqual(self.vert["loadCombinationName"], "SEISMIC")
        self.assertEqual(self.vert["loadFunctionDiscr"], "0.2")
        self.assertEqual(self.vert["masterPointName"], "Crown")
        self.assertEqual(self.modal["masterPointName"], "MaxDisplacement")

    def test_saved_state_is_preserved(self):
        self.assertEqual(self.vert["state"]["State"], "ExecutedCompleted")
        self.assertEqual(self.vert["state"]["Step"], "5")
        self.assertEqual(self.vert["state"]["Fo"], "214.7")
        self.assertEqual(self.vert["state"]["ExitDescription"], "5 steps converged")
        self.assertTrue(self.vert["isExecuted"])
        self.assertEqual(self.modal["state"]["State"], "NotExecutedNotToBeExecuted")
        self.assertFalse(self.modal["isExecuted"])
        self.assertNotIn("ExitDescription", self.modal["state"])

    def test_model_point_lists_are_projected(self):
        self.assertEqual(self.vert["activeModelPoints"],
                         [{"Key": "1", "Value": "true"}, {"Key": "2", "Value": "false"}])
        self.assertEqual(self.vert["displacementModelPoints"],
                         [{"Key": "1", "Value": "0"}, {"Key": "2", "Value": "1.5"}])
        self.assertEqual(self.model["modelPoints"][0]["name"], "Crown")
        self.assertEqual(self.model["modelPoints"][0]["elementLabel"], "Node (1)")
        self.assertEqual(self.model["modelPoints"][0]["positionLabel"], "Node")
        self.assertEqual(self.model["modelPoints"][1]["description"], "SpanQuarter")
        self.assertEqual(self.model["modelPoints"][1]["elementLabel"], "Quad (1)")
        self.assertEqual(self.model["modelPoints"][1]["positionLabel"], "Node4")
        self.assertTrue(self.vert["modelPoints"][0]["isMaster"])
        self.assertEqual(self.vert["modelPoints"][1]["displacement"], "1.5")

    def test_initial_analysis_reference_is_named(self):
        self.assertEqual(self.modal["initialAnalysisKey"], "1")
        self.assertEqual(self.modal["initialAnalysisName"], "Vert")
        self.assertEqual(self.modal["pushModalAnalysisName"], "Vert")

    def test_load_functions_and_combinations_are_projected(self):
        fn = self.vert["loadFunction"]
        self.assertEqual(fn["key"], "1")
        self.assertEqual(fn["typeDiscr"], "false")
        self.assertEqual(fn["discrVal"], "0.2")
        self.assertEqual([(i["pseudoTime"], i["multiplier"]) for i in fn["items"]],
                         [("0", "0"), ("1", "1")])
        combo = self.vert["loadCombination"]
        self.assertEqual(combo["name"], "SEISMIC")
        self.assertEqual(len(combo["subCombinations"]), 1)
        items = combo["subCombinations"][0]["items"]
        self.assertEqual(items[0]["conditionName"], "G1")
        self.assertEqual(items[0]["coefficient"], "GammaUnfavSTR")
        self.assertEqual(items[0]["value"], "1.35")
        self.assertEqual(items[1]["conditionName"], "Q")
        self.assertEqual(items[1]["coefficient"], "Psi0")
        self.assertEqual(items[1]["value"], "0.6")


if __name__ == "__main__":
    unittest.main()
