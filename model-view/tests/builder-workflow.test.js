import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Builder } from '../static/builder.js';

function status() {
  return { textContent: '', classList: { add() {}, remove() {} } };
}

test('layer-material action changes only explicitly selected strips', () => {
  const oldDocument = globalThis.document;
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.checked = false; }
    append(...items) { this.children.push(...items); }
    addEventListener(event, callback) { this.listeners[event] = callback; }
  }
  globalThis.document = { createElement: tag => new Element(tag) };
  try {
    const builder = new Builder({}, () => {});
    builder.materials = [
      { key: '18', name: 'Wall', attributes: { PurposeType: 'MasonryMaterial' } },
      { key: '19', name: 'Fill', attributes: { PurposeType: 'MasonryMaterial' } },
    ];
    const strip = (name, material) => ({ nodes: [{ path: [], attributes: { Name: name, MaterialKey: material } }] });
    builder.collections = { wizard_corsia: [strip('Left wall', '18'), strip('Middle', '19'), strip('Right wall', '18')] };
    builder.scheduleGeometryPreview = () => {};
    builder.render = () => {};
    const parent = new Element('div');
    builder.renderBackfillStripOverrides(parent, builder.collections.wizard_corsia);
    const labels = parent.children.filter(child => child.tag === 'label');
    const button = parent.children.find(child => child.tag === 'button');
    assert.equal(labels.length, 3);
    assert.ok(labels.every(label => !label.children[0].checked));
    button.listeners.click();
    assert.equal(builder.changes.size, 0);
    labels[1].children[0].checked = true;
    button.listeners.click();
    assert.equal(builder.wizardCurrent('wizard_corsia', 0, 'MaterialKey'), '18');
    assert.equal(builder.wizardCurrent('wizard_corsia', 1, 'MaterialKey'), '0');
    assert.equal(builder.wizardCurrent('wizard_corsia', 2, 'MaterialKey'), '18');
  } finally {
    globalThis.document = oldDocument;
  }
});

test('builder offers a single download action', () => {
  const oldDocument = globalThis.document;
  const oldOption = globalThis.Option;
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
    append(...items) { this.children.push(...items); }
    replaceChildren(...items) { this.children = items; }
    setAttribute() {}
    addEventListener() {}
    add(item) { this.children.push(item); }
  }
  globalThis.document = { createElement: tag => new Element(tag) };
  globalThis.Option = class { constructor(label, value) { this.label = label; this.value = value; } };
  try {
    const root = new Element('root');
    const builder = new Builder(root, () => {});
    builder.mode = 'edit';
    builder.renderEdit = () => {};
    builder.render();
    const actions = root.children.find(item => item.className === 'builder-actions');
    assert.deepEqual(actions.children.map(item => item.textContent), ['Download HRX']);
  } finally {
    globalThis.document = oldDocument;
    globalThis.Option = oldOption;
  }
});

test('opening an HRX loads its model into the viewer immediately', async () => {
  const shown = [];
  const builder = new Builder({}, (model, options) => shown.push({ model, options }));
  builder.status = status();
  builder.render = () => {};
  builder.changes.set('old', { value: 'old' });
  builder.editSteps = [{ changes: [{ value: 'old' }] }];
  builder.json = async (url, request) => {
    assert.equal(url, '/api/builder/open');
    assert.deepEqual(request, { source: 'new-source', name: 'bridge.hrx' });
    return { inspection: { materials: [], analyses: [], collections: {} }, model: { name: 'bridge.hrx' } };
  };
  await builder.loadSource('new-source', 'bridge.hrx');
  assert.equal(builder.source, 'new-source');
  assert.equal(builder.viewerSource, 'new-source');
  assert.equal(builder.changes.size, 0);
  assert.deepEqual(builder.editSteps, []);
  assert.deepEqual(shown, [{ model: { name: 'bridge.hrx' }, options: { preserveView: false } }]);
});

test('live updates regenerate only after geometry edits and retain the camera', async () => {
  const oldSetTimeout = globalThis.setTimeout;
  const oldClearTimeout = globalThis.clearTimeout;
  let callback;
  globalThis.setTimeout = fn => { callback = fn; return 1; };
  globalThis.clearTimeout = () => {};
  try {
    const shown = [];
    const builder = new Builder({}, (model, options) => shown.push({ model, options }));
    builder.status = status();
    builder.mode = 'edit';
    builder.source = 'source';
    builder.editSteps = [{ changes: [], operations: [{ op: 'add_material' }] }];
    builder.changes.set('pier', { collection: 'wizard_pier', value: '500' });
    builder.json = async (url, request) => {
      assert.equal(url, '/api/builder/preview');
      assert.equal(request.rebuild_geometry, true);
      assert.equal(request.steps, builder.editSteps);
      return { name: 'updated' };
    };
    builder.scheduleGeometryPreview();
    await callback();
    assert.deepEqual(shown, [{ model: { name: 'updated' }, options: { preserveView: true } }]);

    builder.changes.clear();
    builder.mode = 'create';
    builder.payload = { name: 'new bridge' };
    builder.json = async (url, request) => {
      assert.equal(request.mode, 'create');
      assert.equal(request.payload.name, 'new bridge');
      return { name: 'new bridge' };
    };
    builder.scheduleGeometryPreview();
    await callback();
    assert.equal(shown.at(-1).model.name, 'new bridge');
  } finally {
    globalThis.setTimeout = oldSetTimeout;
    globalThis.clearTimeout = oldClearTimeout;
  }
});

test('download automatically requests regeneration after geometry changes', async () => {
  const oldFetch = globalThis.fetch;
  const oldDocument = globalThis.document;
  const oldSetTimeout = globalThis.setTimeout;
  const oldCreateUrl = URL.createObjectURL;
  const oldRevokeUrl = URL.revokeObjectURL;
  let request;
  let clicked = false;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/builder/export');
    request = JSON.parse(options.body);
    return { ok: true, blob: async () => new Blob(['hrx']) };
  };
  globalThis.document = { createElement: () => ({ click() { clicked = true; } }) };
  globalThis.setTimeout = () => 1;
  URL.createObjectURL = () => 'blob:result';
  URL.revokeObjectURL = () => {};
  try {
    const builder = new Builder({}, () => {});
    builder.status = status();
    builder.mode = 'edit';
    builder.source = 'original-source';
    builder.sourceName = 'bridge.hrx';
    builder.appliedGeometryChanges = true;
    builder.editSteps = [{ changes: [{ collection: 'wizard_pier' }], operations: [] }];
    await builder.run();
    assert.equal(clicked, true);
    assert.equal(request.rebuild_geometry, true);
    assert.equal(request.source, 'original-source');
    assert.deepEqual(request.steps, builder.editSteps);
    assert.equal(request.replace_existing_mesh, undefined);
  } finally {
    globalThis.fetch = oldFetch;
    globalThis.document = oldDocument;
    globalThis.setTimeout = oldSetTimeout;
    URL.createObjectURL = oldCreateUrl;
    URL.revokeObjectURL = oldRevokeUrl;
  }
});

test('geometry links mirror abutments and propagate only edited fields', () => {
  const builder = new Builder({}, () => {});
  builder.scheduleGeometryPreview = () => {};
  const record = attributes => ({ nodes: [{ path: [], attributes }] });
  builder.collections = {
    wizard_abutment: [record({ b1: '10', b3: '20', AbutmentKind: 'Left' }), record({ b1: '30', b3: '40', AbutmentKind: 'Right' })],
    wizard_span: [record({ L: '100', f: '40' }), record({ L: '200', f: '50' })],
    wizard_pier: [record({ H: '10' }), record({ H: '20' })],
  };
  builder.wizardSet('wizard_span', 0, 'L', '110');
  assert.equal(builder.wizardCurrent('wizard_span', 1, 'L'), '200');
  builder.geometryLinks = { abutments: true, spans: true, piers: true };
  assert.equal(builder.wizardCurrent('wizard_span', 1, 'L'), '200');
  builder.wizardSet('wizard_span', 0, 'L', '120');
  assert.equal(builder.wizardCurrent('wizard_span', 1, 'L'), '120');
  assert.equal(builder.wizardCurrent('wizard_span', 1, 'f'), '50');
  builder.wizardSet('wizard_abutment', 0, 'b1', '15');
  assert.equal(builder.wizardCurrent('wizard_abutment', 1, 'b3'), '15');
  builder.wizardSet('wizard_abutment', 0, 'AbutmentKind', 'Other');
  assert.equal(builder.wizardCurrent('wizard_abutment', 1, 'AbutmentKind'), 'Right');
  builder.wizardSet('wizard_pier', 1, 'H', '30');
  assert.equal(builder.wizardCurrent('wizard_pier', 0, 'H'), '30');
});

test('create geometry links update the counterpart and its visible field', () => {
  const builder = new Builder({}, () => {});
  const left = { b1: 10 }, right = { b3: 30 };
  builder.payload = { left_abutment: left, right_abutment: right, spans: [], piers: [] };
  builder.geometryLinks.abutments = true;
  const input = { value: '' };
  builder.geometryInputs.set(right, new Map([['b3', input]]));
  builder.propagateCreateLink(left, 'b1');
  assert.equal(right.b3, 10);
  assert.equal(input.value, '10');
});

test('analysis editing groups expose P-Delta and preserve every saved property', async () => {
  const { analysisPropertyGroups } = await import('../static/builder.js');
  const attributes = { Name: 'Vert', PdeltaEffect: 'EachStep', ConvergenceTolerance: '0.001', CustomSetting: '42' };
  const groups = analysisPropertyGroups(attributes);
  assert.deepEqual(groups.find(group => group.id === 'iterative').keys, ['PdeltaEffect']);
  assert.deepEqual(groups.find(group => group.id === 'advanced').keys, ['CustomSetting']);
  assert.deepEqual(groups.flatMap(group => group.keys).sort(), Object.keys(attributes).sort());
});

test('analysis step count edits the referenced load function and excludes dynamic-only fields', async () => {
  const { analysisPropertyGroups } = await import('../static/builder.js');
  const groups = analysisPropertyGroups({ Name: 'Vert', DynamicAlfa: '-0.33', DampingRatio1: '0.05', Other: 'x' });
  assert.deepEqual(groups.flatMap(group => group.keys).sort(), ['Name', 'Other']);
  const oldDocument = globalThis.document;
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.value = ''; }
    append(...items) { this.children.push(...items); }
    addEventListener(type, listener) { this.listeners[type] = listener; }
    setCustomValidity() {} reportValidity() {}
  }
  globalThis.document = { createElement: tag => new Element(tag) };
  try {
    const builder = new Builder({}, () => {}); builder.mode = 'edit'; builder.scheduleGeometryPreview = () => {};
    const record = attributes => ({ attributes, nodes: [{ path: [], attributes }] });
    const analysis = record({ AnalysisType: '2', LoadFunctionKey: '7' });
    builder.collections = { analysis: [analysis], load_function: [{ key: '7', ...record({ typeDiscr: 'false', DiscrVal: '0.2' }) }],
      load_function_item: [record({ loadFunctionKey: '7', pseudoTime: '0', multiplier: '0' }), record({ loadFunctionKey: '7', pseudoTime: '1', multiplier: '1' })] };
    const parent = new Element('root'); builder.renderAnalysisSteps(analysis, 0, builder.changes, parent);
    const input = parent.children[0].children[1]; assert.equal(input.value, '5');
    input.value = '20'; input.listeners.change();
    const change = builder.changes.get('load_function:0::DiscrVal');
    assert.equal(change.collection, 'load_function');
    assert.equal(Math.ceil(1 / Number(change.value)), 20);
    input.value = '5'; input.listeners.change(); assert.equal(builder.changes.size, 0);
  } finally { globalThis.document = oldDocument; }
});

test('analysisPropertyGroups adapts groups based on AnalysisType', async () => {
  const { analysisPropertyGroups } = await import('../static/builder.js');
  // Static nonlinear (AnalysisType 2) should include iterative and convergence but exclude modal
  const staticAttrs = {
    AnalysisType: '2',
    Name: 'Pushover',
    PdeltaEffect: 'EachStep',
    ConvergenceTolerance: '0.001',
    NumberOfEigenModes: '5',
  };
  const staticGroups = analysisPropertyGroups(staticAttrs);
  const staticGroupIds = staticGroups.map(g => g.id);
  assert.ok(staticGroupIds.includes('control'));
  assert.ok(staticGroupIds.includes('iterative'));
  assert.ok(staticGroupIds.includes('convergence'));
  assert.ok(!staticGroupIds.includes('modal'), 'Static analysis must not include modal group');

  // Modal analysis (AnalysisType 5) should include modal but exclude iterative and convergence
  const modalAttrs = {
    AnalysisType: '5',
    Name: 'Modal_0',
    NumberOfEigenModes: '10',
    PdeltaEffect: 'None',
    ConvergenceTolerance: '0.001',
  };
  const modalGroups = analysisPropertyGroups(modalAttrs);
  const modalGroupIds = modalGroups.map(g => g.id);
  assert.ok(modalGroupIds.includes('control'));
  assert.ok(modalGroupIds.includes('modal'), 'Modal analysis must include modal group');
  assert.ok(!modalGroupIds.includes('iterative'), 'Modal analysis must not include iterative group');
  assert.ok(!modalGroupIds.includes('convergence'), 'Modal analysis must not include convergence group');
});

test('material units toNativeValue converts display values back to native units', async () => {
  const { toNativeValue, convertedValue } = await import('../static/material-units.js');
  // Stress (MPa in engineering, factor 10): 16200 MPa -> 1620 kN/cm²
  assert.equal(toNativeValue('16200', 'Ehor', 'engineering'), '1620');
  assert.equal(convertedValue('1620', 'Ehor', 'engineering'), '16200');

  // Weight (kN/m³ in engineering, factor 1e6): 22.4 kN/m³ -> 0.0000224 kN/cm³
  const nativeWeight = toNativeValue('22.4', 'w', 'engineering');
  assert.equal(Number(nativeWeight), 2.24e-5);
  assert.equal(convertedValue(nativeWeight, 'w', 'engineering'), '22.4');

  // Native set preserves values exactly
  assert.equal(toNativeValue('1620', 'Ehor', 'native'), '1620');
});

test('builder materialOptions formats items as name (key)', () => {
  const builder = new Builder({}, () => {});
  builder.materials = [
    { key: '18', name: 'Masonry' },
    { key: '141', name: 'Foundation' },
  ];
  const options = builder.materialOptions();
  assert.deepEqual(options, [
    ['0', 'None (0)'],
    ['18', 'Masonry (18)'],
    ['141', 'Foundation (141)'],
  ]);
});

