// Base coordinates always remain immutable: changing step or scale cannot compound motion.
export function deformedPoints(nodes, displacement, scale) {
  if (!Number.isFinite(scale) || scale < 0) throw new Error('Deformation scale must be nonnegative.');
  if (nodes.length !== displacement.length) throw new Error('Displacement and mesh node counts differ.');
  return nodes.map((node, i) => node.point.map((x, axis) => {
    const u = displacement[i][axis];
    if (!Number.isFinite(u)) throw new Error('Invalid saved displacement.');
    return x + scale * u;
  }));
}

export function decodeQuadDisplacements(encoded, quadCount) {
  const expected = quadCount * 12;
  if (encoded instanceof Float32Array) {
    if (encoded.length !== expected || !encoded.every(Number.isFinite)) {
      throw new Error('Invalid Quad vertex displacement buffer.');
    }
    return encoded;
  }
  if (Array.isArray(encoded)) {
    if (encoded.length !== quadCount) throw new Error('Quad displacement count differs from mesh Quad count.');
    const out = new Float32Array(expected);
    let offset = 0;
    for (let q = 0; q < quadCount; q++) {
      const vertices = encoded[q];
      if (!Array.isArray(vertices) || vertices.length !== 4) throw new Error('Each Quad requires 4 vertex displacements.');
      for (let v = 0; v < 4; v++) {
        const u = vertices[v];
        if (!Array.isArray(u) || u.length !== 3) throw new Error('Each Quad vertex requires 3 displacement components.');
        for (let a = 0; a < 3; a++) {
          const val = Number(u[a]);
          if (!Number.isFinite(val)) throw new Error('Invalid saved Quad displacement.');
          out[offset++] = val;
        }
      }
    }
    return out;
  }
  if (typeof encoded === 'string') {
    const raw = atob(encoded);
    if (raw.length !== expected * 4) throw new Error('Quad displacement byte length does not match mesh Quad count.');
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const view = new DataView(bytes.buffer);
    const out = new Float32Array(expected);
    for (let i = 0; i < expected; i++) {
      const val = view.getFloat32(i * 4, true);
      if (!Number.isFinite(val)) throw new Error('Invalid saved Quad displacement.');
      out[i] = val;
    }
    return out;
  }
  throw new Error('Unsupported Quad displacement format.');
}

// Reconstructs independent per-Quad corner coordinates so adjacent Quads can separate or slide at interfaces.
export function deformedQuadPoints(baseQuadPoints, quadDisplacements, scale, phase = 1) {
  if (!Number.isFinite(scale) || scale < 0) throw new Error('Deformation scale must be nonnegative.');
  if (!Number.isFinite(phase)) throw new Error('Deformation phase must be finite.');
  const quadCount = baseQuadPoints.length;
  const flat = decodeQuadDisplacements(quadDisplacements, quadCount);
  const factor = scale * phase;
  const result = new Array(quadCount);
  let offset = 0;
  for (let q = 0; q < quadCount; q++) {
    const base = baseQuadPoints[q];
    if (!Array.isArray(base) || base.length !== 4) throw new Error('Each Quad requires 4 base corner points.');
    const corners = new Array(4);
    for (let v = 0; v < 4; v++) {
      const pt = base[v];
      const x = Array.isArray(pt) ? pt[0] : pt.x;
      const y = Array.isArray(pt) ? pt[1] : pt.y;
      const z = Array.isArray(pt) ? pt[2] : pt.z;
      corners[v] = [
        x + factor * flat[offset],
        y + factor * flat[offset + 1],
        z + factor * flat[offset + 2],
      ];
      offset += 3;
    }
    result[q] = corners;
  }
  return result;
}

export function displacementColormap(t) {
  t = Math.max(0, Math.min(1, Number(t) || 0));
  const stops = [
    { t: 0.00, r: 0.10, g: 0.20, b: 0.85 },
    { t: 0.25, r: 0.10, g: 0.75, b: 0.85 },
    { t: 0.50, r: 0.20, g: 0.85, b: 0.30 },
    { t: 0.75, r: 0.95, g: 0.85, b: 0.10 },
    { t: 1.00, r: 0.90, g: 0.15, b: 0.10 },
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    if (t <= stops[i + 1].t) {
      const f = (t - stops[i].t) / (stops[i + 1].t - stops[i].t);
      return [
        stops[i].r + f * (stops[i + 1].r - stops[i].r),
        stops[i].g + f * (stops[i + 1].g - stops[i].g),
        stops[i].b + f * (stops[i + 1].b - stops[i].b)
      ];
    }
  }
  const last = stops[stops.length - 1];
  return [last.r, last.g, last.b];
}

export function computeDisplacementContours({
  quads,
  nodeKeyToIndex,
  nodeDisplacements,
  quadDisplacements,
  component = 'magnitude',
  phase = 1,
  makeColor = (r, g, b) => [r, g, b]
}) {
  const quadCount = quads.length;
  const flatQuadDisp = quadDisplacements ? decodeQuadDisplacements(quadDisplacements, quadCount) : null;
  const values = new Float32Array(quadCount * 4);

  let min = Infinity;
  let max = -Infinity;

  let offset = 0;
  for (let q = 0; q < quadCount; q++) {
    const quad = quads[q];
    for (let v = 0; v < 4; v++) {
      let ux = 0, uy = 0, uz = 0;
      if (flatQuadDisp) {
        ux = flatQuadDisp[offset] * phase;
        uy = flatQuadDisp[offset + 1] * phase;
        uz = flatQuadDisp[offset + 2] * phase;
      } else if (nodeDisplacements && nodeKeyToIndex) {
        const nk = quad.nodeKeys?.[v];
        const nIdx = nodeKeyToIndex.get(String(nk)) ?? nodeKeyToIndex.get(Number(nk));
        if (nIdx !== undefined && nodeDisplacements[nIdx]) {
          const u = nodeDisplacements[nIdx];
          ux = u[0] * phase;
          uy = u[1] * phase;
          uz = u[2] * phase;
        }
      }
      offset += 3;

      let val = 0;
      if (component === 'x') val = ux * 10;
      else if (component === 'y') val = uy * 10;
      else if (component === 'z') val = uz * 10;
      else val = Math.hypot(ux, uy, uz) * 10;

      values[q * 4 + v] = val;
      if (val < min) min = val;
      if (val > max) max = val;
    }
  }

  if (!Number.isFinite(min)) { min = 0; max = 0; }
  const range = (max - min) || 1e-12;

  const quadColors = new Array(quadCount);
  for (let q = 0; q < quadCount; q++) {
    const cCorners = new Array(4);
    for (let v = 0; v < 4; v++) {
      const val = values[q * 4 + v];
      const t = (val - min) / range;
      const rgb = displacementColormap(t);
      cCorners[v] = makeColor(rgb[0], rgb[1], rgb[2]);
    }
    quadColors[q] = cCorners;
  }

  return {
    quadColors,
    min,
    max,
    component,
    unit: 'mm'
  };
}

