/**
 * Compute funicular thrust line segments and plastic hinges across masonry quads.
 */

export function extractResultant(row) {
  if (!row) return null;
  if (Array.isArray(row)) {
    return { forces: [row[0], row[1], row[2]], moments: [row[3], row[4], row[5]] };
  }
  return row;
}

export function computeInterfaceThrust(ifaceData, rawRow, nodeMap, hingeThreshold = 0.85, tol = 1e-5) {
  if (!ifaceData || !rawRow) return null;
  const n2 = Array.isArray(rawRow) ? rawRow[1] : rawRow.forces?.[1];
  const mz = Array.isArray(rawRow) ? rawRow[5] : rawRow.moments?.[2];
  if (typeof n2 !== 'number' || n2 >= -tol || !Number.isFinite(n2)) return null;
  if (typeof mz !== 'number' || !Number.isFinite(mz)) return null;

  const L = Number(ifaceData.length);
  if (!L || L <= 0) return null;

  const ex = mz / n2;
  const eta = (2 * Math.abs(ex)) / L;
  const xi = 0.5 + ex / L;

  const p1Raw = nodeMap(ifaceData.nodeKeys[0]) ?? ifaceData.points?.[0];
  const p2Raw = nodeMap(ifaceData.nodeKeys[1]) ?? ifaceData.points?.[1];
  if (!p1Raw || !p2Raw) return null;

  const toVec = p => Array.isArray(p) ? p : [p.x, p.y, p.z];
  const p1 = toVec(p1Raw), p2 = toVec(p2Raw);

  const clampedXi = Math.max(0, Math.min(1, xi));
  const point = [
    (1 - clampedXi) * p1[0] + clampedXi * p2[0],
    (1 - clampedXi) * p1[1] + clampedXi * p2[1],
    (1 - clampedXi) * p1[2] + clampedXi * p2[2],
  ];

  const isHinge = eta >= hingeThreshold;
  // Extreme fiber where the hinge opens/compresses:
  const hingePoint = ex >= 0 ? p2 : p1;

  return { ex, eta, xi, isHinge, point, hingePoint, n2, mz, p1, p2, length: L };
}

// Width grouping must use the undeformed mesh: the viewer's node map points at
// playback-deformed coordinates, which would split one cross-section into a new
// group at every step. The deformed map is still used later for the drawn line.
function referenceNodeMap(mesh, nodeMap) {
  if (!Array.isArray(mesh?.nodes) || !mesh.nodes.length) return nodeMap;
  const nodes = new Map();
  for (const node of mesh.nodes) {
    const p = node?.point;
    if (p) nodes.set(Number(node.key), Array.isArray(p) ? p : [p.x, p.y, p.z]);
  }
  return key => nodes.get(Number(key)) ?? nodeMap(key);
}

export function buildWidthGroups(mesh, nodeMap) {
  const pairs = mesh?.thrustPairs || [];
  const interfaces = mesh?.interfaces || {};
  const toVec = p => Array.isArray(p) ? p : [p.x, p.y, p.z];
  const reference = referenceNodeMap(mesh, nodeMap);
  const pointFor = (iface, index) => {
    const p = reference(iface.nodeKeys[index]);
    if (p) return p;
    const fallback = iface.points?.[index];
    return fallback ? toVec(fallback) : null;
  };
  const groups = new Map();

  for (const pair of pairs) {
    const [quadKey, i1Key, i2Key, matKey] = pair;
    const if1 = interfaces[String(i1Key)];
    const if2 = interfaces[String(i2Key)];
    if (!if1 || !if2) continue;

    const a1Raw = pointFor(if1, 0), b1Raw = pointFor(if1, 1);
    const a2Raw = pointFor(if2, 0), b2Raw = pointFor(if2, 1);
    if (!a1Raw || !b1Raw || !a2Raw || !b2Raw) continue;

    const a1 = toVec(a1Raw), b1 = toVec(b1Raw);
    const a2 = toVec(a2Raw), b2 = toVec(b2Raw);

    const m1x = (a1[0] + b1[0]) * 0.5, m1y = (a1[1] + b1[1]) * 0.5, m1z = (a1[2] + b1[2]) * 0.5;
    const m2x = (a2[0] + b2[0]) * 0.5, m2y = (a2[1] + b2[1]) * 0.5, m2z = (a2[2] + b2[2]) * 0.5;

    const dx = m2x - m1x, dy = m2y - m1y, dz = m2z - m1z;
    const w1x = b1[0] - a1[0], w1y = b1[1] - a1[1], w1z = b1[2] - a1[2];

    let nx = dy * w1z - dz * w1y;
    let ny = dz * w1x - dx * w1z;
    let nz = dx * w1y - dy * w1x;
    const nLen = Math.hypot(nx, ny, nz);
    if (nLen > 1e-6) {
      nx /= nLen; ny /= nLen; nz /= nLen;
    } else {
      nx = 0; ny = 1; nz = 0;
    }

    const dot1 = m1x * nx + m1y * ny + m1z * nz;
    const p1x = Math.round((m1x - dot1 * nx) * 10) / 10;
    const p1y = Math.round((m1y - dot1 * ny) * 10) / 10;
    const p1z = Math.round((m1z - dot1 * nz) * 10) / 10;

    const dot2 = m2x * nx + m2y * ny + m2z * nz;
    const p2x = Math.round((m2x - dot2 * nx) * 10) / 10;
    const p2y = Math.round((m2y - dot2 * ny) * 10) / 10;
    const p2z = Math.round((m2z - dot2 * nz) * 10) / 10;

    const dotW = w1x * nx + w1y * ny + w1z * nz;
    const wx = Math.round((w1x - dotW * nx) * 10) / 10;
    const wy = Math.round((w1y - dotW * ny) * 10) / 10;
    const wz = Math.round((w1z - dotW * nz) * 10) / 10;

    const project = p => {
      const d = p[0] * nx + p[1] * ny + p[2] * nz;
      return [p[0] - d * nx, p[1] - d * ny, p[2] - d * nz];
    };

    const groupKey = `${matKey}:${p1x},${p1y},${p1z}:${p2x},${p2y},${p2z}:${wx},${wy},${wz}`;
    let grp = groups.get(groupKey);
    if (!grp) {
      grp = {
        key: groupKey,
        matKey: String(matKey),
        j1Key: `${matKey}:${p1x},${p1y},${p1z}`,
        j2Key: `${matKey}:${p2x},${p2y},${p2z}`,
        normal: [nx, ny, nz],
        j1Seg: [project(a1), project(b1)],
        j2Seg: [project(a2), project(b2)],
        pairs: []
      };
      groups.set(groupKey, grp);
    }
    grp.pairs.push(pair);
  }

  mergeAdjacentWidthGroups(groups);
  return groups;
}

const MERGE_TOL = 0.5;

function segmentsAdjacent(s1, s2, tol) {
  const [a, b] = s1;
  const [c, d] = s2;
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const len2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2;
  if (len2 < tol * tol) return false;
  const len = Math.sqrt(len2);

  const distance = p => {
    const ap = [p[0] - a[0], p[1] - a[1], p[2] - a[2]];
    const along = (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / len;
    const lateral = Math.hypot(
      ap[0] - (along / len) * ab[0],
      ap[1] - (along / len) * ab[1],
      ap[2] - (along / len) * ab[2]
    );
    return { lateral, along };
  };

  const dc = distance(c), dd = distance(d);
  if (dc.lateral > tol || dd.lateral > tol) return false;
  const lo = Math.min(dc.along, dd.along);
  const hi = Math.max(dc.along, dd.along);
  return hi >= -tol && lo <= len + tol;
}

// A structure extruded through its thickness is discretized by two or more
// Quads that share a joint. Their joint interfaces are collinear and touch, so
// the section resultant is one point, not one thrust line per column.
function mergeAdjacentWidthGroups(groups) {
  const items = Array.from(groups.values());
  if (items.length < 2) return;
  const parent = items.map((_, i) => i);
  const find = i => {
    while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; }
    return i;
  };
  const union = (i, j) => { const a = find(i), b = find(j); if (a !== b) parent[b] = a; };

  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      const g = items[i], h = items[j];
      if (g.matKey !== h.matKey || !g.j1Seg || !h.j1Seg) continue;
      const dot = g.normal[0] * h.normal[0] + g.normal[1] * h.normal[1] + g.normal[2] * h.normal[2];
      if (Math.abs(dot) < 0.9999) continue;
      if (segmentsAdjacent(g.j1Seg, h.j1Seg, MERGE_TOL) &&
          segmentsAdjacent(g.j2Seg, h.j2Seg, MERGE_TOL)) union(i, j);
    }
  }

  const roots = new Map();
  items.forEach((item, i) => {
    const root = find(i);
    let target = roots.get(root);
    if (!target) {
      target = {
        ...item,
        key: item.key,
        j1Key: item.j1Key,
        j2Key: item.j2Key,
        pairs: item.pairs.slice()
      };
      roots.set(root, target);
      return;
    }
    target.key += `|${item.key}`;
    target.j1Key += `|${item.j1Key}`;
    target.j2Key += `|${item.j2Key}`;
    target.pairs.push(...item.pairs);
  });

  groups.clear();
  for (const target of roots.values()) groups.set(target.key, target);
}

export function computeThrustLines(mesh, step, slotMap, nodeMap, options = {}) {
  const pairs = mesh?.thrustPairs || [];
  const interfaces = mesh?.interfaces || {};
  const filter = options.materialFilter || 'all';
  const threshold = options.hingeThreshold ?? 0.85;
  const tol = options.normalTolerance ?? 1e-5;
  const combineWidth = Boolean(options.combineWidth);

  const ifaceCache = new Map();
  const segmentPositions = [];
  const hingesMap = new Map();
  const toVec = p => Array.isArray(p) ? p : [p.x, p.y, p.z];

  function getIfaceThrust(iKey) {
    let res = ifaceCache.get(iKey);
    if (res === undefined) {
      const slot = slotMap(iKey);
      const row = slot != null ? step?.interfaceResultants?.[slot] : null;
      res = computeInterfaceThrust(interfaces[String(iKey)], row, nodeMap, threshold, tol);
      ifaceCache.set(iKey, res);
    }
    return res;
  }

  if (!combineWidth) {
    for (const pair of pairs) {
      const [quadKey, i1Key, i2Key, matKey] = pair;
      if (filter !== 'all') {
        if (filter instanceof Set ? !filter.has(String(matKey)) : Array.isArray(filter) ? !filter.includes(String(matKey)) : String(matKey) !== String(filter)) continue;
      }

      const res1 = getIfaceThrust(i1Key);
      if (res1?.isHinge && !hingesMap.has(i1Key)) {
        hingesMap.set(i1Key, { key: i1Key, position: res1.hingePoint, thrustPoint: res1.point, ratio: res1.eta });
      }

      const res2 = getIfaceThrust(i2Key);
      if (res2?.isHinge && !hingesMap.has(i2Key)) {
        hingesMap.set(i2Key, { key: i2Key, position: res2.hingePoint, thrustPoint: res2.point, ratio: res2.eta });
      }

      if (res1 && res2) {
        segmentPositions.push(
          res1.point[0], res1.point[1], res1.point[2],
          res2.point[0], res2.point[1], res2.point[2]
        );
      }
    }

    return {
      positions: new Float32Array(segmentPositions),
      segmentCount: segmentPositions.length / 6,
      hinges: Array.from(hingesMap.values()),
      hingeCount: hingesMap.size,
      compressedCount: ifaceCache.size,
    };
  }

  // Combined width centroid line calculation:
  if (options.rebuildGroups && mesh) mesh._thrustWidthGroups = null;
  let groups = mesh?._thrustWidthGroups;
  if (!groups) {
    groups = buildWidthGroups(mesh, nodeMap);
    if (mesh) mesh._thrustWidthGroups = groups;
  }

  for (const grp of groups.values()) {
    if (filter !== 'all') {
      if (filter instanceof Set ? !filter.has(grp.matKey) : Array.isArray(filter) ? !filter.includes(grp.matKey) : grp.matKey !== String(filter)) continue;
    }

    let c1Total = 0, p1x = 0, p1y = 0, p1z = 0, xi1Sum = 0;
    let c2Total = 0, p2x = 0, p2y = 0, p2z = 0, xi2Sum = 0;

    for (const pair of grp.pairs) {
      const res1 = getIfaceThrust(pair[1]);
      if (res1) {
        const c1 = -res1.n2;
        c1Total += c1;
        p1x += c1 * res1.point[0];
        p1y += c1 * res1.point[1];
        p1z += c1 * res1.point[2];
        xi1Sum += c1 * res1.xi;
      }

      const res2 = getIfaceThrust(pair[2]);
      if (res2) {
        const c2 = -res2.n2;
        c2Total += c2;
        p2x += c2 * res2.point[0];
        p2y += c2 * res2.point[1];
        p2z += c2 * res2.point[2];
        xi2Sum += c2 * res2.xi;
      }
    }

    if (c1Total > tol && c2Total > tol) {
      const cp1 = [p1x / c1Total, p1y / c1Total, p1z / c1Total];
      const cp2 = [p2x / c2Total, p2y / c2Total, p2z / c2Total];

      segmentPositions.push(
        cp1[0], cp1[1], cp1[2],
        cp2[0], cp2[1], cp2[2]
      );

      const avgXi1 = xi1Sum / c1Total;
      const eta1 = 2 * Math.abs(avgXi1 - 0.5);
      if (eta1 >= threshold && !hingesMap.has(grp.j1Key)) {
        let hx = 0, hy = 0, hz = 0, hw = 0;
        for (const pair of grp.pairs) {
          const res1 = getIfaceThrust(pair[1]);
          if (res1) {
            const c1 = -res1.n2;
            const pt = avgXi1 >= 0.5 ? res1.p2 : res1.p1;
            hx += c1 * pt[0]; hy += c1 * pt[1]; hz += c1 * pt[2]; hw += c1;
          }
        }
        const hPt = hw > 0 ? [hx / hw, hy / hw, hz / hw] : cp1;
        hingesMap.set(grp.j1Key, { key: grp.j1Key, position: hPt, thrustPoint: cp1, ratio: eta1 });
      }

      const avgXi2 = xi2Sum / c2Total;
      const eta2 = 2 * Math.abs(avgXi2 - 0.5);
      if (eta2 >= threshold && !hingesMap.has(grp.j2Key)) {
        let hx = 0, hy = 0, hz = 0, hw = 0;
        for (const pair of grp.pairs) {
          const res2 = getIfaceThrust(pair[2]);
          if (res2) {
            const c2 = -res2.n2;
            const pt = avgXi2 >= 0.5 ? res2.p2 : res2.p1;
            hx += c2 * pt[0]; hy += c2 * pt[1]; hz += c2 * pt[2]; hw += c2;
          }
        }
        const hPt = hw > 0 ? [hx / hw, hy / hw, hz / hw] : cp2;
        hingesMap.set(grp.j2Key, { key: grp.j2Key, position: hPt, thrustPoint: cp2, ratio: eta2 });
      }
    }
  }

  return {
    positions: new Float32Array(segmentPositions),
    segmentCount: segmentPositions.length / 6,
    hinges: Array.from(hingesMap.values()),
    hingeCount: hingesMap.size,
    compressedCount: ifaceCache.size,
  };
}
