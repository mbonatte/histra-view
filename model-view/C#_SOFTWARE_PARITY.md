# C# software parity review — `model_mesh_complete` benchmark

This note records what is in the new `C#_Software_View` folder, what the native
HiStrA Bridges UI exposes, which fields matter, how the benchmark behaves, and
what was implemented in HiStrA View as a result.

Sources:

- `C#_Software_View/model_mesh_complete/model_mesh_complete.hrx` — native C#
  model, version `2026.1.1`, `WizardType="RailBridge"`.
- `model_mesh_complete.hrb` / `.hrbk` — same model in the native binary
  container (4-byte magic `da 73 21 77` followed by a gzip stream; 571,918
  bytes on disk, 5,360,993 bytes decompressed).
- `C#_Software_View/images/` — 22 screenshots of the C# wizard, material
  editor, vehicle/schema editors, analysis dialogs, results menus and
  configuration dialogs.
- `C#_Original/source/...` — local decompiled reference used to answer the
  behavioural questions. It is not tracked in Git.

---

## 1. Benchmark model inventory

### 1.1 Global data

| Item | Value |
|---|---|
| HiStrA version | `2026.1.1` |
| Wizard type | `RailBridge` |
| Units | native HRX units; this model is cm / kN / kN·cm |
| Deck length `Bridge.L` | 4270 cm |
| Deck width `Bridge.B` | 530 cm |
| Bridge height `Bridge.H` | 490 cm |
| Bounds | X `-99.95 … 4322.90`, Y `-350.0 … 345.0`, Z `-873.62 … 626.26` cm |
| Nodes | 3235 |
| Quads | 2529 |
| Vertex triangles | 20 (not drawn by the current viewer) |
| Geometry-line restraints (GLR) | 160 |
| Restraints | 315 |
| Surface restraints | 11 |
| NodeC | 355 |
| Arch-ring quads (`Bridge/QuadSpanKeys`) | 230 |
| Materials | 8 masonry + 9 other library materials |
| Analyses | 21 |
| Load conditions | 7 |
| Load combinations | 11 |
| Load functions | 21 |
| Load templates | 34 (17 line loads, 15 vehicles, 2 schemas) |

The model is deliberately irregular. It is a four-span masonry rail bridge
with a 10° skew, a 2 % longitudinal grade, pier caps wider than the deck, and
four different arch geometries, including a very tall narrow arch.

### 1.2 Bridge definition (C# Geometry → General)

| Field | Value | Why it matters |
|---|---:|---|
| `Width` | 530 | Total deck width. Sum of the five `Corsia` widths. |
| `WidthTopPile` | 600 | Width at impost/cap level. When it differs from `Width`, the C# mesher widens the two edge strips and intersects their top nodes with the inclined plane. |
| `IsWidthTopPileCustom` | true | Uses the custom 600 cm impost width. |
| `Nl` | 100 | Maximum mesh length for the bridge, wall and arch meshers. |
| `Nt` | 20000 | Maximum mesh thickness parameter. |
| `InclinationAngle` | 10° | Skew. C# shifts X by `Y·tan(angle)` and multiplies strip thickness by `1/cos(angle)`. |
| `Slope` | 0.02 | 2 % grade. C# adds `X·slope` to Z after meshing. |
| `Zlevel` | 500 | Deck level used by the wizard. |
| `VehicleLoadName` | `LineLoad-E5` | Train/line-load model selected for the load schema. |
| `IsVehicleLoad` | false | No moving-vehicle load generation is requested; the schema uses a line load. |
| `NumVehicles` | 1 | One train/vehicle. |
| `DynamicCoefficientProcedure` | `RealDynamicCoefficient` | Dynamic amplification procedure. |
| `Velocity` | 2777.778 | Vehicle speed used by the dynamic procedure. |

### 1.3 Cross-section lanes (`Corsia`)

| # | Name | Width (cm) | Wall height (cm) | Material | Train load |
|---:|---|---:|---:|---|---|
| 1 | Left spandrel wall | 40 | 50 | Ballast (#21) | no |
| 2 | Unloaded area 1 | 150 | 0 | none (0) | no |
| 3 | Binary 1 | 150 | 0 | none (0) | yes (`AllowVehicle=true`) |
| 4 | Unloaded area 2 | 150 | 0 | none (0) | no |
| 5 | Right spandrel wall | 40 | 50 | Ballast (#21) | no |

The two edge lanes have a positive wall height, so the C# mesher builds the
fourth elevation layer (spandrel wall) for them.

### 1.4 Supports and spans

| Element | Key dimensions (cm) | Material |
|---|---|---|
| Left abutment AB1 | `H=500`, `Hf=100`, `b1=20`, `b2=400`, `b3=20`, `w1=20`, `w2=600`, `w3=20`, `B1f=20`, `B3f=20`, `W1f=20`, `W3f=20`, alignment Center, `Hsp1=990`, `Hsp2=400` | Piers (#17), foundation #1 |
| Pier P1 | `H=800`, `Hf=100`, `b1=10`, `b2=270`, `b3=10`, `w1=10`, `w2=650`, `w3=10`, `B1f=10`, `B3f=10`, `W1f=10`, `W3f=10`, alignment Center, `Hsp1=Hsp2=150` | Piers (#17), foundation #1 |
| Span S1 | `L=1000`, `f=300`, `Circolare=true`, `Asx=Adx=28.57434°`, `Tb=Tt=100`, `S2=10` | Arches (#18), pulvino #22 |
| Pier P2 | `H=500`, `Hf=0`, `b2=250`, `w2=600`, alignment Bottom | Piers (#17) |
| Span S2 | `L=800`, `f=200`, `Circolare=false`, `Asx=Adx=15°`, `Tb=100`, `Tt=50` | Arches (#18) |
| Pier P3 | `H=500`, `Hf=0`, `b2=250`, `w2=600`, alignment Bottom | Piers (#17) |
| Span S3 | `L=200`, `f=350`, `Circolare=true`, `Asx=Adx=0°`, `Tb=Tt=100` | Arches (#18) |
| Span S4 | `L=600`, `f=50`, `Circolare=false`, `Asx=Adx=0°`, `Tb=Tt=100` | Arches (#18) |
| Right abutment AB2 | `H=500`, `Hf=0`, `b2=500`, `w2=650`, alignment Top, `Hsp2=990` | Piers (#17) |

`S1` is the left springing setback and `S2` the right one. The C# arch block
uses `Adx` for both halves; `Asx` is stored and used by the UI/report.

### 1.5 Backfill and elevation layers

| Elevation field | Value |
|---|---:|
| `H1` | 200 cm |
| `H2` | 210 cm |
| `H3` | 80 cm |
| `IsStratigraphyVariable` | false |

| Layer | Material 1 | Material 2 | Uniform | Rows for material 1 | Generate elements |
|---|---|---|---:|---:|---|
| 1 | Backfill (#19) | Fill (#20) | false | 1 | true |
| 2 | Fill (#20) | Concrete Vault (#24) | false | 1 | true |
| 3 | Ballast (#21) | Ballast (#21) | true | 1 | true |

### 1.6 Masonry materials

The eight `PurposeType="MasonryMaterial"` templates are exactly the eight
materials shown in the C# Masonry Materials library.

Values below are shown in the C# display units (kN/m² and kN/m³). The HRX
stores the same quantities in native kN/cm² and kN/cm³; multiply the HRX
`Ehor`/`FmHor`/`FtmHor`/`fvk0d`/`Gd` values by 10,000 and the `w` value by
1,000,000 to obtain the display values.

| Key | Name | E (kN/m²) | fm (kN/m²) | ft (kN/m²) | τ0 (kN/m²) | G (kN/m²) | Unit weight (kN/m³) | Shear law | Sliding check contact area |
|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | Foundations | 1,250,000 | 3,000 | 100 | 75 | 416,666.7 | 18 | Elasto-plastic ductility fixed | false |
| 17 | Piers | 1,250,000 | 3,000 | 100 | 75 | 416,666.7 | 18 | Elasto-plastic ductility fixed | false |
| 18 | Arches | 1,250,000 | 3,000 | 100 | 75 | 416,666.7 | 18 | Elasto-plastic ductility fixed | **true** |
| 19 | Backfill | 300,000 | 500 | 25 | 31.11 | 115,000 | 18 | Elastic | false |
| 20 | Fill | 300,000 | 500 | 25 | 18 | 115,000 | 19 | Elastic | false |
| 21 | Ballast | 300,000 | 200 | 10 | 15 | 115,000 | 19 | Elastic | false |
| 22 | Pier cap | 1,250,000 | 3,000 | 100 | 75 | 416,666.7 | 18 | Elasto-plastic ductility fixed | false |
| 24 | Concrete Vault | 6,474,286 | 11,330 | 566.5 | 15 | 2,697,619 | 25 | Elastic | false |

The screenshot of material “Arches” is the benchmark’s material #18. Its
Advanced → Sliding tab has **Check contact area for the evaluation of the shear
strength** enabled, cohesion 74.99999 kN/m², friction 0.6 and plastic stiffness
ratio 0. The screenshot’s E = 1,250,000 kN/m², ft = 100 kN/m²,
σc = 3,000 kN/m² and G = 416,666.7 kN/m² are the same values in display units.

### 1.7 Loads and schemas

Load conditions: Gravity (G1), Variable (Qk), Vehicle (Qk), Lateral Earth
Pressure (G2), Swaying action, Breaking action, Centrifugal forces.

Load combinations: `SLU.STR`, `SLU.GEO`, `SLE.Rare`, `SLE.Frequent`,
`SLE.Quasi permanent`, plus the generated base/derived combinations used by the
21 analyses.

Templates:

- 17 `LineLoad` templates, including `LineLoad-E5` (key 131, one 0.88 kN/cm
  line load, ψ0=ψ1=0.8, ψ2=0).
- 15 `VehicleLoad` templates, including `LM71` (key 100, 24 axle rows) and
  `ZeroLoadVehicle` (key 132, used only to position a line/area load on a lane).
- 2 `Schema` templates: `Schema-LineLoad-E5-Case1` and `…Case2`. Each has 10
  positions and 5 lane paths. The loaded lane is `Binary 1`; the line load is
  `LineLoad-E5` and the vehicle is `ZeroLoadVehicle`, with
  `excludeLineLoadInVehicleArea=true`.

The vehicle editor columns shown in the screenshot are exactly the
`LoadTemplateItem` attributes: Name, Load condition, Direction, X, Y, Length,
Width, Load value, ψ0, ψ1, ψ2. The template header adds Name, Description,
`D1…D4` and the dynamic coefficient.

### 1.8 Analyses

The 21 analyses are: `Vert`, `SLE Rare Base`, `SLE Frequent Base`,
`SLE Quasi permanent Base`, `SLE Rare`, `SLE Frequent`, `SLE Quasi permanent`,
`SLU.STR Base`, `SLU.STR`, `SLU.STR COLLAPSE`, `SLU.GEO Base`, `SLU.GEO`,
four `Pushover ±X/±Y Massa`, four `Pushover ±X/±Y Modal`, and `Modal`.

All static nonlinear analyses use `AnalysisType=2`, `IntegrationMethod=LoadControl`,
`Method=ModifiedRegulaFalsiLineSearch`, `MaxIterations=1000`,
`ConvergenceTolerance=0.0001`, `AdapticConvergenceCriteria=Work`, and the
native load function / load combination references. The screenshot analysis
“SLE Quasi permanent Base” is analysis key 4.

---

## 2. What the C# UI looks like and which fields matter

### 2.1 Geometry wizard

The wizard is a top-level tab strip: **Geometry | Material | Loads | Schema |
Analysis**. Geometry has sub-tabs: **General**, **Left abutment:AB1**,
**Span 1:S1**, **Pier 1:P1**, **Span 2:S2**, **Pier 2:P2**, **Span 3:S3**,
**Pier 3:P3**, **Span 4:S4**, **Right abutment:AB2**, **Backfill**, **Trunks**.

**General** is the cross-section table plus global mesh/geometry fields:

- Table: Id, Name, Description, Lane width, Wall height, Wall material, Train load.
- Below the table: Max mesh length, inclination angle of abutments/piers,
  slope of the bridge, width of the bridge, and “Width of the bridge at impost
  level of the arches” (checkbox + value).
- Right side: type of load and “Apply as” (line load).

**Abutment / pier** pages group the fields exactly as the C# `BridgeElement`:
Height H; w1/w2/w3; Width W; b1/b2/b3; Base B; Alignment; Abutment material;
Foundation parameters (Hf, b1f, b3f, w1f, w3f, foundation material); Add lateral
restraint left/right (Hsp1/Hsp2 + geotechnical material); reinforcement left
and right (top/bottom tick + material). The important mesh drivers are
`b1/b2/b3` (shaft widening), `w1/w2/w3` (impost widening), `H/Hf`, alignment,
and `WidthTopPile`.

**Span** pages group the vault fields: Span length L, Width W, rise f,
thickness Tt = Tb, thickness law, shape (Elliptical/Circular), angle α,
S1/S2, span material, pier-cap material, and reinforcement layer under the
vault (thickness Tr + material). The important mesh drivers are L, f, Tb, Tt,
Asx/Adx, S1/S2, Dz and the shape flag.

**Backfill** has an elevation table (X, H1, H2, H3) and three layer tabs with
material 1, material 2, uniform-material flag, number of rows for material 1,
and “Generate computational elements”.

### 2.2 Material editor

The Masonry Materials page has a library on the left and a document on the
right. The header has Name, Description, Simple/Advanced mode, and specific
weight W. Advanced mode has three mechanism tabs:

- **Rocking mechanism** — isotropic/orthotropic behavior; Young’s modulus E;
  tensile law (Elastic / Linear hardening / Linear softening / Exponential),
  tensile strength ft, fracture energy Gt, unload behaviour (Initial/Origin/
  Mixed) and βt; compressive law, compressive strength fm, fracture energy Gc,
  unload behaviour and βc; ductility fields when the law requires them.
- **Shear mechanism** — constitutive law (Elastic / Elasto-plastic /
  Elasto-plastic and ductility fixed / …), yielding domain (Turnsek-Cacovic /
  Mohr-Coulomb / Linear), shear modulus G, shear strength τ0, stiffness
  shear/sliding ratio α, reload stiffness ratio κrs, maximum tensile ratio,
  ultimate shear strain γu, Cacovic coefficient b; cyclic parameters.
- **Sliding mechanism** — isotropic/orthotropic; **Check contact area for the
  evaluation of the shear strength**; per-direction constitutive law, yielding
  domain, cohesion c, friction ratio μ, plastic stiffness ratio κ, maximum
  tensile ratio and fracture energy Gs.

The important rule is that fields are law-dependent: changing the constitutive
law changes which strength/energy/ductility fields are editable. The current
HiStrA View material editor already follows that pattern.

### 2.3 Loads / vehicles and Schema

The **Loads** page is a vehicle library plus a table editor:

- Header: Name, Description, Add/Copy/Delete/Import/Export, `D1…D4`, Dynamic
  coefficient.
- Table: Name, Load condition, Direction, X, Y, Length, Width, Load value,
  ψ0, ψ1, ψ2.
- The screenshot shows `LM71` with 24 axle rows and the characteristic
  UIC71 axle loads (38.195 / 76.39 kN), all in load condition “Vehicle”,
  direction Gravity, `Y=0.7175 m`, ψ0=ψ1=0.8, ψ2=0.

The **Schema** page selects a schema and edits its lane paths and vehicle
positions:

- Path table: Lane, Vehicle, NumVehicle, Opposite, AreaLoad, Exclude, L1, L2,
  LineLoad, Exclude, L1, L2.
- Position definition: equally spaced vs worth sections + additional positions;
  number of positions; a position table; and combination coefficients GC for
  vehicle, braking, swaying and centrifugal actions.

### 2.4 Analyses

The C# Define Analyses dialog has a list (Executed, Name, Type analysis, Start
from, Load combo, Description) and a lower property panel with tabs:
**Control parameters**, **Iterative strategy**, **Convergence criteria**,
**Model points**, **Loads applied**, **Load function**.

Important fields:

- Control: type of load distribution, load-control % vs target displacement,
  start if previous analysis incomplete, stop at load reduction, save every N
  steps, control point, direction (Simple / Cartesian / Polar), seismic flag.
- Iterative: integration method (Load Control / Arc Length), numerical method
  (Modified/Standard Newton-Raphson), line search, tolerance, max iterations,
  max/min eta, automatic load step, max load reductions, load factor reduction;
  arc-length ray dr, max increment dλ, desired iterations.
- Convergence: tolerance, max displacement, criterion (Force / Displacement /
  Work).
- Model points: active monitoring points and displacement points.
- Load function: max discretization, pseudo-time vs load multiplier, table and
  multiplier-vs-pseudo-time curve.

### 2.5 Results and the Quad inspector

The C# Response menu contains: Deformed shape, Displacements in global
direction, **Stress/Strain**, **Interface**, Truss, Arch element response,
Plot push-over F-U, Plot push-over λ-U, Plot response curve, Influence lines,
Advanced options.

Stress/Strain submenu: Diagonal link phase, Diagonal link sigma, Stress in
global direction, Stress in local direction, Principal stress, Strain in local
direction, Plastic strain in local direction, ColorMap of plastic strain,
ColorMap of ratio plastic strain in dir1/dir2, ColorMap of ratio plastic
strain. Interface submenu: Transversal stress, Sliding stress, Out of plane
sliding stress, Transversal Phase, Sliding Phase, Out of plane sliding Phase.

The “Properties of the Quad” panel shows: Name; ModelPoints; Geometry;
Material; Load; ReferenceSystem; Parent (ParentElement, MasterElement); and
Advanced (Normal1X…Normal4Z, G, **Update mesh**, **Active custom mesh**).

The Advanced Options dialog tabs are **Solver**, **Tolerance**, **Mass matrix**,
**Interface**, **Bridge**:

- Solver: Internal solver, Save all links status, Show error graph, Show error
  graph at each DOF, Use parallel solver, Write log file.
- Tolerance: tolerance to check node coincidence (0.01 m in the screenshot),
  tolerance to check if a point is on a plane (0.01 m).
- Mass matrix: lumped/consistent mass matrix.
- Interface: max links distance (0.4 m), number of links rows (3).
- Bridge: “Geotechnical Links are disabled on loading Lateral Earth Pressure”.

The Model informations dialog has Code (e.g. Italian code NTC 2018),
Building / Seismic Response Spectrum / User info tabs, building name, owner,
country, region, province, city, address, CAP, latitude/longitude, notes, and
the code/spectrum settings.

### 2.6 Screenshot index

| Folder | Screenshot | Screen |
|---|---|---|
| `geometry` | 8.56.53 PM | General / cross-section table |
| `geometry` | 8.59.26 PM | Left abutment AB1 (H, w1–w3, b1–b3, foundation, reinforcement, lateral restraints) |
| `geometry` | 9.00.38 PM | Span 1:S1 (L, W, f, thickness law, shape, α, S1/S2, materials) |
| `geometry` | 9.06.08 PM | Backfill heights and layer tabs |
| `material` | 9.07.44 PM | Masonry → Rocking mechanism |
| `material` | 9.08.18 PM | Masonry → Shear mechanism |
| `material` | 9.09.11 PM | Masonry → Sliding mechanism (contact-area checkbox) |
| `load` | 9.09.41 PM | Vehicles → LM71 axle table |
| `load` | 9.09.45 PM | Schema → lane paths and positions |
| `analysis` | 9.12.09 PM | Control parameters |
| `analysis` | 9.12.28 PM | Iterative strategy (Load Control) |
| `analysis` | 9.12.40 PM | Iterative strategy (Arc Length) |
| `analysis` | 9.12.51 PM | Convergence criteria |
| `analysis` | 9.13.08 PM | Load function |
| `results` | 9.13.25 PM | Response → Stress/Strain submenu |
| `results` | 9.13.35 PM | Response → Interface submenu |
| `configuration` | 9.14.29 PM | Properties of the Quad (Update mesh / Active custom mesh) |
| `configuration` | 9.15.26 PM | Advanced Options → Solver |
| `configuration` | 9.15.36 PM | Advanced Options → Tolerance |
| `configuration` | 9.15.49 PM | Advanced Options → Interface |
| `configuration` | 9.15.58 PM | Advanced Options → Bridge |
| `configuration` | 9.16.06 PM | Model informations |

---

## 3. Answers to the two questions

### 3.1 “Check contact area for the evaluation of the shear strength”

This flag changes how the sliding (Coulomb) spring computes its shear limit.
It is stored as `CheckContactArea` on the masonry material and copied to the
`SpringCoulomb02/03` and `ConstitutiveLawCoulomb` objects.

In the C# spring implementation (`SpringCoulomb03.setTrialStrainInitial` and
the `_old`/`2` variants):

- **Checked** — the spring uses the current contact area `_AreaCorrente`
  instead of the full interface area. The cohesion contribution is adjusted by
  `cohesion * (contactArea - previousContactArea) / Area`, and the shear
  limit is evaluated with `contactArea / Area`. As the joint opens and the
  contact area shrinks, the available cohesion and shear strength reduce.
- **Unchecked** — `_TcontactArea = Area`, so the full interface area is used
  and the shear limit is evaluated with a ratio of 1.0.

It is therefore a “reduced contact area” option for joints that can open or
lose contact (rocking masonry, arch springings, cracked piers). It does **not**
change the normal stiffness or the friction coefficient; it scales the area
over which cohesion and shear strength are mobilised. In the benchmark model
only the “Arches” material has it enabled.

### 3.2 “Update mesh” and “Active custom mesh”

Both are C# `Element` properties in the **Advanced** category
(`C#_Original/source/ModelLibrary/Objects/Element.cs`):

- **Update mesh** (`IsGeometryModified`) — “If it is checked performs the
  discretization of this object.” It tells the model mesher to re-discretize
  this object. Unchecking it freezes the current mesh for that object, which is
  useful when a local mesh was edited or must be preserved. The C# description
  is literally “If it is checked performs the discretization of this object”.
- **Active custom mesh** (`IsGeometryCustomized`) — “If it is checked you can
  customize discretization parameters.” It enables object-specific mesh
  controls instead of the global mesh settings. It does not itself change the
  geometry; it only exposes the custom discretization fields.

The hidden companion flags are `IsPropertyModified` and
`IsPropertyCustomized`, which mark that an object’s properties were overridden.
In the screenshot the selected Quad has **Update mesh = checked** and
**Active custom mesh = unchecked**, i.e. it will be re-meshed with the global
settings.

---

## 4. C#/Python parity findings

### 4.1 What already matches

- `hrx_model.parse_hrx` reads the benchmark correctly: 3235 nodes, 2529 quads,
  8 masonry materials, 21 analyses, 7 load conditions, 11 combinations,
  21 load functions and 34 load templates. It warns that the 20 `Vertex`
  triangles are not drawn.
- `csharp_import.spec_from_hrx` reads the four spans, their `Circolare` flags,
  the five lanes, the two abutments, three piers and the elevation layers.
- The elliptical arch port reproduces the C# arch-ring **topology** for a span:
  the benchmark’s 230 `QuadSpanKey` arch quads and a simplified Python run
  produce the same 500 arch-ring nodes. Exact node positions still differ:
  C# samples the extrados separately for each elevation layer, intersects the
  edge strips with the inclined plane, and applies the support widening before
  the skew/slope transform. The Python port currently samples the whole
  extrados in one pass and uses a constant strip width.
- The full C# model uses 2529 quads + 20 transition triangles. The current
  Python mesher produces only quads (2352 in the simplified run), so a
  byte-exact full-model mesh is not yet possible.

### 4.2 `Circolare` is a wizard flag, not a C# mesher branch

This is the most important parity nuance. `BridgeMesher.AddBridgeRow1` never
reads `Span.circolare`. It always builds the ellipse from `L`, `f`, `Tb`, `Tt`
and **`Adx`** (the same angle is used for both halves). The C# wizard uses the
`Circolare` choice to derive and lock `Asx`/`Adx` with
`max(0, asin((R - f) / R))`, where `R = (f² + (L + S1 + S2)²/4) / (2f)`. A
normal circular span is therefore represented by an ellipse that passes
through the springing and crown with the correct slope. Between those points
it is still an ellipse. For a tall segment the formula is clamped to 0, which
is why span 3 stores `Asx=Adx=0`.

The benchmark proves the distinction: span 3 has `L=200`, `f=350`,
`Circolare=true`, `Asx=Adx=0`. The C# mesh is the tall half-ellipse visible in
the 3D screenshot (a narrow, very tall opening), not a shallow circular
segment. A true circle through the same three points would have
`R = (350² + 100²) / 700 = 189.29 cm` and a springing angle of about -58.1°.

HiStrA View now has both behaviours:

- `circolare=false` → C#-parity elliptical branch using `Asx`/`Adx`.
- `circolare=true` → true circular intrados (viewer extension), with the
  springing angle derived from `L`, `S1`, `S2` and `f`.

In create mode the true-circle extension produces a circular saved mesh, but
the native `Circolare` flag does not encode that extension. On re-import for
re-meshing, the flag is preserved while the C# elliptical algorithm is used.
Consequently the wizard data alone cannot reproduce an extension mesh; retain
the saved mesh or create it again with the viewer's true-circle option.

For strict C# mesh parity, use the elliptical option. The UI labels this
explicitly (“C# elliptical (Asx/Adx)” vs “True circular (viewer extension)”).

### 4.3 Bugs found and fixed

- `circular_radius()` rejected `rise > length/2` as “more than a semicircle”.
  That is mathematically wrong: a circle through a chord and a crown is always
  a minor arc, and the C# wizard allows tall segments such as `L=200, f=350`.
  The restriction is removed.
- `half_arch_params_circular()` used `acos(a/R)` for the springing angle,
  which is always positive and mirrors the springing above the circle centre.
  For tall segments the intrados then did not pass through `z=0`. It now uses
  the signed angle `atan2(-centre_z, a)`, so the springing and crown are exact
  for both shallow and tall segments.

### 4.4 Remaining parity backlog

HiStrA View also provides an optional rectangular transverse pier-shoulder
approximation. `HiStrAShoulderHeight` is a HiStrA View extension on a `Pier`,
not a native C# wizard field. It creates masonry quads above the two parts of a
centered pier extending outside the deck, using the pier material and the
existing transverse subdivisions. A height of zero disables the feature. The
rectangle preserves the section area of an ideal triangular shoulder if its
height is half the triangle's height; it does not reproduce the sloped shape.
It is restricted to straight, level bridges with centered, untapered piers and
deck-width pier caps. Python preparation has been checked for pier and
neighboring masonry contacts; C# remeshing and the structural response have not
been validated.

1. **Inclined + tapered supports.** The Python generator now applies the C#
   edge-strip displacement and varying vertex thickness for skewed, widened,
   tapered and offset supports. The benchmark can be generated with passive
   earth-pressure flags disabled in memory. It is not yet fully geometrically
   equivalent to C# in every case; the benchmark support quads now match as
   described below.
2. **Transition triangles.** The C# model has 20 `Vertex` triangles at curved
   layer transitions. The Python mesher emits quads only.
3. **Surface restraints / passive earth pressure.** The benchmark has 11
   `SurfaceRestraint` objects and 160 GLRs; the Python mesher produces fewer
   foundation supports and does not yet generate passive-pressure surfaces.
4. **Load generation.** The benchmark sets `IsVehicleLoad=false` and relies on
   the schema/line load. Native vehicle-load generation is still rejected by
   the Python mesher.
5. **Results menus.** The viewer covers deformed shape, modal shapes, response
   curves and interface/stress contours. The C# “Arch element response”,
   “Influence lines” and push-over curve menus are not yet projected.

For constant elevation sections with one crossing boundary followed by a layer
above the arch, the generator samples the two ellipse segments independently
and reproduces the C# first curved band and its following bands. Other crossing
configurations still use the viewer's quad-only clipping construction, not the
C# transition-triangle algorithm. Their cut boundaries can produce partial-face
interfaces and their geometry is not validated for structural use. Crossing
boundaries with multiple elevation sections or overhanging arches remain
unsupported. Older generated meshes are identified by exact geometry before
regeneration; the source HRX is never modified.

The diagnostic `python -m tests.compare_benchmark_mesh` regenerates the local
benchmark after disabling passive earth-pressure flags in the imported
in-memory specification. With a 0.05 native-unit vertex tolerance and matching
material keys, all 715 generated pier/abutment quads and 105 foundation quads
match the corresponding native material counts and vertex thicknesses. It also
matches 1,218 backfill quads; the remaining backfill transition is not yet
ported. The whole generated mesh contains 2,710 quads, versus 2,529 quads and
20 triangles in the C# file. This
reveals remaining geometry and topology differences; it does not establish
structural or solver validity.

---

## 5. What was implemented

- Added a **Geometry** tab to the HRX editor that exposes the native
  `WizardData` groups: bridge definition, cross-section lanes, abutments,
  spans, piers, backfill/elevation layers and trunks. Fields use the C# names
  and labels, with material dropdowns and help text for mesh-driving values.
- Added a **Configuration** tab for `ModelProperty` (General info, Building,
  Soil, Service life), `AdvancedOptionsDefault` (solver, tolerance, mass matrix,
  interface, bridge) and root-level model flags.
- Added **Vehicles**, **Line loads** and **Load schemas** to the Loads editor.
  A vehicle/line-load template exposes its `LoadTemplateItem` rows through the
  section selector, and schema paths/positions are editable.
- Added help text for the two questions:
  - the sliding material checkbox now explains the contact-area rule;
  - the Quad inspector explains “Update mesh” and “Active custom mesh”.
- Extended the create-mode payload/UI with the C# support dimensions
  (`b1/b3/w1/w2/w3`, alignment, foundation, geotechnical materials, passive
  pressure, reinforcement) and the full span dimensions (`W`, `Tb1/Tb2`,
  `Treinf`, `L1/L2/f2`, reinforcement material).
- Added `tests/test_benchmark_model.py`, which validates the benchmark
  inventory, the four mixed spans, the five lanes, the importer, and both the
  short and tall circular spans.

### Files touched

- `model-view/builder_api.py` — wizard/configuration/load collections and
  protected-key handling.
- `model-view/histra_builder/ui.py` — C# support/span payload fields.
- `model-view/histra_builder/generator/csharp_arch.py` — tall circular
  segments and signed springing angle.
- `model-view/static/builder.js` — Geometry/Configuration tabs, load
  categories, field labels and help text.
- `model-view/static/app.js` — Quad inspector explanation for the two C#
  advanced flags.
- `model-view/tests/test_csharp_arch.py` — tall-segment regression.
- `model-view/tests/test_benchmark_model.py` — benchmark regression suite.

---

## 6. Quick field checklist for future parity work

If a future C# export is compared again, check these first:

1. `Width`, `WidthTopPile`, `IsWidthTopPileCustom`, `Nl`, `InclinationAngle`,
   `Slope`, `Zlevel`.
2. Per lane: `Width`, `Height`, `MaterialKey`, `AllowVehicle`.
3. Per support: `H`, `Hf`, `b1/b2/b3`, `w1/w2/w3`, `B1f/B3f`, `W1f/W3f`,
   `VerticalAllignment`, `MaterialKey`, `MaterialFoundationKey`, `Hsp1/Hsp2`,
   `SpintaPassivaSX/DX`.
4. Per span: `L`, `f`, `Circolare`, `Asx`, `Adx`, `Tb`, `Tt`, `Tb1/Tb2`,
   `Treinf`, `S1`, `S2`, `Dz`, `LawS`, `MaterialKey`, `MaterialPulvinoKey`.
5. Elevations: `H1`, `H2`, `H3`, layer `MaterialKey`/`MaterialKey2`,
   `UniformMaterial`, `RowIndexMaterial`, `GenerateComputationalElements`.
6. Mesh: node/quad/vertex counts, `QuadSpanKeys` count, `GeometryLineRestraint`
   count, `Restraint` count, `SurfaceRestraint` count.
7. Loads: vehicle rows (`LoadValue`, `Psi0/1/2`, `X`, `Y`), schema paths,
   schema positions and `LoadTemplateItem` references.
8. Analyses: `AnalysisType`, `IntegrationMethod`, `Method`, `LoadCombinationKey`,
   `LoadFunctionKey`, `ConvergenceTolerance`, `MaxIterations`,
   `AdapticConvergenceCriteria`.
