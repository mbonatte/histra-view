import { QuadViewer } from './mesh-viewer.js';
import { ModelOverlays } from './model-overlays.js';
import { MaterialsPage } from './materials.js';
import { ResultsPage } from './results.js';

const $ = id => document.getElementById(id);
const state = { model: null, tab: 'materials', hiddenMaterials: new Set(), selected: null, busy: false };
const materialsPage = new MaterialsPage();
const resultsPage = new ResultsPage($('resultsPage'), (data, analysis, step) => {
  $('fileName').textContent = data.name;
  const analysisName = analysis?.name || data.name;
  const stepLabel = step ? (step.label || `step ${step.step}`) : 'results';
  $('status').textContent = `${analysisName} · ${stepLabel} · saved results`;
  $('stats').textContent = data.mesh?.nodes?.length ? `${data.mesh.nodes.length} nodes / ${data.mesh.quads.length} quads` : 'Response curves';
});
let viewer;
let overlays;
const format = value => typeof value === 'number' ? value.toLocaleString(undefined, { maximumSignificantDigits: 6 }) : String(value ?? '—');
const vectorText = values => values?.map(format).join(', ') ?? '—';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showMessage(text, error = false) {
  $('message').textContent = text;
  $('message').classList.remove('hidden');
  $('message').classList.toggle('error', error);
}

function properties(values) {
  const dl = element('dl', 'properties');
  for (const [key, value] of Object.entries(values)) {
    const row = element('div');
    row.append(element('dt', '', key), element('dd', '', format(value)));
    dl.append(row);
  }
  return dl;
}

function rawAttributes(attributes) {
  const details = element('details');
  details.append(element('summary', '', 'All HRX attributes'), properties(attributes));
  return details;
}

function inspect(kind, record) {
  state.selected = record ? { kind, id: record.id ?? record.key } : null;
  const panel = $('inspection');
  panel.replaceChildren();
  if (!record) {
    panel.append(element('div', 'empty-icon', '⌖'), element('h2', '', 'Explore the model'), element('p', '', 'Select an element, material, load, or restraint to inspect its properties.'));
    renderList();
    return;
  }
  panel.append(element('div', 'eyebrow', kind.toUpperCase()), element('h2', '', record.name || `${kind} ${record.key}`));
  if (kind === 'material') {
    const a = record.attributes;
    panel.append(element('p', '', a.Description || a.PurposeType || 'Material definition'));
    panel.append(properties({ Key: record.key, 'Assigned quads': record.quadCount, Color: record.color,
      Ehor: a.Ehor ?? a.E ?? '—', Ever: a.Ever ?? '—', Gd: a.Gd ?? a.G ?? '—',
      FmHor: a.FmHor ?? '—', FmVer: a.FmVer ?? '—', 'Unit weight (w / Gamma)': a.w ?? a.Gamma ?? '—' }));
    const fullProperties = element('button', 'full-material-button', 'Open material properties →');
    fullProperties.onclick = () => materialsPage.open(record.key);
    panel.append(fullProperties);
  } else if (kind === 'quad') {
    const material = state.model.materials.find(m => String(m.key) === String(record.material));
    panel.append(properties({ Key: record.key, Material: material?.name ?? record.material,
      'Material key': record.material, Layer: viewer.layerDefinitions.get(String(record.layer))?.name ?? record.layer,
      Parent: `${record.parentType} ${record.parentKey}`, Nodes: record.nodeKeys.join(', '),
      Thicknesses: vectorText(record.thicknesses) }));
    const button = element('button', '', 'Inspect material →');
    button.style.marginTop = '16px';
    button.disabled = !material;
    button.onclick = () => { setTab('materials'); inspect('material', material); };
    panel.append(button);
  } else if (kind === 'load') {
    const condition = state.model.loadConditions.find(c => c.key === record.conditionKey);
    panel.append(properties({ Type: record.kind, 'Load condition': condition?.name || record.conditionKey,
      'Signed value': record.value, Direction: vectorText(record.direction), 'Template key': record.templateKey,
      Target: `${record.elementType} ${record.elementKey}`, Source: record.source, Display: record.drawable ? 'Drawn' : 'Not supported yet' }));
    panel.append(element('p', '', 'Value is in HRX native units; intensity is not a total resultant. Arrow lengths are proportional within the displayed loads.'));
  } else if (kind === 'restraint') {
    panel.append(properties({ Key: record.key, Type: record.attributes.Type || record.type,
      'Attached element': `${record.attributes.ComputationalElementType || record.attributes.ParentType || '—'} ${record.attributes.ComputationalElementKey || record.attributes.ParentKey || ''}`,
      Material: record.attributes.MaterialKey ?? '—' }));
    const grid = element('div', 'dof-grid');
    for (const [dof, behavior] of Object.entries(record.dofs)) {
      const cell = element('div', 'dof');
      cell.append(element('strong', '', dof), element('span', '', behavior));
      grid.append(cell);
    }
    panel.append(grid, element('p', '', 'U1–U3 are translations; R1–R3 are rotations, in the restraint’s local reference system.'), properties(record.referenceSystem));
  }
  panel.append(rawAttributes(record.attributes || {}));
  renderList();
}

function setTab(tab) {
  state.tab = tab;
  $('search').value = '';
  for (const button of document.querySelectorAll('[data-tab]')) button.setAttribute('aria-selected', String(button.dataset.tab === tab));
  $('conditionField').classList.toggle('hidden', tab !== 'loads');
  $('listTitle').textContent = { materials: 'ASSIGNED MATERIALS', loads: 'ASSIGNED LOADS', restraints: 'SUPPORT DEFINITIONS' }[tab];
  $('listHelp').textContent = { materials: 'Toggle visibility or inspect a material.', loads: 'Inspect applied values and directions.', restraints: 'Inspect support locations and local DOFs.' }[tab];
  $('search').placeholder = `Find ${tab === 'materials' ? 'material' : tab === 'loads' ? 'load' : 'restraint'}…`;
  renderList();
}

function renderList() {
  if (!state.model) return;
  const list = $('entityList');
  list.replaceChildren();
  const query = $('search').value.trim().toLowerCase();
  const rows = state.model[state.tab].filter(record => {
    if (state.tab === 'loads' && $('condition').value && record.conditionKey !== $('condition').value) return false;
    return `${record.name} ${record.key} ${record.kind || ''} ${record.type || ''}`.toLowerCase().includes(query);
  });
  $('listCount').textContent = rows.length;
  const kind = { materials: 'material', loads: 'load', restraints: 'restraint' }[state.tab];
  for (const record of rows) {
    const row = element('div', 'entity');
    row.classList.toggle('selected', state.selected?.kind === kind && state.selected.id === (record.id ?? record.key));
    const button = element('button', 'inspect-button');
    const swatch = element('span', 'swatch');
    swatch.style.background = record.color || (kind === 'load' ? '#ffbc66' : '#60d9c5');
    const info = element('span', 'entity-info');
    const title = kind === 'restraint' ? `Restraint ${record.key}` : record.name || `${kind} ${record.key}`;
    const subtitle = kind === 'material' ? `${record.quadCount.toLocaleString()} quads · #${record.key}`
      : kind === 'load' ? `${record.kind} · ${format(record.value)} · #${record.key}`
      : `${record.attributes.Type || record.type.replace('Geometry', '')} · ${Object.values(record.dofs).filter(d => d === 'Fixed').length}/6 fixed`;
    info.append(element('span', 'entity-name', title), element('span', 'entity-meta', subtitle));
    button.append(swatch, info);
    button.onclick = () => {
      viewer.clearSelection();
      inspect(kind, record);
      if (kind !== 'material' && record.points.length) focusPoint(record.points);
    };
    row.append(button);
    if (kind === 'material') {
      const hidden = state.hiddenMaterials.has(String(record.key));
      row.classList.toggle('hidden-entity', hidden);
      const visibility = element('button', 'visibility', hidden ? '○' : '◉');
      visibility.setAttribute('aria-label', `${hidden ? 'Show' : 'Hide'} ${record.name}`);
      visibility.setAttribute('aria-pressed', String(!hidden));
      visibility.onclick = () => {
        if (hidden) state.hiddenMaterials.delete(String(record.key));
        else state.hiddenMaterials.add(String(record.key));
        updateVisibility();
        renderList();
      };
      row.append(visibility);
    }
    list.append(row);
  }
  if (!rows.length) list.append(element('p', 'muted', query ? 'No matching entities.' : 'No assigned entities in this view.'));
}

function focusPoint(points) {
  const center = points[0].map((_, i) => points.reduce((sum, p) => sum + p[i], 0) / points.length);
  const delta = viewer.controls.target.clone();
  viewer.controls.target.set(...center);
  delta.sub(viewer.controls.target);
  viewer.camera.position.sub(delta);
  viewer.controls.update();
}

function updateVisibility() {
  const layer = $('layer').value;
  viewer.visibleQuad = q => !state.hiddenMaterials.has(String(q.material)) && (!layer || String(q.layer) === layer);
  viewer.clearSelection();
  viewer.rebuild();
  updateStats();
}

function updateStats() {
  const model = state.model;
  const visible = viewer.state.quads.filter(q => viewer.visibleQuad(q)).length;
  $('stats').textContent = `${model.nodes.length.toLocaleString()} nodes / ${visible.toLocaleString()} of ${model.quads.length.toLocaleString()} quads`;
  $('status').textContent = visible ? 'Model ready' : 'All mesh elements hidden';
}

function updateOverlays() {
  if (!state.model) return;
  overlays.update(state.model, { loads: $('loads').checked, restraints: $('restraints').checked,
    condition: $('condition').value, symbolScale: Number($('symbolScale').value) });
  $('scaleValue').value = `${$('symbolScale').value}×`;
}

function populateSelect(select, records, label) {
  select.replaceChildren(new Option(label, ''));
  for (const record of records) select.add(new Option(`${record.name || record.key} [${record.key}]`, record.key));
}

function loadModel(model) {
  // Finish projection and validation before replacing the visible model.
  state.model = model;
  state.modelViewed = location.hash !== '#materials';
  state.hiddenMaterials.clear();
  state.selected = null;
  materialsPage.setModel(model);
  viewer.visibleQuad = () => true;
  viewer.materialDefinitions = new Map(model.materials.map(m => [String(m.key), m]));
  viewer.layerDefinitions = new Map(model.layers.map(l => [String(l.key), l]));
  viewer.loadPreview(model, { name: model.name });
  viewer.setView('iso');
  $('fileName').textContent = model.name;
  $('modelTitle').textContent = model.name.replace(/\.hrx$/i, '').replaceAll('_', ' ');
  $('modelSubtitle').textContent = `${model.materials.length} materials · ${model.restraints.length} restraints · ${model.loads.length} loads`;
  $('entityCount').textContent = model.quads.length.toLocaleString();
  const usedLayers = new Set(model.quads.map(q => q.layerKey));
  const layers = model.layers.filter(l => usedLayers.has(l.key));
  for (const key of usedLayers) if (!layers.some(l => l.key === key)) layers.push({ key, name: 'Layer' });
  populateSelect($('layer'), layers, 'All layers');
  populateSelect($('condition'), model.loadConditions, 'All assigned conditions');
  $('dimensions').textContent = `Z up · ${model.units}`;
  $('warnings').replaceChildren(...model.warnings.map(w => element('p', 'warning', w)));
  $('warningCount').textContent = model.warnings.length;
  updateOverlays();
  inspect(null, null);
  updateStats();
  $('message').classList.add('hidden');
  showPage();
}

function showPage() {
  const materials = location.hash === '#materials';
  const results = location.hash === '#results';
  $('modelWorkspace').classList.toggle('hidden', materials || results);
  $('materialsPage').classList.toggle('hidden', !materials);
  $('resultsPage').classList.toggle('hidden', !results);
  for (const [id, active] of [['materialsNav', materials], ['resultsNav', results], ['modelNav', !materials && !results]]) {
    if (active) $(id).setAttribute('aria-current', 'page');
    else $(id).removeAttribute('aria-current');
  }
  if (results) resultsPage.activate();
  else {
    resultsPage.deactivate();
    if (state.model) { $('fileName').textContent = state.model.name; updateStats(); }
  }
  if (!materials && !results && viewer) {
    viewer.resize();
    if (state.model && !state.modelViewed) { viewer.fit(); state.modelViewed = true; }
    viewer.needsRender = true;
  }
}

window.addEventListener('hashchange', showPage);

async function readModel(file = null) {
  if (state.busy) return;
  state.busy = true;
  $('openFile').disabled = $('loadExample').disabled = true;
  showMessage(file ? `Opening ${file.name}…` : 'Reading the example model…');
  $('status').textContent = 'Reading HRX';
  try {
    const response = await fetch(file ? '/api/model' : '/api/model/example', file ? { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file } : {});
    const model = await response.json();
    if (!response.ok) throw new Error(model.error || `HTTP ${response.status}`);
    if (file) model.name = file.name;
    loadModel(model);
  } catch (error) {
    showMessage(error.message || String(error), true);
    $('status').textContent = state.model ? 'Import failed · previous model retained' : 'Unable to load model';
  } finally {
    state.busy = false;
    $('openFile').disabled = $('loadExample').disabled = false;
    $('fileInput').value = '';
  }
}

const RESULT_EXTENSIONS = new Set(['.results', '.histra', '.json', '.rar', '.zip']);
const MODEL_EXTENSIONS = new Set(['.hrx', '.xml']);

function importId() {
  return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function uploadImportFile(file, id, role) {
  const response = await fetch(
    `/api/results/import?import_id=${encodeURIComponent(id)}&role=${encodeURIComponent(role)}` +
    `&name=${encodeURIComponent(file.name)}`,
    { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file }
  );
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Upload of ${file.name} failed.`);
  return payload;
}

async function readResultFiles(files) {
  if (state.busy) return;
  const selected = [...files];
  if (!selected.length) return;
  const modelFile = selected.find(file => MODEL_EXTENSIONS.has(PathLike(file.name)));
  const resultFile = selected.find(file => RESULT_EXTENSIONS.has(PathLike(file.name)));
  if (!resultFile) {
    if (modelFile) return readModel(modelFile);
    showMessage('Select an HRX model and a .Results, .histra, or .json result file.', true);
    return;
  }
  if (resultFile.name.toLowerCase().endsWith('.results') && !modelFile) {
    showMessage('A native C# .Results import also needs its matching HRX model.', true);
    return;
  }
  state.busy = true;
  $('openResultFile').disabled = true;
  showMessage(`Importing ${resultFile.name}${modelFile ? ` with ${modelFile.name}` : ''}…`);
  $('status').textContent = 'Uploading result files';
  try {
    const id = importId();
    if (modelFile) await uploadImportFile(modelFile, id, 'model');
    await uploadImportFile(resultFile, id, 'results');
    $('status').textContent = 'Reading result files';
    const response = await fetch(`/api/results/import/complete?import_id=${encodeURIComponent(id)}`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    location.hash = '#results';
    resultsPage.loadDirectResults(data, resultFile.name);
    $('fileName').textContent = resultFile.name;
    $('status').textContent = `Imported ${resultFile.name}`;
    if (data.mesh?.nodes?.length) {
      $('stats').textContent = `${data.mesh.nodes.length} nodes / ${data.mesh.quads.length} quads`;
    } else {
      $('stats').textContent = 'Pushover curves';
    }
    $('message').classList.add('hidden');
  } catch (error) {
    showMessage(`Results import failed: ${error.message || String(error)}`, true);
    $('status').textContent = 'Results import failed';
  } finally {
    state.busy = false;
    $('openResultFile').disabled = false;
    $('resultFileInput').value = '';
  }
}

function PathLike(name) {
  return `.${String(name).toLowerCase().split('.').pop()}`;
}

function showBlankStart() {
  $('fileName').textContent = 'No model loaded';
  $('status').textContent = 'Select a model or result';
  $('stats').textContent = 'No model loaded';
  $('modelTitle').textContent = 'Open a model to begin';
  $('modelSubtitle').textContent = 'Use Open HRX or Import Results';
  $('entityCount').textContent = '0';
  $('message').textContent = 'Open an HRX model or import a result file to begin. You can also drop files here.';
  $('message').classList.remove('hidden', 'error');
}

try {
  viewer = new QuadViewer($('viewport'), { extrude: true, thicknessScale: 1, opacity: 1 });
  overlays = new ModelOverlays(viewer, inspect);
  showPage();
  viewer.on('selection', selected => inspect(selected ? 'quad' : null, selected?.quad));
  for (const button of document.querySelectorAll('[data-tab]')) button.onclick = () => setTab(button.dataset.tab);
  for (const button of document.querySelectorAll('[data-view]')) button.onclick = () => {
    viewer.setView(button.dataset.view);
    for (const other of document.querySelectorAll('[data-view]')) other.classList.toggle('active', other === button);
  };
  for (const button of document.querySelectorAll('[data-projection]')) button.onclick = () => {
    viewer.setProjection(button.dataset.projection);
    for (const other of document.querySelectorAll('[data-projection]')) other.classList.toggle('active', other === button);
  };
  $('openFile').onclick = () => $('fileInput').click();
  $('fileInput').onchange = () => { if ($('fileInput').files[0]) readModel($('fileInput').files[0]); };
  $('openResultFile').onclick = () => $('resultFileInput').click();
  $('resultFileInput').onchange = () => { if ($('resultFileInput').files.length) readResultFiles($('resultFileInput').files); };
  $('loadExample').onclick = () => readModel();
  $('search').oninput = renderList;
  $('condition').onchange = () => { renderList(); updateOverlays(); };
  $('layer').onchange = updateVisibility;
  $('colorBy').onchange = () => viewer.setOptions({ colorBy: $('colorBy').value });
  for (const id of ['edges', 'nodes', 'extrude']) $(id).onchange = () => viewer.setOptions({ [id]: $(id).checked });
  for (const id of ['loads', 'restraints', 'symbolScale']) $(id).oninput = updateOverlays;
  $('opacity').oninput = () => {
    viewer.setOptions({ opacity: Number($('opacity').value) }, { rebuild: false });
    $('opacityValue').value = `${Math.round(Number($('opacity').value) * 100)}%`;
  };
  $('grid').onchange = () => { viewer.grid.visible = $('grid').checked; viewer.needsRender = true; };
  $('fitView').onclick = () => viewer.fit();
  const setFocusView = enabled => {
    document.body.classList.toggle('focus-view', enabled);
    $('togglePanels').setAttribute('aria-pressed', String(enabled));
    $('togglePanels').textContent = enabled ? 'Exit focus' : 'Focus';
    $('togglePanels').title = enabled ? 'Show side panels (\\)' : 'Hide side panels (\\)';
    requestAnimationFrame(() => { viewer.resize(); viewer.needsRender = true; });
  };
  $('togglePanels').onclick = () => setFocusView(!document.body.classList.contains('focus-view'));
  $('clearSelection').onclick = () => { viewer.clearSelection(); inspect(null, null); };
  $('resetVisibility').onclick = () => { state.hiddenMaterials.clear(); $('layer').value = ''; updateVisibility(); renderList(); };
  document.addEventListener('keydown', event => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return;
    if (event.key.toLowerCase() === 'f') (location.hash === '#results' ? resultsPage.viewer : viewer)?.fit();
    if (event.key === '\\' && (!location.hash || location.hash === '#model')) {
      setFocusView(!document.body.classList.contains('focus-view'));
    }
    if (event.key === 'Escape') { viewer.clearSelection(); inspect(null, null); }
  });
  document.addEventListener('dragover', event => { event.preventDefault(); $('dropHint').classList.remove('hidden'); });
  document.addEventListener('dragleave', event => { if (!event.relatedTarget) $('dropHint').classList.add('hidden'); });
  document.addEventListener('drop', event => {
    event.preventDefault(); $('dropHint').classList.add('hidden');
    const files = [...(event.dataTransfer?.files || [])];
    if (!files.length) return;
    if (files.some(file => RESULT_EXTENSIONS.has(PathLike(file.name)))) {
      readResultFiles(files);
    } else {
      readModel(files[0]);
    }
  });
  showBlankStart();
} catch (error) {
  showMessage(`The 3D viewer could not start: ${error.message}. Check that WebGL is available.`, true);
  $('status').textContent = 'Viewer unavailable';
}
