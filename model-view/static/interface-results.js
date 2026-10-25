import * as THREE from 'three';
import { phaseColors } from './stress-data.js';
import { InterfaceStressView } from './interface-stress-view.js';
import { downloadCsv, responseChart } from './result-charts.js';
import { resultantAt, normalTolerance, eccentricities, thrustPosition } from './interface-resultants.js';

const fmt = v => v == null ? '—' : v && Math.abs(v) < 1e-4 ? v.toExponential(3) : Number(v).toLocaleString(undefined, { maximumSignificantDigits: 5 });
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const color = (value, maximum) => {
  if (value == null) return '#677789';
  const t = Math.min(1, Math.abs(value) / (maximum || 1));
  return new THREE.Color('#e1e6eb').lerp(new THREE.Color(value < 0 ? '#527cda' : '#e76152'), t).getStyle();
};

export class InterfaceResults {
  constructor(root, onStep) {
    this.root = root; this.onStep = onStep;
    root.innerHTML = `<div class="eyebrow">INTERFACE RESULTS</div><h1>Stress contours</h1><p class="interface-intro">Select a colored interface directly in the 3D view. Its fibre contour and values appear on the right.</p><div class="interface-visual"></div>
      <details class="interface-browser"><summary>Find an interface by ID</summary><div class="interface-filters"><input type="search" aria-label="Find interface" placeholder="Interface ID, parent or phase…"><label><input type="checkbox" checked> Restraints only</label><span class="interface-count"></span></div><select size="6" aria-label="Interface by ID" class="interface-id-picker"></select></details>
      <details class="interface-advanced"><summary>Forces, moments, thrust history & exports</summary><p class="result-note">Forces and moments have a saved value at every step. Playback switches the 3D field to normal force N2; spring stress and phase contours are available at the final step only.</p><div class="interface-step-controls"><button aria-label="Play interface history">▶ Play</button><button aria-label="Previous interface step">‹</button><button aria-label="Next interface step">›</button><input type="range" min="0" max="0" value="0" step="1" aria-label="Interface analysis step"><output></output></div><div class="interface-detail"><p>Select an interface in the model.</p></div></details>`;
    this.stressView = new InterfaceStressView(root.querySelector('.interface-visual'), key => this.select(key), onStep);
    this.advanced = root.querySelector('.interface-advanced');
    this.advanced.ontoggle = () => {
      if (!this.advanced.open) { this.clearThrustMarker(); return; }
      if (this.selected == null) return;
      if (this.detail?.key === this.selected && this.detail.analysis === this.analysis.name && this.currentPanel?.isConnected) this.renderCurrent();
      else this.select(this.selected);
    };
    const controls = root.querySelector('.interface-step-controls');
    this.stepSlider = controls.querySelector('input'); this.stepLabel = controls.querySelector('output'); this.playButton = controls.querySelector('button');
    const forceStep = index => { this.pause(); this.stressView.field.value = 'normalForce'; this.onStep(index); };
    this.stepSlider.oninput = () => forceStep(Number(this.stepSlider.value));
    const transport = controls.querySelectorAll('button');
    transport[0].onclick = () => this.timer ? this.pause() : this.play();
    transport[1].onclick = () => forceStep(Math.max(0, this.stepIndex - 1));
    transport[2].onclick = () => forceStep(Math.min(this.analysis.steps.length - 1, this.stepIndex + 1));
    this.search = root.querySelector('input[type=search]'); this.supports = root.querySelector('.interface-browser input[type=checkbox]');
    this.search.oninput = this.supports.onchange = () => this.list();
    this.idPicker = root.querySelector('.interface-id-picker'); this.idPicker.onchange = () => this.select(Number(this.idPicker.value));
  }

  destroy() {
    this.pause(); this.ticket = (this.ticket || 0) + 1;
    this.clearThrustMarker(); this.stressView.destroy();
  }

  update(analysis, mesh, stepIndex, modelSha256, sourceId) {
    const changed = this.analysis !== analysis;
    this.sourceId = sourceId; this.mesh = mesh; this.modelSha256 = modelSha256; this.stepIndex = stepIndex;
    this.stepSlider.max = analysis.steps.length - 1; this.stepSlider.value = stepIndex;
    this.stepLabel.textContent = `Step ${analysis.steps[stepIndex].step} / ${analysis.steps.at(-1).step} · ${analysis.steps[stepIndex].status} · 5 steps/s`;
    this.analysis = analysis;
    if (changed) {
      this.pause();
      const selected = analysis.interfaces.find(i => i.key === this.selected) || analysis.interfaces.filter(i => i.restrained).sort((a,b) => a.forces[1]-b.forces[1])[0] || analysis.interfaces[0];
      this.selected = selected?.key;
    }
    this.stressView.update(analysis, mesh, stepIndex, modelSha256, this.selected, sourceId);
    this.viewer = this.stressView.viewer;
    if (changed) { this.list(); if (this.selected != null) this.select(this.selected); }
    else this.renderCurrent();
  }

  list() {
    if (!this.analysis) return;
    const q = this.search.value.trim().toLowerCase();
    const rows = this.analysis.interfaces.filter(i => (!this.supports.checked || i.restrained) && `${i.key} ${i.parents.join(' ')} ${i.materialKey} ${Object.keys(i.phases).join(' ')}`.toLowerCase().includes(q));
    const parentLabel = i => i.parentTypes ? `${i.parentTypes[0]} #${i.parents[0]} / ${i.parentTypes[1]} #${i.parents[1]}` : `parents ${i.parents.join(' / ')}`;
    this.idPicker.replaceChildren(...rows.map(i => new Option(`#${i.key} · ${i.restrained ? 'Restraint' : 'Element interface'} · ${parentLabel(i)}`, i.key, false, i.key === this.selected)));
    this.root.querySelector('.interface-count').textContent = `${rows.length} interfaces`;
  }

  async select(key) {
    this.pause();
    this.selected = key; this.list(); this.stressView.selectKey(key);
    const ticket = this.ticket = (this.ticket || 0) + 1;
    this.clearThrustMarker();
    const detail = this.root.querySelector('.interface-detail'); detail.replaceChildren(node('p', `Reading interface #${key}…`));
    // The visual contour already contains the selected spring values. Load
    // additional force/sliding details only when their disclosure is opened.
    if (!this.advanced.open) return;
    try {
      const response = await fetch(`/api/results/${encodeURIComponent(this.sourceId)}/interface?analysis=${encodeURIComponent(this.analysis.name)}&key=${key}`);
      const data = await response.json();
      if (ticket !== this.ticket) return;
      if (!response.ok) throw new Error(data.error || 'Unable to read interface.');
      const finalResultant = resultantAt(this.analysis, this.analysis.steps.length - 1, key);
      if (data.modelSha256 !== this.modelSha256 || ![...data.forces, ...data.moments].every((v, i) => v === [...finalResultant.forces, ...finalResultant.moments][i])) {
        throw new Error('Result files changed. Reload Results to load a consistent dataset.');
      }
      this.detail = data;
      detail.replaceChildren(node('h2', `Interface #${key} · ${data.analysis}`));
      this.currentPanel = node('section', undefined, 'interface-current'); detail.append(this.currentPanel);
      this.historyPlot = node('div', undefined, 'interface-history-plot');
      const historyControls = node('div', undefined, 'curve-controls'), historyLabel = node('label', 'Interface history');
      this.historyQuantity = node('select'); this.historyQuantity.setAttribute('aria-label', 'Interface history quantity');
      for (const [v, t] of [['forces', 'Forces'], ['moments', 'Moments'], ['thrust', 'Compression thrust path']]) this.historyQuantity.add(new Option(t, v));
      this.historyQuantity.onchange = () => this.renderCurrent(); historyLabel.append(this.historyQuantity);
      const exportHistory = node('button', 'Export resultants CSV'); exportHistory.onclick = () => this.exportHistory();
      historyControls.append(historyLabel, exportHistory); detail.append(historyControls, this.historyPlot);
      this.snapshotNotice = node('p', undefined, 'result-note');
      const finalButton = node('button', 'Go to final spring snapshot'); finalButton.onclick = () => { this.pause(); this.onStep(this.analysis.steps.length - 1); };
      this.finalButton = finalButton; detail.append(this.snapshotNotice, finalButton);
      this.snapshotPanel = node('section'); detail.append(this.snapshotPanel);
      const snapshot = this.snapshotPanel;
      snapshot.append(node('h3', `Spring snapshot · final step ${this.analysis.steps.at(-1).step}`));
      const p1Type = data.geometry.parent_type_element1 || 'Element';
      const p2Type = data.geometry.parent_type_element2 || 'Element';
      detail.append(node('p', `Parents: ${p1Type} #${data.geometry.parent_element_key1} / ${p2Type} #${data.geometry.parent_element_key2} · material ${this.analysis.interfaces.find(i => i.key === key).materialKey}`, 'result-note'));
      const axes = node('p', `Local axes: e1 (${data.geometry.reference_e1.map(fmt).join(', ')}), e2 (${data.geometry.reference_e2.map(fmt).join(', ')}), e3 (${data.geometry.reference_e3.map(fmt).join(', ')})`, 'result-note'); detail.append(axes);
      const controls = node('div', undefined, 'curve-controls');
      const label = node('label', 'Fibre map'); const select = node('select'); select.setAttribute('aria-label', 'Spring map quantity');
      const quantities = [['stress', 'Normal stress [MPa]'], ['phase', 'Constitutive phase'], ['force', 'Normal force [kN]']];
      if (data.normal.some(s => s.strain != null || s.displacement != null)) quantities.splice(1, 0, ['strain', 'Normal strain [cm]']);
      for (const [value, text] of quantities) select.add(new Option(text, value)); label.append(select);
      const csv = node('button', 'Export springs CSV'); csv.onclick = () => downloadCsv(`${data.analysis}-interface-${key}.csv`, [['group', 'index', 'row', 'column', 'force_kN', 'gross_area_cm2', 'nominal_stress_MPa', 'strain_cm', 'phase'], ...[...data.normal.map(s => ({ ...s, group: 'normal' })), ...data.sliding].map(s => [s.group, s.index, s.row, s.col, s.force, s.area, s.stress, s.strain ?? s.displacement, s.phase])]);
      controls.append(label, csv); snapshot.append(controls);
      const map = node('div', undefined, 'spring-map'), readout = node('p', 'Hover or focus a fibre for force, stress and phase.', 'spring-readout'); snapshot.append(map, readout);
      select.onchange = () => this.drawMap(map, readout, select.value); this.drawMap(map, readout, select.value);
      const phases = node('div', undefined, 'phase-legend');
      for (const [phase, count] of Object.entries(this.analysis.interfaces.find(i => i.key === key).phases)) { const item = node('span', `${phase} (${count})`); item.style.borderColor = phaseColors[phase] || '#8193a5'; phases.append(item); } snapshot.append(phases);
      snapshot.append(node('p', 'σ = fibre force / fibre area. Sliding τ below is nominal force / gross area, not force / compressed contact area.', 'result-note'));
      const localForces = node('details'); localForces.append(node('summary', 'Final local resisting force vector (12 DOFs, native kN / kN·cm)'));
      if (Array.isArray(data.localForces) && data.localForces.length) {
        localForces.append(node('p', data.localForces.map(fmt).join(', '), 'result-note'));
      } else {
        localForces.append(node('p', 'The 12-DOF local resisting force vector is not exported by this result format.', 'result-note'));
      }
      snapshot.append(localForces);
      const table = node('table', undefined, 'result-table');
      const head = node('tr'); for (const text of ['Sliding link', 'Force [kN]', 'τ nom. [MPa]', 'Phase']) head.append(node('th', text)); table.append(head);
      data.sliding.forEach((s, i) => { const tr = node('tr'); for (const text of [`${s.group === 'slid' ? 'In-plane' : 'Out-of-plane'} ${i + 1}`, fmt(s.force), fmt(s.stress), s.phase]) tr.append(node('td', text)); table.append(tr); }); snapshot.append(table);
      this.locate(data.geometry);
      this.renderCurrent();
    } catch (error) {
      if (ticket !== this.ticket) return;
      detail.replaceChildren(node('p', error.message)); const retry = node('button', 'Retry'); retry.onclick = () => this.select(key); detail.append(retry);
    }
  }

  play() {
    if (!this.analysis || this.timer) return;
    this.stressView.field.value = 'normalForce'; this.stressView.paint();
    if (this.stepIndex === this.analysis.steps.length - 1) this.onStep(0);
    this.playButton.textContent = 'Ⅱ Pause'; this.playButton.setAttribute('aria-label', 'Pause interface history');
    this.timer = setInterval(() => {
      this.onStep(Math.min(this.analysis.steps.length - 1, this.stepIndex + 1));
      if (this.stepIndex === this.analysis.steps.length - 1) this.pause();
    }, 200);
  }

  pause() {
    clearInterval(this.timer); this.timer = null;
    this.playButton.textContent = '▶ Play'; this.playButton.setAttribute('aria-label', 'Play interface history');
  }

  clearThrustMarker() {
    if (!this.thrustMarker || !this.viewer) return;
    this.viewer.scene.remove(this.thrustMarker);
    this.thrustMarker.geometry.dispose(); this.thrustMarker.material.dispose(); this.thrustMarker = null;
    this.viewer.needsRender = true;
  }

  renderCurrent() {
    if (!this.advanced.open) return;
    if (!this.detail || this.detail.key !== this.selected || this.detail.analysis !== this.analysis.name || !this.currentPanel?.isConnected) return;
    const r = resultantAt(this.analysis, this.stepIndex, this.selected), tol = normalTolerance(this.analysis, this.selected), e = eccentricities(r, tol);
    const step = this.analysis.steps[this.stepIndex];
    this.currentPanel.replaceChildren(node('h3', `Saved step ${step.step} · local resultants`));
    const props = node('dl', undefined, 'properties');
    for (const [label, value] of [['V1 / N2 / V3 [kN]', r.forces.map(fmt).join(' / ')], ['Mx / My / Mz [kN·cm]', r.moments.map(fmt).join(' / ')], ['ex = Mz / N2 [cm]', e ? fmt(e.ex) : 'Undefined'], ['ey = Mx / N2 [cm]', e ? fmt(e.ey) : 'Undefined']]) {
      const row = node('div'); row.append(node('dt', label), node('dd', value)); props.append(row);
    }
    this.currentPanel.append(props, node('p', !e ? `Near-zero normal force (|N2| ≤ ${fmt(tol)} kN): thrust point omitted.` : e.compression ? 'Compression thrust point shown in green on the undeformed interface.' : 'Normal resultant is tensile: no compression thrust point.', 'result-note'));
    const final = this.stepIndex === this.analysis.steps.length - 1;
    this.snapshotPanel.classList.toggle('hidden', !final); this.finalButton.classList.toggle('hidden', final);
    this.snapshotNotice.textContent = final ? '' : 'Spring stress and phase histories are not saved at this step. The stage-end snapshot is available at the final step.';
    if (this.historyQuantity.value === 'thrust') this.drawThrustPath();
    else {
      const moments = this.historyQuantity.value === 'moments';
      const proxy = { name: this.analysis.name, steps: this.analysis.steps.map((s, i) => ({ ...s, reactions: resultantAt(this.analysis, i, this.selected)[moments ? 'moments' : 'forces'] })) };
      this.historyPlot.replaceChildren(responseChart(proxy, 'reactions', 'step', this.stepIndex, i => { this.pause(); this.onStep(i); }, false,
        { title: `Interface ${this.selected} ${moments ? 'moments' : 'forces'}`, unit: moments ? 'kN·cm' : 'kN', names: moments ? ['Mx', 'My', 'Mz'] : ['V1', 'N2', 'V3'] }));
    }
    if (this.viewer) {
      this.clearThrustMarker();
      const position = thrustPosition(this.detail.geometry, e);
      if (position) {
        const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(position, 3));
        this.thrustMarker = new THREE.Points(geo, new THREE.PointsMaterial({ color: '#7dffc4', size: 10, sizeAttenuation: false, depthTest: false, depthWrite: false, transparent: true }));
        this.thrustMarker.renderOrder = 20; this.viewer.scene.add(this.thrustMarker);
      }
      this.viewer.needsRender = true;
    }
  }

  drawThrustPath() {
    const g = this.detail.geometry, tol = normalTolerance(this.analysis, this.selected);
    const path = this.analysis.steps.map((s, i) => eccentricities(resultantAt(this.analysis, i, this.selected), tol));
    const footprint = g.vint2d.map(p => [p[0] - g.length / 2, p[1]]);
    const all = [...footprint, ...path.filter(e => e?.compression).map(e => [e.ex, e.ey])];
    let xmin = Math.min(...all.map(p => p[0])), xmax = Math.max(...all.map(p => p[0])), ymin = Math.min(...all.map(p => p[1])), ymax = Math.max(...all.map(p => p[1]));
    const dx = xmax - xmin || 1, dy = ymax - ymin || 1; xmin -= dx * .1; xmax += dx * .1; ymin -= dy * .1; ymax += dy * .1;
    const scale = Math.min(380 / (xmax - xmin), 250 / (ymax - ymin));
    const x = v => 245 + (v - (xmin + xmax) / 2) * scale, y = v => 165 - (v - (ymin + ymax) / 2) * scale;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 480 340'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `Compression thrust path at interface ${this.selected}`);
    const add = (tag, attrs, text) => { const n = document.createElementNS(svg.namespaceURI, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text) n.textContent = text; svg.append(n); return n; };
    add('polygon', { points: footprint.map(p => `${x(p[0])},${y(p[1])}`).join(' '), fill: '#2b3d49', stroke: '#d5ad72' });
    let previous = null;
    path.forEach((e, i) => {
      if (!e?.compression) { previous = null; return; }
      if (previous) add('line', { x1: x(previous.ex), y1: y(previous.ey), x2: x(e.ex), y2: y(e.ey), stroke: '#69d8c2', 'stroke-width': 2 });
      const dot = add('circle', { cx: x(e.ex), cy: y(e.ey), r: i === this.stepIndex ? 6 : 3, fill: i === this.stepIndex ? '#fff' : '#69d8c2', tabindex: 0 });
      const title = document.createElementNS(svg.namespaceURI, 'title'); title.textContent = `Step ${this.analysis.steps[i].step}: ex ${fmt(e.ex)} cm, ey ${fmt(e.ey)} cm`; dot.append(title);
      dot.onclick = () => { this.pause(); this.onStep(i); }; dot.onkeydown = ev => { if (ev.key === 'Enter') dot.onclick(); }; previous = e;
    });
    add('text', { x: 55, y: 20, fill: '#bcd0dc', 'font-size': 12 }, `ex [${fmt(xmin)} … ${fmt(xmax)} cm] · ey [${fmt(ymin)} … ${fmt(ymax)} cm]`);
    add('text', { x: 55, y: 320, fill: '#bcd0dc', 'font-size': 11 }, 'Thrust point trajectory across steps at this interface');
    this.historyPlot.replaceChildren(svg);
  }

  exportHistory() {
    const tol = normalTolerance(this.analysis, this.selected);
    downloadCsv(`${this.analysis.name}-interface-${this.selected}-resultants.csv`, [['step', 'V1_kN', 'N2_kN', 'V3_kN', 'Mx_kNcm', 'My_kNcm', 'Mz_kNcm', 'ex_cm', 'ey_cm', 'compression_thrust'], ...this.analysis.steps.map((s, i) => { const r = resultantAt(this.analysis, i, this.selected), e = eccentricities(r, tol); return [s.step, ...r.forces, ...r.moments, e?.ex, e?.ey, e?.compression ?? false]; })]);
  }

  drawMap(parent, readout, quantity) {
    const data = this.detail, rows = data.geometry.nrow, cols = data.geometry.ncol;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 400 345'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', `Interface ${data.key} spring grid: ${quantity}`);
    const getVal = s => quantity === 'strain' ? (s.strain ?? s.displacement) : s[quantity];
    const maximum = Math.max(...data.normal.map(s => Math.abs(getVal(s) || 0)));
    data.normal.forEach(s => {
      const rect = document.createElementNS(svg.namespaceURI, 'rect');
      const val = getVal(s);
      for (const [k, v] of Object.entries({ x: 30 + s.col * 330 / cols, y: 10 + s.row * 300 / rows, width: 330 / cols - 1, height: 300 / rows - 1, fill: quantity === 'phase' ? phaseColors[s.phase] || '#8193a5' : color(val, maximum), tabindex: 0 })) rect.setAttribute(k, v);
      const text = `Fibre ${s.index} · row ${s.row}, col ${s.col} · F ${fmt(s.force)} kN · σ ${fmt(s.stress)} MPa · ε ${fmt(s.strain ?? s.displacement)} cm · ${s.phase}`;
      const title = document.createElementNS(svg.namespaceURI, 'title'); title.textContent = text; rect.append(title); rect.onpointerenter = rect.onfocus = () => { readout.textContent = text; }; svg.append(rect);
    });
    const legend = document.createElementNS(svg.namespaceURI, 'text'); legend.setAttribute('x', '30'); legend.setAttribute('y', '335'); legend.setAttribute('fill', '#aabac7'); legend.setAttribute('font-size', '11');
    legend.textContent = quantity === 'phase' ? `${rows} rows × ${cols} columns · constitutive phases` : `Blue − / red + · range ±${fmt(maximum)} ${quantity === 'stress' ? 'MPa' : (quantity === 'strain' ? 'cm' : 'kN')}`; svg.append(legend); parent.replaceChildren(svg);
  }

  locate() {
    this.viewer = this.stressView.viewer;
    this.stressView.selectKey(this.selected);
  }
}
