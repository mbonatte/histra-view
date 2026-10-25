"""Quad diagonal-spring geometry and stiffness (C# ``Quad``).

Owns the diagonal-spring kinematic transformation (``dAlfa2dDiag`` /
``dDiag2dAlfa``, ``cosAlfa``), ``computeK`` and the C#
``GetDiagonalStiffness`` port. The methods live on a mixin so ``Quad`` remains
the single public dataclass; every body is verbatim from the original class.
"""
from __future__ import annotations

from math import sqrt

import numpy as np


class QuadGeometryMixin:
    """Diagonal-spring kinematics, tangent stiffness and C# stiffness port."""

    __slots__ = ()


    def d_alfa_2d_diag(self) -> float:
        r"""Kinematic factor from 7th DOF (warping amplitude) to diagonal spring strain.

        Corresponds to C# ``DAlfa2DDiag()``:

            = Length[0] * Length[3] * Sin[0] / Diago[1]
        """
        if self.diago[1] == 0.0:
            return 0.0
        return self.length[0] * self.length[3] * self.sin[0] / self.diago[1]

    def d_diag_2d_alfa(self) -> float:
        """Inverse of :meth:`d_alfa_2d_diag`."""
        v = self.d_alfa_2d_diag()
        return 1.0 / v if v != 0.0 else 0.0

    @property
    def cos_alfa(self) -> float:
        """Literal port of C# ``Quad.cosAlfa``.

        The property is a law-of-cosines quantity based on ``Diago[0]`` and
        can legitimately be negative for distorted quadrilaterals.  Its sign
        is part of the diagonal Coulomb friction law.
        """
        denominator = 2.0 * self.length[0] * self.diago[0]
        if denominator == 0.0:
            return 0.0
        return (
            self.length[0] * self.length[0]
            + self.diago[0] * self.diago[0]
            - self.length[1] * self.length[1]
        ) / denominator

    # ── ComputeK ─────────────────────────────────────────────────────────────

    def compute_k(self, alfa: float = 0.0) -> float:
        """Diagonal (7th DOF) stiffness.

        C# ``ComputeK``:

            k = Spring.GetK(alfa)
            Status.K = k * DAlfa2DDiag()^2
        """
        if self.spring is None:
            return 0.0
        from histra.preprocessing.csharp_math import csharp_pow

        k = self.spring.get_k(alfa)
        dalfa = self.d_alfa_2d_diag()
        self.status.k = k * csharp_pow(dalfa, 2.0)
        return self.status.k

    # ── GetDiagonalStiffness ─────────────────────────────────────────────────

    def get_diagonal_stiffness(self, E: float, G: float) -> float:
        """Full in-plane stiffness projected onto the diagonal (7th) DOF.

        C# ``GetDiagonalStiffness(E, G)``.

        Performs a 2×2 Gauss-Legendre integration of the plane-stress
        constitutive matrix B^T·D·B over the quadrilateral mid-surface,
        then projects through the warping displacement vector.

        Parameters
        ----------
        E : Young's modulus.
        G : Shear modulus.
        """
        from histra.preprocessing.csharp_math import csharp_pow

        nu = E / (2.0 * G) - 1.0           # Poisson ratio
        lam = E * nu / (2.0 * (1.0 + 2.0 * nu))  # λ = νE/((1+ν)(1-2ν)) – first Lamé param

        # Local node coordinates (X, Y)
        L0, L1, L3 = self.length[0], self.length[1], self.length[3]
        Cos0, Cos1 = self.cos[0], self.cos[1]
        Sin0, Sin1 = self.sin[0], self.sin[1]
        X = [ -L0 / 2.0,  L0 / 2.0,
               L0 / 2.0 - L1 * Cos1,  -L0 / 2.0 + L3 * Cos0 ]
        Y = [ 0.0, 0.0,  L1 * Sin1,  L3 * Sin0 ]

        # Gauss points (2×2)
        gp = csharp_pow(3.0, 0.5) / 3.0
        gauss = [gp, -gp]

        # Accumulated stiffness coefficients (symmetric 4×4 layout)
        num3 = num4 = num5 = num6 = 0.0
        num7 = num8 = num9 = 0.0
        num10 = num11 = num12 = 0.0
        num3 = num4 = num5 = num6 = 0.0
        num7 = num8 = num9 = 0.0
        num10 = num11 = num12 = 0.0

        # Gauss-point arrays (2 × 2)
        array3 = [[0.0]*2 for _ in range(2)]   # thickness interpolated
        array4 = [[0.0]*2 for _ in range(2)]
        array5 = [[0.0]*2 for _ in range(2)]
        array6 = [[0.0]*2 for _ in range(2)]
        array7 = [[0.0]*2 for _ in range(2)]
        array8 = [[0.0]*2 for _ in range(2)]
        array9 = [[0.0]*2 for _ in range(2)]
        array10 = [[0.0]*2 for _ in range(2)]
        array11 = [[0.0]*2 for _ in range(2)]
        array12 = [[0.0]*2 for _ in range(2)]
        array13 = [[0.0]*2 for _ in range(2)]
        array14 = [[0.0]*2 for _ in range(2)]
        array15 = [[0.0]*2 for _ in range(2)]
        array16 = [[0.0]*2 for _ in range(2)]
        array17 = [[0.0]*2 for _ in range(2)]
        array18 = [[0.0]*2 for _ in range(2)]
        array19 = [[0.0]*2 for _ in range(2)]
        array20 = [[0.0]*2 for _ in range(2)]
        array21 = [[0.0]*2 for _ in range(2)]
        array22 = [[0.0]*2 for _ in range(2)]
        array23 = [[0.0]*2 for _ in range(2)]
        array24 = [[0.0]*2 for _ in range(2)]
        array25 = [[0.0]*2 for _ in range(2)]
        array26 = [[0.0]*2 for _ in range(2)]
        array27 = [[0.0]*2 for _ in range(2)]
        array28 = [[0.0]*2 for _ in range(2)]
        array29 = [[0.0]*2 for _ in range(2)]
        array30 = [[0.0]*2 for _ in range(2)]
        array31 = [[0.0]*2 for _ in range(2)]
        array32 = [[0.0]*2 for _ in range(2)]
        array33 = [[0.0]*2 for _ in range(2)]
        array34 = [[0.0]*2 for _ in range(2)]

        for i in range(2):
            for j in range(2):
                xi = gauss[i]
                eta = gauss[j]

                # C# array3 = interpolated thickness
                array3[i][j] = (self.thickness[0] * ((1.0 - xi) * (1.0 - eta) / 4.0) +
                                self.thickness[1] * ((1.0 + xi) * (1.0 - eta) / 4.0) +
                                self.thickness[2] * ((1.0 + xi) * (1.0 + eta) / 4.0) +
                                self.thickness[3] * ((1.0 - xi) * (1.0 + eta) / 4.0))

                # array4..array11: shape function derivatives at xi,eta
                # These correspond to dN_k/dxi and dN_k/deta for each of the 4 nodes
                # but the C# code evaluates them in a specific pattern.

                # C# array4 = -(1-eta)/4  (dN0/dxi)
                # array5 =  (1-eta)/4     (dN1/dxi)
                # array6 =  (1+eta)/4     (dN2/dxi)
                # array7 = -(1+eta)/4     (dN3/dxi)
                array4[i][j] = -(1.0 - eta) / 4.0
                array5[i][j] =  (1.0 - eta) / 4.0
                array6[i][j] =  (1.0 + eta) / 4.0
                array7[i][j] = -(1.0 + eta) / 4.0

                # array8 = -(1-xi)/4      (dN0/deta)
                # array9 = -(1+xi)/4      (dN1/deta)
                # array10 = (1+xi)/4      (dN2/deta)
                # array11 = (1-xi)/4      (dN3/deta)
                array8[i][j] = -(1.0 - xi) / 4.0
                array9[i][j] = -(1.0 + xi) / 4.0
                array10[i][j] = (1.0 + xi) / 4.0
                array11[i][j] = (1.0 - xi) / 4.0

                # Jacobian rows: dX/dxi, dX/deta and dY/dxi, dY/deta
                # array12 = dX/dxi, array13 = dX/deta
                # array14 = dY/dxi, array15 = dY/deta
                array12[i][j] = (X[0] * array4[i][j] + X[1] * array5[i][j] +
                                 X[2] * array6[i][j] + X[3] * array7[i][j])
                array13[i][j] = (X[0] * array8[i][j] + X[1] * array9[i][j] +
                                 X[2] * array10[i][j] + X[3] * array11[i][j])
                array14[i][j] = (Y[0] * array4[i][j] + Y[1] * array5[i][j] +
                                 Y[2] * array6[i][j] + Y[3] * array7[i][j])
                array15[i][j] = (Y[0] * array8[i][j] + Y[1] * array9[i][j] +
                                 Y[2] * array10[i][j] + Y[3] * array11[i][j])

                # Jacobian determinant
                array16[i][j] = (array12[i][j] * array15[i][j] -
                                 array13[i][j] * array14[i][j])

                if abs(array16[i][j]) < 1e-30:
                    continue

                # Inverse Jacobian
                array17[i][j] =  array15[i][j] / array16[i][j]   # dxi/dX
                array18[i][j] = -array14[i][j] / array16[i][j]   # deta/dX
                array19[i][j] = -array13[i][j] / array16[i][j]   # dxi/dY
                array20[i][j] =  array12[i][j] / array16[i][j]   # deta/dY

                # dN_i/dX, dN_i/dY assembled into "B" columns
                # array21 = dN2/dX, array22 = dN3/dX
                # array23 = dN2/dY, array24 = dN3/dY
                # (only nodes 2 and 3 have non-zero warping contribution)
                # Wait — the C# code computes for all 4 "columns", but actually:
                # array21 = dN1/dX * (1+eta)/4 + dN2/dX * (1+xi)/4  (??)
                # Let's re-read the C# more carefully.

                # C# array21 = array17 * (1+eta)/4 + array18 * (1+xi)/4
                # This is NOT a shape function derivative — it's a B-matrix
                # component for the warping DOF.
                # Actually looking at the C# code:
                #   array21[i,j] = array17[i,j] * (1+eta)/4 + array18[i,j] * (1+xi)/4
                # These are the terms ∂N_k/∂x · ψ_k where ψ is the warping shape.

                array21[i][j] = (array17[i][j] * (1.0 + eta) / 4.0 +
                                 array18[i][j] * (1.0 + xi) / 4.0)
                array22[i][j] = (-array17[i][j] * (1.0 + eta) / 4.0 +
                                 array18[i][j] * (1.0 - xi) / 4.0)
                array23[i][j] = (array19[i][j] * (1.0 + eta) / 4.0 +
                                 array20[i][j] * (1.0 + xi) / 4.0)
                array24[i][j] = (-array19[i][j] * (1.0 + eta) / 4.0 +
                                 array20[i][j] * (1.0 - xi) / 4.0)

                # Constitutive contributions to the 4×4 stiffness block
                # (actually 2×2 since we only have 2 warping modes)
                # These are B^T·D·B integrated over the element.
                array25[i][j] = ((lam + 2.0 * G) * csharp_pow(array21[i][j], 2.0) +
                                 G * csharp_pow(array23[i][j], 2.0))
                array26[i][j] = ((lam + G) * array21[i][j] * array23[i][j])
                array27[i][j] = ((lam + 2.0 * G) * array21[i][j] * array22[i][j] +
                                 G * array23[i][j] * array24[i][j])
                array28[i][j] = (lam * array21[i][j] * array24[i][j] +
                                 G * array23[i][j] * array22[i][j])
                array29[i][j] = ((lam + 2.0 * G) * csharp_pow(array23[i][j], 2.0) +
                                 G * csharp_pow(array21[i][j], 2.0))
                array30[i][j] = (lam * array23[i][j] * array22[i][j] +
                                 G * array21[i][j] * array24[i][j])
                array31[i][j] = ((lam + 2.0 * G) * array23[i][j] * array24[i][j] +
                                 G * array21[i][j] * array22[i][j])
                array32[i][j] = ((lam + 2.0 * G) * csharp_pow(array22[i][j], 2.0) +
                                 G * csharp_pow(array24[i][j], 2.0))
                array33[i][j] = ((lam + G) * array22[i][j] * array24[i][j])
                array34[i][j] = ((lam + 2.0 * G) * csharp_pow(array24[i][j], 2.0) +
                                 G * csharp_pow(array22[i][j], 2.0))

                # Accumulate weighted by thickness * detJ
                # Match source thickness * stiffness contribution * detJ order.
                num3 += array3[i][j] * array25[i][j] * array16[i][j]
                num4 += array3[i][j] * array26[i][j] * array16[i][j]
                num5 += array3[i][j] * array27[i][j] * array16[i][j]
                num6 += array3[i][j] * array28[i][j] * array16[i][j]
                num7 += array3[i][j] * array29[i][j] * array16[i][j]
                num8 += array3[i][j] * array30[i][j] * array16[i][j]
                num9 += array3[i][j] * array31[i][j] * array16[i][j]
                num10 += array3[i][j] * array32[i][j] * array16[i][j]
                num11 += array3[i][j] * array33[i][j] * array16[i][j]
                num12 += array3[i][j] * array34[i][j] * array16[i][j]

        # Warping displacement vector (C# array2)
        Sin2, Sin3 = self.sin[2], self.sin[3]
        Cos2, Cos0 = self.cos[2], self.cos[0]
        a = [0.0] * 4
        if abs(Sin2) > 1e-30:
            a[0] = -L3 * Sin3 * Sin1 / Sin2
            a[1] = -L3 * Sin3 * Cos1 / Sin2
        else:
            a[0] = a[1] = 0.0
        a[2] = -L3 * Sin0
        a[3] =  L3 * Cos0

        # Quadratic form a^T · [stiffness_4x4] · a
        S = (num3 * csharp_pow(a[0], 2.0) + num7 * csharp_pow(a[1], 2.0) + num10 * csharp_pow(a[2], 2.0) + num12 * csharp_pow(a[3], 2.0) +
             2.0 * num4 * a[0] * a[1] +
             2.0 * num5 * a[0] * a[2] +
             2.0 * num6 * a[0] * a[3] +
             2.0 * num8 * a[1] * a[2] +
             2.0 * num9 * a[1] * a[3] +
             2.0 * num11 * a[2] * a[3])

        # Scale by (d_diag_2d_alfa)^2
        scale = self.d_diag_2d_alfa()
        return scale * scale * S

    # ── SetNonLinearProperties ───────────────────────────────────────────────
