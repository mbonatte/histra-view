import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const source = (await readFile(new URL('../static/export-image.js', import.meta.url), 'utf8'))
  .replace("from 'three'", `from '${new URL('../node_modules/three/build/three.module.js', import.meta.url).href}'`);
const { exportDimensions, sanitizeFilename } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('exportDimensions scales the canvas and clamps oversized exports', () => {
  assert.deepEqual(exportDimensions(800, 600, 3), { width: 2400, height: 1800, scale: 3 });
  const huge = exportDimensions(4000, 3000, 4, 8192);
  assert.equal(huge.width, 8192);
  assert.equal(huge.height, 6144);
  assert.ok(huge.scale <= 2.0481);
});

test('sanitizeFilename keeps report-safe characters', () => {
  assert.equal(sanitizeFilename('Pushover_Span2_Quarter · step 45'), 'Pushover_Span2_Quarter-step-45');
  assert.equal(sanitizeFilename(''), 'view');
});
