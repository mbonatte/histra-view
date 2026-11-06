import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile, writeFile, mkdir, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Vector3, BufferGeometry } from 'three';

const tmp = join(tmpdir(), 'test-histra-materials-' + Date.now() + '-' + Math.random().toString(36).slice(2));
await mkdir(tmp, { recursive: true });

const threeHref = new URL('../node_modules/three/build/three.module.js', import.meta.url).href;
const orbitHref = new URL('../node_modules/three/examples/jsm/controls/OrbitControls.js', import.meta.url).href;

const staticDir = new URL('../static/', import.meta.url);
const files = await readdir(staticDir);
for (const file of files) {
  if (file.endsWith('.js')) {
    let content = await readFile(new URL(file, staticDir), 'utf8');
    content = content.replace(/from 'three'/g, `from '${threeHref}'`);
    content = content.replace(/from '\/vendor\/OrbitControls\.js'/g, `from '${orbitHref}'`);
    await writeFile(join(tmp, file), content);
  }
}

const { ResultsPage } = await import('file://' + join(tmp, 'results.js'));
await rm(tmp, { recursive: true, force: true });

class MockElement {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this._classListSet = new Set();
    const set = this._classListSet;
    this.classList = {
      add: cls => set.add(cls),
      remove: cls => set.delete(cls),
      toggle: (cls, force) => {
        if (force === undefined) {
          if (set.has(cls)) set.delete(cls);
          else set.add(cls);
        } else if (force) {
          set.add(cls);
        } else {
          set.delete(cls);
        }
        return set.has(cls);
      },
      contains: cls => set.has(cls),
    };
    this.attributes = {};
    this.textContent = '';
    this.value = '';
    this.style = {};
    this.disabled = false;
  }
  get className() {
    return Array.from(this._classListSet).join(' ');
  }
  set className(val) {
    this._classListSet.clear();
    for (const c of String(val).split(/\s+/).filter(Boolean)) {
      this._classListSet.add(c);
    }
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = [...items]; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
}

function createMockPage() {
  const page = Object.create(ResultsPage.prototype);
  page.hiddenMaterials = new Set();
  page.data = {
    mesh: {
      materials: [
        { key: '1', name: 'Arch masonry', color: '#e06666' },
        { key: '2', name: 'Piers', color: '#6fa8dc' },
        { key: '3', name: 'Unassigned soil', color: '#93c47d' },
      ],
      quads: [
        { key: 10, materialKey: '1', nodeKeys: [1, 2, 3, 4] },
        { key: 11, materialKey: '1', nodeKeys: [2, 5, 6, 3] },
        { key: 12, materialKey: '1', nodeKeys: [5, 7, 8, 6] },
        { key: 20, materialKey: '2', nodeKeys: [9, 10, 11, 12] },
        { key: 21, materialKey: '2', nodeKeys: [10, 13, 14, 11] },
        { key: 30, materialKey: '4', nodeKeys: [15, 16, 17, 18] },
      ],
      nodes: [
        { key: '1', point: [0, 0, 0] },
      ],
    },
  };
  page.viewer = {
    visibleQuad: () => true,
    options: { thicknessScale: 1 },
    state: {
      quads: page.data.mesh.quads.map(q => ({
        ...q,
        material: String(q.materialKey),
        normal: new Vector3(0, 0, 1),
        normals: [new Vector3(0, 0, 1), new Vector3(0, 0, 1), new Vector3(0, 0, 1), new Vector3(0, 0, 1)],
        thicknesses: [10, 10, 10, 10],
      })),
      nodes: new Map(),
    },
    rebuild: () => {},
    needsRender: false,
  };
  page.baseNodes = new Map();
  for (let i = 1; i <= 20; i++) page.baseNodes.set(i, new Vector3(i * 10, 0, 0));
  page.baseNormals = page.viewer.state.quads.map(() => ({
    normal: new Vector3(0, 0, 1),
    normals: [new Vector3(0, 0, 1), new Vector3(0, 0, 1), new Vector3(0, 0, 1), new Vector3(0, 0, 1)],
  }));
  page.ghostGeometries = {};
  page.elements = {
    resultMaterialsGroup: new MockElement('div'),
    resultMaterialsTitle: new MockElement('span'),
    resultMaterialsCount: new MockElement('span'),
    resultMaterialSearch: new MockElement('input'),
    resultMaterialsList: new MockElement('div'),
    resultResetMaterials: new MockElement('button'),
    resultExtrude: { checked: true },
    thrustFilter: { value: 'all' },
  };
  page.$ = id => page.elements[id] || null;
  page.draw = () => { page.drawCalled = (page.drawCalled || 0) + 1; };
  return page;
}

test('getMaterialsList extracts defined materials, computes quad counts, and recovers unlisted keys', () => {
  const page = createMockPage();
  const list = page.getMaterialsList();
  assert.equal(list.length, 4);

  const arch = list.find(m => m.key === '1');
  assert.ok(arch);
  assert.equal(arch.name, 'Arch masonry');
  assert.equal(arch.color, '#e06666');
  assert.equal(arch.quadCount, 3);

  const piers = list.find(m => m.key === '2');
  assert.ok(piers);
  assert.equal(piers.name, 'Piers');
  assert.equal(piers.quadCount, 2);

  const unassigned = list.find(m => m.key === '3');
  assert.ok(unassigned);
  assert.equal(unassigned.name, 'Unassigned soil');
  assert.equal(unassigned.quadCount, 0);

  const extra = list.find(m => m.key === '4');
  assert.ok(extra);
  assert.equal(extra.name, 'Material 4');
  assert.equal(extra.quadCount, 1);
});

test('toggleMaterial toggles single material visibility and updates viewer.visibleQuad', () => {
  const page = createMockPage();
  page.renderMaterialsList = () => {};
  page.buildGhostGeometries = () => {};

  page.toggleMaterial('1');
  assert.ok(page.hiddenMaterials.has('1'));
  assert.equal(page.viewer.visibleQuad({ material: '1' }), false);
  assert.equal(page.viewer.visibleQuad({ material: '2' }), true);
  assert.equal(page.viewer.visibleQuad({ material: '4' }), true);
  assert.equal(page.drawCalled, 1);

  page.toggleMaterial('1');
  assert.ok(!page.hiddenMaterials.has('1'));
  assert.equal(page.viewer.visibleQuad({ material: '1' }), true);
  assert.equal(page.drawCalled, 2);
});

test('toggleMaterial with altKey isolates a material and restores when re-triggered', () => {
  const page = createMockPage();
  page.renderMaterialsList = () => {};
  page.buildGhostGeometries = () => {};

  // Alt-click material '2': isolate '2' (hide '1', '3', '4')
  page.toggleMaterial('2', true);
  assert.ok(!page.hiddenMaterials.has('2'));
  assert.ok(page.hiddenMaterials.has('1'));
  assert.ok(page.hiddenMaterials.has('3'));
  assert.ok(page.hiddenMaterials.has('4'));
  assert.equal(page.viewer.visibleQuad({ material: '2' }), true);
  assert.equal(page.viewer.visibleQuad({ material: '1' }), false);

  // Alt-click material '2' again: already isolated, so restore all
  page.toggleMaterial('2', true);
  assert.equal(page.hiddenMaterials.size, 0);
  assert.equal(page.viewer.visibleQuad({ material: '1' }), true);
  assert.equal(page.viewer.visibleQuad({ material: '2' }), true);
  assert.equal(page.viewer.visibleQuad({ material: '4' }), true);
});

test('resetMaterials restores all materials and resets visibleQuad', () => {
  const page = createMockPage();
  page.renderMaterialsList = () => {};
  page.buildGhostGeometries = () => {};

  page.hiddenMaterials.add('1');
  page.hiddenMaterials.add('2');
  page.resetMaterials();

  assert.equal(page.hiddenMaterials.size, 0);
  assert.equal(page.viewer.visibleQuad({ material: '1' }), true);
  assert.equal(page.viewer.visibleQuad({ material: '2' }), true);
});

test('renderMaterialsList constructs UI items with swatches, counts, and toggle buttons', () => {
  const oldDoc = globalThis.document;
  globalThis.document = {
    createElement: tag => new MockElement(tag),
  };
  try {
    const page = createMockPage();
    page.buildGhostGeometries = () => {};

    page.renderMaterialsList();
    const listEl = page.$('resultMaterialsList');
    assert.equal(listEl.children.length, 4);
    assert.equal(page.$('resultMaterialsCount').textContent, '4');
    assert.ok(page.$('resultResetMaterials').classList.contains('hidden'));

    // Check row structure for first item
    const firstRow = listEl.children[0];
    assert.ok(!firstRow.classList.contains('hidden-entity'));
    const inspectBtn = firstRow.children.find(c => c.classList.contains('inspect-button'));
    assert.ok(inspectBtn);
    const swatch = inspectBtn.children.find(c => c.classList.contains('swatch'));
    assert.equal(swatch.style.background, '#e06666');
    const nameEl = inspectBtn.children[1].children.find(c => c.classList.contains('entity-name'));
    assert.equal(nameEl.textContent, 'Arch masonry');
    const metaEl = inspectBtn.children[1].children.find(c => c.classList.contains('entity-meta'));
    assert.equal(metaEl.textContent, '3 quads · #1');

    const toggleBtn = firstRow.children.find(c => c.classList.contains('visibility'));
    assert.ok(toggleBtn);
    assert.equal(toggleBtn.textContent, '◉');

    // Now hide material '1' and re-render
    page.hiddenMaterials.add('1');
    page.renderMaterialsList();
    assert.ok(listEl.children[0].classList.contains('hidden-entity'));
    assert.equal(listEl.children[0].children.find(c => c.classList.contains('visibility')).textContent, '○');
    assert.equal(page.$('resultMaterialsCount').textContent, '3/4');
    assert.ok(!page.$('resultResetMaterials').classList.contains('hidden'));

    // Test search filter
    page.$('resultMaterialSearch').value = 'Piers';
    page.renderMaterialsList();
    assert.equal(listEl.children.length, 1);
    assert.equal(listEl.children[0].children[0].children[1].children[0].textContent, 'Piers');
  } finally {
    globalThis.document = oldDoc;
  }
});

test('buildGhostGeometries excludes edges of hidden materials', () => {
  const page = createMockPage();
  page.viewer.visibleQuad = q => !page.hiddenMaterials.has(String(q.material));

  page.buildGhostGeometries();
  assert.ok(page.ghostGeometries.true instanceof BufferGeometry);
  const fullExtrudedCount = page.ghostGeometries.true.getAttribute('position').count;
  assert.ok(fullExtrudedCount > 0);

  // Hide material '1' (3 quads out of 6)
  page.hiddenMaterials.add('1');
  page.buildGhostGeometries();
  const filteredExtrudedCount = page.ghostGeometries.true.getAttribute('position').count;
  assert.ok(filteredExtrudedCount < fullExtrudedCount);
  assert.equal(filteredExtrudedCount, fullExtrudedCount / 2);
});
