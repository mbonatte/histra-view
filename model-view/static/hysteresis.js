import { unitSets } from './material-units.js';

const node = (tag, text, className) => {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
};
const svgNode = (tag, attributes = {}, text) => {
  const result = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attributes)) result.setAttribute(key, value);
  if (text !== undefined) result.textContent = text;
  return result;
};
const number = value => value !== 0 && (Math.abs(value) < 0.001 || Math.abs(value) >= 1e5)
  ? value.toExponential(2) : Number(value.toPrecision(4)).toString();

export class HysteresisPreview {
  constructor() { this.cache = new Map(); this.settings = new Map(); }

  mount(parent, attributes, mechanism, units) {
    this.resizeObserver?.disconnect();
    const section = node('section', undefined, 'hysteresis-preview');
    section.append(node('h2', 'Calculated hysteresis preview'));
    const form = node('form', undefined, 'preview-controls');
    const field = (text, input) => { const label = node('label', text); label.append(input); form.append(label); return input; };
    const direction = field('Local direction', node('select'));
    direction.setAttribute('aria-label', 'Preview local direction');
    direction.add(new Option(mechanism === 'rocking' ? '1 & 3' : '1', '1'));
    if (mechanism === 'rocking' && attributes.ortpf === 'true' || mechanism === 'sliding' && attributes.ortsc === 'true') direction.add(new Option('2', '2'));
    if (mechanism === 'sliding' && attributes.ortsc === 'true') direction.add(new Option('3', '3'));
    const amplitude = field('Maximum strain, ε', node('input'));
    amplitude.type = 'number'; amplitude.step = 'any'; amplitude.min = '1e-10'; amplitude.max = '1'; amplitude.placeholder = 'Automatic';
    amplitude.setAttribute('aria-label', 'Maximum preview strain');
    const cycles = field('Cycles', node('input'));
    cycles.type = 'number'; cycles.min = '1'; cycles.max = '8'; cycles.value = '3'; cycles.step = '1';
    cycles.setAttribute('aria-label', 'Preview cycles');
    const history = field('Strain history', node('select'));
    history.add(new Option('Increasing cycles', 'cyclic')); history.add(new Option('Monotonic tension', 'monotonic'));
    history.setAttribute('aria-label', 'Preview strain history');
    const run = node('button', 'Update graph'); run.type = 'submit'; form.append(run);
    const download = node('button', 'Export CSV'); download.type = 'button'; download.disabled = true; form.append(download);
    const status = node('p', 'Calculating with Python spring laws…', 'preview-status'); status.setAttribute('role', 'status');
    const plot = node('div', undefined, 'hysteresis-plot');
    const note = node('p', 'Virgin material coupon · zero applied normal stress · prescribed strain cycles. This preview does not run or modify a structural analysis.', 'material-note');
    section.append(form, status, plot, note);
    parent.append(section);
    const settingsKey = JSON.stringify({ attributes, mechanism });
    const saved = this.settings.get(settingsKey);
    if (saved) { direction.value = saved.direction; amplitude.value = saved.amplitude ?? ''; cycles.value = saved.cycles; history.value = saved.history; }
    let result;
    const draw = () => {
      if (result && plot.clientWidth) plot.replaceChildren(this.chart(result.points, units, Math.max(360, plot.clientWidth)));
    };
    this.resizeObserver = new ResizeObserver(draw);
    this.resizeObserver.observe(plot);
    const calculate = async () => {
      const request = { attributes, mechanism, direction: direction.value, cycles: Number(cycles.value), amplitude: amplitude.value || null, history: history.value };
      this.settings.set(settingsKey, { direction: request.direction, cycles: request.cycles, amplitude: request.amplitude, history: request.history });
      const key = JSON.stringify(request);
      run.disabled = true; download.disabled = true;
      status.textContent = 'Calculating with Python spring laws…';
      try {
        let data = this.cache.get(key);
        if (!data) {
          const response = await fetch('/api/material/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: key });
          data = await response.json();
          if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
          this.cache.set(key, data);
          if (this.cache.size > 50) this.cache.delete(this.cache.keys().next().value);
        }
        if (!section.isConnected) return;
        result = data;
        amplitude.value = Number(data.amplitude.toPrecision(10)).toString();
        // Start with a chart even when this workspace is initially hidden;
        // resize observation fits the axes when the page becomes visible.
        plot.replaceChildren(this.chart(data.points, units, Math.max(360, plot.clientWidth || 900)));
        status.textContent = `${data.points.length.toLocaleString()} samples · peak strain ±${number(data.amplitude)} · ${data.cycles} ${history.value === 'cyclic' ? 'cycles' : 'loading stages'} · ${unitSets[units].stress[0]}`;
        note.textContent = data.description;
        download.disabled = false;
      } catch (error) {
        plot.replaceChildren();
        status.textContent = `Preview unavailable: ${error.message}`;
      } finally { run.disabled = false; }
    };
    form.onsubmit = event => { event.preventDefault(); if (form.reportValidity()) calculate(); };
    download.onclick = () => {
      if (!result) return;
      const [unit, factor] = unitSets[units].stress;
      const csv = `sample,strain,stress (${unit})\n` + result.points.map(([strain, stress], i) => `${i},${strain},${stress * factor}`).join('\n');
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      const link = node('a'); link.href = url; link.download = `${attributes.Name || 'masonry'}-${mechanism}-hysteresis.csv`; link.click(); URL.revokeObjectURL(url);
    };
    calculate();
  }

  chart(points, units, width = 900) {
    const [unit, factor] = unitSets[units].stress;
    const data = points.map(([strain, stress]) => [strain, stress * factor]);
    const height = 370, left = 85, right = 25, top = 35, bottom = 65;
    const xs = data.map(p => p[0]), ys = data.map(p => p[1]);
    let xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const dx = (xmax - xmin) || 1e-6, dy = (ymax - ymin) || 1;
    xmin -= dx * .06; xmax += dx * .06; ymin -= dy * .08; ymax += dy * .08;
    const x = v => left + (v - xmin) / (xmax - xmin) * (width - left - right);
    const y = v => height - bottom - (v - ymin) / (ymax - ymin) * (height - top - bottom);
    const svg = svgNode('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': `Calculated material hysteresis: strain versus stress in ${unit}` });
    svg.append(svgNode('title', {}, `Calculated ${points.length}-sample cyclic material response`));
    const ticks = width < 600 ? 4 : 5;
    for (let i = 0; i <= ticks; i++) {
      const xv = xmin + (xmax - xmin) * i / ticks, yv = ymin + (ymax - ymin) * i / ticks;
      svg.append(svgNode('line', { x1: x(xv), x2: x(xv), y1: top, y2: height - bottom, class: 'plot-grid' }),
        svgNode('line', { x1: left, x2: width - right, y1: y(yv), y2: y(yv), class: 'plot-grid' }),
        svgNode('text', { x: x(xv), y: height - bottom + 23, 'text-anchor': 'middle', class: 'plot-tick' }, number(xv)),
        svgNode('text', { x: left - 12, y: y(yv) + 4, 'text-anchor': 'end', class: 'plot-tick' }, number(yv)));
    }
    svg.append(svgNode('line', { x1: x(0), x2: x(0), y1: top, y2: height - bottom, class: 'plot-zero' }),
      svgNode('line', { x1: left, x2: width - right, y1: y(0), y2: y(0), class: 'plot-zero' }),
      svgNode('text', { x: width / 2, y: height - 13, 'text-anchor': 'middle', class: 'plot-label' }, 'Strain, ε [dimensionless]'),
      svgNode('text', { x: left, y: 19, class: 'plot-label' }, `Stress [${unit}]`));
    svg.append(svgNode('path', { d: data.map(([a, b], i) => `${i ? 'L' : 'M'}${x(a).toFixed(2)},${y(b).toFixed(2)}`).join(' '), class: 'hysteresis-curve' }));
    const marker = svgNode('circle', { r: 5, class: 'plot-marker', visibility: 'hidden' });
    const readout = svgNode('text', { x: width - right, y: 19, 'text-anchor': 'end', class: 'plot-label' });
    svg.append(marker, readout);
    svg.addEventListener('pointermove', event => {
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
      let nearest = data[0], distance = Infinity;
      for (const sample of data) {
        const d = (x(sample[0]) - point.x) ** 2 + (y(sample[1]) - point.y) ** 2;
        if (d < distance) { distance = d; nearest = sample; }
      }
      marker.setAttribute('cx', x(nearest[0])); marker.setAttribute('cy', y(nearest[1])); marker.setAttribute('visibility', 'visible');
      readout.textContent = `ε ${number(nearest[0])} · σ ${number(nearest[1])} ${unit}`;
    });
    svg.addEventListener('pointerleave', () => { marker.setAttribute('visibility', 'hidden'); readout.textContent = ''; });
    return svg;
  }
}
