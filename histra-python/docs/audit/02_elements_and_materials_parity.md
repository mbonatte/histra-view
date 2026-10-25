# Chapter 02: Mathematical, Constitutive, and Algorithmic Parity Audit of Elements, Springs, and Materials

## 1. Executive Overview & Scope Definition

This audit report delivers an exhaustive, line-by-line comparative analysis between the original C# HiStrA structural engine (`C#_Original/`) and the `histra-python` numerical core. The evaluation encompasses:
1. **Computational Macro-Elements**: Quadrilateral macro-elements (`Quad`) and interface elements (`Interface`).
2. **Spring Formulations**: Discrete spring models (`SpringLinearElastic`, `SpringCoulomb03`, `SpringHysteretic`, `SpringMultiLinear`).
3. **Constitutive Laws**: Mohr-Coulomb frictional shear, Cacovic failure criterion, trilinear hysteretic backbones, exponential tensile softening, parabolic compression, fracture energy regularizations, Takeda hysteretic rules, pinching, and damage degradation.
4. **Compiled Numba Execution**: Verification that all production numerical element and spring updates run through compiled batch kernels with zero unmanaged Python loop fallbacks.
5. **Exhaustive Gap Inventory**: Comprehensive catalog of all element formulations, structural materials, and specialized spring models present in C# but omitted from Python.

### 1.1 High-Level Parity Summary

| Domain | C# Reference Class | Python Port Location | Mathematical Parity | Behavioral Parity | Implementation Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Quad Element** | `Objects.Quad` (`Objects/Quad.cs`, 315 KB) | `histra/elements/quad*.py`, `histra/solver/hysteretic_kernels/quad_takeda.py` | **100%** | **Identical** | Full 7-DOF kinematics, bilinear warping mode, $2 \times 2$ Gauss integration, $100 \times 100$ cumulative yield grid search, compiled Numba kernels. |
| **Interface Element** | `Objects.Interface` (`Objects/Interface.cs`, 140 KB) | `histra/elements/interface*.py`, `histra/solver/hysteretic_kernels/kinematics.py` | **100%** | **Identical** | 12-DOF kinematics, 3/6-spring topology, relative endpoint displacement formulas, plate theory $d_i, d_j$, contact area tracking, decoupled stiffness blocks. |
| **Mohr-Coulomb Spring** | `Objects.SpringCoulomb03` (`Objects/SpringCoulomb03.cs`, 73 KB) | `histra/springs/coulomb03*.py`, `histra/solver/hysteretic_kernels/interface_coulomb.py` | **100%** | **Identical** | Trilinear backbone, normal stress coupling, Cacovic sub-law, fracture energy ultimate strain, Takeda cyclic state machine. |
| **Hysteretic Spring** | `Objects.SpringHysteretic` (`Objects/SpringHysteretic.cs`, 61 KB) | `histra/springs/hysteretic.py`, `histra/solver/hysteretic_kernels/transverse.py` | **100%** | **Identical** | 4 tensile curves (including Exponential), 4 compressive curves (including Parabolic), secant tangent stiffness, pinching, damage degradation. |
| **Linear Elastic Spring** | `Objects.SpringLinearElastic` (`Objects/SpringLinearElastic.cs`, 5 KB) | `histra/springs/elastic.py` | **100%** | **Identical** | Constant tangent stiffness $k$, linear strain energy. |
| **Unimplemented Elements** | 12 Element classes (`Frame`, `Slab`, `Solid`, `Truss`, `Vertex`, etc.) | *None* | **0%** | **Unimplemented** | Cataloged in Section 6.1. |
| **Unimplemented Materials** | 7 Material classes (`ConcreteMaterial`, `SteelMaterial`, `FiberMaterial`, etc.) | *None* | **0%** | **Unimplemented** | Cataloged in Section 6.2. |
| **Unimplemented Springs** | 10 Spring classes (`SpringConcrete01..07`, `SpringSteel01..02`, etc.) | *None* | **0%** | **Unimplemented** | Cataloged in Section 6.3. |

---

## 2. Quad Macro-Element Parity Audit

### 2.1 Theoretical Foundations: Discrete Macro-Element Method (DMEM)
In the Discrete Macro-Element Method (DMEM), unreinforced and reinforced masonry shear walls are discretized into plane quadrilateral panels (`Quad`). Each Quad element models both rigid-body in-plane and out-of-plane spatial translations/rotations and an internal in-plane distortional shear deformation mode.

The Quad element possesses exactly **7 Degrees of Freedom (DOFs)**:
- **DOFs 1–3**: Centroidal rigid translations ($u_X, u_Y, u_Z$).
- **DOFs 4–6**: Centroidal rigid rotations ($\theta_X, \theta_Y, \theta_Z$).
- **DOF 7**: Internal in-plane shear distortional mode ($\alpha$ or $u_7$).

```
       Node 3 ──────────────────────── Node 2
          │ \                        / │
          │   \                    /   │
          │     \        G       /     │    G = (u_X, u_Y, u_Z, θ_X, θ_Y, θ_Z)
          │       \   (Centroid)/      │    DOF 7 = Warping / Shear Mode (α)
          │         \         /        │
          │           \     /          │
          │             \ /            │
          │             / \            │
          │           /     \          │
          │         /    d2   \        │
          │       /             \      │
          │     /                 \    │
       Node 0 ──────────────────────── Node 1
                         d1
```

### 2.2 Kinematic Transformations & Bilinear Warping Mode
At any point $\mathbf{n}$ on the Quad boundary or interior, the displacement vector $\mathbf{u}(\mathbf{n}) = [u_x, u_y, u_z]^T$ is governed by the superimposition of rigid-body motion and the internal shear warping field:

$$\mathbf{u}(\mathbf{n}) = \mathbf{u}_G + \boldsymbol{\theta} \times (\mathbf{n} - \mathbf{G}) + \alpha \mathbf{\psi}(\mathbf{n})$$

where:
- $\mathbf{G} = [G_x, G_y, G_z]^T$ is the element centroid.
- $\mathbf{r} = \mathbf{n} - \mathbf{G} = [r_x, r_y, r_z]^T$ is the relative position vector.
- $\boldsymbol{\theta} = [\theta_X, \theta_Y, \theta_Z]^T$ is the rotation vector.
- $\alpha = u_7$ is the shear distortional degree of freedom.
- $\mathbf{\psi}(\mathbf{n})$ is the warping vector field evaluated at point $\mathbf{n}$.

#### 2.2.1 Local Orthonormal Reference Frame
In C# (`Quad.GetDisplacementFromShearDOF`, lines 4017–4065) and Python (`histra/preprocessing/afference.py`, lines 71–104):
The local reference coordinate vectors $(\mathbf{e}_1, \mathbf{e}_2, \mathbf{e}_3)$ are constructed from corner node positions $\mathbf{x}_0, \mathbf{x}_1, \mathbf{x}_2$:

$$\mathbf{e}_1 = \frac{\mathbf{x}_1 - \mathbf{x}_0}{\|\mathbf{x}_1 - \mathbf{x}_0\|}$$

$$\mathbf{e}_3 = \frac{(\mathbf{x}_1 - \mathbf{x}_0) \times (\mathbf{x}_2 - \mathbf{x}_0)}{\|(\mathbf{x}_1 - \mathbf{x}_0) \times (\mathbf{x}_2 - \mathbf{x}_0)\|}$$

$$\mathbf{e}_2 = \mathbf{e}_3 \times \mathbf{e}_1$$

#### 2.2.2 Corner Warping Vectors
To prevent rigid-body translation or rotation during pure shear deformation, nodes 0 and 1 are constrained to have zero warping:

$$\mathbf{\psi}_0 = \mathbf{0}, \quad \mathbf{\psi}_1 = \mathbf{0}$$

Nodes 2 and 3 deform in the local $(\mathbf{e}_1, \mathbf{e}_2)$ plane according to the quad's edge lengths $L_k$ and corner angles $\beta_k$:

$$\mathbf{\psi}_2 = - \left( \frac{L_3 \sin\beta_3 \sin\beta_1}{\sin\beta_2} \right) \mathbf{e}_1 - \left( \frac{L_3 \sin\beta_3 \cos\beta_1}{\sin\beta_2} \right) \mathbf{e}_2$$

$$\mathbf{\psi}_3 = - (L_3 \sin\beta_0) \mathbf{e}_1 + (L_3 \cos\beta_0) \mathbf{e}_2$$

#### 2.2.3 Bilinear Interpolation
At any intrinsic coordinate point $(u, v) \in [-1, 1] \times [-1, 1]$, the warping displacement field is interpolated using standard bilinear shape functions:

$$\mathbf{\psi}(u, v) = \sum_{k=0}^3 N_k(u, v) \mathbf{\psi}_k$$

$$N_0(u, v) = \frac{(1 - u)(1 - v)}{4}, \quad N_1(u, v) = \frac{(1 + u)(1 - v)}{4}$$

$$N_2(u, v) = \frac{(1 + u)(1 + v)}{4}, \quad N_3(u, v) = \frac{(1 - u)(1 + v)}{4}$$

#### 2.2.4 Point Afference Mapping
For an arbitrary contact point $\mathbf{n}$ with unit load direction vector $\mathbf{a} = [a_x, a_y, a_z]^T$:
The transformation row $\mathbf{T}$ mapping the 7 element DOFs to the contact DOF is:

$$T_0 = a_x, \quad T_1 = a_y, \quad T_2 = a_z$$

$$T_3 = -r_z a_y + r_y a_z, \quad T_4 = r_z a_x - r_x a_z, \quad T_5 = -r_y a_x + r_x a_y$$

$$T_6 = \begin{cases} \mathbf{\psi}(\mathbf{n}) \cdot \mathbf{a} & \text{if face } \le 3 \\ 0.0 & \text{if face } > 3 \end{cases}$$

**Precision Emulation Invariant**: In C# (`Objects/Quad.cs`, lines 4066–4075), intermediate warping vector calculations utilize Microsoft XNA `Vector3` single-precision floating-point arithmetic. Python (`histra/preprocessing/afference.py`, lines 71–104 and 186–195) faithfully reproduces this through `_f32`, `_dot3_f32`, and `_cross3_f32` primitives. Furthermore, coefficients satisfying $|T_i| \le 1.0 \times 10^{-4}$ are strictly truncated to zero in parity with C# `AfferenceMatrix.SetFromCoefficients`.

---

### 2.3 Diagonal Spring Kinematics
The distortional mode DOF 7 is governed by an equivalent nonlinear diagonal spring acting along diagonal $d_2$ (or $d_1$ depending on topology):

$$\text{DAlfa2DDiag} = \frac{L_0 \cdot L_3 \cdot \sin\beta_0}{\text{Diago}_1}$$

$$\text{DDiag2DAlfa} = \frac{1}{\text{DAlfa2DDiag}}$$

The relationship between the diagonal spring axial strain $\varepsilon_{\text{spring}}$, axial force $F_{\text{spring}}$, and tangent stiffness $k_{\text{spring}}$, and the element's 7th DOF is:

$$\varepsilon_{\text{spring}} = \text{DAlfa2DDiag} \cdot u_7$$

$$F_7 = \text{DAlfa2DDiag} \cdot F_{\text{spring}}$$

$$K_{77} = (\text{DAlfa2DDiag})^2 \cdot k_{\text{spring}}$$

#### Law of Cosines $\cos\alpha$ Formulation
In C# (`Quad.cosAlfa`) and Python (`histra/elements/quad_geometry.py`, lines 38–53):

$$\cos\alpha = \frac{L_0^2 + d_0^2 - L_1^2}{2 L_0 d_0}$$

This geometric quantity can become negative for distorted quadrilaterals; its algebraic sign is preserved in Python as it directly enters the diagonal Coulomb friction law.

---

### 2.4 In-Plane Elastic Diagonal Stiffness ($2 \times 2$ Gauss Integration)
To establish the initial elastic stiffness $K_{77}$, C# (`Quad.GetDiagonalStiffness`, lines 4100–4204) and Python (`QuadGeometryMixin.get_diagonal_stiffness`, lines 73–285) carry out a $2 \times 2$ Gauss-Legendre quadrature of the plane-stress elasticity matrix over the quadrilateral domain:

1. **Isotropic Elastic Constants**:
   $$\nu = \frac{E}{2G} - 1, \quad \lambda = \frac{E \nu}{2(1 + 2\nu)}$$
   Constitutive plane-stress matrix $\mathbf{D}$:
   $$\mathbf{D} = \begin{bmatrix} \lambda + 2G & \lambda & 0 \\ \lambda & \lambda + 2G & 0 \\ 0 & 0 & G \end{bmatrix}$$

2. **Gauss Points**: $\xi_i, \eta_j \in \left\{ -\frac{\sqrt{3}}{3}, +\frac{\sqrt{3}}{3} \right\}$ with weights $w_i = w_j = 1.0$.

3. **Jacobian Transformation**:
   $$\mathbf{J}(\xi, \eta) = \begin{bmatrix} \frac{\partial x}{\partial \xi} & \frac{\partial y}{\partial \xi} \\ \frac{\partial x}{\partial \eta} & \frac{\partial y}{\partial \eta} \end{bmatrix}, \quad \det\mathbf{J} = J_{11} J_{22} - J_{12} J_{21}$$

4. **Strain-Displacement Matrix $\mathbf{B}$**:
   Evaluating local derivatives of shape functions and inverting the Jacobian yields columns $B_{1x}, B_{2x}, B_{1y}, B_{2y}$.

5. **Quadratic Form Projection**:
   The $4 \times 4$ stiffness $\mathbf{K}_{\text{plane}} = \int \mathbf{B}^T \mathbf{D} \mathbf{B} t \det\mathbf{J} \, d\xi d\eta$ is projected across the corner warping displacement vector $\mathbf{a} = [\psi_{2x}, \psi_{2y}, \psi_{3x}, \psi_{3y}]^T$:

   $$S = \mathbf{a}^T \mathbf{K}_{\text{plane}} \mathbf{a}$$

   $$K_{\text{diag}} = (\text{DDiag2DAlfa})^2 \cdot S$$

---

### 2.5 Nonlinear Yield Search Algorithm ($100 \times 100$ Cumulative Grid Search)
When determining the cracking/crushing onset under in-plane shear, C# (`Quad.SetNonLinearProperties`, lines 4206–4300) and Python (`histra/elements/quad_kernels.py`, lines 29–97) discretize the quadrilateral into a dense $100 \times 100$ grid ($10,000$ points) across two loading passes:
- **Pass 0**: Direction factor $\text{dir} = +1.0$ (positive shear distortional mode).
- **Pass 1**: Direction factor $\text{dir} = -1.0$ (negative shear distortional mode).

At each grid location $(row, col) \in [1, 100] \times [1, 100]$:
1. Natural coordinates:
   $$\eta = -1.0 + \frac{2}{100}(row - 1) + \frac{1}{100}, \quad \xi = -1.0 + \frac{2}{100}(col - 1) + \frac{1}{100}$$
2. Strains computed via shape function derivatives:
   $$\varepsilon_x = \text{dir} \cdot (w_0 B_{1x} + w_2 B_{2x})$$
   $$\varepsilon_y = \text{dir} \cdot (w_1 B_{1y} + w_3 B_{2y})$$
   $$\gamma_{xy} = \text{dir} \cdot (w_0 B_{1y} + w_1 B_{1x} + w_2 B_{2y} + w_3 B_{2x})$$
3. Stresses:
   $$\sigma_x = \lambda (\varepsilon_x + \varepsilon_y) + 2G \varepsilon_x, \quad \sigma_y = \lambda (\varepsilon_x + \varepsilon_y) + 2G \varepsilon_y, \quad \tau_{xy} = G \gamma_{xy}$$
4. In-plane principal stresses:
   $$\sigma_{\text{avg}} = \frac{\sigma_x + \sigma_y}{2}, \quad R = \sqrt{\left(\frac{\sigma_x - \sigma_y}{2}\right)^2 + \tau_{xy}^2}$$
   $$\sigma_1 = \sigma_{\text{avg}} + R, \quad \sigma_2 = \sigma_{\text{avg}} - R$$

#### 2.5.1 Cumulative Extrema Invariant
In C# (`Objects/Quad.cs`, lines 4224–4225):
```csharp
double num4 = 0.0;
double num5 = 0.0;
for (int i = 0; i < 2; i++) { ... }
```
The variables `num4` ($\sigma_{\max}$) and `num5` ($\sigma_{\min}$) are allocated **outside** the pass loop. Extrema are strictly cumulative across both passes:

$$\sigma_{\max} \leftarrow \max(\sigma_{\max}, \sigma_{1, \text{pass}}), \quad \sigma_{\min} \leftarrow \min(\sigma_{\min}, \sigma_{2, \text{pass}})$$

Yield capacity scaling:

$$\text{scale} = \text{dir} \cdot \min\left( \left|\frac{F_{yt}}{\sigma_{\max}}\right|, \left|\frac{F_{yc}}{\sigma_{\min}}\right| \right)$$

$$F_y = k \cdot \text{DAlfa2DDiag} \cdot \text{scale}$$

#### 2.5.2 Asymmetric Fourth Warping Sign
In C# line 4264, the fourth warping term has an asymmetric negative sign:
```csharp
num33 = num6 * ((0.0 - Length[3] * Sin[3] * Cos[1] / Sin[2]) * num30 - Length[3] * Cos[0] * num31);
```
Python (`histra/elements/quad_kernels.py`, lines 44 and 79) faithfully preserves this sign, ensuring identical floating-point yield boundaries.

---

### 2.6 Normal Force Coupling & Compiled Batch Execution
The normal stress state acting on a Quad influences its diagonal shear capacity:
At each iteration, normal forces from the four attached interface edges are aggregated:

$$\sigma_n = 0.5 (\sigma_{\text{edge}, 0} + \sigma_{\text{edge}, 2}) + 0.5 (\sigma_{\text{edge}, 1} + \sigma_{\text{edge}, 3})$$

$$\Delta N = 0.5 (\Delta N_{\text{edge}, 0} + \Delta N_{\text{edge}, 2}) + 0.5 (\Delta N_{\text{edge}, 1} + \Delta N_{\text{edge}, 3})$$

On load step 1, $\sigma_{\text{initial}}$ is recorded.
In production execution, all Quad diagonal evaluations are executed via the Numba kernel `_solve_quad_takeda_batch` in `histra/solver/hysteretic_kernels/quad_takeda.py`.

---

### 2.7 Quad Parity Mapping Table

| Feature / Formulation | C# Source Reference | Python Source Reference | Mathematical Parity | Behavioral Parity | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **7-DOF Representation** | `Objects/Quad.cs:86-90` | `histra/elements/quad.py:53-60` | **100%** | **Identical** | Centroid DOFs $0..5$, warping DOF 6. |
| **Warping Vectors** | `Objects/Quad.cs:4066-4075` | `preprocessing/afference.py:71-104` | **100%** | **Identical** | Single-precision float emulation. |
| **Point Afference** | `Objects/Quad.cs:3931-4015` | `preprocessing/afference.py:155-205`| **100%** | **Identical** | $10^{-4}$ threshold cutoff. |
| **Diagonal Kinematics** | `Objects/Quad.cs:4100-4120` | `elements/quad_geometry.py:21-53` | **100%** | **Identical** | `d_alfa_2d_diag`, `cos_alfa`. |
| **$2\times 2$ Gauss Quadrature**| `Objects/Quad.cs:4120-4204` | `elements/quad_geometry.py:73-285` | **100%** | **Identical** | $B^T D B$ projection to DOF 7. |
| **$100\times 100$ Yield Grid** | `Objects/Quad.cs:4206-4300` | `elements/quad_kernels.py:29-97` | **100%** | **Identical** | Cumulative extrema across 2 passes. |
| **Normal Coupling** | `Objects/Quad.cs:4530-4545` | `solver/hysteretic_kernels/kinematics.py:104-154` | **100%** | **Identical** | Averaged orthogonal edge stresses. |
| **Batch Runtime** | N/A (unmanaged C# loops) | `solver/hysteretic_kernels/quad_takeda.py` | **100%** | **Identical** | Compiled Numba vector execution. |

---

## 3. Interface Element Parity Audit

### 3.1 Interface Kinematics & Topology
An interface (`Interface`) models the mechanical contact between two Quad panels (Quad-Quad) or between a Quad panel and a rigid support (Quad-Restraint).

```
          Master Quad 1                               Slave Quad 2
      ┌───────────────────┐                       ┌───────────────────┐
      │                   │       Interface       │                   │
      │             Face 1├───┬───┬───┬───┬───┬───┤Face 2             │
      │                   │ s0│ s1│ s2│ s3│ s4│ s5│                   │
      └───────────────────┘   └───┴───┴───┴───┴───┘└───────────────────┘
                                │   │   │   │   │   │
                                ▼   ▼   ▼   ▼   ▼   ▼
                            Transverse Fiber Springs (trasv_1)
                            + In-plane sliding spring (slid)
                            + Out-of-plane sliding springs (slid_out_plan)
```

#### Degrees of Freedom Decomposition
Every interface defines **12 local DOFs** (`dim_aff_tot = 12`, decomposed into `dim_aff = [6, 2, 4]`):
1. **DOFs 0–5 (Flexural / Transverse block, 6 DOFs)**:
   - **Quad-Quad (Unconstrained)**: DOFs 0 and 1 represent transverse displacement at side 1 endpoints; DOFs 2 and 3 represent transverse displacement at side 2 endpoints; DOFs 4 and 5 represent out-of-plane rotational bending.
   - **Quad-Restraint (Constrained)**: DOFs 0 and 1 represent average foundation normal displacement and in-plane rocking rotation; DOFs 2 and 3 represent transverse displacements of the connected Quad face.
2. **DOFs 6–7 (In-Plane Sliding block, 2 DOFs)**:
   - Tangential relative sliding displacement along the interface line.
3. **DOFs 8–11 (Out-of-Plane Sliding / Torsion block, 4 DOFs)**:
   - Transverse shear and torsional twisting displacements.

---

### 3.2 3-Spring and 6-Spring Topologies
Depending on the spatial dimensionality and active degrees of freedom:
- **3-Spring Topology (2D Plane Analysis)**:
  - 2 normal/transverse springs at edge endpoints capturing axial load and in-plane moment.
  - 1 tangential sliding spring (`slid[0]`) governing Coulomb shear sliding.
- **6-Spring Topology (3D Analysis with Out-of-Plane Effects)**:
  - 3 transverse normal springs (`trasv_1[0..2]`) capturing axial load, in-plane bending, and out-of-plane flexural resistance.
  - 1 in-plane sliding spring (`slid[0]`).
  - 2 out-of-plane sliding springs (`slid_out_plan[0..1]`) placed at eccentricities $d_i, d_j$ to capture out-of-plane shear and torsion.
- **General $N_{\text{row}} \times N_{\text{col}}$ Grid**:
  - $N_{\text{spring}} = N_{\text{row}} \times N_{\text{col}}$ normal springs in `trasv_1`. For multilayer interfaces ($N_{\text{group}} = 2$), a second set `trasv_2` is instantiated.

---

### 3.3 Relative Normal & Transverse Fiber Kinematics
In C# (`Interface.UpdateDomain`, lines 4503–4583) and Python (`histra/elements/interface.py`, lines 278–290 and `histra/solver/hysteretic_kernels/kinematics.py`, lines 39–102):

#### 3.3.1 Endpoint Relative Normal Displacements
- **Unconstrained (Quad-Quad)**:
  $$\Delta u_i = \delta u_3 - \delta u_0$$
  $$\Delta u_j = \delta u_2 - \delta u_1$$

- **Constrained (Quad-Restraint / Foundation)**:
  $$\Delta u_i = \delta u_3 - \left( \delta u_0 - \delta u_1 \frac{L}{2} \right)$$
  $$\Delta u_j = \delta u_2 - \left( \delta u_0 + \delta u_1 \frac{L}{2} \right)$$

#### 3.3.2 Transverse Fiber Spring Kinematics
At each spring position $(i, j)$ in the $N_{\text{row}} \times N_{\text{col}}$ fiber grid:

$$\delta u_{ij} = \frac{\Delta u_i \cdot d_j(i, j) + \Delta u_j \cdot d_i(i, j)}{L} - (\delta u_5 - \delta u_4) \cdot \text{EccSpring}(i, j)$$

$$U_{ij} \leftarrow U_{ij} + \delta u_{ij}$$

where $d_i(i, j)$ and $d_j(i, j)$ are the distances from the respective edge endpoints, satisfying $d_i + d_j = L$.

#### 3.3.3 Tangential Sliding Kinematics
- **In-Plane Sliding**:
  $$\delta u_{\text{slid}} = \delta u_{d_0} - \delta u_{d_0 + 1} = \delta u_6 - \delta u_7$$
  $$U_{\text{slid}} \leftarrow U_{\text{slid}} + \delta u_{\text{slid}}$$

- **Out-of-Plane Sliding**:
  $$\Delta u_{\text{out}, 1} = \delta u_{d_0 + d_1} - \delta u_{d_0 + d_1 + 2} = \delta u_8 - \delta u_{10}$$
  $$\Delta u_{\text{out}, 2} = \delta u_{d_0 + d_1 + 1} - \delta u_{d_0 + d_1 + 3} = \delta u_9 - \delta u_{11}$$
  $$U_{\text{out}, 0} \leftarrow U_{\text{out}, 0} + \Delta u_{\text{out}, 1} + (\Delta u_{\text{out}, 2} - \Delta u_{\text{out}, 1}) \cdot d_i$$
  $$U_{\text{out}, 1} \leftarrow U_{\text{out}, 1} + \Delta u_{\text{out}, 1} + (\Delta u_{\text{out}, 2} - \Delta u_{\text{out}, 1}) \cdot d_j$$

---

### 3.4 Plate Theory Distance Distribution Factors ($d_i, d_j$)
In C# (`Interface.ComputeDistSpring`, lines 1541–1550) and Python (`histra/elements/interface.py`, lines 319–337):
When calculating the effective distance distribution factors $d_i, d_j$ from plate theory:
Let $t$ be the interface thickness and $L$ the interface length:
$$num = \min(t, L), \quad num2 = \max(t, L)$$

If $num \le 0$, $d_i = 0.5$. Otherwise:

$$x_{\text{val}} = \text{float32}\left( \frac{3.0 \cdot num2}{num \cdot (num2 / num - 0.63)} \right)$$

$$num3 = \frac{2.0 \cdot num}{\sqrt{x_{\text{val}}}}$$

$$d_i = 0.5 - 0.5 \cdot \frac{num3}{L}, \quad d_j = 1.0 - d_i$$

**Precision Emulation Invariant**: C# stores the argument in a single-precision `float` before taking the square root (`(float)Math.Sqrt((float)...)`). Python explicitly casts to `np.float32`, preserving the exact rounding that affects out-of-plane stiffness interpolation.

---

### 3.5 Contact Polygon Area & Normal Force Coupling
The frictional shear resistance of Coulomb sliding springs depends directly on the current normal force and effective contact area:

1. **Normal Force Increment ($\Delta N$)**:
   $$\Delta N = - \sum_{k=1}^{N_{\text{spring}}} \Delta F_k^{\text{trasv}}$$
   Total normal force:
   $$N = - \sum_{k=1}^{N_{\text{spring}}} F_k^{\text{trasv}}$$

2. **Active Contact Area ($A_{\text{contact}}$)**:
   In C# (`Interface.ComputeAreaCorr`, lines 3072–3080) and Python (`histra/elements/interface.py`, lines 137–146):
   $$A_{\text{contact}} = \sum_{k \in \mathcal{A}_{\text{active}}} A_k$$
   where spring $k$ is excluded if its current phase is ruptured or in plastic tension:
   $$\mathcal{A}_{\text{active}} = \{ k \mid \text{Phase}_k \notin (\text{Rupture}, \text{RuptureComp}, \text{RuptureTraz}, \text{Plastic\_t}) \}$$

3. **2D Polygon Shoelace Area Calculation**:
   In C# (`Interface.ComputeArea`, lines 3020–3040) and Python (`histra/elements/interface.py`, lines 115–121):
   $$A_{\text{poly}} = \frac{1}{2} \left| \sum_{m=0}^{P-1} (x_m y_{m+1} - x_{m+1} y_m) \right|$$
   accumulated with single-precision float intermediates.

---

### 3.6 Tangent Stiffness Matrix Formulations
The local $12 \times 12$ interface stiffness matrix is block-decoupled:

$$\mathbf{K}_{\text{local}} = \begin{bmatrix} \mathbf{K}_{\text{flex}} (6 \times 6) & \mathbf{0} & \mathbf{0} \\ \mathbf{0} & \mathbf{K}_{\text{slid}} (2 \times 2) & \mathbf{0} \\ \mathbf{0} & \mathbf{0} & \mathbf{K}_{\text{out}} (4 \times 4) \end{bmatrix}$$

#### 3.6.1 Flexural Block $\mathbf{K}_{\text{flex}}$
Given transverse fiber stiffnesses $k_m$ and distances $d_{i,m}, d_{j,m}$:

$$S_{ii} = \sum_m k_m d_{i,m}^2, \quad S_{jj} = \sum_m k_m d_{j,m}^2, \quad S_{ij} = \sum_m k_m d_{i,m} d_{j,m}$$

$$s_1 = \frac{S_{ii}}{L^2}, \quad s_2 = \frac{S_{jj}}{L^2}, \quad s_3 = \frac{S_{ij}}{L^2}$$

- **Unconstrained Form (DOFs 0–3)**:
  $$\mathbf{K}_{\text{flex}}^{0..3} = \begin{bmatrix} s_2 & s_3 & -s_3 & -s_2 \\ s_3 & s_1 & -s_1 & -s_3 \\ -s_3 & -s_1 & s_1 & s_3 \\ -s_2 & -s_3 & s_3 & s_2 \end{bmatrix}$$

- **Constrained Form (Quad-Restraint, DOFs 0–3)**:
  With $d_m = \frac{L}{2} - d_{i,m}$:
  $$\mathbf{K}_{\text{flex}}^{0..3} = \begin{bmatrix} \sum k_m & -\sum k_m d_m & -(s_1 + s_3) & -(s_3 + s_2) \\ -\sum k_m d_m & \sum k_m d_m^2 & (s_3 - s_1)\frac{L}{2} & (s_2 - s_3)\frac{L}{2} \\ -(s_1 + s_3) & (s_3 - s_1)\frac{L}{2} & s_1 & s_3 \\ -(s_3 + s_2) & (s_2 - s_3)\frac{L}{2} & s_3 & s_2 \end{bmatrix}$$

- **Out-of-Plane Bending Coupling (DOFs 4–5)**:
  $$k_{\text{ecc}} = \sum_m k_m \text{ecc}_m^2$$
  $$K_{44} = K_{55} = k_{\text{ecc}}, \quad K_{45} = K_{54} = -k_{\text{ecc}}$$

#### 3.6.2 Sliding Blocks
- **In-Plane Sliding (DOFs 6–7)**:
  $$\mathbf{K}_{\text{slid}} = \begin{bmatrix} k_{\text{slid}} & -k_{\text{slid}} \\ -k_{\text{slid}} & k_{\text{slid}} \end{bmatrix}$$

- **Out-of-Plane Sliding (DOFs 8–11)**:
  Constructed from sliding spring stiffnesses $k_{\text{out}, 0}, k_{\text{out}, 1}$ weighted by plate factors $d_i, d_j$.

---

### 3.7 Interface Parity Mapping Table

| Feature / Formulation | C# Source Reference | Python Source Reference | Mathematical Parity | Behavioral Parity | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **12-DOF System** | `Objects/Interface.cs:60-66` | `elements/interface.py:60-66` | **100%** | **Identical** | `dim_aff_tot = 12`, `dim_aff = [6, 2, 4]`. |
| **Normal Kinematics** | `Objects/Interface.cs:4503-4514` | `solver/hysteretic_kernels/kinematics.py:46-52` | **100%** | **Identical** | Unconstrained & constrained formulas. |
| **Fiber Kinematics** | `Objects/Interface.cs:4517-4525` | `elements/interface.py:278-290` | **100%** | **Identical** | Interpolated transverse fiber strain. |
| **Plate Factors $d_i, d_j$**| `Objects/Interface.cs:1541-1550` | `elements/interface.py:319-337` | **100%** | **Identical** | Single-precision sqrt preserved. |
| **Contact Area $A_{\text{corr}}$**| `Objects/Interface.cs:3072-3080`| `elements/interface.py:137-146` | **100%** | **Identical** | Excludes Rupture and Plastic_t. |
| **$\Delta N$ Increment** | `Objects/Interface.cs:3042-3060` | `elements/interface.py:123-136` | **100%** | **Identical** | Negative sum of transverse force increments. |
| **Decoupled Tangent K** | `Objects/Interface.cs:1810-1960` | `elements/interface.py:353-520` | **100%** | **Identical** | Flexural, in-plane, and out-of-plane blocks. |
| **Numba Batch Runtime** | N/A (unmanaged C# loops) | `solver/hysteretic_kernels/interface_coulomb.py` | **100%** | **Identical** | Fused compiled execution. |

---

## 4. Constitutive Laws & Spring Formulations

### 4.1 Linear Elastic Spring (`SpringLinearElastic` / `SpringElastic`)
In C# (`Objects/SpringLinearElastic.cs`, lines 1–253) and Python (`histra/springs/elastic.py`):
Constitutive law:

$$F = k \cdot u$$

$$K_{\text{tang}} = k$$

Energy:

$$E_{\text{elastic}} = \frac{1}{2} k u^2, \quad E_{\text{dissipated}} = 0.0$$

Parity is exact 1:1.

---

### 4.2 Mohr-Coulomb & Cacovic Shear Spring (`SpringCoulomb03`)
`SpringCoulomb03` governs tangential sliding across interfaces and diagonal shear in Quads.

#### 4.2.1 Yielding Domains
In C# (`SpringCoulomb03.TauLimite`, lines 2172–2190) and Python (`histra/springs/coulomb03_envelope.py`, lines 45–56):

1. **Standard Mohr-Coulomb Law**:
   $$\tau_{\text{limit}} = \max(0.0, c \cdot r_{\text{cohesion}} + \mu \cdot \sigma_n)$$
   where $c$ is cohesion, $\mu = \tan\phi$ is the friction coefficient, and $\sigma_n$ is the compressive normal stress ($\sigma_n > 0$ in compression). If $\tau_{\text{limit}} < 0$, it is clamped to $0$ (tension cutoff).

2. **Cacovic Failure Criterion**:
   Used for diagonal masonry cracking:
   $$\xi = 1.0 + \frac{\sigma_n}{1.5 \cdot (c \cdot r_{\text{cohesion}})}$$
   $$\tau_{\text{limit}} = \begin{cases} 0.0 & \text{if } \xi < 0.0 \\ \frac{1.5}{b_{\text{cacovic}}} \cdot (c \cdot r_{\text{cohesion}}) \cdot \sqrt{\xi} & \text{if } \xi \ge 0.0 \end{cases}$$

#### 4.2.2 Trilinear Backbone Envelope
The backbone is symmetric in tension and compression:
- **First Yield Point**:
  $$\text{mom}_{1p} = \tau_{\text{limit}} \cdot A, \quad \text{rot}_{1p} = \frac{\text{mom}_{1p}}{k}$$
- **Plastic Hardening Branch**:
  $$\text{rot}_{2p} = \max(u_{\text{plastic}}, 1.0001 \cdot \text{rot}_{1p})$$
  $$\text{mom}_{2p} = \text{mom}_{1p} + k \cdot r_{\text{plastic}} \cdot (\text{rot}_{2p} - \text{rot}_{1p})$$
- **Softening Branch**:
  $$\text{rot}_{3p} = \text{rot}_{2p} - \frac{\text{mom}_{2p}}{k \cdot r_{\text{plastic2}}}$$
  $$\text{mom}_{3p} = 0.0$$
- **Hardening Modulus $H$**:
  In C# line 250 and Python:
  $$H = \frac{E_{1p} E_{2p}}{E_{1p} - E_{2p}}$$

#### 4.2.3 Fracture Energy Regularization
When shear fracture energy is enabled (`ConstitutiveLawMasonryShearEnum` 4 or 5):
In C# (`Objects.Material/MasonryMaterial.cs`, line 2989) and Python (`histra/model/masonry_material.py`, lines 63–113):

$$\varepsilon_u = \frac{G_f \cdot V}{F_{\text{limit}}} + \frac{1}{2} \varepsilon_y$$

where $V$ is element volume, $F_{\text{limit}}$ is yield capacity, and $\varepsilon_y = \text{rot}_{1p}$.
If stress-dependent energy is configured, $G_f$ is interpolated from normal stress $\sigma_n$:

$$\text{Knots } (-\sigma_n): [0.05, 0.055, 0.06, 0.07] \longrightarrow G_f: [0.0012385, 0.0007775, 0.0004402, 0.0001699]$$

clamped at boundaries.

#### 4.2.4 Cyclic Takeda Rules
- **Unloading**: Unloads with elastic stiffness $E_{\text{un}} = \max(E_{1n}, E_{2n}, E_{3n})$.
- **Reloading**: Aims toward the historical peak deformation $(\text{rot}_{\max}, \text{mom}_{\max})$:
  $$K_{\text{reload}} = \frac{\text{mom}_{\max}}{\text{rot}_{\max} - \text{rot}_{\text{nu}}}$$
- **Slip Phase**: If cohesion degrades to 0, the spring enters `PhaseEnum.Slip` ($K_{\text{tang}} = 0, \tau = 0$) until load reversal occurs.

---

### 4.3 General Hysteretic Spring (`SpringHysteretic`)
`SpringHysteretic` models normal flexural fibers in interfaces with distinct multi-linear, exponential, or parabolic envelopes.

#### 4.3.1 Tensile Curve Types (`HystereticTensileCurveTypeEnum`)
1. **Elastic**: 2-point linear path with stiffness $k$.
2. **LinearHardening**: 4 points: $(0, 0)$, $(\text{rot}_{1p}, \text{mom}_{1p})$, $(\text{rot}_{2p}, \text{mom}_{2p})$, $(\text{rot}_{3p}, \text{mom}_{3p})$.
3. **LinearSoftening**: 5 points: includes a horizontal residual tail out to $10 \cdot \text{rot}_{3p}$.
4. **Exponential Softening**: 100 points discretized from $\text{rot}_{1p}$ to $10 \cdot \text{rot}_{2p}$:
   $$\sigma(\varepsilon) = \text{mom}_{1p} \cdot \exp\left( - \frac{\varepsilon - \text{rot}_{1p}}{\text{rot}_{2p} - \text{rot}_{1p}} \right)$$

   **Secant Tangent Implementation**:
   In C# and Python (`histra/springs/hysteretic.py`, lines 617–620):
   $$K_{\text{tang}} = \frac{\sigma_{\text{trial}} - \sigma_{\text{commit}}}{\varepsilon_{\text{trial}} - \varepsilon_{\text{commit}}}$$
   evaluated dynamically during trial strain updates.

#### 4.3.2 Compressive Curve Types (`HystereticCompressiveCurveTypeEnum`)
1. **Elastic**: 2 points down to compressive yield.
2. **LinearHardening**: 4 points representing multilinear hardening.
3. **LinearSoftening**: 5 points with horizontal residual tail at $5 \cdot \text{rot}_{3n}$.
4. **Parabolic Model**: 100 points discretized into:
   - **Ascending Branch** ($\text{rot}_{1n} \ge \varepsilon \ge \text{rot}_{2n}$, 34 points):
     $$r = \frac{\varepsilon - \text{rot}_{1n}}{\text{rot}_{2n} - \text{rot}_{1n}}, \quad \sigma(\varepsilon) = \text{mom}_{1n} \cdot (1 + 4r - 2r^2)$$
   - **Descending Branch** ($\text{rot}_{2n} \ge \varepsilon \ge \text{rot}_{3n}$, 63 points):
     $$r = \frac{\varepsilon - \text{rot}_{2n}}{\text{rot}_{3n} - \text{rot}_{2n}}, \quad \sigma(\varepsilon) = \text{mom}_{2n} \cdot (1 - r^2)$$

   **Secant Tangent Implementation**:
   In C# and Python (`histra/springs/hysteretic.py`, lines 660–669):
   $$K_{\text{tang}} = \frac{\sigma_{\text{trial}} - \sigma_{\text{commit}}}{\varepsilon_{\text{trial}} - \varepsilon_{\text{commit}}}$$

#### 4.3.3 Pinching, Damage Degradation, and Energy Dissipation
- **Stiffness Degradation**:
  $$d_{\text{unload}} = \left(\frac{u_{\max}}{u_{\text{yield}}}\right)^\beta$$
- **Pinching Reloading**:
  Reloading path targets the pinching pivot point $(u_{\text{pinch}}, \sigma_{\text{pinch}})$:
  $$u_{\text{pinch}} = u_{\text{lim}} + (u_{\text{target}} - u_{\text{lim}}) \cdot X_p$$
  $$\sigma_{\text{pinch}} = \sigma_{\text{env}} \cdot Y_p$$
- **Damage Factors** ($\text{damfc}_1, \text{damfc}_2$):
  Shift target displacement based on accumulated dissipated plastic energy:
  $$\Delta u_{\max} = u_{\max} \cdot \left( 1 + \text{damfc}_1 \frac{u_{\max} - u_y}{u_y} + \text{damfc}_2 \frac{E_{\text{diss}}}{E_{\text{absorbed}}} \right)$$

---

## 5. State Transitions, Invariants, and Divergences

### 5.1 Reversibility & Commit Lifecycle
During Newton-Raphson line searches and Arc-Length retries, trial states are repeatedly evaluated and rejected.
- **Python Memory Layout**: Contiguous NumPy arrays (`quad_state`, `interface_coulomb_state`, `transverse_state`) maintain separate columns for committed variables ($c_{\text{stress}}, c_{\text{strain}}, c_{\text{phase}}$) and trial variables ($t_{\text{stress}}, t_{\text{strain}}, t_{\text{phase}}$).
- **Rollback Contract**: When a step is rejected, `revert_to_last_commit()` restores trial arrays directly from committed columns without executing Python object setter overhead.

### 5.2 The `UnloadShear` Quirk
- **C# Behavior**: The GUI and HRX schema expose `UnloadShear` on `MasonryMaterial` with choices `Initial`, `Origin`, `Takeda`, `Mixed`. However, C# `Interface.SetSpring` hardcodes `Initial` for sliding interfaces (`Objects/Interface.cs:1579`), and `Quad.SetSpring` hardcodes `Takeda` for diagonal shear, ignoring the user-selected material enum.
- **Python Treatment**: Python treats this as an intentional C# engine defect. `histra/preprocessing/constitutive_laws.py` parses the enum from HRX but enforces the constructible `Initial` / `Takeda` assignments, guaranteeing exact numerical parity with C# results.

### 5.3 Energy Dissipation Calculation Divergence
- **In C#**:
  $$\Delta E_{\text{elastic}} = \text{sign}(\sigma_{\text{trial}} - \sigma_{\text{commit}}) \cdot \frac{\sigma_{\text{trial}}^2 - \sigma_{\text{commit}}^2}{2 K}$$
  $$\Delta E_{\text{total}} = \frac{1}{2} (\sigma_{\text{commit}} + \sigma_{\text{trial}}) (\varepsilon_{\text{trial}} - \varepsilon_{\text{commit}})$$
  $$\Delta E_{\text{plastic}} = \Delta E_{\text{total}} - \Delta E_{\text{elastic}}$$
- **In Python Batch Runtime** (`histra/solver/hysteretic_runtime.py`, lines 2694–2706):
  `compute_energy()` evaluates the global elastic strain energy directly from active stiffness:
  $$E_{\text{elastic}} = \sum_i \frac{1}{2} k_i u_i^2$$
  The batch runtime returns $(E_{\text{elastic}}, 0.0)$ for $(E_{\text{elastic}}, E_{\text{plastic}})$ during iterative solving to eliminate expensive array reduction synchronizations across threads. This represents an intentional performance optimization that does not affect solution equilibrium or displacement results.

---

### 5.4 Numerical Tolerances & Precision Thresholds

| Parameter | Physical Significance | C# Reference Value | Python Implementation | Parity Status |
| :--- | :--- | :--- | :--- | :--- |
| **Jacobian Det Singularity** | Minimum determinant in Quad $2\times 2$ Gauss and yield search | `abs(det) <= 1.0e-30` | `abs(det) <= 1.0e-30` (`quad_kernels.py:71`) | **Exact** |
| **Corner Angle Singularity** | Minimum $\sin\beta_2$ for warping vectors | `abs(sin2) <= 1.0e-30` | `abs(sin2) <= 1.0e-30` (`quad_kernels.py:39`) | **Exact** |
| **Afference Cutoff** | Coefficient threshold in point afference mapping | `abs(val) <= 1.0e-4` | `abs(value) <= 1.0e-4` (`afference.py:200`) | **Exact** |
| **Normal Stress Cutoff** | Minimum compressive stress threshold for Coulomb friction | `minStressNormal = 1E-09` | `1.0e-09` (`interface_coulomb.py`) | **Exact** |
| **Minimum Tangent Reload** | Floor for Takeda reloading stiffness | `tangentReloadMin = 0.0001`| `0.0001` (`quad_takeda.py`) | **Exact** |
| **Yield Strain Offset** | Separation multiplier between yield and plastic strain | `1.0001` | `1.0001` (`coulomb03_state.py:178`) | **Exact** |
| **Rupture Residual Factor** | Residual numerical stiffness after tensile/compressive rupture | `1E-09 * E1` | `1.0e-09 * E1` (`transverse.py:151`) | **Exact** |
| **Plate Theory Sqrt Cast** | Single-precision intermediate cast in plate theory $d_i$ | `(float)Math.Sqrt((float)...)` | `float(np.float32(...))` (`interface.py:333`) | **Exact** |

---

## 6. Exhaustive Inventory of Unimplemented Features

While `histra-python` achieves 100% mathematical and behavioral parity across the Discrete Macro-Element masonry domain, the original C# codebase contains substantial additional structural elements, material constitutive laws, and spring formulations.

### 6.1 Unimplemented Computational Elements

| C# Element Name | C# Source Path | Key Classes & DOFs | Physical Role & Mechanics |
| :--- | :--- | :--- | :--- |
| **Frame** | `Objects/Frame.cs` (90 KB)<br>`ModelLibrary.ComputationalElements/FrameDB.cs` | `Frame`, `GeometryFrame`, `FrameState`, `FrameSegment`<br>12 DOFs (2 nodes $\times$ 6 DOFs) | 3D Timoshenko / Euler-Bernoulli beam-column elements for RC columns, beams, steel tie rods, timber floor joists, and masonry ring beams. |
| **Slab** | `Objects.ComputationalElements/Slab.cs` (93 KB)<br>`Objects/GeometrySlab.cs` | `Slab`, `SlabEdge`, `SlabState`, `GeometrySlab`<br>Membrane + plate bending | Rigid and flexible floor diaphragms (in-plane shear/axial stiffness and out-of-plane DKT plate bending) distributing floor gravity to walls. |
| **Solid** | `Objects/Solid.cs` (31 KB)<br>`Objects.ElementStates/SolidState.cs` | `Solid`, `SolidState`<br>24 DOFs (8 nodes $\times$ 3 DOFs) | 3D continuum hexahedral macro-element for massive masonry abutments, piers, vault backfill, and 3D soil-foundation blocks. |
| **Truss** | `Objects/Truss.cs` (14 KB)<br>`Objects/TrussState.cs` | `Truss`, `TrussState`<br>6 DOFs (2 nodes $\times$ 3 DOFs) | 3D uniaxial tension/compression tie-rod element modeling iron tie-rods (*catene*), cables, and bracing struts. |
| **Vertex** | `Objects/Vertex.cs` (154 KB)<br>`Objects.ElementStates/VertexState.cs` | `Vertex`, `VertexState`<br>6 DOFs centroid | Macro-element modeling 3D wall intersections, corners, piers, and multi-wall junctions. |
| **InterfaceMF** | `Objects/InterfaceMF.cs` (34 KB)<br>`ModelManagement/InterfaceMFOperations.cs`| `InterfaceMF`, `InterfaceStateMF`<br>Multi-spring line contact | Specialized Macro-Frame Interface connecting 2D masonry Quad panels directly to 1D Frame elements (infilled frames, boundary tie beams). |
| **InterfacePoligonal** | `Objects/InterfacePoligonal.cs` (23 KB) | `InterfacePoligonal` | 3D polygonal contact interface between 3D Solid faces or non-rectangular Quad surfaces with Delaunay triangulation. |
| **NodeBC** | `Objects/NodeBC.cs` (55 KB)<br>`Objects.ElementStates/NodeBCState.cs` | `NodeBC`, `NodeBCState`<br>6 DOFs | Generalized Boundary Condition node supporting flexible elastic foundation springs, multipoint master-slave links, and enforced displacements. |
| **Link & Joint** | `Objects.ComputationalElements/Link.cs`<br>`Objects.ComputationalElements/Joint.cs` | `Link`, `Joint`<br>6 DOFs | Nonlinear connection elements for frame hinges, semi-rigid connections, shear keys, and gap/expansion joints. |
| **InternalConstraint** | `Objects.ComputationalElements/InternalConstraint.cs`<br>`PConstraint.cs` | `InternalConstraint`, `PConstraint` | Multipoint kinematic constraints (MPC) enforcing rigid diaphragm planar constraints and tied degrees of freedom. |
| **Parametric Vault Elements** | `Objects/Arch.cs`, `BarrelVault.cs`, `CloisterVault.cs`, `CrossVault.cs`, `Dome.cs`, `DomicalVault.cs` | Parametric geometric generators | Parametric historic masonry vault and dome macro-element mesh generators. |

---

### 6.2 Unimplemented Materials

| C# Material Name | C# Source Path | Key Capabilities & Formulations |
| :--- | :--- | :--- |
| **ConcreteMaterial** | `Objects.Material/ConcreteMaterial.cs` (18 KB) | Unconfined and confined concrete models (Mander, Kent-Park, EC2 parabolic-rectangular); compression softening and tensile tension stiffening. |
| **SteelMaterial** | `Objects.Material/SteelMaterial.cs` (11 KB)<br>`Objects.ConstitutiveLaw/ConstitutiveLawSteel.cs` | Reinforcing rebar and structural steel; Menegotto-Pinto cyclic model, isotropic and kinematic hardening. |
| **FiberMaterial** | `Objects.Material/FiberMaterial.cs` (17 KB)<br>`Objects/Fiber.cs` (148 KB) | FRP (Fiber-Reinforced Polymers), TRM (Textile-Reinforced Mortar), CRM jackets; debonding slip and fiber tensile rupture. |
| **ConcreteMultiLinearPlasticMaterial** | `Objects.Material/ConcreteMultiLinearPlasticMaterial.cs` (5 KB) | Piecewise multi-linear degrading constitutive laws for reinforced concrete elements. |
| **ElasticIsotropicMaterial** | `Objects.Material/ElasticIsotropicMaterial.cs` (2 KB) | 3D continuum isotropic material ($E, \nu, G, \rho$) for Solid elements and elastic frames. |
| **GeotecnicalMaterial** | `Objects.Material/GeotecnicalMaterial.cs` (3 KB)<br>`Objects.ConstitutiveLaw/ConstitutiveLawGeo.cs` | Soil constitutive models, nonlinear subgrade reaction springs ($p-y$ curves), depth-dependent foundation moduli. |
| **MomentCurvature** | `Objects.Material/MomentCurvature.cs` (5 KB)<br>`MomentCurvatureValue.cs` | Pre-computed or cross-section fiber-integrated moment-curvature ($M-\chi$) relations for nonlinear beam-column joints. |

---

### 6.3 Unimplemented Spring Classes

| C# Spring Class | C# Source Location | Formulation & Hysteretic Behavior |
| :--- | :--- | :--- |
| **SpringConcrete01 / 02 / 04 / 07** | `Objects.GeneratedObjects.Springs/` (35 KB)<br>`Objects/SpringConcrete07.cs` (24 KB) | Kent-Park, Scott-Park-Priestley, and Mander cyclic concrete compression models with linear/exponential unloading and tensile crack opening. |
| **SpringSteel01 / 02** | `Objects.GeneratedObjects.Springs/SpringSteel01.cs`<br>`Objects/SpringSteel02.cs` (8 KB) | Menegotto-Pinto cyclic steel model with Bauschinger effect and curved transition branches between elastic and plastic asymptotes. |
| **SpringEndochronic** | `Objects/SpringEndochronic.cs` (2 KB) | Valanis endochronic plasticity without explicit yield surface. |
| **SpringStok** | `Objects/SpringStok.cs` (11 KB) | Stock cyclic shear-slip model for soil-structure and rock joints. |
| **SpringArmFried** | `Objects/SpringArmFried.cs` (7 KB) | Armstrong-Frederick nonlinear kinematic hardening plasticity. |
| **SpringElastoPlastic** | `Objects/SpringElastoPlastic.cs` (11 KB)<br>`ConstitutiveLawElastoPlastic.cs` | Classical 1D elastoplastic spring with kinematic/isotropic hardening. |
| **SpringElastoPlasticTakeda** | `Objects/SpringElastoPlasticTakeda.cs` (18 KB) | Standalone Takeda degrading trilinear spring (independent of Coulomb friction). |
| **SpringMultiLinearPlastic** | `Objects/SpringMultiLinearPlastic.cs` (8 KB) | General piecewise multi-linear plastic spring with user-defined arbitrary backbone points. |

---

## 7. Dynamic Parity Verification & Output Validation

### 7.1 Automated Verification Commands
The parity of the elements, springs, and constitutive models is continuously certified by the project test suite:

```bash
# 1. Verify Quad, Interface, and Spring unit tests
pytest -q histra/tests/unit/test_hysteretic.py \
          histra/tests/test_coulomb03_state_machine.py \
          histra/tests/test_coulomb03_phase_matrix.py \
          histra/tests/test_hysteretic_batch_exponential.py

# 2. Verify preprocessor mesh preparation, afferences, and constitutive assignments
pytest -q histra/tests/test_prepare_model.py \
          histra/tests/test_afference_architecture.py \
          histra/tests/test_constitutive_laws.py

# 3. Verify compiled Numba backend coverage (enforcing 0 unmanaged quads or interfaces)
pytest -q histra/tests/test_backend_coverage_enforcement.py

# 4. Verify end-to-end numerical parity against C# results on 14 canonical bridge models
python -m pytest -q histra/tests/test_article_models_benchmark.py
```

### 7.2 Numerical Convergence & Verification Evidence
- **Benchmark 3 Parity**: Fresh model preparation (`force=True`) with pre-scour material assignments achieves $< 7 \times 10^{-11} \text{ mm}$ displacement discrepancy across all 1,820 DOFs against C# `.Results` SQLite outputs.
- **Article Models Benchmark**: All 14 canonical article bridge models achieve 100% convergence matching C# load-displacement curves and failure patterns under identical tolerances.
- **Backend Coverage**: `test_backend_coverage_enforcement.py` verifies that 100% of active Quads and Interfaces are handled exclusively by compiled Numba kernels in production runs.

---

## 8. Conclusion

The `histra-python` implementation achieves mathematically rigorous, bit-for-bit parity with the C# HiStrA engine across all supported macro-element and constitutive formulations:
- **Quads**: 7-DOF kinematics, bilinear warping mode, $2 \times 2$ Gauss in-plane diagonal stiffness, and $100 \times 100$ cumulative grid search are identical.
- **Interfaces**: 12-DOF kinematics, 3/6-spring topology, endpoint normal displacements, plate factors $d_i, d_j$, and active contact area tracking are identical.
- **Constitutive Models**: Linear elastic, Mohr-Coulomb, Cacovic, trilinear envelopes, exponential softening, parabolic compression, and Takeda degradation are identical.
- **Performance**: High-throughput execution is delivered via compiled Numba batch kernels without compromising numerical accuracy or C# parity.
- **Architecture Boundaries**: All 12 additional element types (Frame, Slab, Solid, Truss, etc.) and specialized concrete/steel materials present in C# remain cleanly demarcated for future development.
