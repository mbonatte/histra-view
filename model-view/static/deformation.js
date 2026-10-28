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

export function grayColormap(t) {
  const v = 0.14 + 0.76 * Math.max(0, Math.min(1, Number(t) || 0));
  return [v, v, v];
}

function interpolateRgbStops(stops, t) {
  t = Math.max(0, Math.min(1, Number(t) || 0));
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1];
    if (t <= b[0]) {
      const f = (t - a[0]) / (b[0] - a[0] || 1);
      return [a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * (b[3] - a[3])];
    }
  }
  const last = stops[stops.length - 1];
  return [last[1], last[2], last[3]];
}

const TURBO_STOPS = [
  [0.00, 0.19, 0.07, 0.23], [0.10, 0.27, 0.45, 0.93],
  [0.20, 0.10, 0.72, 0.92], [0.30, 0.13, 0.93, 0.65],
  [0.40, 0.48, 1.00, 0.35], [0.50, 0.84, 0.97, 0.15],
  [0.60, 1.00, 0.72, 0.10], [0.70, 1.00, 0.39, 0.03],
  [0.80, 0.87, 0.13, 0.02], [0.90, 0.54, 0.02, 0.01],
  [1.00, 0.48, 0.02, 0.01],
];
const VIRIDIS_STOPS = [
  [0.000, 0.267, 0.005, 0.329], [0.125, 0.254, 0.239, 0.529],
  [0.250, 0.164, 0.416, 0.556], [0.375, 0.104, 0.557, 0.511],
  [0.500, 0.063, 0.671, 0.431], [0.625, 0.184, 0.769, 0.337],
  [0.750, 0.478, 0.821, 0.318], [0.875, 0.741, 0.873, 0.150],
  [1.000, 0.993, 0.906, 0.144],
];
const COOLWARM_STOPS = [
  [0.00, 0.23, 0.30, 0.75], [0.25, 0.45, 0.60, 0.86],
  [0.50, 0.865, 0.865, 0.865], [0.75, 0.95, 0.55, 0.40],
  [1.00, 0.70, 0.00, 0.15],
];

export const turboColormap = t => interpolateRgbStops(TURBO_STOPS, t);
export const viridisColormap = t => interpolateRgbStops(VIRIDIS_STOPS, t);
export const coolwarmColormap = t => interpolateRgbStops(COOLWARM_STOPS, t);

export function csharpStressColormap(t) {
  t = Math.max(0, Math.min(1, Number(t) || 0));
  const stops = [
    { t: 0.000, r: 0.00, g: 0.00, b: 0.55 }, // DarkBlue
    { t: 0.125, r: 0.00, g: 0.00, b: 1.00 }, // Blue
    { t: 0.250, r: 0.00, g: 0.75, b: 1.00 }, // DeepSkyBlue
    { t: 0.375, r: 0.68, g: 0.85, b: 0.90 }, // LightBlue
    { t: 0.500, r: 0.00, g: 1.00, b: 0.00 }, // Lime
    { t: 0.625, r: 0.56, g: 0.93, b: 0.56 }, // LightGreen
    { t: 0.750, r: 1.00, g: 1.00, b: 0.00 }, // Yellow
    { t: 0.875, r: 1.00, g: 0.65, b: 0.00 }, // Orange
    { t: 1.000, r: 1.00, g: 0.00, b: 0.00 }, // Red
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

export function computeScalarContours({
  quads,
  values,
  min,
  max,
  faceValues = null,
  faceGrids = null,
  colormap = displacementColormap,
  makeColor = (r, g, b) => [r, g, b]
}) {
  const quadCount = quads.length;
  if (!Array.isArray(values) && !ArrayBuffer.isView(values)) throw new Error('Missing scalar values.');
  if (values.length !== quadCount * 4) throw new Error('Scalar values must provide four corners per Quad.');
  const finite = [];
  for (const value of values) if (Number.isFinite(value)) finite.push(value);
  const minimum = Number.isFinite(min) ? min : (finite.length ? Math.min(...finite) : 0);
  const maximum = Number.isFinite(max) ? max : (finite.length ? Math.max(...finite) : 0);
  const range = (maximum - minimum) || 1e-12;
  const quadColors = new Array(quadCount);
  for (let q = 0; q < quadCount; q++) {
    const corners = new Array(4);
    for (let v = 0; v < 4; v++) {
      const raw = values[q * 4 + v];
      const value = Number.isFinite(raw) ? raw : minimum;
      const rgb = colormap((value - minimum) / range);
      corners[v] = makeColor(rgb[0], rgb[1], rgb[2]);
    }
    quadColors[q] = corners;
  }
  let quadFaceColors = null;
  if (faceValues) {
    if (faceValues.length !== quadCount * 24) throw new Error('Face values must provide six faces with four corners per Quad.');
    quadFaceColors = new Array(quadCount);
    for (let q = 0; q < quadCount; q++) {
      const faces = new Array(6);
      for (let face = 0; face < 6; face++) {
        const corners = new Array(4);
        for (let v = 0; v < 4; v++) {
          const raw = faceValues[q * 24 + face * 4 + v];
          const value = Number.isFinite(raw) ? raw : minimum;
          const rgb = colormap((value - minimum) / range);
          corners[v] = makeColor(rgb[0], rgb[1], rgb[2]);
        }
        faces[face] = corners;
      }
      quadFaceColors[q] = faces;
    }
  }
  let quadFaceGrids = null;
  if (faceGrids) {
    if (faceGrids.length !== quadCount) throw new Error('Face grids must provide one entry per Quad.');
    quadFaceGrids = new Array(quadCount);
    for (let q = 0; q < quadCount; q++) {
      const faces = new Array(6).fill(null);
      for (let face = 0; face < 6; face++) {
        const grid = faceGrids[q]?.[face];
        if (!grid) continue;
        if (!Number.isInteger(grid.n) || !Number.isInteger(grid.m) || grid.n < 2 || grid.m < 2) {
          throw new Error('Face grids need valid n/m dimensions.');
        }
        if (!Array.isArray(grid.values) || grid.values.length !== grid.n * grid.m) {
          throw new Error('Face grid values do not match n × m.');
        }
        const colors = new Array(grid.values.length);
        for (let index = 0; index < grid.values.length; index++) {
          const raw = grid.values[index];
          const value = Number.isFinite(raw) ? raw : minimum;
          const rgb = colormap((value - minimum) / range);
          colors[index] = makeColor(rgb[0], rgb[1], rgb[2]);
        }
        faces[face] = { n: grid.n, m: grid.m, colors };
      }
      quadFaceGrids[q] = faces;
    }
  }
  return { quadColors, quadFaceColors, quadFaceGrids, min: minimum, max: maximum };
}

export function computeDisplacementContours({
  quads,
  nodeKeyToIndex,
  nodeDisplacements,
  quadDisplacements,
  component = 'magnitude',
  phase = 1,
  min = null,
  max = null,
  colormap = displacementColormap,
  makeColor = (r, g, b) => [r, g, b]
}) {
  const quadCount = quads.length;
  const flatQuadDisp = quadDisplacements ? decodeQuadDisplacements(quadDisplacements, quadCount) : null;
  const values = new Float32Array(quadCount * 4);

  let naturalMin = Infinity;
  let naturalMax = -Infinity;

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
      if (val < naturalMin) naturalMin = val;
      if (val > naturalMax) naturalMax = val;
    }
  }

  const dataMin = Number.isFinite(naturalMin) ? naturalMin : 0;
  const dataMax = Number.isFinite(naturalMax) ? naturalMax : 0;
  const usedMin = Number.isFinite(min) ? min : dataMin;
  const usedMax = Number.isFinite(max) ? max : dataMax;
  const range = (usedMax - usedMin) || 1e-12;

  const quadColors = new Array(quadCount);
  for (let q = 0; q < quadCount; q++) {
    const cCorners = new Array(4);
    for (let v = 0; v < 4; v++) {
      const val = values[q * 4 + v];
      const t = (val - usedMin) / range;
      const rgb = colormap(t);
      cCorners[v] = makeColor(rgb[0], rgb[1], rgb[2]);
    }
    quadColors[q] = cCorners;
  }

  return {
    quadColors,
    min: usedMin,
    max: usedMax,
    dataMin,
    dataMax,
    component,
    unit: 'mm'
  };
}

