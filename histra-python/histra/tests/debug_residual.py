import sys
import os
sys.path.insert(0, r"C:\Users\mbonatte\Documents\Coding\histra-python")
import numpy as np
from histra.io.hr_loader import load_model
from histra.solver.nonlinear_solver import solve_static_nonlinear, ModelManager
from histra.types.linear_system import LinearSystem
from histra.solver.assembler import assemble_global_k, assemble_load_vector, get_restrained_dofs
from scipy.sparse.linalg import spsolve

hrx_path = r"C:\Users\mbonatte\Documents\Coding\histra-python\model-output\model.hrx"
model = load_model(hrx_path)

n = model.gdl
ls = LinearSystem(n)

# Assemble reference load
ModelManager._ptarget = assemble_load_vector(model, 1, 1)
ModelManager._fext = np.zeros(n)
ModelManager._pq = np.zeros(n)

# Assemble initial K
K = assemble_global_k(model, 0.0)
ls.k = K

# Find fixed DOFs
fixed = get_restrained_dofs(model, K=K)
free = sorted(set(range(n)) - fixed)
print(f"n={n}, nfree={len(free)}, nfixed={len(fixed)}")

# Solve duP = K^-1 * P
P = ModelManager._ptarget.copy()
for d in fixed:
    if d < n: P[d] = 0.0
duP = np.zeros(n)
duP[free] = spsolve(K[np.ix_(free, free)], P[free])
print(f"||duP|| = {np.linalg.norm(duP):.6e}")
print(f"||P|| = {np.linalg.norm(P):.6e}")

# Apply predictor: lambda=0.02, Du = 0.02 * duP
dlambda_pred = 0.02
Du = dlambda_pred * duP

# Zero element states
for quad in model.collections.quads.values():
    for i in range(len(quad.status.u)):
        quad.status.u[i] = 0.0
    if quad.spring is not None:
        quad.spring.revert_to_last_commit()
for intf in model.collections.interfaces.values():
    for i in range(len(intf.status.u)):
        intf.status.u[i] = 0.0

# Update domain with predictor Du
from histra.types.integrator_state import IntegratorState
state = IntegratorState()
ls.x = Du
ModelManager.update_domain(model, ls, state)

# Now compute residual: R = lambda*P - F_int
# Compute scattered internal forces (separated by quad and interface)
ls.set_zero_load()
for quad in model.collections.quads.values():
    if quad.spring is None or len(quad.aff) <= 6:
        continue
    quad.set_resisting_force()
    for entry in quad.aff[6]:
        gdl = entry.gdl - 1
        if 0 <= gdl < n:
            ls.sumb(gdl, -quad.status.f * entry.alfa)
quad_F = ls.b.copy()

# Interface
ls.set_zero_load()
for intf in model.collections.interfaces.values():
    intf.get_resisting_force(ls)
intf_F = ls.b.copy()

# Total scattered (-F_int)
total_F = quad_F + intf_F

# R = lambda*P - F_int = lambda*P + total_F (since total_F = -F_int)
R = total_F + dlambda_pred * P
for d in fixed:
    if d < n: R[d] = 0.0
R_norm = np.linalg.norm(R)
print(f"\nAfter predictor (lambda={dlambda_pred}):")
print(f"  ||R|| = {R_norm:.6e}")
print(f"  max|R_i| = {np.max(np.abs(R)):.6e}")

# Check: is K * Du_predictor = lambda * P?
u_total = Du.copy()
Ku = K @ u_total
lambdaP = dlambda_pred * P
for d in fixed:
    if d < n: Ku[d] = 0.0; lambdaP[d] = 0.0
print(f"\n  ||K*Du - lambda*P|| = {np.linalg.norm(Ku - lambdaP):.6e}")
print(f"  ||K*Du|| = {np.linalg.norm(Ku):.6e}")
print(f"  ||lambda*P|| = {np.linalg.norm(lambdaP):.6e}")

# Check: quad contribution to K@u
# K_quad · Du should = quad_F scattered (with sign flipped)
# Actually F_int_from_springs = -(K · Du), so K · Du = -quad_F (for quads)
print(f"\n  ||quad_F|| (scattered) = {np.linalg.norm(quad_F):.6e}")
print(f"  -quad_F (which should be K_quad·Du) = {np.linalg.norm(-quad_F):.6e}")
print(f"  ||intf_F|| (scattered) = {np.linalg.norm(intf_F):.6e}")
print("  ||K_quad_only@u|| = not computed separately")
print(f"  ||K@u (full)|| = {np.linalg.norm(K @ u_total):.6e}")
# Test: build K from quads only
K_quad_only = assemble_global_k.__wrapped__(model, 0.0) if hasattr(assemble_global_k, '__wrapped__') else None
# Skip the above, just check consistency for quads only
quad_K_u = np.zeros(n)
for quad in model.collections.quads.values():
    if quad.spring is None or len(quad.aff) <= 6:
        continue
    quad.compute_k(0.0)
    k_scalar = quad.status.k
    for ei in quad.aff[6]:
        gi = ei.gdl - 1
        for ej in quad.aff[6]:
            gj = ej.gdl - 1
            if 0 <= gi < n and 0 <= gj < n:
                quad_K_u[gi] += k_scalar * ei.alfa * ej.alfa * u_total[gj]
print(f"  ||quad_K@u|| = {np.linalg.norm(quad_K_u):.6e}")
print(f"  ||-quad_F|| vs ||quad_K@u|| = {np.linalg.norm(-quad_F):.6e} vs {np.linalg.norm(quad_K_u):.6e}")
print(f"  ||(-quad_F) - quad_K@u|| = {np.linalg.norm(-quad_F - quad_K_u):.6e}")

# For interfaces, F_int = K_int @ u (where K_int comes from assemble_global_k)
intf_K_u = K @ u_total - quad_K_u
print(f"  ||intf_K@u|| = {np.linalg.norm(intf_K_u):.6e}")
print(f"  ||-intf_F|| vs ||intf_K@u|| = {np.linalg.norm(-intf_F):.6e} vs {np.linalg.norm(intf_K_u):.6e}")
print(f"  ||(-intf_F) - intf_K@u|| = {np.linalg.norm(-intf_F - intf_K_u):.6e}")

# Check: F_int from get_resisting_force vs K*u
ls_fint = np.zeros(n)
for quad in model.collections.quads.values():
    if quad.spring is None or len(quad.aff) <= 6:
        continue
    quad.set_resisting_force()
    for entry in quad.aff[6]:
        gdl = entry.gdl - 1
        if 0 <= gdl < n:
            ls_fint[gdl] -= quad.status.f * entry.alfa
for intf in model.collections.interfaces.values():
    # Save ls.b, compute, read back
    old_b = ls.b.copy()
    ls.b[:] = 0.0
    intf.get_resisting_force(ls)
    ls_fint += ls.b
    ls.b[:] = old_b

print(f"\n  ||F_int (from springs)|| = {np.linalg.norm(ls_fint):.6e}")
print(f"  ||K*u (from assembly)|| = {np.linalg.norm(K @ u_total):.6e}")
print(f"  ||K*u + F_int|| = {np.linalg.norm(K @ u_total + ls_fint):.6e}")

# R_from_K = lambda*P - K@u, should be ~0 for predictor
R_from_K = dlambda_pred * P - K @ u_total
for d in fixed:
    if d < n: R_from_K[d] = 0.0
print(f"\n  ||R_from_K (lambda*P - K*u)|| = {np.linalg.norm(R_from_K):.6e}")
# R_from_springs = lambda*P + ls_fint (since ls_fint = -spring_forces)
R_from_springs = dlambda_pred * P + ls_fint
for d in fixed:
    if d < n: R_from_springs[d] = 0.0
print(f"  ||R_from_springs (lambda*P + F_int_springs)|| = {np.linalg.norm(R_from_springs):.6e}")
# The actual residual computed by form_unbalance
R_actual = ls.b.copy()
for d in fixed:
    if d < n: R_actual[d] = 0.0
print(f"  ||R_actual (ls.b)|| = {np.linalg.norm(R_actual):.6e}")

# Now apply Newton correction: du_star = K^-1 * R
R = ls.b.copy()
du_star = np.zeros(n)
du_star[free] = spsolve(K[np.ix_(free, free)], R[free])
print(f"  ||du_star|| = {np.linalg.norm(du_star):.6e}")

# Check which DOFs are most perturbed / have largest residual
print(f"  Largest |du_star_i| = {np.max(np.abs(du_star)):.6e}")
idx_largest_dus = int(np.argmax(np.abs(du_star)))
print(f"  At DOF {idx_largest_dus}, value={du_star[idx_largest_dus]:.6e}")

# Update domain with du_star
ls.x = du_star
ModelManager.update_domain(model, ls, state)

# Compute new residual
ls.set_zero_load()
for quad in model.collections.quads.values():
    if quad.spring is None or len(quad.aff) <= 6:
        continue
    quad.set_resisting_force()
    for entry in quad.aff[6]:
        gdl = entry.gdl - 1
        if 0 <= gdl < n:
            ls.sumb(gdl, -quad.status.f * entry.alfa)
for intf in model.collections.interfaces.values():
    intf.get_resisting_force(ls)

ls.b += dlambda_pred * P
for d in fixed:
    if d < n: ls.b[d] = 0.0

R_norm_new = np.linalg.norm(ls.b)
print("\nAfter Newton correction (du_star):")
print(f"  ||R|| = {R_norm_new:.6e}")
print(f"  max|R_i| = {np.max(np.abs(ls.b)):.6e}")
print(f"  Ratio: {R_norm_new/R_norm:.6f}")
