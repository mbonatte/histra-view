import { viewSettings, viewSettingsMarkup, bindViewSettings, applyViewerSettings } from './view-settings.js';
import { resultFieldStepIndex } from './result-field-policy.js';
import * as THREE from 'three';
import { QuadViewer } from './mesh-viewer.js';
import { decodeQuadDisplacements, deformedPoints, deformedQuadPoints, computeDisplacementContours, computeScalarContours, csharpStressColormap, displacementColormap, grayColormap, turboColormap, viridisColormap, coolwarmColormap } from './deformation.js';
import { responseChart, ResponseCurves } from './result-charts.js';
import { InterfaceResults } from './interface-results.js';
import { computeThrustLines } from './thrust-line.js';
import { downloadBlob, exportDimensions, exportViewerPng, sanitizeFilename } from './export-image.js';

const number = value => {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  const numeric = Number(value);
  return numeric !== 0 && Math.abs(numeric) < 1e-4
    ? numeric.toExponential(3)
    : numeric.toLocaleString(undefined, { maximumSignificantDigits: 6 });
};

const PALETTES = {
  csharp: {
    label: 'C# stress',
    colormap: csharpStressColormap,
    colors: ['#00008b', '#0000ff', '#00bfff', '#add8e6', '#00ff00', '#90ee90', '#ffff00', '#ffa500', '#ff0000'],
  },
  displacement: {
    label: 'Blue–green–red',
    colormap: displacementColormap,
    colors: ['#1933d9', '#19bfd9', '#33d94c', '#f2d919', '#e62619'],
  },
  turbo: {
    label: 'Turbo',
    colormap: turboColormap,
    colors: ['#30123b', '#4458cb', '#1a9bd9', '#21d48e', '#7bf43a', '#d5e21a', '#ffb81a', '#f66b0d', '#d32e00', '#8a0b00', '#7a0403'],
  },
  viridis: {
    label: 'Viridis',
    colormap: viridisColormap,
    colors: ['#440154', '#414d8a', '#2a6f8e', '#1b8f82', '#2aab6c', '#5dc863', '#a2d84f', '#d8e219', '#fde725'],
  },
  coolwarm: {
    label: 'Blue–white–red',
    colormap: coolwarmColormap,
    colors: ['#3b4cbf', '#7399db', '#dddddd', '#f28c66', '#b30026'],
  },
  gray: {
    label: 'Grayscale',
    colormap: grayColormap,
    colors: ['#242424', '#4a4a4a', '#777777', '#a4a4a4', '#d1d1d1'],
  },
};

const PHASE_HEX = ['#67cbb4', '#ed796d', '#bb78e7', '#7ba4e5', '#53c7db', '#e7bb6b', '#c1d375', '#ff4f87', '#f4a34f', '#f4d44f'];
const phaseColormap = value => {
  const color = new THREE.Color(PHASE_HEX[Math.max(0, Math.min(PHASE_HEX.length - 1, Math.round(value * (PHASE_HEX.length - 1))))]);
  return [color.r, color.g, color.b];
};
PALETTES.phase = {
  label: 'Constitutive phase',
  colormap: phaseColormap,
  colors: PHASE_HEX,
};

const paletteSpec = (name, field) => {
  if (name && name !== 'auto' && PALETTES[name]) return PALETTES[name];
  if (field?.kind === 'stress') return PALETTES.csharp;
  if (field?.kind === 'plastic') return PALETTES.gray;
  if (field?.kind === 'phase') return PALETTES.phase;
  return PALETTES.displacement;
};

export class ResultsPage {
  constructor(root, onSummary = () => {}) {
    this.root = root;
    this.onSummary = onSummary;
    this.section = 'shape';
    this.colorRangeCustom = null;
    this.stepFieldCache = new Map();
    this.stepFields = null;
    this.pendingStepField = null;
    this.prefetchAttempted = new Set();
    this.prefetchTimer = null;
    this.modalShapeCache = new Map();
    this.pendingModalShape = null;
    this.thrustSliderInitialized = false;
    this.thrustMaxForce = 0;
    this.importedData = null;
    this.hiddenMaterials = new Set();
    this.analysisCache = new Map();
    this.activeChainAnalyses = null;
    this.chainedAnalysis = null;
    root.innerHTML = `
      <aside class="results-sidebar">
        <div class="panel-title">ANALYSIS RESULTS <span class="count">DEFORMATION</span></div>
        <nav class="result-sections" aria-label="Result types"><button data-result-section="shape" aria-pressed="true">Deformed shape</button><button data-result-section="modes" aria-pressed="false">Modal shapes</button><button data-result-section="curves" aria-pressed="false">Response curves</button><button data-result-section="interfaces" aria-pressed="false">Stress contours</button></nav>
        <section class="results-controls">
          <div class="eyebrow">SAVED ANALYSIS</div>
          <h1>Deformed shape</h1>
          <p class="results-description">Explore movement through each analysis stage.</p>
          <div class="result-source-actions">
            <label class="field">Result source<select id="resultDataset" disabled aria-label="Result source"></select></label>
            <button id="sidebarImportResult" class="sidebar-import-btn" type="button" title="Import HRX + .Results, .histra, .json, or archive">📁 Import file…</button>
          </div>
          <p id="resultDiagnostics" class="result-diagnostics hidden" role="status"></p>
          <label class="field">Analysis<select id="resultAnalysis" disabled aria-label="Result analysis"></select></label>
          <div id="modeControls" class="hidden"><label class="field">Modal analysis<select id="modalAnalysis" aria-label="Modal analysis"></select></label><label class="field">Mode order<select id="modalSort" aria-label="Modal order"><option value="massY" selected>Effective mass Y (descending)</option><option value="massX">Effective mass X (descending)</option><option value="massZ">Effective mass Z (descending)</option><option value="frequency">Frequency (ascending)</option></select></label><label class="field">Mode<select id="modalMode" aria-label="Mode number"></select></label><dl class="properties"><div><dt>Frequency</dt><dd id="modalFrequency">—</dd></div><div><dt>Period</dt><dd id="modalPeriod">—</dd></div><div><dt>Effective mass X/Y/Z</dt><dd id="modalMass">—</dd></div></dl><p class="result-note">Shape normalized to maximum nodal |U| = 1. Scale sets display amplitude in cm. Animation uses a 2-second display cycle, independently of the physical frequency.</p></div>
          <div id="resultDrawingControls">
          <label class="field">Deformation scale
            <div class="result-scale-row"><input id="resultScale" type="number" min="0" max="1000000" step="any" value="10" aria-label="Deformation scale"><span>×</span></div>
          </label>
          <div class="result-scale-actions"><button id="resultActual">Actual size · 1×</button><button id="resultAuto">Auto scale</button></div>
          <label class="field">Color map
            <select id="resultColorBy" aria-label="Color map component">
              <option value="none">Uniform (model color)</option>
              <option value="magnitude" selected>Displacement |U| (magnitude)</option>
              <option value="x">Displacement Ux (X direction)</option>
              <option value="y">Displacement Uy (Y direction)</option>
              <option value="z">Displacement Uz (Z / vertical)</option>
            </select>
          </label>
          <label class="field">Color palette
            <select id="resultPalette" aria-label="Color palette">
              <option value="auto" selected>Auto (field default)</option>
              <option value="csharp">C# stress</option>
              <option value="displacement">Blue–green–red</option>
              <option value="turbo">Turbo</option>
              <option value="viridis">Viridis</option>
              <option value="coolwarm">Blue–white–red</option>
              <option value="gray">Grayscale</option>
            </select>
          </label>
          <label class="field">Color range
            <div class="result-range-row">
              <input id="resultColorMin" type="number" step="any" placeholder="Auto min" aria-label="Color range minimum">
              <span>to</span>
              <input id="resultColorMax" type="number" step="any" placeholder="Auto max" aria-label="Color range maximum">
              <button id="resultColorAuto" type="button">Auto</button>
            </div>
          </label>
          <div class="toggle-row"><label for="resultGhost">Undeformed outline</label><input id="resultGhost" type="checkbox" checked></div>
          <details class="result-shared-settings"><summary>Global view settings</summary><div id="resultSharedViewSettings">${viewSettingsMarkup('result', { result: true })}</div></details>
          <div class="toggle-row"><label for="resultThrust">Line of thrust <span class="thrust-badge">●</span></label><input id="resultThrust" type="checkbox"></div>
          <div class="toggle-row hidden" id="thrustCentroidRow"><label for="resultThrustCentroid">Width centroid line</label><input id="resultThrustCentroid" type="checkbox" checked></div>
          <div class="toggle-row hidden" id="thrustHingesRow"><label for="resultHinges">Plastic hinges <span class="hinge-badge">●</span></label><input id="resultHinges" type="checkbox" checked></div>
          <label class="field hidden" id="thrustFilterField">Thrust blocks<select id="thrustFilter" aria-label="Filter thrust line by element group"><option value="all">All structural blocks</option></select></label>
          <label class="field hidden" id="thrustMinForceField">Minimum compression force [kN]
            <div class="thrust-range-row">
              <input id="resultThrustMinForce" type="range" min="0" max="1" step="any" value="0" aria-label="Minimum compression force for thrust line">
              <output id="resultThrustMinForceValue" for="resultThrustMinForce">0 / 0 kN</output>
            </div>
          </label>
          <div class="result-materials-group" id="resultMaterialsGroup">
            <div class="entity-heading"><span id="resultMaterialsTitle">ASSIGNED MATERIALS</span><span id="resultMaterialsCount" class="count">0</span></div>
            <p class="muted result-materials-help">Toggle visibility of material elements.</p>
            <input id="resultMaterialSearch" class="search hidden" type="search" placeholder="Find material…" aria-label="Search materials">
            <div id="resultMaterialsList" class="entity-list"></div>
            <button id="resultResetMaterials" type="button" class="secondary hidden result-reset-materials-btn">↺ Show all materials</button>
          </div>
          </div>
          <dl class="properties result-properties">
            <div id="resultScourRow" class="hidden"><dt>Scour stage</dt><dd id="resultScour">—</dd></div>
            <div id="resultFormulationRow" class="hidden"><dt>Formulation</dt><dd id="resultFormulation">—</dd></div>
            <div id="resultPierRow" class="hidden"><dt>Pier 1 settlement / uplift</dt><dd id="resultPier">—</dd></div>
            <div><dt>Analysis outcome</dt><dd id="resultOutcome">—</dd></div>
            <div><dt>Saved step</dt><dd id="resultStepValue">—</dd></div>
            <div><dt>Load factor λ</dt><dd id="resultLambda">—</dd></div>
            <div><dt>Control displacement</dt><dd id="resultControl">—</dd></div>
            <div><dt>Maximum nodal |U|</dt><dd id="resultMaximum">—</dd></div>
          </dl>
          <p class="result-note">Displacements are in cm. The scale changes the drawing only; values above remain actual results.</p>
          <p class="result-note">Each Quad element deforms independently with its own C# vertex kinematics so joints can open or slide; nodal readouts use the C# shared-node averaging convention. Each static stage includes its accumulated initial deformation.</p>
          <div id="resultMiniChart"></div>
        </section>
        <div class="result-source"><span class="eyebrow">RESULT SOURCE</span><p id="resultSource">wall_model</p></div>
      </aside>
      <section class="results-viewport has-force-preview" aria-label="Interactive deformed shape">
        <div class="results-canvas"></div>
        <div class="viewport-top"><span class="viewport-label"><span class="status-dot"></span> DEFORMED SHAPE</span><span class="result-scale-badge" id="resultScaleBadge">10× deformation</span></div>
        <div class="view-toolbar" aria-label="Results camera controls"><button data-result-view="iso" class="active">3D</button><button data-result-view="front">Front</button><button data-result-view="top">Top</button><button data-result-view="side">Side</button><span></span><button data-result-projection="perspective" class="active" title="Perspective camera">Persp</button><button data-result-projection="ortho" title="Orthographic camera">Ortho</button><span></span><button id="resultFit">Fit ↗</button><span></span><button id="resultExport" title="Export the current 3D view as a high-resolution PNG">Export PNG</button></div>
        <div class="disp-legend hidden" id="dispLegend">
          <span class="disp-legend-title" id="dispLegendTitle">|U| [mm]</span>
          <span class="disp-legend-min" id="dispLegendMin">0.00 mm</span>
          <i class="disp-gradient"></i>
          <span class="disp-legend-mid" id="dispLegendMid">0.00 mm</span>
          <span class="disp-legend-max" id="dispLegendMax">0.00 mm</span>
        </div>
        <div class="message" id="resultMessage" role="status">Reading saved displacement history…</div>
        <div class="result-legend"><span><i></i>Deformed</span><span><i></i>Undeformed</span><span id="thrustLegend" class="hidden"><i class="thrust-icon"></i>Line of thrust</span><span id="hingeLegend" class="hidden"><b class="hinge-icon">●</b>Hinges (<span id="hingeCount">0</span>)</span><span id="resultStageLabel"></span></div>
        <div class="result-timeline">
          <div class="result-transport"><button id="resultPlay" disabled aria-label="Play deformation">▶ Play</button><button id="resultPrevious" disabled aria-label="Previous result step">‹</button><button id="resultNext" disabled aria-label="Next result step">›</button><label>Playback<select id="resultSpeed" aria-label="Playback speed"><option value="500">2 steps/s</option><option value="200" selected>5 steps/s</option><option value="100">10 steps/s</option></select></label><output id="resultStepLabel">—</output></div>
          <input id="resultStep" type="range" min="0" max="0" step="1" value="0" disabled aria-label="Analysis step">
          <div class="result-timeline-labels"><span>Initial state</span><span id="resultFinalLabel">Final saved step</span></div>
        </div>
      </section><section class="result-document hidden" id="resultDocuments"><div id="responseCurves"></div><div id="interfaceResults" class="hidden"></div></section>
      <dialog id="resultExportDialog" class="export-dialog" aria-labelledby="exportTitle">
        <h2 id="exportTitle">Export view as PNG</h2>
        <p class="export-intro">High-resolution PNG for reports and LaTeX. A PDF would embed this same raster; PNG keeps the export direct and lossless.</p>
        <div class="export-grid">
          <label class="field">Resolution<select id="exportScale" aria-label="Export resolution"><option value="2">2×</option><option value="3">3×</option><option value="4" selected>4×</option></select></label>
          <label class="field">Background<select id="exportBackground" aria-label="Export background"><option value="white" selected>White</option><option value="screen">Screen dark</option><option value="transparent">Transparent</option></select></label>
        </div>
        <div class="toggle-row"><label for="exportCaption">Caption and legend</label><input id="exportCaption" type="checkbox" checked></div>
        <div class="toggle-row"><label for="exportCrop">Tight crop</label><input id="exportCrop" type="checkbox" checked></div>
        <div class="toggle-row"><label for="exportAxes">Axes and grid</label><input id="exportAxes" type="checkbox"></div>
        <p class="export-size" id="exportSize">—</p>
        <p class="export-status" id="exportStatus" role="status"></p>
        <div class="export-actions"><button id="exportDownload">Download PNG</button><button id="exportClose">Close</button></div>
      </dialog>`;
    this.$ = id => root.querySelector(`#${id}`);
    root.querySelector('.results-viewport').append(this.$('resultMiniChart'));
    this.curves = new ResponseCurves(this.$('responseCurves'), (index, analysisName, stageStep) => {
      this.navigateToStep(index, analysisName, stageStep);
    });
    this.interfaces = new InterfaceResults(this.$('interfaceResults'), (stepNumber, analysisName) => {
      this.navigateToStep(stepNumber, analysisName);
    });
    this.$('sidebarImportResult').onclick = () => document.getElementById('resultFileInput')?.click();
    for (const button of root.querySelectorAll('[data-result-section]')) button.onclick = () => this.showSection(button.dataset.resultSection);
    this.$('resultDataset').onchange = () => {
      if (this.$('resultDataset').value.startsWith('imported') && this.importedData) {
        this.data = this.importedData;
        this.selectAnalysis();
        return;
      }
      this.data = null;
      this.activate();
    };
    this.$('modalAnalysis').onchange = () => {
      if (this.$('modalMode')) this.$('modalMode').value = '';
      this.selectModal();
    };
    this.$('modalSort').onchange = () => {
      if (this.$('modalMode')) this.$('modalMode').value = '';
      this.selectModal();
    };
    this.$('modalMode').onchange = () => { this.pause(); this.modePhase = 1; this.draw(); };
    this.$('resultStep').oninput = () => { this.pause(); this.draw(); };
    this.$('resultColorBy').onchange = () => { this.colorRangeCustom = null; this.syncColorMode(); this.draw(); };
    this.$('resultPalette').onchange = () => this.draw();
    this.$('resultColorMin').onchange = () => this.applyColorRangeInputs();
    this.$('resultColorMax').onchange = () => this.applyColorRangeInputs();
    this.$('resultColorAuto').onclick = () => { this.colorRangeCustom = null; this.draw(); };
    this.$('resultScale').oninput = () => { this.autoScaled = false; this.draw(); };
    this.$('resultActual').onclick = () => { this.autoScaled = false; this.$('resultScale').value = '1'; this.draw(); };
    this.$('resultAuto').onclick = () => this.autoScale();
    this.$('resultAnalysis').onchange = () => { this.loadAnalysis(); };
    this.$('resultPrevious').onclick = () => this.move(-1);
    this.$('resultNext').onclick = () => this.move(1);
    this.$('resultPlay').onclick = () => this.timer ? this.pause() : this.play();
    this.$('resultSpeed').onchange = () => { if (this.timer) { this.pause(); this.play(); } };
    this.$('resultGhost').onchange = () => { if (this.ghost) { this.ghost.visible = this.$('resultGhost').checked; this.viewer.needsRender = true; } };
    bindViewSettings(this.$('resultSharedViewSettings'), 'result');
    viewSettings.subscribe((settings, changed) => {
      if (!this.viewer) return;
      applyViewerSettings(this.viewer, settings, { rebuild: false });
      if ('extrude' in changed && this.ghost && this.ghostGeometries) this.ghost.geometry = this.ghostGeometries[String(settings.extrude)];
      if ('extrude' in changed || 'colorBy' in changed) this.draw();
    });
    this.$('resultThrust').onchange = () => {
      const active = this.$('resultThrust').checked;
      this.$('thrustCentroidRow').classList.toggle('hidden', !active);
      this.$('thrustHingesRow').classList.toggle('hidden', !active);
      this.$('thrustFilterField').classList.toggle('hidden', !active || this.$('thrustFilter').options.length <= 1);
      this.$('thrustMinForceField').classList.toggle('hidden', !active);
      this.draw();
    };
    this.$('resultThrustCentroid').onchange = () => this.draw();
    this.$('resultHinges').onchange = () => this.draw();
    this.$('thrustFilter').onchange = () => this.draw();
    this.$('resultThrustMinForce').oninput = () => this.draw();
    this.$('resultResetMaterials').onclick = () => this.resetMaterials();
    this.$('resultMaterialSearch').oninput = () => this.renderMaterialsList();
    this.$('resultFit').onclick = () => this.viewer?.fit();
    this.$('resultExport').onclick = () => this.openExportDialog();
    this.$('exportScale').onchange = () => this.updateExportSize();
    this.$('exportBackground').onchange = () => this.updateExportSize();
    this.$('exportCrop').onchange = () => this.updateExportSize();
    this.$('exportDownload').onclick = () => this.downloadExport();
    this.$('exportClose').onclick = () => this.$('resultExportDialog').close();
    this.$('resultExportDialog').addEventListener('close', () => {
      this.$('exportStatus').textContent = '';
    });
    for (const button of root.querySelectorAll('[data-result-view]')) button.onclick = () => {
      this.viewer?.setView(button.dataset.resultView);
      for (const other of root.querySelectorAll('[data-result-view]')) other.classList.toggle('active', other === button);
    };
    for (const button of root.querySelectorAll('[data-result-projection]')) button.onclick = () => {
      this.viewer?.setProjection(button.dataset.resultProjection);
      for (const other of root.querySelectorAll('[data-result-projection]')) other.classList.toggle('active', other === button);
    };
    document.addEventListener('visibilitychange', () => { if (document.hidden) { this.pause(); this.interfaces.pause(); } });
  }

  async activate() {
    if (this.data) {
      this.viewer?.resize();
      if (this.needsViewportFit) {
        this.needsViewportFit = false;
        this.viewer?.setView('iso');
      }
      this.draw();
      this.summary();
      return;
    }
    if (this.loading) return;
    this.loading = true;
    this.deactivate();
    if (this.viewer) this.viewer.modelGroup.visible = false;
    if (this.ghost) this.ghost.visible = false;
    this.$('resultDiagnostics').classList.add('hidden');
    this.showSection('shape');
    for (const button of this.root.querySelectorAll('[data-result-section]')) button.disabled = true;
    this.$('resultMessage').classList.remove('hidden', 'error');
    this.$('resultMessage').textContent = 'Reading saved displacement history…';
    for (const id of ['resultDataset', 'resultAnalysis', 'resultStep', 'resultPlay', 'resultPrevious', 'resultNext', 'resultExport']) this.$(id).disabled = true;
    try {
      if (!this.catalog) {
        const response = await fetch('/api/results/catalog');
        const catalog = await response.json();
        if (!response.ok) throw new Error(catalog.error || 'Unable to read result sources.');
        this.catalog = catalog;
        this.$('resultDataset').replaceChildren(...(catalog.sources || []).map(source => new Option(source.label, source.id)));
        this.$('resultDataset').value = catalog.defaultSource || '';
        if (!catalog.sources?.length) {
          const message = this.$('resultMessage');
          message.textContent = 'No result source is preloaded. Use Import Results and select an HRX plus a .Results/.histra/.json file.';
          message.classList.remove('hidden');
          return;
        }
      }
      const sourceId = this.$('resultDataset').value;
      this.$('resultSource').textContent = this.catalog.sources.find(source => source.id === sourceId).label;
      const response = await fetch(`/api/results/${encodeURIComponent(sourceId)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to read saved results.');
      this.interfaces.destroy();
      this.interfaces = new InterfaceResults(this.$('interfaceResults'), index => { this.$('resultStep').value = index; this.draw(); });
      if (this.viewer) {
        if (this.ghost) { this.viewer.scene.remove(this.ghost); this.ghost.material.dispose(); }
        if (this.thrustLineMesh) { this.viewer.scene.remove(this.thrustLineMesh); this.thrustLineMesh.geometry.dispose(); this.thrustLineMesh.material.dispose(); this.thrustLineMesh = null; }
        if (this.hingeMesh) { this.viewer.scene.remove(this.hingeMesh); this.hingeMesh.geometry.dispose(); this.hingeMesh.material.dispose(); this.hingeMesh = null; }
        Object.values(this.ghostGeometries || {}).forEach(geometry => geometry.dispose());
      } else {
        this.viewer = new QuadViewer(this.root.querySelector('.results-canvas'), { extrude: true, opacity: 1, colorBy: 'single' });
        const activeProj = this.root.querySelector('[data-result-projection].active')?.dataset.resultProjection;
        if (activeProj) this.viewer.setProjection(activeProj);
      }
      this.data = data;
      this.slotMap = null;
      if (this.$('thrustFilter')) {
        this.$('thrustFilter').replaceChildren(new Option('All blocks', 'all'));
        if (data.mesh.thrustPairs?.length) {
          const matsInPairs = new Set(data.mesh.thrustPairs.map(p => String(p[3])));
          const hasBackfill = data.mesh.materials.some(m => matsInPairs.has(String(m.key)) && /backfill|soil/i.test(m.name));
          if (hasBackfill) {
            this.$('thrustFilter').add(new Option('Arches, piers & foundations', 'structural'));
          }
          for (const mat of data.mesh.materials) {
            if (matsInPairs.has(String(mat.key))) {
              this.$('thrustFilter').add(new Option(mat.name, mat.key));
            }
          }
          if (hasBackfill) this.$('thrustFilter').value = 'structural';
        }
        this.$('thrustFilterField').classList.toggle('hidden', !this.$('resultThrust').checked || this.$('thrustFilter').options.length <= 1);
        this.$('thrustMinForceField').classList.toggle('hidden', !this.$('resultThrust').checked);
      }
      applyViewerSettings(this.viewer, viewSettings.get(), { rebuild: false });
      this.viewer.modelGroup.visible = true;
      this.hiddenMaterials.clear();
      this.viewer.visibleQuad = q => !this.hiddenMaterials.has(String(q.material));
      this.viewer.loadPreview(data.mesh, { name: data.name, modelPoints: data.modelPoints || data.mesh?.modelPoints });
      this.baseNormals = this.viewer.state.quads.map(q => ({ normal: q.normal.clone(), normals: q.normals?.map(n => n.clone()) }));
      this.baseNodes = new Map([...this.viewer.state.nodes].map(([key, p]) => [key, p.clone()]));
      this.baseQuadPoints = this.viewer.state.quads.map(q => q.nodeKeys.map(k => {
        const p = this.baseNodes.get(k);
        return [p.x, p.y, p.z];
      }));
      this.buildGhostGeometries();
      this.ghost = new THREE.LineSegments(this.ghostGeometries.true, new THREE.LineBasicMaterial({ color: 0xffca7d, transparent: true, opacity: 0.55, depthWrite: false }));
      this.viewer.scene.add(this.ghost);
      this.ghost.visible = this.$('resultGhost').checked;
      applyViewerSettings(this.viewer, viewSettings.get());
      this.ghost.geometry = this.ghostGeometries[String(this.$('resultExtrude').checked)];
      this.renderMaterialsList();
      this.analysisCache.clear();
      for (const a of (data.analyses || [])) this.analysisCache.set(a.name, a);
      this.activeChainAnalyses = null;
      this.chainedAnalysis = null;
      this.$('resultAnalysis').replaceChildren(); this.$('modalAnalysis').replaceChildren(); this.$('modalMode').replaceChildren();
      const analysisOptions = data.analysisCatalog?.length
        ? data.analysisCatalog
        : data.analyses.map(analysis => ({ name: analysis.name, label: analysis.name }));
      for (const analysis of analysisOptions) this.$('resultAnalysis').add(new Option(analysis.label || analysis.name, analysis.name));
      if (analysisOptions.length > 1) this.$('resultAnalysis').add(new Option('⭐ Whole history (all stages)', '__all__'));
      const analysisNames = analysisOptions.map(analysis => analysis.name);
      this.$('resultAnalysis').value = data.defaultAnalysis
        || (analysisNames.includes('LiveLoad_0') ? 'LiveLoad_0' : analysisNames.includes('LiveLoad_1') ? 'LiveLoad_1' : analysisNames.at(-1));
      for (const id of ['resultAnalysis', 'resultStep', 'resultPlay', 'resultPrevious', 'resultNext', 'resultExport']) this.$(id).disabled = false;
      this.$('resultSource').textContent = data.name;
      for (const analysis of data.modal) this.$('modalAnalysis').add(new Option(analysis.name, analysis.name));
      for (const button of this.root.querySelectorAll('[data-result-section]')) button.disabled = false;
      const modalButton = this.root.querySelector('[data-result-section=modes]');
      modalButton.disabled = !data.modal.length;
      modalButton.title = data.modal.length ? 'View saved modal results' : 'This source contains no saved modal results';
      this.selectModal();
      this.$('resultMessage').classList.add('hidden');
      this.selectAnalysis();
      this.viewer.setView('iso');
    } catch (error) {
      this.data = null;
      const message = this.$('resultMessage');
      message.textContent = error.message;
      const retry = document.createElement('button');
      retry.textContent = 'Retry';
      retry.onclick = () => { message.textContent = 'Reading saved displacement history…'; message.classList.remove('error'); this.activate(); };
      message.append(document.createElement('br'), retry);
      message.classList.add('error');
    } finally { this.loading = false; this.$('resultDataset').disabled = !this.catalog?.sources?.length; }
  }

  loadDirectResults(data, label = 'Imported results') {
    this.deactivate();
    this.importedData = data;
    this.data = data;
    this.nodeKeyToIndex = null;
    this.slotMap = null;
    this.stepFields = null;
    this.stepFieldCache.clear();
    this.prefetchAttempted.clear();
    this.modalShapeCache.clear();
    this.autoScaled = true;
    this.needsViewportFit = this.root.classList.contains('hidden');
    this.$('resultDiagnostics').classList.add('hidden');
    this.$('resultMessage').classList.add('hidden');

    this.interfaces.destroy();
    this.interfaces = new InterfaceResults(this.$('interfaceResults'), (stepNumber, analysisName) => {
      this.navigateToStep(stepNumber, analysisName);
    });

    if (this.$('thrustFilter') && data.mesh) {
      this.$('thrustFilter').replaceChildren(new Option('All blocks', 'all'));
      if (data.mesh.thrustPairs?.length) {
        const matsInPairs = new Set(data.mesh.thrustPairs.map(p => String(p[3])));
        const hasBackfill = (data.mesh.materials || []).some(m => matsInPairs.has(String(m.key)) && /backfill|soil/i.test(m.name));
        if (hasBackfill) {
          this.$('thrustFilter').add(new Option('Arches, piers & foundations', 'structural'));
        }
        for (const mat of data.mesh.materials || []) {
          if (matsInPairs.has(String(mat.key))) {
            this.$('thrustFilter').add(new Option(mat.name, mat.key));
          }
        }
        if (hasBackfill) this.$('thrustFilter').value = 'structural';
      }
      this.$('thrustFilterField')?.classList.toggle('hidden', !this.$('resultThrust')?.checked || this.$('thrustFilter').options.length <= 1);
      this.$('thrustMinForceField')?.classList.toggle('hidden', !this.$('resultThrust')?.checked);
    }

    for (const button of this.root.querySelectorAll('[data-result-section]')) button.disabled = false;
    const modalButton = this.root.querySelector('[data-result-section=modes]');
    if (modalButton) {
      modalButton.disabled = !data.modal?.length;
      modalButton.title = data.modal?.length ? 'View saved modal results' : 'This source contains no saved modal results';
    }

    this.analysisCache.clear();
    for (const a of (data.analyses || [])) this.analysisCache.set(a.name, a);
    this.activeChainAnalyses = null;
    this.chainedAnalysis = null;

    this.$('resultAnalysis').replaceChildren();
    const analysisOptions = data.analysisCatalog?.length ? data.analysisCatalog : (data.analyses || []);
    for (const analysis of analysisOptions) {
      this.$('resultAnalysis').add(new Option(analysis.label || analysis.name, analysis.name));
    }
    if (analysisOptions.length > 1) {
      this.$('resultAnalysis').add(new Option('⭐ Whole history (all stages)', '__all__'));
    }
    this.$('resultAnalysis').value = data.defaultAnalysis
      || data.analyses?.[0]?.name
      || analysisOptions[0]?.name
      || '';
    for (const id of ['resultAnalysis', 'resultStep', 'resultPlay', 'resultPrevious', 'resultNext', 'resultExport']) this.$(id).disabled = false;
    this.$('resultSource').textContent = label;

    const sourceId = data.sourceId || 'imported';
    if (this.catalog?.sources && !this.catalog.sources.some(s => s.id === sourceId)) {
      this.catalog.sources.unshift({ id: sourceId, label });
    }
    let option = Array.from(this.$('resultDataset').options).find(o => o.value === sourceId);
    if (!option) {
      option = new Option(`📁 ${label}`, sourceId);
      this.$('resultDataset').add(option, 0);
    } else {
      option.textContent = `📁 ${label}`;
    }
    this.$('resultDataset').value = sourceId;
    this.$('resultDataset').disabled = false;

    this.$('modalAnalysis').replaceChildren();
    this.$('modalMode').replaceChildren();
    for (const analysis of data.modal || []) this.$('modalAnalysis').add(new Option(analysis.name, analysis.name));
    const defaultModal = (data.modal || []).find(m => m.name === data.defaultAnalysis)?.name || data.modal?.[0]?.name || '';
    this.$('modalAnalysis').value = defaultModal;
    this.selectModal();

    if (data.mesh && data.mesh.nodes?.length) {
      if (!this.viewer) {
        this.viewer = new QuadViewer(this.root.querySelector('.results-canvas'), { extrude: true, opacity: 1, colorBy: 'single' });
        const activeProj = this.root.querySelector('[data-result-projection].active')?.dataset.resultProjection;
        if (activeProj) this.viewer.setProjection(activeProj);
      }
      if (this.ghost) { this.viewer.scene.remove(this.ghost); this.ghost.material.dispose(); }
      if (this.thrustLineMesh) { this.viewer.scene.remove(this.thrustLineMesh); this.thrustLineMesh.geometry.dispose(); this.thrustLineMesh.material.dispose(); this.thrustLineMesh = null; }
      if (this.hingeMesh) { this.viewer.scene.remove(this.hingeMesh); this.hingeMesh.geometry.dispose(); this.hingeMesh.material.dispose(); this.hingeMesh = null; }
      Object.values(this.ghostGeometries || {}).forEach(geometry => geometry.dispose());

      applyViewerSettings(this.viewer, viewSettings.get(), { rebuild: false });
      this.viewer.modelGroup.visible = true;
      this.hiddenMaterials.clear();
      this.viewer.visibleQuad = q => !this.hiddenMaterials.has(String(q.material));
      this.viewer.loadPreview(data.mesh, { name: data.name || label, modelPoints: data.modelPoints || data.mesh?.modelPoints });
      this.baseNormals = this.viewer.state.quads.map(q => ({ normal: q.normal.clone(), normals: q.normals?.map(n => n.clone()) }));
      this.baseNodes = new Map([...this.viewer.state.nodes].map(([key, p]) => [key, p.clone()]));
      this.baseQuadPoints = this.viewer.state.quads.map(q => q.nodeKeys.map(k => {
        const p = this.baseNodes.get(k);
        return p ? [p.x, p.y, p.z] : [0, 0, 0];
      }));
      this.buildGhostGeometries();
      this.ghost = new THREE.LineSegments(this.ghostGeometries.true, new THREE.LineBasicMaterial({ color: 0xffca7d, transparent: true, opacity: 0.55, depthWrite: false }));
      this.viewer.scene.add(this.ghost);
      this.ghost.visible = this.$('resultGhost').checked;
      applyViewerSettings(this.viewer, viewSettings.get());
      this.ghost.geometry = this.ghostGeometries[String(this.$('resultExtrude').checked)];
      this.renderMaterialsList();
      if (!this.needsViewportFit) {
        this.viewer.resize();
        this.viewer.setView('iso');
      }
    }

    if (data.analyses?.length) {
      this.selectAnalysis();
    }
    const isModalTarget = Boolean(
      data.modal?.length
      && data.modal.some(m => m.name === this.$('resultAnalysis').value)
      && (!this.analysis?.steps || this.analysis.steps.length <= 1)
    );
    this.showSection(isModalTarget ? 'modes' : (this.section === 'modes' && !data.modal?.length ? 'shape' : (this.section || 'shape')));
    this.summary();
  }

  deactivate() { this.pause(); this.interfaces.pause(); }
  get analysis() {
    if (this.$('resultAnalysis')?.value === '__all__' && this.chainedAnalysis) {
      return this.chainedAnalysis;
    }
    const current = this.$('resultAnalysis')?.value;
    return this.data?.analyses?.find(a => a.name === current)
      || this.analysisCache?.get(current)
      || this.data?.analyses?.[0];
  }
  get step() { return this.analysis?.steps[Number(this.$('resultStep').value)]; }
  get modal() { return this.data?.modal.find(m => m.name === this.$('modalAnalysis').value); }
  get mode() { return this.modal?.modes[Number(this.$('modalMode').value)]; }

  showSection(section) {
    if (section === 'modes' && !this.data?.modal.length) return;
    this.pause();
    this.interfaces.pause();
    if (this.section === 'modes' && section !== 'modes') this.$('resultScale').value = this.staticScale ?? 10;
    if (section === 'modes' && this.section !== 'modes') { this.staticScale = this.$('resultScale').value; this.$('resultScale').value = 15; this.modePhase = 1; }
    this.section = section;
    for (const button of this.root.querySelectorAll('[data-result-section]')) button.setAttribute('aria-pressed', String(button.dataset.resultSection === section));
    const drawing = section === 'shape' || section === 'modes';
    this.root.querySelector('.results-viewport').classList.toggle('hidden', !drawing);
    this.root.querySelector('.results-viewport').classList.toggle('has-force-preview', section === 'shape');
    this.$('resultDocuments').classList.toggle('hidden', drawing);
    this.$('responseCurves').classList.toggle('hidden', section !== 'curves');
    this.$('interfaceResults').classList.toggle('hidden', section !== 'interfaces');
    this.$('resultDocuments').classList.toggle('interface-workspace-open', section === 'interfaces');
    this.$('modeControls').classList.toggle('hidden', section !== 'modes');
    this.$('resultAnalysis').closest('label').classList.toggle('hidden', section === 'modes');
    this.$('resultDrawingControls').classList.toggle('hidden', !drawing);
    this.$('dispLegend')?.classList.toggle('hidden', !drawing || this.$('resultColorBy')?.value === 'none');
    this.$('resultActual').classList.toggle('hidden', section === 'modes');
    const isShape = section === 'shape';
    this.$('resultThrust')?.closest('.toggle-row')?.classList.toggle('hidden', !isShape);
    this.$('thrustCentroidRow')?.classList.toggle('hidden', !isShape || !this.$('resultThrust')?.checked);
    this.$('thrustHingesRow')?.classList.toggle('hidden', !isShape || !this.$('resultThrust')?.checked);
    this.$('thrustFilterField')?.classList.toggle('hidden', !isShape || !this.$('resultThrust')?.checked || this.$('thrustFilter')?.options.length <= 1);
    this.$('thrustMinForceField')?.classList.toggle('hidden', !isShape || !this.$('resultThrust')?.checked);
    this.$('resultScale').closest('label').firstChild.textContent = section === 'modes' ? 'Mode amplitude [cm]' : 'Deformation scale';
    this.root.querySelector('.viewport-label').lastChild.textContent = section === 'modes' ? ' MODAL SHAPE' : ' DEFORMED SHAPE';
    this.root.querySelector('.result-properties').classList.toggle('hidden', section === 'modes');
    this.$('resultMiniChart').classList.toggle('hidden', section !== 'shape');
    if (section === 'interfaces' && this.analysis && this.interfaces.stressView.field.value !== 'normalForce') this.$('resultStep').value = this.analysis.steps.length - 1;
    this.$('resultStep').classList.toggle('hidden', section === 'modes');
    this.$('resultSpeed').closest('label').classList.toggle('hidden', section === 'modes');
    this.root.querySelector('.result-legend span').lastChild.textContent = section === 'modes' ? 'Mode shape' : 'Deformed';
    this.$('resultPrevious').disabled = this.$('resultNext').disabled = section === 'modes';
    this.root.querySelector('.result-timeline-labels').classList.toggle('hidden', section === 'modes');
    this.root.querySelector('.results-controls h1').textContent = { shape: 'Deformed shape', modes: 'Modal shapes', curves: 'Response curves', interfaces: 'Interface contours' }[section] || 'Analysis results';
    this.root.querySelector('.results-description').textContent = { shape: 'Explore movement through each analysis stage.', modes: 'Inspect the saved eigenmodes before and after scour.', curves: 'Inspect forces, reactions and energies at saved steps.', interfaces: 'Click an interface in 3D to inspect its stress contour. Use All interfaces to see the field across the model.' }[section] || '';
    this.syncColorMode();
    if (this.data) { this.draw(); this.viewer.resize(); }
  }

  async loadModalShapes() {
    if (!this.modal?.lazy || !this.data?.sourceId) return;
    const modal = this.modal;
    const cached = this.modalShapeCache.get(modal.name);
    if (cached) {
      modal.modes = cached;
      modal.lazy = false;
      this.selectModal();
      return;
    }
    if (this.pendingModalShape) return;
    this.pendingModalShape = modal.name;
    const message = this.$('resultMessage');
    message.textContent = 'Reading modal shapes…';
    message.classList.remove('hidden', 'error');
    try {
      const response = await fetch(
        `/api/results/${encodeURIComponent(this.data.sourceId)}/modal?analysis=${encodeURIComponent(modal.name)}`
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Unable to read modal shapes.');
      if (!payload.modes?.length) throw new Error('The modal attachment contains no mode shapes.');
      this.modalShapeCache.set(modal.name, payload.modes);
      if (this.modal?.name === modal.name) {
        modal.modes = payload.modes;
        modal.lazy = false;
        message.classList.add('hidden');
        this.selectModal();
      }
    } catch (error) {
      message.textContent = error.message;
      message.classList.add('error');
    } finally {
      this.pendingModalShape = null;
    }
  }

  selectModal() {
    if (!this.modal) return;
    const previous = this.$('modalMode').value;
    const order = this.$('modalSort')?.value || 'massY';
    const sorted = this.modal.modes.map((mode, index) => ({ mode, index }));
    sorted.sort((left, right) => {
      if (order === 'frequency') return (left.mode.frequency - right.mode.frequency) || (left.mode.number - right.mode.number);
      const component = order === 'massX' ? 0 : order === 'massZ' ? 2 : 1;
      return (right.mode.massPercent?.[component] || 0) - (left.mode.massPercent?.[component] || 0)
        || (left.mode.number - right.mode.number);
    });
    this.$('modalMode').replaceChildren(...sorted.map(({ mode, index }) => {
      const yMass = Number(mode.massPercent?.[1] || 0);
      return new Option(`Mode ${mode.number} · ${number(mode.frequency)} Hz · Y mass ${number(yMass)}%`, index);
    }));
    const options = [...this.$('modalMode').options];
    this.$('modalMode').value = options.some(option => option.value === previous) ? previous : options[0]?.value || '0';
    this.modePhase = 1;
    if (this.section === 'modes') {
      if (this.modal.lazy) this.loadModalShapes();
      else { this.pause(); this.draw(); }
    }
  }

  resolveAnalysisChain(targetName) {
    const catalog = this.data?.analysisCatalog || [];
    if (!catalog.length) return targetName && targetName !== '__all__' ? [targetName] : [];
    if (!targetName || targetName === '__all__') {
      return catalog.filter(item => !String(item.name || '').toLowerCase().startsWith('modal')).map(item => item.name);
    }
    const byKey = new Map();
    const byName = new Map();
    for (const item of catalog) {
      if (item.key != null) byKey.set(String(item.key), item);
      byName.set(item.name, item);
    }
    const targetItem = byName.get(targetName);
    if (!targetItem) return [targetName];
    const chain = [];
    const seen = new Set();
    let current = targetItem;
    while (current) {
      const k = String(current.key ?? current.name);
      if (seen.has(k)) break;
      seen.add(k);
      chain.push(current.name);
      const initKey = String(current.initialAnalysisKey ?? '-100');
      if (!initKey || Number(initKey) < 0) break;
      current = byKey.get(initKey) || null;
    }
    return chain.reverse();
  }

  async loadAnalysisData(name) {
    if (!name || name === '__all__') return null;
    if (this.analysisCache.has(name)) return this.analysisCache.get(name);
    const found = this.data?.analyses?.find(a => a.name === name);
    if (found) {
      this.analysisCache.set(name, found);
      return found;
    }
    const sourceId = this.$('resultDataset')?.value || this.data?.sourceId;
    if (!sourceId) return null;
    const response = await fetch(`/api/results/${encodeURIComponent(sourceId)}?analysis=${encodeURIComponent(name)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Unable to read analysis ${name}.`);
    const analysis = data.analyses?.[0];
    if (analysis) {
      this.analysisCache.set(analysis.name, analysis);
    }
    return analysis;
  }

  async getAnalysisChain(targetName) {
    const names = this.resolveAnalysisChain(targetName);
    if (!names.length) return [];
    const analyses = await Promise.all(names.map(name => this.loadAnalysisData(name)));
    return analyses.filter(Boolean);
  }

  buildChainedAnalysis(analyses) {
    if (!analyses?.length) return null;
    if (analyses.length === 1) return analyses[0];
    const latest = analyses.at(-1);
    const first = analyses[0];
    const chainStages = [];
    const allSteps = [];
    let cumulativeStep = 0;
    for (let si = 0; si < analyses.length; si++) {
      const a = analyses[si];
      const startIdx = cumulativeStep;
      for (let i = 0; i < a.steps.length; i++) {
        const s = a.steps[i];
        allSteps.push({
          ...s,
          analysisName: a.name,
          stageLabel: a.name,
          stageStep: s.step,
          stageIndex: si,
          cumulativeStep: cumulativeStep++,
          isStageStart: i === 0,
        });
      }
      chainStages.push({
        name: a.name,
        key: a.key,
        stepCount: a.steps.length,
        startIndex: startIdx,
        endIndex: cumulativeStep - 1,
      });
    }

    let mergedModelPoints = null;
    const mpPoints = latest.modelPoints?.points || first.modelPoints?.points;
    if (mpPoints?.length) {
      const mergedPoints = mpPoints.map(p => {
        const ux = [], uy = [], uz = [];
        let anyAvail = false;
        for (const a of analyses) {
          const matchPoint = a.modelPoints?.points?.find(mp => String(mp.key) === String(p.key));
          if (matchPoint?.available && matchPoint.displacement_cm) {
            anyAvail = true;
            ux.push(...(matchPoint.displacement_cm.ux || []));
            uy.push(...(matchPoint.displacement_cm.uy || []));
            uz.push(...(matchPoint.displacement_cm.uz || []));
          } else {
            const zeroes = new Array(a.steps.length).fill(0);
            ux.push(...zeroes);
            uy.push(...zeroes);
            uz.push(...zeroes);
          }
        }
        return {
          ...p,
          available: anyAvail,
          displacement_cm: { ux, uy, uz },
        };
      });
      mergedModelPoints = {
        step: allSteps.map(s => s.cumulativeStep),
        points: mergedPoints,
      };
    }

    return {
      name: `Whole history (${analyses.map(a => a.name).join(' → ')})`,
      shortName: 'Whole history',
      isChain: true,
      chainStages,
      steps: allSteps,
      interfaces: latest.interfaces,
      interfaceOrder: latest.interfaceOrder,
      modelPoints: mergedModelPoints,
      finalStress: latest.finalStress,
      stressFields: latest.stressFields,
      outcome: `Whole history · ${analyses.length} stages · ${allSteps.length} saved steps`,
      diagnostics: latest.diagnostics,
      curveOnly: false,
    };
  }

  async navigateToStep(indexOrStep, analysisName, stageStep) {
    this.pause();
    if (this.$('resultAnalysis').value === '__all__') {
      const idx = typeof indexOrStep === 'number' ? indexOrStep : Number(indexOrStep);
      this.$('resultStep').value = Math.min(Math.max(0, idx), this.analysis.steps.length - 1);
      this.draw();
      return;
    }
    if (analysisName && analysisName !== this.analysis?.name) {
      this.$('resultAnalysis').value = analysisName;
      await this.loadAnalysis();
      const stepIdx = this.analysis?.steps?.findIndex(s => s.step === (stageStep ?? indexOrStep));
      this.$('resultStep').value = stepIdx >= 0 ? stepIdx : Math.min(Number(indexOrStep), this.analysis.steps.length - 1);
      this.draw();
      return;
    }
    const stepIdx = typeof indexOrStep === 'number' && indexOrStep < this.analysis?.steps?.length
      ? indexOrStep
      : this.analysis?.steps?.findIndex(s => s.step === (stageStep ?? indexOrStep));
    this.$('resultStep').value = stepIdx >= 0 ? stepIdx : 0;
    this.draw();
  }

  async loadAnalysis() {
    const name = this.$('resultAnalysis').value;
    if (!name || this.analysisLoading) return;
    const select = this.$('resultAnalysis');
    select.disabled = true;
    if (this.$('resultExport')) this.$('resultExport').disabled = true;
    this.analysisLoading = true;
    const message = this.$('resultMessage');
    const previous = this.data?.analyses?.[0]?.name;
    try {
      if (name === '__all__') {
        message.textContent = 'Reading whole history across all stages…';
        message.classList.remove('hidden', 'error');
        const chain = await this.getAnalysisChain('__all__');
        this.activeChainAnalyses = chain;
        this.chainedAnalysis = this.buildChainedAnalysis(chain);
        message.classList.add('hidden');
        await this.selectAnalysis();
        return;
      }
      this.chainedAnalysis = null;
      if (this.analysisCache.has(name)) {
        const cached = this.analysisCache.get(name);
        this.data.analyses = [cached];
        message.classList.add('hidden');
        await this.selectAnalysis();
        return;
      }
      message.textContent = 'Reading saved displacement history…';
      message.classList.remove('hidden', 'error');
      const sourceId = this.$('resultDataset').value;
      const response = await fetch(`/api/results/${encodeURIComponent(sourceId)}?analysis=${encodeURIComponent(name)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to read saved results.');
      this.data.analyses = data.analyses;
      if (data.analyses?.[0]) {
        this.analysisCache.set(data.analyses[0].name, data.analyses[0]);
      }
      this.data.modal = data.modal;
      this.data.analysisCatalog = data.analysisCatalog || this.data.analysisCatalog;
      this.data.defaultAnalysis = data.defaultAnalysis;
      this.data.scourStage = data.scourStage;
      this.data.formulation = data.formulation;
      this.data.sourceSchema = data.sourceSchema;
      this.data.modelSha256 = data.modelSha256;
      this.data.units = data.units;
      this.data.sourceUnits = data.sourceUnits;
      this.data.title = data.title;
      this.data.name = data.name;
      this.$('resultSource').textContent = data.name;
      message.classList.add('hidden');
      await this.selectAnalysis();
    } catch (error) {
      if (previous) select.value = previous;
      message.textContent = error.message || String(error);
      message.classList.add('error');
    } finally {
      this.analysisLoading = false;
      select.disabled = false;
      if (this.$('resultExport')) this.$('resultExport').disabled = false;
    }
  }

  applyColorRangeInputs() {
    const min = this.$('resultColorMin').valueAsNumber;
    const max = this.$('resultColorMax').valueAsNumber;
    this.colorRangeCustom = Number.isFinite(min) && Number.isFinite(max) && max > min
      ? { min, max }
      : null;
    this.draw();
  }

  colorRangeFor(dataMin, dataMax) {
    const custom = this.colorRangeCustom;
    if (custom && Number.isFinite(custom.min) && Number.isFinite(custom.max) && custom.max > custom.min) {
      return { min: custom.min, max: custom.max, auto: false };
    }
    return { min: dataMin, max: dataMax, auto: true };
  }

  setColorRangeInputs(dataMin, dataMax, usedMin, usedMax) {
    const minInput = this.$('resultColorMin');
    const maxInput = this.$('resultColorMax');
    const format = value => Number.isFinite(value) ? String(Number(value.toPrecision(7))) : '';
    if (document.activeElement !== minInput) minInput.value = format(usedMin ?? dataMin);
    if (document.activeElement !== maxInput) maxInput.value = format(usedMax ?? dataMax);
  }

  stepFieldKey() {
    const record = this.step;
    const aName = record?.analysisName || this.analysis?.name || '';
    return record ? `${aName}|${record.stageStep ?? record.step}` : null;
  }

  async loadStepFields({ quiet = false } = {}) {
    if (!(this.data?.nativeCsharp || this.data?.lazyFields) || !this.analysis || !this.step) return;
    const key = this.stepFieldKey();
    if (!key || this.stepFieldCache.has(key) || this.pendingStepField) return;
    this.pendingStepField = key;
    const aName = this.step?.analysisName || this.analysis?.name;
    const stepNum = this.step?.stageStep ?? this.step?.step;
    const message = this.$('resultMessage');
    if (!quiet) {
      message.textContent = `Reading step ${stepNum} stress fields…`;
      message.classList.remove('hidden', 'error');
    }
    try {
      const response = await fetch(
        `/api/results/${encodeURIComponent(this.data.sourceId)}/fields?analysis=${encodeURIComponent(aName)}` +
        `&step=${encodeURIComponent(stepNum)}`
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Unable to read step stress fields.');
      this.stepFieldCache.set(key, payload);
      if (this.stepFieldCache.size > 16) {
        this.stepFieldCache.delete(this.stepFieldCache.keys().next().value);
      }
      if (this.stepFieldKey() === key) {
        this.stepFields = payload;
        message.classList.add('hidden');
        this.draw();
      }
    } catch (error) {
      if (quiet) {
        this.prefetchAttempted.add(key);
        if (this.stepFieldKey() === key && !message.classList.contains('hidden')) {
          message.textContent = error.message;
          message.classList.add('error');
        }
      } else {
        message.textContent = error.message;
        message.classList.add('error');
      }
    } finally {
      this.pendingStepField = null;
      this.scheduleFieldPrefetch();
    }
  }

  scheduleFieldPrefetch() {
    if (!this.data?.lazyFields || !this.analysis) return;
    clearTimeout(this.prefetchTimer);
    this.prefetchTimer = setTimeout(() => {
      if (!this.data?.lazyFields || !this.analysis) return;
      const key = this.stepFieldKey();
      if (!key || this.stepFieldCache.has(key) || this.pendingStepField || this.prefetchAttempted.has(key)) return;
      this.loadStepFields({ quiet: true });
    }, 0);
  }

  fieldHasValues(field) {
    return Boolean(field?.quadCornerValues || field?.quadFaceValues || field?.quadFaceGrids);
  }

  fieldById(id) {
    const stepFields = this.stepFields
      && this.stepFields.analysis === this.analysis?.name
      && this.stepFields.step === this.step?.step
      ? this.stepFields.stressFields : null;
    const field = (stepFields || this.analysis?.stressFields || []).find(item => item.id === id);
    if (field) return field;
    if (id === 'vonMises' && this.analysis?.finalStress) {
      return {
        id: 'vonMises',
        label: 'Von Mises stress',
        unit: 'MPa',
        kind: 'stress',
        step: this.analysis.finalStress.step,
        available: true,
        ...this.analysis.finalStress,
      };
    }
    return null;
  }

  buildColorOptions() {
    const select = this.$('resultColorBy');
    if (!select) return;
    const current = select.value;
    for (const option of [...select.querySelectorAll('option[data-result-field]')]) option.remove();
    const fields = this.analysis?.stressFields || [];
    for (const field of fields) {
      const suffix = !field.available ? ' · unavailable' : field.partial ? ' · partial' : '';
      const option = new Option(`${field.label} [${field.unit}]${suffix}`, field.id);
      option.disabled = !field.available;
      option.title = field.reason || (field.available
        ? 'Final-step interface-spring field'
        : 'This result format does not contain the required saved spring data');
      option.dataset.resultField = field.id;
      select.add(option);
    }
    if (!fields.length && this.analysis?.finalStress) {
      const option = new Option('Von Mises stress [MPa]', 'vonMises');
      option.title = 'Final saved interface-spring snapshot';
      option.dataset.resultField = 'vonMises';
      select.add(option);
    }
    if (!fields.length && !this.analysis?.finalStress) {
      select.value = 'magnitude';
      return;
    }
    const currentOption = [...select.options].find(option => option.value === current && !option.disabled);
    if (!currentOption) {
      const vonMises = [...select.options].find(option => option.value === 'vonMises' && !option.disabled);
      select.value = vonMises ? 'vonMises' : 'magnitude';
    }
  }

  syncColorMode() {
    const select = this.$('resultColorBy');
    if (!select) return;
    const modes = this.section === 'modes';
    const field = this.fieldById(select.value);
    if (field && (!field.available || modes)) {
      select.value = 'magnitude';
    }
    const scalar = Boolean(this.fieldById(select.value)?.available) && !modes;
    const perStep = Boolean(this.data?.nativeCsharp);
    if (this.analysis) {
      this.$('resultStep').disabled = scalar && !perStep;
      this.$('resultPlay').disabled = scalar && !perStep;
      this.$('resultPrevious').disabled = (scalar && !perStep) || modes;
      this.$('resultNext').disabled = (scalar && !perStep) || modes;
      if (scalar && !perStep) this.$('resultStep').value = this.analysis.steps.length - 1;
    }
  }

  async selectAnalysis() {
    this.pause();
    clearTimeout(this.prefetchTimer);
    this.colorRangeCustom = null;
    this.stepFields = null;
    this.stepFieldCache.clear();
    this.prefetchAttempted.clear();
    this.thrustSliderInitialized = false;
    this.thrustSliderWasEmpty = true;
    this.buildColorOptions();
    this.$('resultStep').max = this.analysis.steps.length - 1;
    this.$('resultStep').value = this.analysis.steps.length - 1;
    const target = this.analysis.lambdaTarget;
    this.$('resultOutcome').textContent = (this.analysis.outcome || '') + (target
      ? target.reached
        ? ` · λ target ${target.target} crossed at step ${target.step} (λ = ${target.achieved})`
        : ` · λ target ${target.target} not reached`
      : '');
    if (this.data?.scourStage) {
      this.$('resultScourRow')?.classList.remove('hidden');
      this.$('resultScour').textContent = this.data.scourStage.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    } else {
      this.$('resultScourRow')?.classList.add('hidden');
    }
    if (this.data?.formulation) {
      this.$('resultFormulationRow')?.classList.remove('hidden');
      this.$('resultFormulation').textContent = this.data.formulation.replace(/_/g, '-');
    } else {
      this.$('resultFormulationRow')?.classList.add('hidden');
    }
    const diagnostics = this.analysis.diagnostics, note = this.$('resultDiagnostics');
    note.classList.toggle('hidden', !diagnostics?.equilibriumFailedSteps);
    note.textContent = diagnostics?.equilibriumFailedSteps ? `Saved diagnostics: equilibrium checks failed at ${diagnostics.equilibriumFailedSteps} of ${diagnostics.equilibriumCheckedSteps} checked steps. Results are displayed as exported.` : '';
    this.$('resultFinalLabel').textContent = `Step ${this.analysis.steps.at(-1).stageStep ?? this.analysis.steps.at(-1).step}`;
    this.syncColorMode();
    if (this.autoScaled) this.autoScale();
    else this.draw();
    this.scheduleFieldPrefetch();

    const currentName = this.$('resultAnalysis')?.value;
    if (currentName && currentName !== '__all__') {
      try {
        const chain = await this.getAnalysisChain(currentName);
        if (this.$('resultAnalysis')?.value === currentName && chain.length > 1) {
          this.activeChainAnalyses = chain;
          this.chainedAnalysis = this.buildChainedAnalysis(chain);
          if (this.section === 'curves') {
            this.curves.update(this.analysis, Number(this.$('resultStep').value), {
              chainAnalysis: this.chainedAnalysis,
              mesh: this.data.mesh,
            });
          }
          if (this.section === 'interfaces' && this.analysis.interfaces?.length) {
            this.interfaces.update(
              this.analysis,
              this.data.mesh,
              Number(this.$('resultStep').value),
              this.data.modelSha256,
              this.data.sourceId,
              { chainAnalyses: chain }
            );
          }
        }
      } catch (_) {}
    }
  }

  syncThrustMinForce(maxForce) {
    const slider = this.$('resultThrustMinForce');
    const output = this.$('resultThrustMinForceValue');
    if (!slider || !output) return false;
    const maximum = Math.max(0, Number(maxForce) || 0);
    const rangeMax = maximum > 0 ? maximum : 1;
    const previous = Number(slider.value) || 0;
    slider.max = String(rangeMax);
    let value = previous;
    if (!this.thrustSliderInitialized || this.thrustSliderWasEmpty) {
      value = maximum > 0 ? maximum * 0.1 : 0;
      this.thrustSliderInitialized = true;
    }
    this.thrustSliderWasEmpty = maximum <= 0;
    if (maximum <= 0) value = 0;
    value = Math.min(Math.max(0, value), rangeMax);
    slider.value = String(value);
    output.textContent = `${number(value)} / ${number(maximum)} kN`;
    return value !== previous;
  }

  draw() {
    if (!this.viewer || !this.step) return;
    const input = this.$('resultScale');
    const scale = input.valueAsNumber;
    if (!Number.isFinite(scale) || scale < 0 || scale > 1000000) { input.setCustomValidity('Use a scale between 0 and 1,000,000.'); return; }
    input.setCustomValidity('');
    const modal = this.section === 'modes';
    if (modal && this.modal?.lazy) {
      this.loadModalShapes();
      return;
    }
    const requestedColor = this.$('resultColorBy')?.value || 'magnitude';
    const nativeCsharp = Boolean(this.data?.nativeCsharp);
    const lazyFields = Boolean(this.data?.lazyFields);
    const requestedField = this.fieldById(requestedColor);
    const scalarRequested = !modal && Boolean(requestedField?.available);
    // Python and bridge snapshots contain spring fields only at the final step.
    // Select that step before looking up or requesting lazy fields: the server
    // returns the final snapshot even when asked for an earlier step.
    this.$('resultStep').value = resultFieldStepIndex(
      Number(this.$('resultStep').value), this.analysis.steps.length, scalarRequested, nativeCsharp
    );
    const atFinalStep = Number(this.$('resultStep').value) === this.analysis.steps.length - 1;
    const needsFieldValues = scalarRequested && (nativeCsharp || lazyFields)
      && (!atFinalStep || !this.fieldHasValues(requestedField));
    if (needsFieldValues) {
      const key = this.stepFieldKey();
      const cached = this.stepFieldCache.get(key);
      if (!cached) {
        this.stepFields = null;
        const message = this.$('resultMessage');
        message.textContent = `Reading step ${this.step.step} stress fields…`;
        message.classList.remove('hidden', 'error');
        this.loadStepFields();
        return;
      }
      this.stepFields = cached;
    } else if (!(nativeCsharp || lazyFields) || !scalarRequested) {
      this.stepFields = null;
    }
    const activeField = this.fieldById(requestedColor);
    const scalarMap = !modal && Boolean(activeField?.available);
    if ((this.section === 'shape' || modal) && this.data.mesh?.nodes?.length && (!modal || this.mode)) {
      const values = modal ? this.mode.displacements.map(v => v.map(u => u * (this.modePhase ?? 1))) : this.step.displacements;
      if (values && values.length === this.data.mesh.nodes.length) {
        const points = deformedPoints(this.data.mesh.nodes, values, scale);
        const bounds = new THREE.Box3();
        points.forEach((point, i) => {
          this.viewer.state.nodes.get(Number(this.data.mesh.nodes[i].key)).set(...point);
        });
        const record = modal ? this.mode : this.step;
        if (record.quadDisplacements) {
          record._decodedQuadDisp ??= decodeQuadDisplacements(record.quadDisplacements, this.viewer.state.quads.length);
          const quadPts = deformedQuadPoints(this.baseQuadPoints, record._decodedQuadDisp, scale, modal ? (this.modePhase ?? 1) : 1);
          this.viewer.state.quads.forEach((quad, i) => {
            if (!quad.points) quad.points = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
            for (let c = 0; c < 4; c++) {
              quad.points[c].set(...quadPts[i][c]);
            }
          });
        } else {
          this.viewer.state.quads.forEach(quad => { quad.points = null; });
        }
        this.viewer.state.quads.forEach((quad, i) => {
          const faceNormal = pts => pts[1].clone().sub(pts[0]).cross(pts[3].clone().sub(pts[0])).normalize();
          const basePts = this.baseQuadPoints[i].map(p => new THREE.Vector3(...p));
          const currPts = quad.points ?? quad.nodeKeys.map(k => this.viewer.state.nodes.get(k));
          const rotation = new THREE.Quaternion().setFromUnitVectors(faceNormal(basePts), faceNormal(currPts));
          quad.normal.copy(this.baseNormals[i].normal).applyQuaternion(rotation);
          quad.normals = this.baseNormals[i].normals?.map(n => n.clone().applyQuaternion(rotation));
        });
        const visibleQuads = this.viewer.state.quads.filter(quad => this.viewer.visibleQuad(quad));
        if (visibleQuads.length > 0) {
          const visibleNodeKeys = new Set(visibleQuads.flatMap(q => q.nodeKeys));
          this.data.mesh.nodes.forEach((node, i) => {
            if (visibleNodeKeys.has(Number(node.key))) {
              bounds.expandByPoint(new THREE.Vector3(...points[i]));
              bounds.expandByPoint(new THREE.Vector3(...node.point));
            }
          });
          visibleQuads.forEach(quad => {
            if (quad.points) {
              for (let c = 0; c < 4; c++) bounds.expandByPoint(quad.points[c]);
            }
          });
        }
        this.viewer.state.bounds.copy(bounds);
        this.viewer.updateModelPoints?.();
        const requestedMode = this.$('resultColorBy')?.value || 'magnitude';
        const colorMode = ['magnitude', 'x', 'y', 'z', 'none'].includes(requestedMode) ? requestedMode : 'magnitude';
        if (scalarMap) {
          const field = activeField;
          const palette = paletteSpec(this.$('resultPalette')?.value, field);
          const range = this.colorRangeFor(field.min, field.max);
          const res = computeScalarContours({
            quads: this.viewer.state.quads,
            values: field.quadCornerValues.flat(),
            min: range.min,
            max: range.max,
            faceValues: field.quadFaceValues ? field.quadFaceValues.flat(3) : null,
            faceGrids: field.quadFaceGrids || null,
            colormap: palette.colormap,
            makeColor: (r, g, b) => new THREE.Color(r, g, b)
          });
          this.viewer.state.quads.forEach((quad, i) => {
            quad.colors = res.quadColors[i];
            quad.faceColors = res.quadFaceColors?.[i] ?? null;
            quad.faceGrids = res.quadFaceGrids?.[i] ?? null;
          });
          this.setColorRangeInputs(field.min, field.max, res.min, res.max);
          const dispLeg = this.$('dispLegend');
          if (dispLeg) {
            dispLeg.classList.remove('hidden');
            const unit = field.unit === '–' ? '' : (field.unit || '');
            const unitSuffix = unit ? ` ${unit}` : '';
            this.$('dispLegendTitle').textContent = `${field.label}${unit ? ` [${unit}]` : ''}${field.partial ? ' · partial' : ''} · step ${field.step}`;
            this.$('dispLegendMin').textContent = `${number(res.min)}${unitSuffix}`;
            this.$('dispLegendMid').textContent = `${number((res.min + res.max) / 2)}${unitSuffix}`;
            this.$('dispLegendMax').textContent = `${number(res.max)}${unitSuffix}`;
            const gradient = this.root.querySelector('.disp-gradient');
            if (gradient) {
              gradient.style.background = `linear-gradient(90deg, ${palette.colors.join(',')})`;
              gradient.classList.toggle('stress', field.kind === 'stress');
            }
          }
        } else if (colorMode !== 'none') {
          if (!this.nodeKeyToIndex && this.data.mesh?.nodes) {
            this.nodeKeyToIndex = new Map(this.data.mesh.nodes.map((n, i) => [String(n.key), i]));
          }
          const palette = paletteSpec(this.$('resultPalette')?.value, null);
          const custom = this.colorRangeCustom;
          const res = computeDisplacementContours({
            quads: this.viewer.state.quads,
            nodeKeyToIndex: this.nodeKeyToIndex,
            nodeDisplacements: values,
            quadDisplacements: record.quadDisplacements,
            component: colorMode,
            phase: modal ? (this.modePhase ?? 1) : 1,
            min: custom?.min,
            max: custom?.max,
            colormap: palette.colormap,
            makeColor: (r, g, b) => new THREE.Color(r, g, b)
          });
          this.viewer.state.quads.forEach((quad, i) => {
            quad.colors = res.quadColors[i];
            quad.faceColors = null;
            quad.faceGrids = null;
          });
          this.setColorRangeInputs(res.dataMin, res.dataMax, res.min, res.max);
          const dispLeg = this.$('dispLegend');
          if (dispLeg) {
            dispLeg.classList.remove('hidden');
            const titles = {
              magnitude: 'Displacement |U|',
              x: 'Displacement Ux (X)',
              y: 'Displacement Uy (Y)',
              z: 'Displacement Uz (Vertical)'
            };
            this.$('dispLegendTitle').textContent = `${titles[colorMode] || 'Displacement'} [mm]`;
            this.$('dispLegendMin').textContent = `${res.min.toFixed(2)} mm`;
            this.$('dispLegendMid').textContent = `${((res.min + res.max) / 2).toFixed(2)} mm`;
            this.$('dispLegendMax').textContent = `${res.max.toFixed(2)} mm`;
            const gradient = this.root.querySelector('.disp-gradient');
            if (gradient) {
              gradient.style.background = `linear-gradient(90deg, ${palette.colors.join(',')})`;
              gradient.classList.remove('stress');
            }
          }
        } else {
          this.viewer.state.quads.forEach(quad => {
            quad.colors = null;
            quad.color = null;
            quad.faceColors = null;
            quad.faceGrids = null;
          });
          const gradient = this.root.querySelector('.disp-gradient');
          if (gradient) {
            gradient.style.background = '';
            gradient.classList.remove('stress');
          }
          this.$('dispLegend')?.classList.add('hidden');
        }
        this.viewer.rebuild();
        if (this.viewer.state.mesh?.geometry?.boundingBox && !this.viewer.state.mesh.geometry.boundingBox.isEmpty()) {
          this.viewer.state.bounds.union(this.viewer.state.mesh.geometry.boundingBox);
        }
      }
    }
    const step = this.step;
    const isChain = Boolean(this.analysis?.isChain);
    const stepNumber = step.stageStep ?? step.step;
    const finalStepNumber = this.analysis.steps.at(-1).stageStep ?? this.analysis.steps.at(-1).step;
    this.$('resultStepValue').textContent = isChain
      ? `${step.analysisName}: step ${stepNumber} (${Number(this.$('resultStep').value) + 1} / ${this.analysis.steps.length})`
      : `${stepNumber} / ${finalStepNumber}`;
    this.$('resultStepLabel').textContent = isChain
      ? `${step.analysisName} · Step ${stepNumber} · ${step.status === 'INITIAL' ? 'Initial' : 'Committed'}`
      : `Step ${stepNumber} · ${step.status === 'INITIAL' ? 'Initial' : 'Committed'}`;
    this.$('resultLambda').textContent = number(step.loadFactor);
    this.$('resultControl').textContent = `${number(step.controlDisplacement)} cm`;
    this.$('resultMaximum').textContent = `${number(step.maxDisplacement)} cm`;
    if (step.pier1Settlement !== undefined) {
      this.$('resultPierRow')?.classList.remove('hidden');
      const sett = (step.pier1Settlement * 10).toFixed(2);
      const upl = (step.pier1Uplift * 10).toFixed(2);
      this.$('resultPier').textContent = `${sett} mm / +${upl} mm`;
    } else {
      this.$('resultPierRow')?.classList.add('hidden');
    }
    this.$('resultScaleBadge').textContent = `${number(scale)}× deformation${scale === 1 ? ' · actual size' : ''}`;
    this.$('resultStageLabel').textContent = `${step.analysisName || this.analysis.name} · step ${stepNumber}`;
    if (modal) {
      this.$('modalFrequency').textContent = `${number(this.mode.frequency)} Hz`;
      this.$('modalPeriod').textContent = `${number(this.mode.period)} s`;
      this.$('modalMass').textContent = this.mode.massPercent.map(v => `${number(v)}%`).join(' / ');
      this.$('resultScaleBadge').textContent = `${number(scale)} cm mode amplitude`;
      this.$('resultStageLabel').textContent = `${this.modal.name} · mode ${this.mode.number}`;
      this.$('resultStepLabel').textContent = `${number(this.mode.frequency)} Hz · ${number(this.mode.period)} s`;
    } else {
      const select = i => { this.pause(); this.$('resultStep').value = i; this.draw(); };
      if (this.section === 'shape') {
        const presentation = this.analysis?.chainStages ? { stages: this.analysis.chainStages } : undefined;
        this.$('resultMiniChart').replaceChildren(responseChart(this.analysis, 'force', 'displacement', Number(this.$('resultStep').value), select, true, presentation));
      }
      if (this.section === 'curves') {
        this.curves.update(this.analysis, Number(this.$('resultStep').value), {
          chainAnalysis: this.chainedAnalysis,
          mesh: this.data.mesh,
        });
      }
      if (this.section === 'interfaces') {
        if (this.analysis.interfaces?.length) {
          const chainList = this.activeChainAnalyses || (this.chainedAnalysis?.chainStages ? this.activeChainAnalyses : [this.analysis]);
          this.interfaces.update(this.analysis, this.data.mesh, Number(this.$('resultStep').value), this.data.modelSha256, this.data.sourceId, {
            chainAnalyses: chainList,
          });
        } else {
          this.$('interfaceResults').innerHTML = '<div class="result-empty-message">No interface stress data saved in this results file.</div>';
        }
      }
    }
    this.updateThrustLine();
    this.summary();
  }

  getHingeTexture() {
    if (this.hingeTexture) return this.hingeTexture;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 32;
    const ctx = canvas.getContext('2d');
    ctx.beginPath();
    ctx.arc(16, 16, 11, 0, Math.PI * 2);
    ctx.fillStyle = '#ef4444';
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();
    this.hingeTexture = new THREE.CanvasTexture(canvas);
    return this.hingeTexture;
  }

  updateThrustLine() {
    if (!this.viewer || !this.step || !this.data?.mesh) return;
    const isShape = this.section === 'shape';
    const show = Boolean(this.$('resultThrust')?.checked && isShape);
    this.$('thrustLegend')?.classList.toggle('hidden', !show);
    this.$('hingeLegend')?.classList.toggle('hidden', !show || !this.$('resultHinges')?.checked);

    if (!show) {
      if (this.thrustLineMesh) this.thrustLineMesh.visible = false;
      if (this.hingeMesh) this.hingeMesh.visible = false;
      this.viewer.needsRender = true;
      return;
    }

    const mesh = this.data.mesh;
    if (!mesh.thrustPairs?.length) {
      this.syncThrustMinForce(0);
      return;
    }

    if (!this.slotMap || this.slotMapAnalysis !== this.analysis) {
      this.slotMap = new Map(this.analysis.interfaceOrder.map((key, index) => [Number(key), index]));
      this.slotMapAnalysis = this.analysis;
    }

    const nodeMap = key => this.viewer.state.nodes.get(Number(key));
    let materialFilter = this.$('thrustFilter')?.value || 'all';
    let allowedMaterials = null;
    if (materialFilter === 'structural') {
      allowedMaterials = new Set(mesh.materials.filter(m => !/backfill|soil/i.test(m.name)).map(m => String(m.key)));
    } else if (materialFilter !== 'all') {
      allowedMaterials = new Set([String(materialFilter)]);
    }
    if (this.hiddenMaterials?.size > 0) {
      if (!allowedMaterials) {
        allowedMaterials = new Set(mesh.materials.map(m => String(m.key)));
      }
      for (const hiddenKey of this.hiddenMaterials) {
        allowedMaterials.delete(String(hiddenKey));
      }
    }
    if (allowedMaterials) {
      materialFilter = allowedMaterials;
    }
    const showHinges = Boolean(this.$('resultHinges')?.checked);
    const combineWidth = Boolean(this.$('resultThrustCentroid')?.checked);
    const readMinForce = () => Math.max(0, Number(this.$('resultThrustMinForce')?.value) || 0);
    let minForce = readMinForce();

    let res = computeThrustLines(mesh, this.step, k => this.slotMap.get(Number(k)), nodeMap, {
      materialFilter,
      hingeThreshold: 0.85,
      combineWidth,
      minForce,
    });
    if (this.syncThrustMinForce(res.maxForce)) {
      minForce = readMinForce();
      res = computeThrustLines(mesh, this.step, k => this.slotMap.get(Number(k)), nodeMap, {
        materialFilter,
        hingeThreshold: 0.85,
        combineWidth,
        minForce,
      });
    }

    if (res.positions.length > 0) {
      if (!this.thrustLineMesh) {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(res.positions, 3));
        const mat = new THREE.LineBasicMaterial({
          color: 0x38bdf8,
          linewidth: 3,
          depthTest: false,
          transparent: true,
          opacity: 0.95
        });
        this.thrustLineMesh = new THREE.LineSegments(geo, mat);
        this.thrustLineMesh.renderOrder = 45;
        this.viewer.scene.add(this.thrustLineMesh);
      } else {
        this.thrustLineMesh.geometry.dispose();
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(res.positions, 3));
        geo.computeBoundingSphere();
        this.thrustLineMesh.geometry = geo;
        this.thrustLineMesh.visible = true;
      }
    } else if (this.thrustLineMesh) {
      this.thrustLineMesh.visible = false;
    }

    if (showHinges && res.hinges.length > 0) {
      const hingePositions = new Float32Array(res.hinges.flatMap(h => h.position));
      if (!this.hingeMesh) {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(hingePositions, 3));
        const mat = new THREE.PointsMaterial({
          map: this.getHingeTexture(),
          size: 14,
          sizeAttenuation: false,
          transparent: true,
          depthTest: false
        });
        this.hingeMesh = new THREE.Points(geo, mat);
        this.hingeMesh.renderOrder = 55;
        this.viewer.scene.add(this.hingeMesh);
      } else {
        this.hingeMesh.geometry.dispose();
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(hingePositions, 3));
        geo.computeBoundingSphere();
        this.hingeMesh.geometry = geo;
        this.hingeMesh.visible = true;
      }
    } else if (this.hingeMesh) {
      this.hingeMesh.visible = false;
    }

    if (this.$('hingeCount')) this.$('hingeCount').textContent = res.hingeCount;
    this.viewer.needsRender = true;
  }

  openExportDialog() {
    if (!this.viewer || (!this.step && this.section !== 'modes')) return;
    this.$('exportStatus').textContent = '';
    this.updateExportSize();
    const dialog = this.$('resultExportDialog');
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute('open', '');
  }

  updateExportSize() {
    const canvas = this.root.querySelector('.results-canvas');
    if (!canvas) return;
    const { width, height } = exportDimensions(canvas.clientWidth, canvas.clientHeight, Number(this.$('exportScale').value));
    const crop = this.$('exportCrop')?.checked;
    const prefix = crop ? 'Up to ' : '';
    this.$('exportSize').textContent = `${prefix}${width.toLocaleString()} × ${height.toLocaleString()} px${crop ? ' before tight crop' : ''} · ${(width / 300).toFixed(2)} in wide at 300 dpi`;
  }

  exportCaption() {
    if (this.section === 'modes' && this.mode) {
      return {
        title: `${this.modal.name} · mode ${this.mode.number}`,
        subtitle: `${number(this.mode.frequency)} Hz · ${number(this.mode.period)} s · ${number(this.$('resultScale').valueAsNumber)} cm amplitude`,
        legend: [],
      };
    }
    if (!this.step) return null;
    const state = this.step;
    const legend = [];
    if (this.ghost?.visible) legend.push({ type: 'line', color: '#ffca7d', label: 'Undeformed' });
    if (this.$('resultThrust')?.checked) legend.push({ type: 'line', color: '#38bdf8', label: 'Line of thrust' });
    if (this.$('resultHinges')?.checked && Number(this.$('hingeCount')?.textContent) > 0) {
      legend.push({ type: 'dot', color: '#ef4444', label: `Hinges (${this.$('hingeCount').textContent})` });
    }
    if (this.$('resultColorBy')?.value !== 'none' && !this.$('dispLegend')?.classList.contains('hidden')) {
      const field = this.fieldById(this.$('resultColorBy').value);
      const palette = paletteSpec(this.$('resultPalette')?.value, field);
      legend.push({
        type: 'gradient',
        colors: palette.colors,
        label: `${field ? `${field.label} ` : ''}${this.$('dispLegendMin')?.textContent ?? ''} – ${this.$('dispLegendMax')?.textContent ?? ''}`,
      });
    }
    return {
      title: `${this.analysis.name} · step ${state.step}`,
      subtitle: `${number(this.$('resultScale').valueAsNumber)}× deformation · max |U| ${number(state.maxDisplacement)} cm · λ ${number(state.loadFactor)}`,
      legend,
    };
  }

  async downloadExport() {
    if (this.exporting || !this.viewer) return;
    this.exporting = true;
    const button = this.$('exportDownload');
    const status = this.$('exportStatus');
    button.disabled = true;
    status.classList.remove('error');
    status.textContent = 'Rendering high-resolution PNG…';
    try {
      const result = await exportViewerPng(this.viewer, {
        scale: Number(this.$('exportScale').value),
        background: this.$('exportBackground').value,
        axes: this.$('exportAxes').checked,
        crop: this.$('exportCrop').checked,
        caption: this.$('exportCaption').checked ? this.exportCaption() : null,
      });
      const base = this.section === 'modes' && this.mode
        ? `${this.modal.name}-mode-${this.mode.number}`
        : `${this.analysis.name}-step-${this.step.step}`;
      const background = this.$('exportBackground').value;
      downloadBlob(result.blob, `${sanitizeFilename(base)}-${background}.png`);
      const size = result.blob.size >= 1024 * 1024
        ? `${(result.blob.size / 1024 / 1024).toFixed(2)} MB`
        : `${Math.max(1, Math.round(result.blob.size / 1024))} KB`;
      status.textContent = `Saved ${result.width.toLocaleString()} × ${result.height.toLocaleString()} px PNG · ${size}`;
    } catch (error) {
      status.textContent = error.message || String(error);
      status.classList.add('error');
    } finally {
      this.exporting = false;
      button.disabled = false;
    }
  }

  autoScale() {
    if (!this.step) return;
    this.autoScaled = true;
    const points = this.data.mesh.nodes.map(n => n.point);
    const span = Math.max(...[0, 1, 2].map(axis => Math.max(...points.map(p => p[axis])) - Math.min(...points.map(p => p[axis]))));
    const maximum = this.section === 'modes' ? 1 : Math.max(...this.analysis.steps.map(s => s.maxDisplacement));
    this.$('resultScale').value = Math.min(1000000, Math.max(1, Math.round(span * 0.1 / (maximum || 1))));
    this.draw();
  }

  move(delta) {
    this.pause();
    if (!this.analysis) return;
    this.$('resultStep').value = Math.max(0, Math.min(this.analysis.steps.length - 1, Number(this.$('resultStep').value) + delta));
    this.draw();
  }

  play() {
    if (!this.analysis || this.timer) return;
    if (this.section === 'modes') {
      const start = performance.now();
      this.$('resultPlay').textContent = 'Ⅱ Pause';
      this.$('resultPlay').setAttribute('aria-label', 'Pause deformation');
      this.timer = setInterval(() => { this.modePhase = Math.cos((performance.now() - start) * Math.PI / 1000); this.draw(); }, 50);
      return;
    }
    if (Number(this.$('resultStep').value) >= this.analysis.steps.length - 1) { this.$('resultStep').value = 0; this.draw(); }
    this.$('resultPlay').textContent = 'Ⅱ Pause';
    this.$('resultPlay').setAttribute('aria-label', 'Pause deformation');
    this.timer = setInterval(() => {
      this.$('resultStep').value = Number(this.$('resultStep').value) + 1;
      this.draw();
      if (Number(this.$('resultStep').value) >= this.analysis.steps.length - 1) this.pause();
    }, Number(this.$('resultSpeed').value));
  }

  pause() {
    clearInterval(this.timer); this.timer = null;
    this.$('resultPlay').textContent = '▶ Play';
    this.$('resultPlay').setAttribute('aria-label', 'Play deformation');
  }

  buildGhostGeometries() {
    if (!this.viewer?.state?.quads || !this.baseNodes) return;
    Object.values(this.ghostGeometries || {}).forEach(g => g?.dispose?.());
    const buildEdges = extrude => {
      const edgePositions = [];
      const addSegment = (a, b) => edgePositions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      const thicknessScale = Number(this.viewer.options.thicknessScale) || 1;
      this.viewer.state.quads.forEach((quad, i) => {
        if (!this.viewer.visibleQuad(quad)) return;
        const base = quad.nodeKeys.map(k => this.baseNodes.get(k));
        if (base.some(p => !p)) return;
        if (!extrude) {
          for (let index = 0; index < 4; index += 1) {
            addSegment(base[index], base[(index + 1) % 4]);
          }
          return;
        }
        const normal = this.baseNormals?.[i]?.normal?.lengthSq() > 1e-18
          ? this.baseNormals[i].normal.clone().normalize()
          : (pts => pts[1].clone().sub(pts[0]).cross(pts[3].clone().sub(pts[0])).normalize())(base);
        const top = base.map((point, index) =>
          point.clone().addScaledVector(this.baseNormals?.[i]?.normals?.[index] ?? normal, (quad.thicknesses?.[index] ?? 0) * thicknessScale * 0.5)
        );
        const bottom = base.map((point, index) =>
          point.clone().addScaledVector(this.baseNormals?.[i]?.normals?.[index] ?? normal, -(quad.thicknesses?.[index] ?? 0) * thicknessScale * 0.5)
        );
        for (let index = 0; index < 4; index += 1) {
          addSegment(top[index], top[(index + 1) % 4]);
          addSegment(bottom[index], bottom[(index + 1) % 4]);
          addSegment(top[index], bottom[index]);
        }
      });
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(edgePositions, 3));
      return geo;
    };
    this.ghostGeometries = {
      true: buildEdges(true),
      false: buildEdges(false),
    };
    if (this.ghost) {
      this.ghost.geometry = this.ghostGeometries[String(this.$('resultExtrude').checked)];
    }
  }

  getMaterialsList() {
    if (!this.data?.mesh) return [];
    const quads = this.viewer?.state?.quads || this.data.mesh.quads || [];
    const quadCounts = new Map();
    for (const q of quads) {
      const matKey = String(q.material ?? q.materialKey ?? '');
      quadCounts.set(matKey, (quadCounts.get(matKey) || 0) + 1);
    }
    const materials = this.data.mesh.materials || [];
    const knownKeys = new Set();
    const list = [];
    for (const m of materials) {
      const key = String(m.key);
      knownKeys.add(key);
      list.push({
        key,
        name: m.name || `Material ${key}`,
        color: m.color || '#6fb7ff',
        quadCount: quadCounts.get(key) || 0,
      });
    }
    for (const [key, count] of quadCounts.entries()) {
      if (key && !knownKeys.has(key)) {
        list.push({
          key,
          name: `Material ${key}`,
          color: '#6fb7ff',
          quadCount: count,
        });
      }
    }
    return list;
  }

  toggleMaterial(key, isAlt = false) {
    const materials = this.getMaterialsList();
    const keyStr = String(key);
    if (isAlt) {
      const allOtherHidden = materials.length > 1 &&
        materials.every(m => String(m.key) === keyStr ? !this.hiddenMaterials.has(String(m.key)) : this.hiddenMaterials.has(String(m.key)));
      if (allOtherHidden) {
        this.hiddenMaterials.clear();
      } else {
        this.hiddenMaterials.clear();
        for (const m of materials) {
          if (String(m.key) !== keyStr) this.hiddenMaterials.add(String(m.key));
        }
      }
    } else {
      if (this.hiddenMaterials.has(keyStr)) {
        this.hiddenMaterials.delete(keyStr);
      } else {
        this.hiddenMaterials.add(keyStr);
      }
    }
    if (this.viewer) {
      this.viewer.visibleQuad = q => !this.hiddenMaterials.has(String(q.material));
    }
    this.renderMaterialsList();
    this.buildGhostGeometries();
    this.draw();
  }

  resetMaterials() {
    this.hiddenMaterials.clear();
    if (this.viewer) {
      this.viewer.visibleQuad = q => !this.hiddenMaterials.has(String(q.material));
    }
    this.renderMaterialsList();
    this.buildGhostGeometries();
    this.draw();
  }

  renderMaterialsList() {
    const listEl = this.$('resultMaterialsList');
    if (!listEl) return;
    const materials = this.getMaterialsList();
    if (!materials.length) {
      this.$('resultMaterialsGroup')?.classList.add('hidden');
      return;
    }
    this.$('resultMaterialsGroup')?.classList.remove('hidden');
    const query = (this.$('resultMaterialSearch')?.value || '').trim().toLowerCase();
    this.$('resultMaterialSearch')?.classList.toggle('hidden', materials.length <= 5 && !query);

    const visibleMaterials = query
      ? materials.filter(m => `${m.name} ${m.key}`.toLowerCase().includes(query))
      : materials;

    const visibleCount = materials.filter(m => !this.hiddenMaterials.has(String(m.key))).length;
    this.$('resultMaterialsCount').textContent = visibleCount === materials.length
      ? String(materials.length)
      : `${visibleCount}/${materials.length}`;

    this.$('resultResetMaterials')?.classList.toggle('hidden', this.hiddenMaterials.size === 0);

    listEl.replaceChildren();
    for (const record of visibleMaterials) {
      const keyStr = String(record.key);
      const hidden = this.hiddenMaterials.has(keyStr);

      const row = document.createElement('div');
      row.className = 'entity';
      if (hidden) row.classList.add('hidden-entity');

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'inspect-button';
      button.title = `${record.name} (Key #${keyStr}) · Click to toggle, Alt-click to isolate`;
      button.onclick = (e) => this.toggleMaterial(record.key, e.altKey);

      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.background = record.color || '#6fb7ff';

      const info = document.createElement('span');
      info.className = 'entity-info';

      const nameEl = document.createElement('span');
      nameEl.className = 'entity-name';
      nameEl.textContent = record.name;

      const metaEl = document.createElement('span');
      metaEl.className = 'entity-meta';
      metaEl.textContent = `${record.quadCount.toLocaleString()} quads · #${keyStr}`;

      info.append(nameEl, metaEl);
      button.append(swatch, info);
      row.append(button);

      const visibility = document.createElement('button');
      visibility.type = 'button';
      visibility.className = 'visibility';
      visibility.textContent = hidden ? '○' : '◉';
      visibility.setAttribute('aria-label', `${hidden ? 'Show' : 'Hide'} ${record.name}`);
      visibility.setAttribute('aria-pressed', String(!hidden));
      visibility.title = `${hidden ? 'Show' : 'Hide'} ${record.name}`;
      visibility.onclick = (e) => {
        e.stopPropagation();
        this.toggleMaterial(record.key, e.altKey);
      };
      row.append(visibility);

      listEl.append(row);
    }
  }

  summary() {
    if (!this.root.classList.contains('hidden') && this.data) {
      const quads = this.viewer?.state?.quads || this.data.mesh?.quads || [];
      const visible = this.viewer ? quads.filter(q => this.viewer.visibleQuad(q)).length : quads.length;
      this.onSummary(this.data,
        this.section === 'modes' ? this.modal : this.analysis,
        this.section === 'modes' ? { step: this.mode.number, label: `mode ${this.mode.number}` } : this.step,
        { visibleQuads: visible, totalQuads: quads.length });
    }
  }
}
