const interfaceSlots = new WeakMap();
function slotFor(analysis, key) {
  let slots = interfaceSlots.get(analysis);
  if (!slots) { slots = new Map(analysis.interfaceOrder.map((id,index) => [Number(id),index])); interfaceSlots.set(analysis,slots); }
  return slots.get(Number(key));
}

export function resultantAt(analysis, index, key) {
  const slot = slotFor(analysis, key);
  const row = analysis.steps[index]?.interfaceResultants?.[slot];
  if (!row || row.length !== 6 || !row.every(Number.isFinite)) return null;
  return { forces: row.slice(0, 3), moments: row.slice(3, 6) };
}

export function normalTolerance(analysis, key) {
  const slot = slotFor(analysis, key);
  const peak = Math.max(...analysis.steps.map(s => Math.abs(s.interfaceResultants[slot][1])));
  return Math.max(1e-8, peak * 1e-8);
}

export function eccentricities(resultant, tolerance) {
  if (!resultant || Math.abs(resultant.forces[1]) <= tolerance) return null;
  const ex = resultant.moments[2] / resultant.forces[1];
  const ey = resultant.moments[0] / resultant.forces[1];
  return Number.isFinite(ex) && Number.isFinite(ey) ? { ex, ey, compression: resultant.forces[1] < 0 } : null;
}

// Native moments use offsets from (Length/2, 0) in the intrinsic interface
// plane. Its intrinsic Y direction maps to reference_e3, with the positive
// sign used by C# CalcolaRisultanti (rather than an assumed r × F convention).
export function thrustPosition(geometry, eccentricity) {
  if (!eccentricity?.compression) return null;
  return geometry.reference_origin.map((v, i) => v
    + (geometry.length / 2 + eccentricity.ex) * geometry.reference_e1[i]
    + eccentricity.ey * geometry.reference_e3[i]);
}
