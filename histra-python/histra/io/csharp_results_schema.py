"""Native SQLite schema from HiStrA's ModelLibrary/SQLite/Create.sql.

Kept in Python so installed wheels need no proprietary source checkout.
The source fingerprint and native database fixtures bind schema parity tests.
"""

SOURCE_SHA256 = '22da1f13505bffee41c4c7cec1101560e141d142ce370825dc9530f221e291e6'

CREATE_SQL = """--ModalValues
CREATE TABLE IF NOT EXISTS "ModalValues" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "Wn" real NULL,
    "Fn" real NULL,
    "Tn" real NULL,
    "GammaX" real NULL,
    "GammaY" real NULL,
    "GammaZ" real NULL,
    "MassaX" real NULL,
    "MassaY" real NULL,
    "MassaZ" real NULL,
    "MTotX" real NULL,
    "MTotY" real NULL,
    "MTotZ" real NULL,
    "Mx_pcent" real NULL,
    "My_pcent" real NULL,
    "Mz_pcent" real NULL,
    "UMaxX" real NULL,
    "UMaxY" real NULL,
    "UMaxZ" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_ModalValues_AnalysisKey_Combination_Step" ON "ModalValues" ("AnalysisKey","Combination","Step");

--ModalValues
CREATE TABLE IF NOT EXISTS "InverseTriangularValues" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "ParentAnalysisKey" integer NULL,
    "Gamma" real NULL,
    "Massa" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_InverseTriangularValues_AnalysisKey_Combination" ON "InverseTriangularValues" ("AnalysisKey","Combination","Step");


--DisplModelPoints
CREATE TABLE IF NOT EXISTS "DisplModelPoints" (
    "Id" integer primary key NOT NULL,
    "ParentKey" integer NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "IdElement" integer NULL,
    "Ux" real NULL,
    "Uy" real NULL,
    "Uz" real NULL,
    "Vx" real NULL,
    "Vy" real NULL,
    "Vz" real NULL,
    "Ax" real NULL,
    "Ay" real NULL,
    "Az" real NULL,
    "ElementType" text NULL
);
CREATE INDEX IF NOT EXISTS "IX_ModelPoint_Key_Step" ON "DisplModelPoints" ("ParentKey","Step");
CREATE INDEX IF NOT EXISTS "IX_ModelPoint_AnalysisKey_Combination_Step" ON "DisplModelPoints" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_ModelPoint_IdElement_AnalysisKey_Combination_Step" ON "DisplModelPoints" ("IdElement","AnalysisKey","Combination","Step");

--DynamicVectorsState
CREATE TABLE IF NOT EXISTS "DynamicVectorsState" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "Dof" integer NULL,
    "U" real NULL,
    "V" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_DynamicVectorsState_AnalysisKey_Combination_Step" ON "DynamicVectorsState" ("AnalysisKey","Combination","Step");

--InterfaceStates
CREATE TABLE IF NOT EXISTS "InterfaceStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL,
    "U7" real NULL,
    "U8" real NULL,
    "U9" real NULL,
    "U10" real NULL,
    "U11" real NULL,
    "U12" real NULL,
    "ForceX" real NULL,
    "ForceY" real NULL,
    "ForceZ" real NULL,
    "BendingMomentsX" real NULL,
    "BendingMomentsY" real NULL,
    "BendingMomentsZ" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_InterfaceStates_AnalysisKey_Combination_Step" ON "InterfaceStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_InterfaceStates_AnalysisKey_Combination_ParentKey" ON "InterfaceStates" ("AnalysisKey","Combination","ParentKey");


--InterfaceStatesMF
CREATE TABLE IF NOT EXISTS "InterfaceStatesMF" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL,
    "U7" real NULL,
    "U8" real NULL,
    "U9" real NULL,
    "U10" real NULL,
    "U11" real NULL,
    "U12" real NULL,
    "ForceX" real NULL,
    "ForceY" real NULL,
    "ForceZ" real NULL,
    "BendingMomentsX" real NULL,
    "BendingMomentsY" real NULL,
    "BendingMomentsZ" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_InterfaceStatesMF_AnalysisKey_Combination_Step" ON "InterfaceStatesMF" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_InterfaceStatesMF_AnalysisKey_Combination_ParentKey" ON "InterfaceStatesMF" ("AnalysisKey","Combination","ParentKey");

--QuadStates
CREATE TABLE IF NOT EXISTS "QuadStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL,
    "U7" real NULL,
    "K" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_QuadStates_ParentKey" ON "QuadStates" ("AnalysisKey","Combination","ParentKey");
CREATE INDEX IF NOT EXISTS "IX_QuadStates_AnalysisKey_Combination_Step" ON "QuadStates" ("AnalysisKey","Combination","ParentKey");

--NodeCStates
CREATE TABLE IF NOT EXISTS "NodeCStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_NodeCStates_ParentKey" ON "NodeCStates" ("AnalysisKey","Combination","ParentKey");
CREATE INDEX IF NOT EXISTS "IX_NodeCStates_AnalysisKey_Combination_Step" ON "NodeCStates" ("AnalysisKey","Combination","Step");

--ReactionSumStates
CREATE TABLE IF NOT EXISTS "ReactionSumStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "R1" real NULL,
    "R2" real NULL,
    "R3" real NULL,
    "Et" real NULL,
    "Eel" real NULL,
    "Ed" real NULL,
    "Ei" real NULL,
    "Evd" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_ReactionsSum_AnalysisKey_Combination_Step" ON "ReactionSumStates" ("AnalysisKey","Combination","Step");

--RestraintStates
CREATE TABLE IF NOT EXISTS "RestraintStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_RestraintStates_AnalysisKey_Combination_ParentKey" ON "RestraintStates" ("AnalysisKey","Combination","ParentKey");
CREATE INDEX IF NOT EXISTS "IX_RestraintStates_AnalysisKey_Combination_Step" ON "RestraintStates" ("AnalysisKey","Combination","Step");

--SpringStatesTmp
CREATE TABLE IF NOT EXISTS "SpringStatesTmp" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "ParentType" integer NULL,
    "SpringPurpose" integer NULL,
    "SpringType" integer NULL,
    "IdLocal" integer NULL,
    "U" real NULL,
    "F" real NULL,
    "Phase" real NULL,
    "Fy1" real NULL,
    "Fy2" real NULL,
    "Up1" real NULL,
    "Up2" real NULL,
    "N" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_SpringStatesTmp_AnalysisKey_Combination_Step" ON "SpringStatesTmp" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_SpringStatesTmp_AnalysisKey_Combination_ParentKey" ON "SpringStatesTmp" ("AnalysisKey","Combination","ParentKey");

--SpringStates
CREATE TABLE IF NOT EXISTS "SpringStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "ParentType" integer NULL,
    "SpringPurpose" integer NULL,
    "SpringType" integer NULL,
    "IdLocal" integer NULL,
    "U" real NULL,
    "F" real NULL,
    "K_tang" real NULL,
    "Fy1" real NULL,
    "Fy2" real NULL,
    "Phase" real NULL,
    "Up1" real NULL,
    "Up2" real NULL,
    "Uy1" real NULL,
    "Uy2" real NULL,
    "Umax1" real NULL,
    "Umax2" real NULL,
    "Uu1" real NULL,
    "Uu2" real NULL,
    "N" real NULL,
    "E" real NULL,
    "Ed" real NULL,
    "Eel" real NULL,
    "LoadIndicator" integer NULL,
    "ContactArea" real NULL,
    "F0" real NULL,
    "CmomMin" real NULL,
    "CmomMax" real NULL,
    "CrotLimNu" real NULL,
    "CrotLimPu" real NULL,
    "CrotYn" real NULL,
    "CrotYp" real NULL,
    "CPhaseUnload_t" integer NULL,
    "CPhaseUnload_c" integer NULL,
    "TangentReload_c" real NULL,
    "TangentReload_t" real NULL,
    "CplasticTensionIndicator" logical NULL,
    "CplasticCompressionIndicator" logical NULL
);
CREATE INDEX IF NOT EXISTS "IX_SpringStates_AnalysisKey_Combination_ParentKey" ON "SpringStates" ("AnalysisKey","Combination","ParentKey");
CREATE INDEX IF NOT EXISTS "IX_SpringStates_AnalysisKey_Combination_Step" ON "SpringStates" ("AnalysisKey","Combination","Step");

--ModalShapeValues
CREATE TABLE IF NOT EXISTS "ModalShapeValues" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "Dof" real NULL,
    "Val" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_ModalShapeValues_AnalysisKey_Combination_Step" ON "ModalShapeValues" ("AnalysisKey","Combination","Step");

--TrussStates
CREATE TABLE IF NOT EXISTS "TrussStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "K" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_TrussStates_AnalysisKey_Combination_Step" ON "TrussStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_TrussStates_AnalysisKey_Combination_ParentKey" ON "TrussStates" ("AnalysisKey","Combination","ParentKey");

--VertexStates
CREATE TABLE IF NOT EXISTS "VertexStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_VertexStates_AnalysisKey_Combination_Step" ON "VertexStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_VertexStates_AnalysisKey_Combination_ParentKey" ON "VertexStates" ("AnalysisKey","Combination","ParentKey");

--FiberStates
CREATE TABLE IF NOT EXISTS "FiberStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_FiberStates_AnalysisKey_Combination_Step" ON "FiberStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_FiberStates_AnalysisKey_Combination_ParentKey" ON "FiberStates" ("AnalysisKey","Combination","ParentKey");

--FrameStates
CREATE TABLE IF NOT EXISTS "FrameStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL,
    "U7" real NULL,
    "U8" real NULL,
    "U9" real NULL,
    "U10" real NULL,
    "U11" real NULL,
    "U12" real NULL,
    "F1" real NULL,
    "F2" real NULL,
    "F3" real NULL,
    "F4" real NULL,
    "F5" real NULL,
    "F6" real NULL,
    "F7" real NULL,
    "F8" real NULL,
    "F9" real NULL,
    "F10" real NULL,
    "F11" real NULL,
    "F12" real NULL,
    "Fq1" real NULL,
    "Fq2" real NULL,
    "Fq3" real NULL,
    "Fq4" real NULL,
    "Fq5" real NULL,
    "Fq6" real NULL,
    "Fq7" real NULL,
    "Fq8" real NULL,
    "Fq9" real NULL,
    "Fq10" real NULL,
    "Fq11" real NULL,
    "Fq12" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_FrameStates_AnalysisKey_Combination_Step" ON "FrameStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_FrameStates_AnalysisKey_Combination_ParentKey" ON "FrameStates" ("AnalysisKey","Combination","ParentKey");

--FrameSectionStates
CREATE TABLE IF NOT EXISTS "FrameSectionStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "ParentType" int NULL,
    "Deformations1" real NULL,
    "Deformations2" real NULL,
    "Deformations3" real NULL,
    "Deformations4" real NULL,
    "Deformations5" real NULL,
    "Deformations6" real NULL,
    "Forces1" real NULL,
    "Forces2" real NULL,
    "Forces3" real NULL,
    "Forces4" real NULL,
    "Forces5" real NULL,
    "Forces6" real NULL,
    "Displacements1" real NULL,
    "Displacements2" real NULL,
    "Displacements3" real NULL,
    "Displacements4" real NULL,
    "Displacements5" real NULL,
    "Displacements6" real NULL,
    "Rotations1" real NULL,
    "Rotations2" real NULL,
    "Rotations3" real NULL,
    "Rotations4" real NULL,
    "Rotations5" real NULL,
    "Rotations6" real NULL,
    "BetaX" real NULL,
    "BetaY" real NULL,
    "BetaZ" real NULL,
    "BetaT" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_FrameSectionStates_AnalysisKey_Combination_Step" ON "FrameSectionStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_FrameSectionStates_AnalysisKey_Combination_ParentKey" ON "FrameSectionStates" ("AnalysisKey","Combination","ParentKey");

--SolidStates
CREATE TABLE IF NOT EXISTS "SolidStates" (
    "Id" integer primary key NOT NULL,
    "AnalysisKey" integer NULL,
    "Combination" integer NULL,
    "Step" integer NULL,
    "ParentKey" integer NULL,
    "U1" real NULL,
    "U2" real NULL,
    "U3" real NULL,
    "U4" real NULL,
    "U5" real NULL,
    "U6" real NULL
);
CREATE INDEX IF NOT EXISTS "IX_SolidStates_AnalysisKey_Combination_Step" ON "SolidStates" ("AnalysisKey","Combination","Step");
CREATE INDEX IF NOT EXISTS "IX_SolidStates_AnalysisKey_Combination_ParentKey" ON "SolidStates" ("AnalysisKey","Combination","ParentKey");



"""
