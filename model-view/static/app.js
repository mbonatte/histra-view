import { QuadViewer } from './mesh-viewer.js';
import { ModelOverlays } from './model-overlays.js';
import { MaterialsPage } from './materials.js';
import { ResultsPage } from './results.js';

const $ = id => document.getElementById(id);
const state = {
  model: null, tab: 'materials', hiddenMaterials: new Set(), selected: null, busy: false,
  quadIndex: new Map(), nodeMap: new Map(), materialMap: new Map(),
  measureMode: false, measurePoints: [],
};
const TAB_META = {
  materials: { title: 'ASSIGNED MATERIALS', help: 'Toggle visibility or inspect a material.', search: 'Find material…' },
  elements: { title: 'MESH ELEMENTS', help: 'Search by key, material, or connected node, then click to focus.', search: 'Find element…' },
  nodes: { title: 'MESH NODES', help: 'Search by key, name, or coordinate, then click to focus.', search: 'Find node…' },
  loads: { title: 'ASSIGNED LOADS', help: 'Inspect applied values and directions.', search: 'Find load…' },
  restraints: { title: 'SUPPORT DEFINITIONS', help: 'Inspect support locations and local DOFs.', search: 'Find restraint…' },
};
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

function setMeasureMode(enabled) {
  state.measureMode = Boolean(enabled);
  viewer.setMeasureMode(state.measureMode);
  $('measure').classList.toggle('active', state.measureMode);
  $('measure').setAttribute('aria-pressed', String(state.measureMode));
  if (state.measureMode) {
    $('measurePanel').classList.remove('hidden');
    const snapNote = $('measureSnap').checked ? ' Snapping to nodes and extruded corners.' : '';
    $('measureHint').textContent = state.measurePoints.length
      ? `Click the second point on the model.${snapNote}`
      : `Click the first point on the model.${snapNote}`;
  } else if (state.measurePoints.length < 2) {
    $('measurePanel').classList.add('hidden');
  }
}

function clearMeasurement() {
  state.measurePoints = [];
  viewer.clearMeasurement();
  viewer.setMeasureMode(false);
  state.measureMode = false;
  $('measure').classList.remove('active');
  $('measure').setAttribute('aria-pressed', 'false');
  $('measurePanel').classList.add('hidden');
  for (const id of ['measureDX', 'measureDY', 'measureDZ', 'measureLength']) $(id).textContent = '—';
}

function updateMeasurement() {
  const points = state.measurePoints;
  if (points.length < 2) return;
  const [a, b] = points;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dz = b.z - a.z;
  $('measureDX').textContent = format(dx);
  $('measureDY').textContent = format(dy);
  $('measureDZ').textContent = format(dz);
  $('measureLength').textContent = format(Math.hypot(dx, dy, dz));
  $('measureHint').textContent = 'Measurement complete. Click Measure to start another.';
}

function registerMeasurement(point) {
  if (!state.measureMode) return;
  if (state.measurePoints.length >= 2) {
    state.measurePoints = [];
    viewer.clearMeasurement();
  }
  state.measurePoints.push(point);
  viewer.setMeasurement(state.measurePoints);
  if (state.measurePoints.length === 1) {
    $('measurePanel').classList.remove('hidden');
    $('measureHint').textContent = 'Click the second point on the model.';
  } else {
    updateMeasurement();
    setMeasureMode(false);
  }
}

function inspect(kind, record) {
  if (kind !== 'node') viewer?.clearNodeSelection();
  state.selected = record ? { kind, id: record.id ?? record.key } : null;
  const panel = $('inspection');
  panel.replaceChildren();
  if (!record) {
    panel.append(element('div', 'empty-icon', '⌖'), element('h2', '', 'Explore the model'), element('p', '', 'Select an element, material, load, or restraint to inspect its properties.'));
    renderList();
    return;
  }
  const heading = kind === 'quad' ? `Element ${record.key}`
    : kind === 'node' ? `Node ${record.key}`
    : record.name || `${kind} ${record.key}`;
  panel.append(element('div', 'eyebrow', kind.toUpperCase()), element('h2', '', heading));
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
    const materialKey = record.materialKey ?? record.material;
    const layerKey = record.layerKey ?? record.layer;
    const material = state.model.materials.find(m => String(m.key) === String(materialKey));
    panel.append(properties({ Key: record.key, Material: material?.name ?? materialKey,
      'Material key': materialKey, Layer: viewer.layerDefinitions.get(String(layerKey))?.name ?? layerKey,
      Parent: `${record.parentTypeElement ?? record.parentType ?? '—'} ${record.parentKey ?? '—'}`,
      Nodes: record.nodeKeys.join(', '),
      Thicknesses: vectorText(record.thicknesses) }));
    const button = element('button', '', 'Inspect material →');
    button.style.marginTop = '16px';
    button.disabled = !material;
    button.onclick = () => { setTab('materials'); inspect('material', material); };
    panel.append(button);
  } else if (kind === 'node') {
    const connected = state.model.quads.filter(quad => quad.nodeKeys.includes(String(record.key))).length;
    panel.append(properties({
      Key: record.key,
      Name: record.name || `Node ${record.key}`,
      X: format(record.point[0]),
      Y: format(record.point[1]),
      Z: format(record.point[2]),
      'Connected elements': connected,
    }));
    panel.append(element('p', '', 'The node is marked in the 3D view. Turn on Mesh nodes to see all nodes.'));
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
  const meta = TAB_META[tab] || TAB_META.materials;
  $('listTitle').textContent = meta.title;
  $('listHelp').textContent = meta.help;
  $('search').placeholder = meta.search;
  renderList();
}

function renderList() {
  if (!state.model) return;
  const list = $('entityList');
  list.replaceChildren();
  const query = $('search').value.trim().toLowerCase();
  const tab = state.tab;
  let records;
  if (tab === 'elements') {
    records = state.model.quads.filter(record => {
      const material = state.materialMap.get(String(record.materialKey));
      return `${record.name || ''} ${record.key} quad element ${material?.name || ''} ${record.nodeKeys.join(' ')}`
        .toLowerCase().includes(query);
    });
  } else if (tab === 'nodes') {
    records = state.model.nodes.filter(record => (
      `${record.name || ''} ${record.key} node ${record.point.join(' ')}`.toLowerCase().includes(query)
    ));
  } else {
    records = state.model[tab].filter(record => {
      if (tab === 'loads' && $('condition').value && record.conditionKey !== $('condition').value) return false;
      return `${record.name} ${record.key} ${record.kind || ''} ${record.type || ''}`.toLowerCase().includes(query);
    });
  }
  const searchable = tab === 'elements' || tab === 'nodes';
  if (searchable && query) {
    const score = record => {
      const key = String(record.key);
      return key === query ? 0 : key.startsWith(query) ? 1 : 2;
    };
    records.sort((left, right) => score(left) - score(right)
      || String(left.key).localeCompare(String(right.key), undefined, { numeric: true }));
  }
  const visible = searchable && !query ? records.slice(0, 500) : records;
  $('listCount').textContent = visible.length === records.length
    ? String(visible.length)
    : `${visible.length}/${records.length}`;
  const kind = { materials: 'material', elements: 'quad', nodes: 'node', loads: 'load', restraints: 'restraint' }[tab];
  for (const record of visible) {
    const row = element('div', 'entity');
    row.classList.toggle('selected', state.selected?.kind === kind && String(state.selected.id) === String(record.id ?? record.key));
    const button = element('button', 'inspect-button');
    const swatch = element('span', 'swatch');
    const material = kind === 'quad' ? state.materialMap.get(String(record.materialKey)) : null;
    swatch.style.background = record.color || material?.color || (kind === 'load' ? '#ffbc66' : '#60d9c5');
    const info = element('span', 'entity-info');
    const title = kind === 'restraint' ? `Restraint ${record.key}`
      : kind === 'node' ? `Node ${record.key}`
      : kind === 'quad' ? `Element ${record.key}`
      : record.name || `${kind} ${record.key}`;
    const subtitle = kind === 'material' ? `${record.quadCount.toLocaleString()} quads · #${record.key}`
      : kind === 'quad' ? `${material?.name || `Material ${record.materialKey}`} · ${record.nodeKeys.length} nodes · #${record.key}`
      : kind === 'node' ? `X ${format(record.point[0])} · Y ${format(record.point[1])} · Z ${format(record.point[2])}`
      : kind === 'load' ? `${record.kind} · ${format(record.value)} · #${record.key}`
      : `${record.attributes.Type || record.type.replace('Geometry', '')} · ${Object.values(record.dofs).filter(d => d === 'Fixed').length}/6 fixed`;
    info.append(element('span', 'entity-name', title), element('span', 'entity-meta', subtitle));
    button.append(swatch, info);
    button.onclick = () => {
      viewer.clearSelection();
      if (kind === 'node') {
        viewer.selectNode(record.key);
        inspect('node', record);
        focusPoint([record.point], true);
        return;
      }
      viewer.clearNodeSelection();
      if (kind === 'quad') {
        const index = state.quadIndex.get(String(record.key));
        if (index != null) viewer.selectQuad(index);
        else inspect('quad', record);
        const points = record.nodeKeys.map(key => state.nodeMap.get(String(key))?.point).filter(Boolean);
        if (points.length) focusPoint(points, true);
        return;
      }
      inspect(kind, record);
      if (kind !== 'material' && record.points?.length) focusPoint(record.points);
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
  if (!records.length) {
    list.append(element('p', 'muted', query ? 'No matching entities.' : 'No assigned entities in this view.'));
  } else if (searchable && !query && records.length > visible.length) {
    list.append(element('p', 'muted', `Showing the first ${visible.length} of ${records.length}. Type to narrow the list.`));
  }
}

function focusPoint(points, zoom = false) {
  const center = points[0].map((_, i) => points.reduce((sum, p) => sum + p[i], 0) / points.length);
  const target = viewer.controls.target.clone();
  viewer.controls.target.set(...center);
  target.sub(viewer.controls.target);
  viewer.camera.position.sub(target);
  if (zoom) {
    const direction = viewer.camera.position.clone().sub(viewer.controls.target);
    if (direction.lengthSq() < 1e-12) direction.set(1, -1, 0.72);
    const bounds = viewer.state.bounds;
    const span = Math.hypot(
      bounds.max.x - bounds.min.x,
      bounds.max.y - bounds.min.y,
      bounds.max.z - bounds.min.z,
    );
    const extent = Math.max(0, ...points.map(point => Math.hypot(
      point[0] - center[0], point[1] - center[1], point[2] - center[2]
    )));
    direction.normalize().multiplyScalar(Math.max(extent * 3, span * 0.08, 1));
    viewer.camera.position.copy(viewer.controls.target).add(direction);
  }
  viewer.controls.update();
  viewer.needsRender = true;
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
  state.nodeMap = new Map(model.nodes.map(node => [String(node.key), node]));
  state.materialMap = new Map(model.materials.map(material => [String(material.key), material]));
  state.quadIndex = new Map(viewer.state.quads.map((quad, index) => [String(quad.key), index]));
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
  $('measureUnits').textContent = model.units === 'HRX native units' ? 'HRX units' : model.units;
  clearMeasurement();
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
  viewer.on('measure', result => registerMeasurement(result.point));
  viewer.setMeasureSnap($('measureSnap').checked);
  $('measureSnap').onchange = () => {
    viewer.setMeasureSnap($('measureSnap').checked);
    if (state.measureMode) setMeasureMode(true);
  };
  $('measure').onclick = () => {
    if (state.measureMode) {
      clearMeasurement();
    } else {
      clearMeasurement();
      setMeasureMode(true);
    }
  };
  $('measureReset').onclick = () => {
    clearMeasurement();
    setMeasureMode(true);
  };
  $('measureClose').onclick = () => clearMeasurement();
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
  $('clearSelection').onclick = () => { viewer.clearSelection(); viewer.clearNodeSelection(); inspect(null, null); };
  $('resetVisibility').onclick = () => { state.hiddenMaterials.clear(); $('layer').value = ''; updateVisibility(); renderList(); };
  document.addEventListener('keydown', event => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return;
    if (event.key.toLowerCase() === 'f') (location.hash === '#results' ? resultsPage.viewer : viewer)?.fit();
    if (event.key.toLowerCase() === 'm' && (!location.hash || location.hash === '#model')) {
      if (state.measureMode) clearMeasurement();
      else { clearMeasurement(); setMeasureMode(true); }
    }
    if (event.key === '\\' && (!location.hash || location.hash === '#model')) {
      setFocusView(!document.body.classList.contains('focus-view'));
    }
    if (event.key === 'Escape') {
      if (state.measureMode || state.measurePoints.length) clearMeasurement();
      else { viewer.clearSelection(); inspect(null, null); }
    }
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
