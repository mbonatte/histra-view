import * as THREE from 'three';
import { QuadViewer } from './mesh-viewer.js';
import { resultantAt } from './interface-resultants.js';
import { decodeContours, contourGroups, stressColor, cssColor, phaseColors, maximumMagnitude } from './stress-data.js';

const fmt = n => n == null ? '—' : n && Math.abs(n) < 1e-4 ? n.toExponential(3) : Number(n.toPrecision(5)).toString();
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const svgEl = (tag, attrs, text) => { const n = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [k,v] of Object.entries(attrs)) n.setAttribute(k,v); if (text) n.textContent = text; return n; };

export class InterfaceStressView {
  constructor(root, onSelect, onStep) {
    this.root = root; this.onSelect = onSelect; this.onStep = onStep; this.cache = new Map();
    root.innerHTML = `<div class="stress-controls"><label>Color by<select aria-label="3D interface field"><option value="stress">Normal stress σn [MPa] · final step</option><option value="strain">Normal strain εn [cm] · final step</option><option value="phase">Normal phase · final step</option><option value="sliding">Sliding stress τ [MPa] · final step</option><option value="slidingOut">Out-of-plane sliding τ23 [MPa] · final step</option><option value="slidingPhase">Sliding phase · final step</option><option value="slidingOutPhase">Out-of-plane sliding phase · final step</option><option value="normalForce">Normal force N2 [kN] · selected step</option></select></label><label>Show<select aria-label="3D interface scope"><option value="supports">Restraint interfaces</option><option value="all">All interfaces in the model</option><option value="selected">Selected interface only</option></select></label><label class="stress-range-field">Color range<div class="stress-range-inputs"><input type="number" class="stress-min-input" step="any" placeholder="Min" aria-label="Color range minimum value"><span>to</span><input type="number" class="stress-max-input" step="any" placeholder="Max" aria-label="Color range maximum value"><button type="button" class="stress-auto-range" title="Reset to auto symmetric range">Auto</button></div></label><label class="stress-structure"><input type="checkbox" checked> Show structure</label><span class="stress-count"></span></div>
      <div class="stress-layout"><section class="stress-scene"><div class="stress-canvas" aria-label="Clickable 3D interface stress contours"></div><div class="stress-camera"><button data-stress-view="iso">3D</button><button data-stress-view="below">From below</button><button data-stress-view="front">Front</button><button data-stress-projection="perspective" class="active" title="Perspective camera">Persp</button><button data-stress-projection="ortho" title="Orthographic camera">Ortho</button><button class="stress-fit">Fit model</button></div><div class="stress-notice" role="status">Reading saved fibre contours…</div><div class="stress-hover">Click a colored interface to inspect it.</div></section>
      <aside class="stress-picked"><div class="eyebrow">SELECTED INTERFACE</div><h2 class="stress-picked-title">Click a colored surface</h2><p class="stress-picked-meta">Each colored cell is one saved normal spring.</p><div class="stress-picked-actions"><button class="stress-focus">Zoom to selection</button><button class="stress-isolate">Isolate</button></div><div class="stress-map" aria-label="Selected interface stress contour"></div><p class="stress-readout">Hover a cell for its stress, force and phase.</p><p class="stress-extrema"></p><p class="stress-field-note"></p></aside></div><div class="stress-legend"></div><p class="stress-help">Click to select · drag to orbit · scroll to zoom. Colors represent stress or strain on interface surfaces. Blue = compression, red = tension/opening. The selected interface is outlined in white.</p>`;
    [this.field, this.scope] = root.querySelectorAll('select');
    this.notice = root.querySelector('.stress-notice');
    this.rangeField = root.querySelector('.stress-range-field');
    this.minInput = root.querySelector('.stress-min-input');
    this.maxInput = root.querySelector('.stress-max-input');
    this.autoRangeBtn = root.querySelector('.stress-auto-range');
    this.field.onchange = () => {
      this.customMin = null;
      this.customMax = null;
      if (this.field.value !== 'normalForce' && !this.perStep && this.analysis && this.stepIndex !== this.analysis.steps.length - 1) this.onStep(this.analysis.steps.length - 1);
      this.paint();
    };
    this.scope.onchange = () => { this.paint(); if (this.scope.value === 'selected') this.focus(); };
    this.minInput.oninput = () => {
      const v = parseFloat(this.minInput.value);
      if (Number.isFinite(v)) { this.customMin = v; this.paint(); }
    };
    this.maxInput.oninput = () => {
      const v = parseFloat(this.maxInput.value);
      if (Number.isFinite(v)) { this.customMax = v; this.paint(); }
    };
    this.autoRangeBtn.onclick = () => {
      this.customMin = null;
      this.customMax = null;
      this.paint();
    };
    root.querySelector('.stress-structure input').onchange = e => { if (this.viewer) { this.viewer.modelGroup.visible = e.target.checked; this.viewer.needsRender = true; } };
    root.querySelector('.stress-focus').onclick = () => this.focus();
    root.querySelector('.stress-isolate').onclick = () => {
      this.scope.value = 'selected'; root.querySelector('input').checked = false;
      if (this.viewer) this.viewer.modelGroup.visible = false;
      this.paint(); this.focus();
    };
    root.querySelector('.stress-fit').onclick = () => this.viewer?.fit();
    for (const button of root.querySelectorAll('[data-stress-view]')) button.onclick = () => this.setView(button.dataset.stressView);
    for (const button of root.querySelectorAll('[data-stress-projection]')) button.onclick = () => {
      this.viewer?.setProjection(button.dataset.stressProjection);
      for (const other of root.querySelectorAll('[data-stress-projection]')) other.classList.toggle('active', other === button);
    };
  }

  async update(analysis, mesh, stepIndex, modelSha256, selected, sourceId) {
    const stepValue = analysis.steps[stepIndex]?.step;
    const perStep = ['benchmark', 'bridge_scour'].includes(sourceId) || sourceId.startsWith('imported_');
    const changed = this.analysis !== analysis || this.sourceId !== sourceId
      || (perStep && this.stepValue !== stepValue);
    this.sourceId = sourceId;
    this.analysis = analysis; this.stepIndex = stepIndex; this.selected = selected ?? this.selected; this.modelSha256 = modelSha256;
    this.stepValue = stepValue; this.perStep = perStep;
    const suffix = perStep ? 'selected step' : 'final step';
    const labels = {
      stress: `Normal stress σn [MPa] · ${suffix}`,
      strain: `Normal strain εn [cm] · ${suffix}`,
      phase: `Normal phase · ${suffix}`,
      sliding: `Sliding stress τ [MPa] · ${suffix}`,
      slidingOut: `Out-of-plane sliding τ23 [MPa] · ${suffix}`,
      slidingPhase: `Sliding phase · ${suffix}`,
      slidingOutPhase: `Out-of-plane sliding phase · ${suffix}`,
      normalForce: 'Normal force N2 [kN] · selected step'
    };
    for (const [value, text] of Object.entries(labels)) {
      const option = this.field.querySelector(`option[value="${value}"]`);
      if (option && !option.disabled) option.textContent = text;
    }
    if (!this.viewer) {
      this.viewer = new QuadViewer(this.root.querySelector('.stress-canvas'), { extrude: true, opacity: .12, edges: false, colorBy: 'single' });
      this.viewer.loadPreview(mesh); this.viewer.grid.visible = false;
      this.setView('below');
      const activeProj = this.root.querySelector('[data-stress-projection].active')?.dataset.stressProjection;
      if (activeProj) this.viewer.setProjection(activeProj);
      this.viewer.pickOverlay = () => {
        const hit = this.pick(this.viewer.raycaster);
        if (!hit) return false;
        this.selectKey(hit.key, hit.cell); this.onSelect(hit.key); return true;
      };
      const canvas = this.viewer.renderer.domElement;
      let last = 0, dragging = false;
      this.viewer.controls.addEventListener('start', () => { dragging = true; });
      this.viewer.controls.addEventListener('end', () => { dragging = false; });
      canvas.addEventListener('pointermove', event => {
        if (dragging || performance.now() - last < 80) return;
        last = performance.now();
        const rect = canvas.getBoundingClientRect(), ray = new THREE.Raycaster();
        ray.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), this.viewer.camera);
        const hit = this.pick(ray);
        canvas.style.cursor = hit ? 'pointer' : 'grab';
        this.root.querySelector('.stress-hover').textContent = hit ? this.cellText(hit.key, hit.cell) : 'Click a colored interface to inspect it.';
      });
    }
    this.viewer.resize();
    if (!changed && this.data) { this.paint(); return; }
    const ticket = this.ticket = (this.ticket || 0) + 1;
    this.data = null; if (this.surface) this.surface.visible = false; this.pickMeshes = [];
    this.showNotice('Reading saved fibre contours…');
    try {
      const cacheKey = perStep
        ? `${sourceId}:${analysis.name}:${stepValue}`
        : `${sourceId}:${analysis.name}`;
      let data = this.cache.get(cacheKey);
      if (!data) {
        const stepQuery = perStep ? `&step=${encodeURIComponent(stepValue)}` : '';
        const response = await fetch(`/api/results/${encodeURIComponent(sourceId)}/contours?analysis=${encodeURIComponent(analysis.name)}${stepQuery}`);
        const raw = await response.json();
        if (!response.ok) throw new Error(raw.error || 'Unable to read contours.');
        data = decodeContours(raw);
        this.cache.set(cacheKey, data);
        if (this.cache.size > 4) this.cache.delete(this.cache.keys().next().value);
      }
      if (ticket !== this.ticket) return;
      if (data.modelSha256 !== modelSha256) throw new Error('The result model changed. Reload Results.');
      if (data.strainAvailable === false) {
        const strainOption = this.field.querySelector('option[value="strain"]');
        if (strainOption) { strainOption.disabled = true; strainOption.textContent = 'Normal strain (not exported)'; }
        if (this.field.value === 'strain') this.field.value = 'stress';
      }
      this.data = data;
      const slidingOption = this.field.querySelector('option[value="sliding"]');
      const slidingOutOption = this.field.querySelector('option[value="slidingOut"]');
      const slidingPhaseOption = this.field.querySelector('option[value="slidingPhase"]');
      const slidingOutPhaseOption = this.field.querySelector('option[value="slidingOutPhase"]');
      for (const [option, available] of [
        [slidingOption, Boolean(data.slidingStress)],
        [slidingOutOption, Boolean(data.slidingOutOfPlaneStress)],
        [slidingPhaseOption, Boolean(data.slidingPhase)],
        [slidingOutPhaseOption, Boolean(data.slidingOutOfPlanePhase)],
      ]) {
        if (!option) continue;
        option.disabled = !available;
        if (!available && this.field.value === option.value) this.field.value = 'stress';
      }
      this.build(); this.paint(); this.selectKey(this.selected);
    } catch (error) {
      if (ticket !== this.ticket) return;
      this.showNotice(error.message, () => { this.analysis = null; this.update(analysis, mesh, this.stepIndex, modelSha256, this.selected, sourceId); });
    }
  }

  destroy() {
    this.ticket = (this.ticket || 0) + 1;
    this.cache.clear();
    this.groupMeshes?.forEach(mesh => mesh.geometry.dispose());
    if (this.viewer) {
      this.viewer.scene.traverse(item => { item.geometry?.dispose(); if (Array.isArray(item.material)) item.material.forEach(material => material.dispose()); else item.material?.dispose(); });
      this.viewer.destroy();
    }
  }

  showNotice(text, retry) {
    this.notice.replaceChildren(el('span', text)); this.notice.classList.remove('hidden');
    if (retry) { const button = el('button', 'Retry'); button.onclick = retry; this.notice.append(button); }
  }

  build() {
    if (this.surface) { this.viewer.scene.remove(this.surface); this.surface.geometry.dispose(); this.surface.material.dispose(); }
    this.groupMeshes?.forEach(m => m.geometry.dispose());
    this.positionAttribute = new THREE.BufferAttribute(this.data.positions, 3);
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', this.positionAttribute);
    this.colors = new Float32Array(this.data.cellCount * 12); geometry.setAttribute('color', new THREE.BufferAttribute(this.colors, 3));
    this.surface = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
    this.viewer.scene.add(this.surface);
    this.groupMeshes = this.data.groups.map(g => {
      const indices = [];
      for (let c = g.start; c < g.start + g.count; c++) indices.push(c*4,c*4+1,c*4+2,c*4,c*4+2,c*4+3);
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', this.positionAttribute); geo.setIndex(indices);
      const bounds = new THREE.Box3().setFromPoints(g.corners.map(p => new THREE.Vector3(...p))); bounds.expandByScalar(.001);
      geo.boundingBox = bounds; geo.boundingSphere = bounds.getBoundingSphere(new THREE.Sphere());
      const pick = new THREE.Mesh(geo, this.surface.material); pick.userData.group = g; pick.updateMatrixWorld(); return pick;
    });
  }

  isPhaseField() {
    return ['phase', 'slidingPhase', 'slidingOutPhase'].includes(this.field.value);
  }

  valueAt(cell, group) {
    if (this.field.value === 'normalForce') {
      return resultantAt(this.analysis, this.stepIndex, group.key).forces[1];
    }
    if (this.field.value === 'strain') return (this.data.strain || this.data.displacement)[cell];
    if (this.field.value === 'sliding') return this.data.slidingStress?.[cell] ?? 0;
    if (this.field.value === 'slidingOut') return this.data.slidingOutOfPlaneStress?.[cell] ?? 0;
    return this.data.stress[cell];
  }

  paint() {
    if (!this.data || !this.surface) return;
    const final = this.stepIndex === this.analysis.steps.length - 1, snapshot = this.field.value !== 'normalForce';
    const missingSnapshot = snapshot && (this.perStep
      ? this.data.step !== this.analysis.steps[this.stepIndex].step
      : !final);
    if (missingSnapshot) {
      this.surface.visible = false; this.pickMeshes = []; this.highlight();
      this.showNotice(`Stress, strain and phase contours are available at final step ${this.data.step}.`);
      const button = el('button', 'Show final-step contour'); button.onclick = () => this.onStep(this.analysis.steps.length - 1); this.notice.append(button);
      this.root.querySelector('.stress-map').replaceChildren();
      this.root.querySelector('.stress-readout').textContent = '';
      this.root.querySelector('.stress-extrema').textContent = '';
      this.root.querySelector('.stress-legend').textContent = `No saved stress, strain or phase contour at step ${this.analysis.steps[this.stepIndex].step}.` ;
      this.root.querySelector('.stress-field-note').textContent = 'No intermediate spring snapshot is available.';
      this.viewer.needsRender = true; return;
    }
    this.notice.classList.add('hidden'); this.surface.visible = true;
    const phaseField = this.isPhaseField();
    if (phaseField) this.rangeField.classList.add('hidden');
    else this.rangeField.classList.remove('hidden');

    this.groups = contourGroups(this.data, this.scope.value, this.selected);
    const keys = new Set(this.groups.map(g => g.key)); this.pickMeshes = this.groupMeshes.filter(m => keys.has(m.userData.group.key));
    const indices = [], values = [];
    for (const g of this.groups) {
      for (let c = g.start; c < g.start + g.count; c++) {
        indices.push(c*4,c*4+1,c*4+2,c*4,c*4+2,c*4+3);
        if (!phaseField) values.push(this.valueAt(c, g));
      }
    }
    this.autoMagnitude = maximumMagnitude(values);
    this.rangeMin = this.customMin != null ? this.customMin : -this.autoMagnitude;
    this.rangeMax = this.customMax != null ? this.customMax : this.autoMagnitude;
    if (document.activeElement !== this.minInput) this.minInput.value = fmt(this.rangeMin);
    if (document.activeElement !== this.maxInput) this.maxInput.value = fmt(this.rangeMax);

    const color = new THREE.Color();
    for (const g of this.groups) {
      for (let c = g.start; c < g.start + g.count; c++) {
        if (phaseField) {
          const phaseArray = this.field.value === 'slidingOutPhase'
            ? this.data.slidingOutOfPlanePhase
            : this.field.value === 'slidingPhase' ? this.data.slidingPhase : this.data.phase;
          color.set(phaseColors[this.data.phaseNames[phaseArray[c]]] || '#8193a5');
        } else {
          color.setRGB(...stressColor(this.valueAt(c, g), this.rangeMin, this.rangeMax), THREE.SRGBColorSpace);
        }
        for (let vertex = 0; vertex < 4; vertex++) color.toArray(this.colors, c*12+vertex*3);
      }
    }
    this.surface.geometry.setIndex(indices); this.surface.geometry.getAttribute('color').needsUpdate = true;
    this.surface.geometry.computeBoundingSphere();
    this.root.querySelector('.stress-count').textContent = `${this.groups.length} interface${this.groups.length === 1 ? "" : "s"} · ${values.length.toLocaleString()} fibres`;
    this.drawLegend(); this.drawSelection(); this.highlight(); this.viewer.needsRender = true;
    this.root.querySelector('.stress-help').textContent = phaseField
      ? `Click a colored interface to select it. Colors identify constitutive phase at ${this.perStep ? 'the selected saved step' : 'the final saved step'}.`
      : (this.field.value === 'strain'
         ? 'Click to select · drag to orbit · scroll to zoom. Colors represent normal strain/deformation on interface surfaces. Blue = compression, red = opening. The selected interface is outlined in white.'
         : 'Click to select · drag to orbit · scroll to zoom. Colors represent stress on interface surfaces. Blue = compression, red = tension. The selected interface is outlined in white.');
  }

  drawLegend() {
    const legend = this.root.querySelector('.stress-legend'); legend.replaceChildren();
    if (this.isPhaseField()) {
      for (const phase of this.data.phaseNames) { const item = el('span', phase); item.style.borderColor = phaseColors[phase] || '#8193a5'; legend.append(item); }
    } else {
      const titles = {
        stress: `Normal stress σn [MPa] · step ${this.data.step}`,
        strain: `Normal strain εn [cm] · step ${this.data.step}`,
        sliding: `Sliding stress τ [MPa] · step ${this.data.step}`,
        slidingOut: `Out-of-plane sliding τ23 [MPa] · step ${this.data.step}`,
        normalForce: `Normal force N2 [kN] · step ${this.analysis.steps[this.stepIndex].step}`
      };
      const title = titles[this.field.value] || titles.stress;
      legend.append(
        el('span', title),
        el('span', fmt(this.rangeMin)),
        el('i', undefined, 'stress-gradient'),
        el('span', (this.rangeMin < 0 && this.rangeMax > 0) ? '0' : ''),
        el('span', fmt(this.rangeMax)),
        el('small', (this.customMin != null || this.customMax != null) ? 'Custom color range' : 'One color scale for all visible interfaces')
      );
    }
  }

  selectKey(key, cell) {
    this.selected = Number(key);
    if (!this.data) return;
    const group = this.data.groups.find(g => g.key === this.selected); if (!group) return;
    if (cell == null && this.selectedGroup?.key === group.key && this.selectedCell != null) cell = this.selectedCell;
    this.selectedGroup = group;
    if (cell == null) {
      cell = group.start;
      for (let i = group.start; i < group.start + group.count; i++) if (Math.abs(this.data.stress[i]) > Math.abs(this.data.stress[cell])) cell = i;
    }
    this.selectedCell = cell;
    if (this.scope.value === 'supports' && !group.restrained) this.scope.value = 'all';
    this.paint();
  }

  pick(raycaster) {
    if (!this.data || !this.surface?.visible) return null;
    const hit = raycaster.intersectObjects(this.pickMeshes || [], false)[0];
    if (!hit) return null;
    const g = hit.object.userData.group;
    return { key: g.key, cell: g.start + Math.floor(hit.faceIndex / 2) };
  }

  cellText(key, cell) {
    if (!this.data) return '';
    if (this.field.value === 'normalForce') return `Interface #${key} · N2 ${fmt(resultantAt(this.analysis, this.stepIndex, key).forces[1])} kN · step ${this.analysis.steps[this.stepIndex].step}`;
    const strain = (this.data.strain || this.data.displacement)?.[cell];
    const sliding = this.data.slidingStress?.[cell];
    const slidingOut = this.data.slidingOutOfPlaneStress?.[cell];
    return `Interface #${key} · σn ${fmt(this.data.stress[cell])} MPa · τ ${fmt(sliding)} MPa · τ23 ${fmt(slidingOut)} MPa · εn ${fmt(strain)} cm · F ${fmt(this.data.force[cell])} kN · ${this.data.phaseNames[this.data.phase[cell]]}`;
  }

  drawSelection() {
    const g = this.selectedGroup; if (!g) return;
    this.root.querySelector('.stress-picked-title').textContent = `#${g.key} · ${g.restrained ? 'Restraint interface' : 'Element interface'}`;
    const parentDesc = g.parentTypes
      ? `${g.parentTypes[0]} #${g.parents[0]} / ${g.parentTypes[1]} #${g.parents[1]}`
      : `Parents ${g.parents.join(' / ')}`;
    this.root.querySelector('.stress-picked-meta').textContent = `${parentDesc} · ${g.nrow} × ${g.ncol} normal springs`;
    const map = this.root.querySelector('.stress-map'); map.replaceChildren();
    if (this.field.value !== 'normalForce'
        && (this.perStep ? this.data.step !== this.analysis.steps[this.stepIndex].step
                         : this.stepIndex !== this.analysis.steps.length - 1)) return;
    const local = c => [0,1,2,3].map(corner => {
      const p = Array.from(this.data.positions.slice(c*12+corner*3,c*12+corner*3+3)).map((v,i) => v-g.origin[i]);
      return [p.reduce((s,v,i)=>s+v*g.e1[i],0),p.reduce((s,v,i)=>s+v*g.e3[i],0)];
    });
    const all = [];
    for (let c=g.start;c<g.start+g.count;c++) all.push(...local(c));
    const xmin=Math.min(...all.map(p=>p[0])), xmax=Math.max(...all.map(p=>p[0])), ymin=Math.min(...all.map(p=>p[1])), ymax=Math.max(...all.map(p=>p[1]));
    const scale=Math.min(270/(xmax-xmin||1),220/(ymax-ymin||1));
    const x=v=>160+(v-(xmin+xmax)/2)*scale,y=v=>130-(v-(ymin+ymax)/2)*scale;
    const svg=svgEl('svg',{viewBox:'0 0 320 265',role:'img','aria-label':`Selected interface ${g.key} ${this.field.value} contour`});
    const force = this.field.value === 'normalForce' ? resultantAt(this.analysis,this.stepIndex,g.key).forces[1] : null;
    const phaseArray = this.field.value === 'slidingOutPhase'
      ? this.data.slidingOutOfPlanePhase
      : this.field.value === 'slidingPhase' ? this.data.slidingPhase : this.data.phase;
    for(let c=g.start;c<g.start+g.count;c++) {
      const v = force !== null ? force : this.valueAt(c, g);
      const fill=this.isPhaseField() ? phaseColors[this.data.phaseNames[phaseArray[c]]] || '#8193a5' : cssColor(stressColor(v, this.rangeMin, this.rangeMax));
      const polygon=svgEl('polygon',{points:local(c).map(p=>`${x(p[0])},${y(p[1])}`).join(' '),fill,stroke:c===this.selectedCell?'#fff':'#111820','stroke-width':c===this.selectedCell?2:0.35,tabindex:0});
      polygon.append(svgEl('title',{},this.cellText(g.key,c)));
      polygon.onpointerenter=polygon.onfocus=()=>{this.root.querySelector('.stress-readout').textContent=this.cellText(g.key,c);};
      polygon.onclick=()=>{this.selectedCell=c;this.drawSelection();this.highlight();};
      polygon.onkeydown=e=>{if(e.key==='Enter') polygon.onclick();}; svg.append(polygon);
    }
    svg.append(svgEl('text',{x:15,y:258,fill:'#9ab0c0','font-size':10},'Local interface plane · actual fibre cells'));
    map.append(svg);
    this.root.querySelector('.stress-readout').textContent=this.cellText(g.key,this.selectedCell);
    const vals = this.isPhaseField()
      ? []
      : Array.from({ length: g.count }, (_, index) => this.valueAt(g.start + index, g));
    const units = { stress: 'MPa', strain: 'cm', sliding: 'MPa', slidingOut: 'MPa' };
    this.root.querySelector('.stress-extrema').textContent=this.field.value==='normalForce'
      ? `Normal resultant: ${fmt(force)} kN`
      : (this.isPhaseField()
         ? 'Constitutive phases shown by colour.'
         : `${this.field.value === 'strain' ? 'Selected εn' : 'Selected value'}: ${fmt(Math.min(...vals))} to ${fmt(Math.max(...vals))} ${units[this.field.value] || ''}`);
    this.root.querySelector('.stress-field-note').textContent=this.field.value==='normalForce' ? 'N2 is a resultant shown uniformly over the face. Switch to a fibre field or phase for the saved spring values.' : `Saved spring values at step ${this.data.step}. Same scale as the 3D view; no averaging across interfaces.`;
  }

  highlight() {
    for (const item of this.outlines || []) { this.viewer.scene.remove(item); item.geometry.dispose(); item.material.dispose(); }
    this.outlines=[]; const g=this.selectedGroup;
    if(!g || !this.groups?.some(v=>v.key===g.key) || !this.surface.visible) return;
    const corners=Array.from(this.data.positions.slice(this.selectedCell*12,this.selectedCell*12+12));
    for(const positions of [g.corners.flat(),corners]) {
      const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
      const line=new THREE.LineLoop(geometry,new THREE.LineBasicMaterial({color:'#fff',depthTest:false,transparent:true,depthWrite:false})); line.renderOrder=30;this.viewer.scene.add(line);this.outlines.push(line);
    }
    this.viewer.needsRender=true;
  }

  focus() {
    if(!this.selectedGroup || !this.viewer) return;
    const box=new THREE.Box3().setFromPoints(this.selectedGroup.corners.map(p=>new THREE.Vector3(...p))),center=box.getCenter(new THREE.Vector3());
    const direction=this.viewer.camera.position.clone().sub(this.viewer.controls.target).normalize(),distance=Math.max(box.getSize(new THREE.Vector3()).length()*1.8,10);
    this.viewer.controls.target.copy(center);this.viewer.camera.position.copy(center).addScaledVector(direction,distance);
    if(this.viewer.camera.isOrthographicCamera){this.viewer.camera.zoom=Math.max((this.viewer._orthoHalfHeight||100)/(distance*0.4),0.1);this.viewer.camera.updateProjectionMatrix();}
    this.viewer.controls.update();this.viewer.needsRender=true;
  }

  setView(view) {
    if(!this.viewer) return;
    this.viewer.setView(view==='below'?'iso':view);
    if(view==='below') {this.viewer.camera.position.z=2*this.viewer.controls.target.z-this.viewer.camera.position.z;this.viewer.controls.update();}
    this.viewer.needsRender=true;
  }
}
