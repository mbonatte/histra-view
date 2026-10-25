const colors = ['#69d8c2', '#f5b86e', '#91a9ff'];
const labels = {
  force: ['Added vertical force', 'kN'], load: ['Load factor λ', '1'],
  reactions: ['HiStrA reactions', 'kN'], energy: ['Energy', 'kN·cm'],
};
const fmt = v => v === 0 ? '0' : Math.abs(v) < .001 || Math.abs(v) > 1e5 ? v.toExponential(2) : Number(v.toPrecision(4)).toString();
const el = (tag, attrs = {}, text) => {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
};

export function curveSeries(analysis, kind, abscissa = 'displacement') {
  const names = kind === 'reactions' ? ['Rₓ', 'Rᵧ', 'R𝓏'] : kind === 'energy' ? ['Elastic', 'Dissipated'] : [labels[kind][0]];
  return names.map((name, i) => ({ name, color: colors[i], points: analysis.steps.map((s, index) => {
    const value = kind === 'reactions' ? s.reactions[i] : kind === 'energy' ? s[i ? 'dissipatedEnergy' : 'elasticEnergy'] : s[kind === 'force' ? 'appliedVerticalForce' : 'loadFactor'];
    return { x: abscissa === 'step' ? s.step : s.controlDisplacement, y: value, index, step: s.step };
  }).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y)) }));
}

export function responseChart(analysis, kind = 'force', abscissa = 'displacement', selected = -1, onSelect = () => {}, compact = false, presentation = {}) {
  const title = presentation.title || labels[kind]?.[0] || 'Force', unit = presentation.unit || labels[kind]?.[1] || 'kN';
  const width = presentation.width || (compact ? 300 : 900), height = presentation.height || (compact ? 200 : 420);
  const left = compact ? 52 : 85, right = 22, top = compact ? 26 : 48, bottom = compact ? 44 : 65;
  const series = presentation.series ? presentation.series : curveSeries(analysis, kind, abscissa);
  const points = series.flatMap(s => s.points);
  series.forEach((s, i) => { if (presentation.names?.[i]) s.name = presentation.names[i]; });
  const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `${title} versus ${abscissa} for ${analysis?.name || 'Results'}`, class: 'response-chart' });
  if (!points.length) { svg.append(el('text', { x: left, y: 60 }, 'No saved values')); return svg; }
  let xmin = Math.min(...points.map(p => p.x)), xmax = Math.max(...points.map(p => p.x));
  let ymin = Math.min(0, ...points.map(p => p.y)), ymax = Math.max(0, ...points.map(p => p.y));
  const dx = xmax - xmin || Math.max(Math.abs(xmin) * .1, 1e-6), dy = ymax - ymin || 1;
  xmin -= dx * .04; xmax += dx * .04; ymin -= dy * .08; ymax += dy * .08;
  const x = v => left + (v - xmin) / (xmax - xmin) * (width - left - right);
  const y = v => height - bottom - (v - ymin) / (ymax - ymin) * (height - top - bottom);
  for (let i = 0; i <= 4; i++) {
    const a = xmin + (xmax - xmin) * i / 4, b = ymin + (ymax - ymin) * i / 4;
    svg.append(el('line', { x1: x(a), x2: x(a), y1: top, y2: height - bottom, class: 'curve-grid' }), el('line', { x1: left, x2: width - right, y1: y(b), y2: y(b), class: 'curve-grid' }),
      el('text', { x: x(a), y: height - bottom + 18, 'text-anchor': 'middle', class: 'curve-tick' }, fmt(a)), el('text', { x: left - 8, y: y(b) + 4, 'text-anchor': 'end', class: 'curve-tick' }, fmt(b)));
  }
  const xLabel = presentation.xLabel || (abscissa === 'step' ? 'Saved step' : 'Control displacement [cm]');
  svg.append(el('text', { x: left, y: compact ? 14 : 19, class: 'curve-label' }, `${title} [${unit}]`),
    el('text', { x: width / 2, y: height - 7, 'text-anchor': 'middle', class: 'curve-label' }, xLabel));
  const readout = el('text', { x: width - right, y: 36, 'text-anchor': 'end', class: 'curve-label' });
  series.forEach((s, si) => {
    const pathAttrs = { d: s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.x)},${y(p.y)}`).join(' '), fill: 'none', stroke: s.color, 'stroke-width': compact ? 2 : 2.5 };
    if (s.dashed) pathAttrs['stroke-dasharray'] = '6,4';
    svg.append(el('path', pathAttrs));
    if (series.length > 1) svg.append(el('text', { x: left + si * 140, y: height - 29, fill: s.color, class: 'curve-label' }, s.name));
    for (const p of s.points) {
      const isSelected = p.index === selected || p.isPeak;
      const dot = el('circle', { cx: x(p.x), cy: y(p.y), r: isSelected ? 5 : compact ? 2 : 3.5, fill: isSelected ? '#fff' : s.color, stroke: s.color, 'stroke-width': 1.5, tabindex: compact ? -1 : 0 });
      dot.append(el('title', {}, `Step ${p.step ?? ''}: ${s.name} ${fmt(p.y)} ${unit}; ${fmt(p.x)} ${abscissa === 'step' ? '' : presentation.xUnit || 'cm'}`));
      dot.onclick = () => onSelect(p.index);
      dot.onkeydown = e => { if (e.key === 'Enter') onSelect(p.index); };
      dot.onpointerenter = () => { readout.textContent = `${s.name} · ${fmt(p.y)} ${unit} at ${fmt(p.x)} ${presentation.xUnit || 'cm'}`; };
      svg.append(dot);
    }
  });
  if (!compact) svg.append(readout);
  return svg;
}

export function downloadCsv(name, rows) {
  const csv = rows.map(row => row.map(v => `"${String(v ?? '').replaceAll('"', '""')}"`).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
}

export class ResponseCurves {
  constructor(root, onSelect) {
    this.root = root; this.onSelect = onSelect;
    root.innerHTML = `<div class="eyebrow">STATIC ANALYSIS</div><h1>Response curves</h1><div class="curve-controls"><label>Quantity<select aria-label="Curve quantity"><option value="force">Force–displacement</option><option value="load">Load factor</option><option value="reactions">Reactions X / Y / Z</option><option value="energy">Elastic / dissipated energy</option></select></label><label>Horizontal axis<select aria-label="Curve horizontal axis"><option value="displacement">Control displacement [cm]</option><option value="step">Saved step</option></select></label><button>Export CSV</button></div><div class="response-plot"></div><p class="result-note">Click a sample to select its saved step. Added vertical force = initial Rz − expected Rz (downward positive), excluding the stage’s existing load. Reactions retain the HiStrA sign convention. Energies retain their saved signs; initial energy values are absent rather than assumed zero.</p>`;
    [this.quantity, this.abscissa] = root.querySelectorAll('select');
    this.quantity.onchange = this.abscissa.onchange = () => this.draw();
    root.querySelector('button').onclick = () => {
      if (!this.analysis) return;
      const series = curveSeries(this.analysis, this.quantity.value, this.abscissa.value);
      downloadCsv(`${this.analysis.name}-${this.quantity.value}.csv`, [['series', 'step', this.abscissa.value === 'step' ? 'step' : 'control_displacement_cm', labels[this.quantity.value][1]], ...series.flatMap(s => s.points.map(p => [s.name, p.step, p.x, p.y]))]);
    };
  }
  update(analysis, selected) { this.analysis = analysis; this.selected = selected; this.draw(); }
  draw() { if (this.analysis) this.root.querySelector('.response-plot').replaceChildren(responseChart(this.analysis, this.quantity.value, this.abscissa.value, this.selected, this.onSelect)); }
}
