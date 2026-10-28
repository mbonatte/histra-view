export const phaseColors = { Elastic: '#67cbb4', Plastic_t: '#ed796d', Plastic_c: '#bb78e7', Unload_c: '#7ba4e5', Unload_t: '#53c7db', Reload_c: '#e7bb6b', Reload_t: '#c1d375', RuptureTraz: '#ff4f87', RuptureComp: '#f4a34f', Rupture: '#f4d44f' };

export function stressColor(value, minOrMax, max) {
  if (!Number.isFinite(value)) return [.4, .45, .5];
  const neutral = [.9, .92, .94], blue = [.2, .36, .82], red = [.9, .25, .2];
  if (max === undefined) {
    const mag = Math.abs(minOrMax) || 1;
    return stressColor(value, -mag, mag);
  }
  const minVal = Number.isFinite(minOrMax) ? minOrMax : -1e-12;
  const maxVal = Number.isFinite(max) ? max : 1e-12;
  if (minVal < 0 && maxVal > 0) {
    if (value < 0) {
      const t = Math.min(1, -value / -minVal);
      return neutral.map((v, i) => v + (blue[i] - v) * t);
    }
    if (value > 0) {
      const t = Math.min(1, value / maxVal);
      return neutral.map((v, i) => v + (red[i] - v) * t);
    }
    return neutral;
  }
  if (minVal >= 0) {
    const t = Math.max(0, Math.min(1, (value - minVal) / (maxVal - minVal || 1)));
    return neutral.map((v, i) => v + (red[i] - v) * t);
  }
  const t = Math.max(0, Math.min(1, (maxVal - value) / (maxVal - minVal || 1)));
  return neutral.map((v, i) => v + (blue[i] - v) * t);
}
export const cssColor = rgb => `rgb(${rgb.map(v => Math.round(v * 255)).join(',')})`;

export function decodeContours(raw) {
  if (raw.encoding !== 'base64-little-endian' || raw.stressUnit !== 'MPa') throw new Error('Unsupported contour encoding or units.');
  const bytes = text => Uint8Array.from(atob(text), c => c.charCodeAt(0));
  const floats = text => {
    const a = bytes(text);
    if (a.byteLength % 4) throw new Error('Invalid contour array.');
    const view = new DataView(a.buffer), out = new Float32Array(a.length / 4);
    for (let i = 0; i < out.length; i++) out[i] = view.getFloat32(i * 4, true);
    if (!out.every(Number.isFinite)) throw new Error('Nonfinite contour data.');
    return out;
  };
  const data = {
    ...raw,
    positions: floats(raw.positions),
    stress: floats(raw.stress),
    force: floats(raw.force),
    area: floats(raw.area),
    displacement: floats(raw.displacement),
    strain: raw.strain ? floats(raw.strain) : floats(raw.displacement),
    phase: bytes(raw.phase),
    slidingStress: raw.slidingStress ? floats(raw.slidingStress) : null,
    slidingOutOfPlaneStress: raw.slidingOutOfPlaneStress ? floats(raw.slidingOutOfPlaneStress) : null,
    slidingPhase: raw.slidingPhase ? bytes(raw.slidingPhase) : null,
    slidingOutOfPlanePhase: raw.slidingOutOfPlanePhase ? bytes(raw.slidingOutOfPlanePhase) : null,
  };
  const required = ['stress', 'force', 'area', 'displacement', 'strain', 'phase'];
  if (data.slidingStress) required.push('slidingStress');
  if (data.slidingOutOfPlaneStress) required.push('slidingOutOfPlaneStress');
  if (data.slidingPhase) required.push('slidingPhase');
  if (data.slidingOutOfPlanePhase) required.push('slidingOutOfPlanePhase');
  if (data.positions.length !== raw.cellCount * 12 || required.some(k => data[k].length !== raw.cellCount)) throw new Error('Contour array sizes do not match.');
  let start = 0;
  for (const g of raw.groups) {
    if (g.start !== start || g.count !== g.nrow * g.ncol) throw new Error('Invalid interface cell mapping.');
    start += g.count;
  }
  if (start !== raw.cellCount || new Set(raw.groups.map(g => g.key)).size !== raw.groups.length
      || !data.phase.every(p => p < raw.phaseNames.length)
      || (data.slidingPhase && !data.slidingPhase.every(p => p < raw.phaseNames.length))
      || (data.slidingOutOfPlanePhase && !data.slidingOutOfPlanePhase.every(p => p < raw.phaseNames.length))) {
    throw new Error('Invalid contour mapping.');
  }
  return data;
}

export function contourGroups(data, scope, selected) {
  return data.groups.filter(g => scope === 'all' || (scope === 'selected' ? g.key === selected : g.restrained));
}

export function maximumMagnitude(values) {
  let maximum = 1e-12;
  for (const value of values) maximum = Math.max(maximum, Math.abs(value));
  return maximum;
}
