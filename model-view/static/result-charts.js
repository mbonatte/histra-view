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
    const x = abscissa === 'step' ? (s.cumulativeStep ?? s.step ?? index) : s.controlDisplacement;
    return {
      x, y: value, index,
      step: s.stageStep ?? s.step ?? index,
      cumulativeStep: s.cumulativeStep ?? index,
      analysisName: s.analysisName || analysis.name,
      stageLabel: s.stageLabel || analysis.name,
    };
  }).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y)) }));
}

export function modelPointSeries(analysis, key, abscissa = 'step') {
  const history = analysis.modelPoints;
  const point = history?.points?.find(p => String(p.key) === String(key));
  if (!point?.available || !point.displacement_cm) return [];
  const indices = new Map(analysis.steps.map((s, i) => [s.step, i]));
  return ['ux', 'uy', 'uz'].map((axis, j) => ({
    name: axis.toUpperCase(), color: colors[j],
    points: (history.step || []).map((step, i) => {
      const s = analysis.steps[i];
      const index = (analysis.isChain || s?.cumulativeStep != null) ? i : indices.get(step);
      const stepObj = index != null ? analysis.steps[index] : s;
      const y = point.displacement_cm[axis]?.[i];
      const x = abscissa === 'step' ? (stepObj?.cumulativeStep ?? step) : stepObj?.controlDisplacement;
      return {
        x, y, index,
        step: stepObj?.stageStep ?? stepObj?.step ?? step,
        cumulativeStep: stepObj?.cumulativeStep ?? i,
        analysisName: stepObj?.analysisName || analysis.name,
        stageLabel: stepObj?.stageLabel || analysis.name,
      };
    }).filter(p => p.index !== undefined && Number.isFinite(p.x) && Number.isFinite(p.y)),
  }));
}

export function nodeDisplacementSeries(analysis, key, mesh, abscissa = 'step') {
  if (!analysis?.steps?.length || !mesh?.nodes?.length) return [];
  const nodeIndex = mesh.nodes.findIndex(n => String(n.key) === String(key));
  if (nodeIndex < 0) return [];
  return ['Ux', 'Uy', 'Uz'].map((name, j) => ({
    name, color: colors[j],
    points: analysis.steps.map((s, index) => {
      const d = s.displacements?.[nodeIndex];
      const y = d ? d[j] : null;
      const x = abscissa === 'step' ? (s.cumulativeStep ?? s.step ?? index) : s.controlDisplacement;
      return {
        x, y, index,
        step: s.stageStep ?? s.step ?? index,
        cumulativeStep: s.cumulativeStep ?? index,
        analysisName: s.analysisName || analysis.name,
        stageLabel: s.stageLabel || analysis.name,
      };
    }).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y)),
  }));
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
  if (presentation.stages?.length > 1 && abscissa === 'step') {
    let acc = 0;
    for (let si = 0; si < presentation.stages.length; si++) {
      const st = presentation.stages[si];
      const startX = x(acc);
      const endX = x(acc + st.stepCount - 1);
      const midX = (startX + endX) / 2;
      svg.append(el('text', {
        x: midX, y: top - 8,
        'text-anchor': 'middle',
        fill: '#8da5b8',
        'font-size': compact ? 9 : 11,
        'font-weight': 'bold',
      }, st.name));
      if (si > 0) {
        svg.append(el('line', {
          x1: startX, x2: startX, y1: top, y2: height - bottom,
          stroke: '#4a6072', 'stroke-width': 1.5, 'stroke-dasharray': '4,4',
        }));
      }
      acc += st.stepCount;
    }
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
      dot.append(el('title', {}, `${p.analysisName ? `${p.analysisName} · ` : ''}Step ${p.step ?? ''}: ${s.name} ${fmt(p.y)} ${unit}; ${fmt(p.x)} ${abscissa === 'step' ? '' : presentation.xUnit || 'cm'}`));
      dot.onclick = () => onSelect(p.index, p.analysisName, p.step);
      dot.onkeydown = e => { if (e.key === 'Enter') onSelect(p.index, p.analysisName, p.step); };
      dot.onpointerenter = () => { readout.textContent = `${p.analysisName ? `${p.analysisName} · ` : ''}${s.name} · ${fmt(p.y)} ${unit} at ${fmt(p.x)} ${presentation.xUnit || 'cm'}`; };
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
    root.innerHTML = `<div class="eyebrow">STATIC ANALYSIS</div><h1>Response curves</h1><div class="curve-controls"><label>Quantity<select aria-label="Curve quantity"><option value="force">Force–displacement</option><option value="load">Load factor</option><option value="reactions">Reactions X / Y / Z</option><option value="energy">Elastic / dissipated energy</option><option value="modelPoint">Model point displacements X / Y / Z</option><option value="nodeDisplacement">Node displacements X / Y / Z</option></select></label><label class="history-scope-control" hidden>Scope<select aria-label="Analysis history scope"><option value="chain" selected>Whole history (chained)</option><option value="current">Current analysis only</option></select></label><label class="model-point-control" hidden>Model point<select aria-label="Model point"></select></label><label class="node-control" hidden>Model node<select aria-label="Model node"></select></label><label>Horizontal axis<select aria-label="Curve horizontal axis"><option value="displacement">Control displacement [cm]</option><option value="step">Saved step</option></select></label><button>Export CSV</button></div><div class="response-plot"></div><p class="result-note">Click a sample to select its saved step. Added vertical force = initial Rz − expected Rz (downward positive), excluding the stage’s existing load. Reactions retain the HiStrA sign convention. Energies retain their saved signs; initial energy values are absent rather than assumed zero.</p>`;
    this.quantity = root.querySelector('select[aria-label="Curve quantity"]');
    this.scope = root.querySelector('select[aria-label="Analysis history scope"]');
    this.point = root.querySelector('select[aria-label="Model point"]');
    this.nodeSelect = root.querySelector('select[aria-label="Model node"]');
    this.abscissa = root.querySelector('select[aria-label="Curve horizontal axis"]');
    this.quantity.onchange = () => { if (this.quantity.value === 'modelPoint' || this.quantity.value === 'nodeDisplacement') this.abscissa.value = 'step'; this.draw(); };
    this.scope.onchange = this.point.onchange = this.nodeSelect.onchange = this.abscissa.onchange = () => this.draw();
    root.querySelector('button').onclick = () => {
      const target = this.targetAnalysis();
      if (!target) return;
      const series = this.series();
      const isDisp = this.quantity.value === 'modelPoint' || this.quantity.value === 'nodeDisplacement';
      const unit = isDisp ? 'cm' : (labels[this.quantity.value]?.[1] || '');
      downloadCsv(`${target.name}-${this.quantity.value}.csv`, [
        ['series', 'analysis', 'stage_step', 'cumulative_step', this.abscissa.value === 'step' ? 'step' : 'control_displacement_cm', unit],
        ...series.flatMap(s => s.points.map(p => [
          s.name,
          p.analysisName || target.name,
          p.step,
          p.cumulativeStep ?? p.step,
          p.x,
          p.y,
        ]))
      ]);
    };
  }
  targetAnalysis() {
    return (this.scope.value === 'chain' && this.chainAnalysis) ? this.chainAnalysis : this.analysis;
  }
  update(analysis, selected, options = {}) {
    this.analysis = analysis;
    this.selected = selected;
    this.chainAnalysis = options.chainAnalysis || null;
    this.mesh = options.mesh || this.mesh;
    const hasChain = Boolean(this.chainAnalysis && this.chainAnalysis.chainStages?.length > 1);
    const scopeCtrl = this.root.querySelector('.history-scope-control');
    if (scopeCtrl) {
      scopeCtrl.hidden = !hasChain;
      scopeCtrl.classList.toggle('hidden', !hasChain);
    }

    const target = this.targetAnalysis();
    const previous = this.point.value;
    this.point.replaceChildren();
    for (const point of target?.modelPoints?.points || this.analysis?.modelPoints?.points || []) {
      const option = document.createElement('option');
      option.value = point.key;
      option.textContent = `${point.label || point.name || `Model point ${point.key}`} (#${point.key})${point.available ? '' : ' — unavailable'}`;
      this.point.append(option);
    }
    if ([...this.point.options].some(option => option.value === previous)) this.point.value = previous;

    const prevNode = this.nodeSelect.value;
    this.nodeSelect.replaceChildren();
    if (this.mesh?.nodes?.length) {
      const mpNodeKeys = new Set((this.mesh.modelPoints || []).map(mp => String(mp.elementKey || mp.key)));
      const nodes = this.mesh.nodes;
      for (const n of nodes) {
        if (nodes.length > 300 && !mpNodeKeys.has(String(n.key)) && this.nodeSelect.options.length >= 200) {
          continue;
        }
        const option = document.createElement('option');
        option.value = n.key;
        option.textContent = `Node ${n.key}${n.name && String(n.name) !== String(n.key) ? ` (${n.name})` : ''}${mpNodeKeys.has(String(n.key)) ? ' ★' : ''}`;
        this.nodeSelect.append(option);
      }
      if ([...this.nodeSelect.options].some(o => o.value === prevNode)) this.nodeSelect.value = prevNode;
    }

    this.draw();
  }
  series() {
    const target = this.targetAnalysis();
    if (this.quantity.value === 'modelPoint') {
      return modelPointSeries(target, this.point.value, this.abscissa.value);
    }
    if (this.quantity.value === 'nodeDisplacement') {
      return nodeDisplacementSeries(target, this.nodeSelect.value, this.mesh, this.abscissa.value);
    }
    return curveSeries(target, this.quantity.value, this.abscissa.value);
  }
  draw() {
    const target = this.targetAnalysis();
    if (!target) return;
    const isPoint = this.quantity.value === 'modelPoint';
    const isNode = this.quantity.value === 'nodeDisplacement';
    const pointCtrl = this.root.querySelector('.model-point-control');
    const nodeCtrl = this.root.querySelector('.node-control');
    if (pointCtrl) { pointCtrl.hidden = !isPoint; pointCtrl.classList.toggle('hidden', !isPoint); }
    if (nodeCtrl) { nodeCtrl.hidden = !isNode; nodeCtrl.classList.toggle('hidden', !isNode); }
    const presentation = {
      series: this.series(),
      stages: target.chainStages || null,
    };
    if (isPoint) {
      presentation.title = 'Model point displacement';
      presentation.unit = 'cm';
    } else if (isNode) {
      presentation.title = `Node ${this.nodeSelect.value} displacement`;
      presentation.unit = 'cm';
    }
    this.root.querySelector('.response-plot').replaceChildren(
      responseChart(target, this.quantity.value, this.abscissa.value, this.selected, (idx, aName, sNum) => {
        if (this.onSelect) this.onSelect(idx, aName, sNum);
      }, false, presentation)
    );
  }
}
