"""Pure Quad yield-search kernels (C# ``Quad.SetNonLinearProperties``).

The C# routine evaluates both principal stresses for each of two opposite unit
diagonal deformations. Its extrema are intentionally cumulative across the two
passes; the first and second returned yield forces can therefore have
different magnitudes. A previous Python simplification used one symmetric
extrema pair and overestimated the Quad cohesion by up to two orders of
magnitude — do not "simplify" the double pass.

``quad_yield_search`` is the compiled kernel; ``quad_yield_search_scalar`` is
the exact scalar fallback and test oracle with the identical operation order.
"""
from __future__ import annotations

from typing import Sequence

from histra._framework_math import csharp_pow

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - scalar fallback remains available
    njit = None



if njit is not None:
    @njit(cache=True, nogil=True)
    def _quad_yield_search_kernel(
        k, E, G, Fyt, Fyc, dalfa,
        L0, L1, L3, cos0, cos1, sin0, sin1, sin2, sin3,
    ):
        nu = E / (2.0 * G) - 1.0
        lam = E * nu / (2.0 * (1.0 + 2.0 * nu))
        x0, x1 = -L0/2.0, L0/2.0
        x2, x3 = L0/2.0-L1*cos1, -L0/2.0+L3*cos0
        y0, y1, y2, y3 = 0.0, 0.0, L1*sin1, L3*sin0
        if abs(sin2) <= 1.0e-30:
            return 0.0, 0.0
        w0 = -L3*sin3*sin1/sin2
        w1 = -L3*sin3*cos1/sin2
        w2 = -L3*sin0
        w3 = -L3*cos0
        max_principal = 0.0
        min_principal = 0.0
        result0 = 0.0
        result1 = 0.0
        n = 100
        for pass_index in range(2):
            direction = 1.0 if pass_index == 0 else -1.0
            pass_min = 0.0
            pass_max = 0.0
            for row in range(1, n+1):
                eta = -1.0 + 2.0/n*(row-1.0) + 1.0/n
                dxi0 = -(1.0-eta)/4.0
                dxi1 = (1.0-eta)/4.0
                dxi2 = (1.0+eta)/4.0
                dxi3 = -(1.0+eta)/4.0
                for col in range(1, n+1):
                    xi = -1.0 + 2.0/n*(col-1.0) + 1.0/n
                    deta0 = -(1.0-xi)/4.0
                    deta1 = -(1.0+xi)/4.0
                    deta2 = (1.0+xi)/4.0
                    deta3 = (1.0-xi)/4.0
                    j11=x0*dxi0+x1*dxi1+x2*dxi2+x3*dxi3
                    j12=x0*deta0+x1*deta1+x2*deta2+x3*deta3
                    j21=y0*dxi0+y1*dxi1+y2*dxi2+y3*dxi3
                    j22=y0*deta0+y1*deta1+y2*deta2+y3*deta3
                    det=j11*j22-j12*j21
                    if abs(det)<=1.0e-30:
                        continue
                    inv11=j22/det; inv12=-j21/det; inv21=-j12/det; inv22=j11/det
                    b1x=inv11*(1.0+eta)/4.0+inv12*(1.0+xi)/4.0
                    b2x=-inv11*(1.0+eta)/4.0+inv12*(1.0-xi)/4.0
                    b1y=inv21*(1.0+eta)/4.0+inv22*(1.0+xi)/4.0
                    b2y=-inv21*(1.0+eta)/4.0+inv22*(1.0-xi)/4.0
                    eps_x=direction*(w0*b1x+w2*b2x)
                    eps_y=direction*(w1*b1y+w3*b2y)
                    gamma=direction*(w0*b1y+w1*b1x+w2*b2y+w3*b2x)
                    sx=lam*(eps_x+eps_y)+2.0*G*eps_x
                    sy=lam*(eps_x+eps_y)+2.0*G*eps_y
                    tau=G*gamma
                    avg=(sx+sy)/2.0
                    radius=csharp_pow(csharp_pow((sx-sy)/2.0,2.0)+csharp_pow(tau,2.0),0.5)
                    pmax=avg+radius; pmin=avg-radius
                    if pmin<pass_min: pass_min=pmin
                    if pmax>pass_max: pass_max=pmax
            if pass_min<min_principal: min_principal=pass_min
            if pass_max>max_principal: max_principal=pass_max
            value=0.0
            if max_principal != 0.0 and min_principal != 0.0:
                scale=direction*min(abs(Fyt/max_principal),abs(Fyc/min_principal))
                value=k*(dalfa*scale)
            if pass_index==0: result0=value
            else: result1=value
        return result0, result1
else:
    _quad_yield_search_kernel = None


def quad_yield_search_scalar(
    k: float, E: float, G: float, Fyt: float, Fyc: float, dalfa: float,
    L0: float, L1: float, L3: float, cos0: float, cos1: float,
    sin0: float, sin1: float, sin2: float, sin3: float,
) -> tuple[float, float]:
    """Scalar fallback: exact operation order of the compiled kernel."""
    nu = E / (2.0 * G) - 1.0
    lam = E * nu / (2.0 * (1.0 + 2.0 * nu))

    x = [-L0 / 2.0, L0 / 2.0, L0 / 2.0 - L1 * cos1, -L0 / 2.0 + L3 * cos0]
    y = [0.0, 0.0, L1 * sin1, L3 * sin0]

    # These are C# num4 (largest principal stress) and num5 (smallest).
    # They are deliberately not reset between the two deformation signs.
    max_principal = 0.0
    min_principal = 0.0
    result = [0.0, 0.0]
    n = 100

    if abs(sin2) <= 1.0e-30:
        return 0.0, 0.0
    w0 = -L3 * sin3 * sin1 / sin2
    w1 = -L3 * sin3 * cos1 / sin2
    w2 = -L3 * sin0
    # C# SetNonLinearProperties uses a negative fourth warping term
    # here (unlike GetDiagonalStiffness, whose projection vector stores
    # the positive value). Preserve that source-level sign asymmetry.
    w3 = -L3 * cos0

    for pass_index in range(2):
        direction = (-1.0) ** pass_index
        pass_min = 0.0
        pass_max = 0.0
        for flat_index in range(n * n):
            row = flat_index // n + 1
            col = flat_index + 1 - (row - 1) * n
            xi = -1.0 + 2.0 / n * (col - 1.0) + 1.0 / n
            eta = -1.0 + 2.0 / n * (row - 1.0) + 1.0 / n

            dxi = [
                -(1.0 - eta) / 4.0,
                (1.0 - eta) / 4.0,
                (1.0 + eta) / 4.0,
                -(1.0 + eta) / 4.0,
            ]
            deta = [
                -(1.0 - xi) / 4.0,
                -(1.0 + xi) / 4.0,
                (1.0 + xi) / 4.0,
                (1.0 - xi) / 4.0,
            ]
            j11 = x[0]*dxi[0]+x[1]*dxi[1]+x[2]*dxi[2]+x[3]*dxi[3]
            j12 = x[0]*deta[0]+x[1]*deta[1]+x[2]*deta[2]+x[3]*deta[3]
            j21 = y[0]*dxi[0]+y[1]*dxi[1]+y[2]*dxi[2]+y[3]*dxi[3]
            j22 = y[0]*deta[0]+y[1]*deta[1]+y[2]*deta[2]+y[3]*deta[3]
            det = j11 * j22 - j12 * j21
            if abs(det) <= 1.0e-30:
                continue

            inv11 = j22 / det
            inv12 = -j21 / det
            inv21 = -j12 / det
            inv22 = j11 / det

            b1x = inv11 * (1.0 + eta) / 4.0 + inv12 * (1.0 + xi) / 4.0
            b2x = -inv11 * (1.0 + eta) / 4.0 + inv12 * (1.0 - xi) / 4.0
            b1y = inv21 * (1.0 + eta) / 4.0 + inv22 * (1.0 + xi) / 4.0
            b2y = -inv21 * (1.0 + eta) / 4.0 + inv22 * (1.0 - xi) / 4.0

            eps_x = direction * (w0 * b1x + w2 * b2x)
            eps_y = direction * (w1 * b1y + w3 * b2y)
            gamma_xy = direction * (
                w0 * b1y + w1 * b1x + w2 * b2y + w3 * b2x
            )
            sigma_x = lam * (eps_x + eps_y) + 2.0 * G * eps_x
            sigma_y = lam * (eps_x + eps_y) + 2.0 * G * eps_y
            tau = G * gamma_xy
            average = (sigma_x + sigma_y) / 2.0
            radius = csharp_pow(csharp_pow((sigma_x-sigma_y)/2.0,2.0)+csharp_pow(tau,2.0),0.5)
            principal_max = average + radius
            principal_min = average - radius
            if principal_min < pass_min:
                pass_min = principal_min
            if principal_max > pass_max:
                pass_max = principal_max

        if pass_min < min_principal:
            min_principal = pass_min
        if pass_max > max_principal:
            max_principal = pass_max

        if max_principal == 0.0 or min_principal == 0.0:
            result[pass_index] = 0.0
        else:
            scale = direction * min(
                abs(Fyt / max_principal),
                abs(Fyc / min_principal),
            )
            result[pass_index] = k * (dalfa * scale)

    return result[0], result[1]


def quad_yield_search(
    k: float, E: float, G: float, Fyt: float, Fyc: float, dalfa: float,
    L0: float, L1: float, L3: float, cos0: float, cos1: float,
    sin0: float, sin1: float, sin2: float, sin3: float,
) -> tuple[float, float]:
    """Dispatch to the compiled kernel, falling back to the scalar oracle."""
    if _quad_yield_search_kernel is not None:
        return _quad_yield_search_kernel(
            float(k), float(E), float(G), float(Fyt), float(Fyc),
            float(dalfa),
            float(L0), float(L1), float(L3),
            float(cos0), float(cos1),
            float(sin0), float(sin1), float(sin2), float(sin3),
        )
    return quad_yield_search_scalar(
        k, E, G, Fyt, Fyc, dalfa,
        L0, L1, L3, cos0, cos1, sin0, sin1, sin2, sin3,
    )
