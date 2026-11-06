import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createViewSettings, applyViewerSettings, viewSettingsMarkup } from '../static/view-settings.js';

test('shared settings notify all views and retain values for later viewers', () => {
  const settings = createViewSettings();
  const seen = [];
  const unsubscribe = settings.subscribe((state, changed) => seen.push({ state, changed }));
  settings.set({ edges: false, extrude: false });
  settings.set({ edges: false });
  assert.equal(seen.length, 1);
  assert.deepEqual(seen[0].changed, { edges: false, extrude: false });
  const viewer = { grid: {}, setOptions(options, config) { this.options = options; this.config = config; } };
  applyViewerSettings(viewer, settings.get(), { rebuild: false });
  assert.equal(viewer.options.edges, false);
  assert.equal(viewer.options.extrude, false);
  assert.equal(viewer.grid.visible, true);
  unsubscribe();
  settings.set({ edges: true });
  assert.equal(seen.length, 1);
});

test('both panels are generated from the same settings with unique IDs', () => {
  const model = viewSettingsMarkup();
  const result = viewSettingsMarkup('result', { result: true });
  for (const name of ['Edges', 'Nodes', 'Extrude', 'ModelPoints', 'ColorBy']) {
    assert.ok(result.includes(`id="result${name}"`));
    assert.ok(model.includes(`id="${name[0].toLowerCase()}${name.slice(1)}"`));
  }
  assert.ok(result.includes('Restraints (Build / View only)'));
});
