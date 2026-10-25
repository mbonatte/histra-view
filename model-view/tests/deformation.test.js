import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decodeQuadDisplacements, deformedPoints, deformedQuadPoints, displacementColormap, computeDisplacementContours, computeScalarContours, csharpStressColormap } from '../static/deformation.js';

test('step/scale changes are relative to the immutable undeformed geometry', () => {
  const nodes = [{ point: [10, 20, 30] }, { point: [0, -2, 1] }];
  const original = structuredClone(nodes);
  const u = [[1, -2, 0.5], [0, 0, -1]];
  assert.deepEqual(deformedPoints(nodes, u, 10), [[20, 0, 35], [0, -2, -9]]);
  assert.deepEqual(deformedPoints(nodes, u, 1), [[11, 18, 30.5], [0, -2, 0]]);
  assert.deepEqual(deformedPoints(nodes, u, 0), nodes.map(n => n.point));
  assert.deepEqual(nodes, original);
});

test('independent quad vertex displacements allow adjacent quads sharing a node to separate', () => {
  // Two quads sharing the vertical edge from (10, 0, 0) to (10, 0, 10)
  const baseQuadPoints = [
    [[0, 0, 0], [10, 0, 0], [10, 0, 10], [0, 0, 10]],
    [[10, 0, 0], [20, 0, 0], [20, 0, 10], [10, 0, 10]],
  ];
  // Quad 0 stays fixed; Quad 1 translates +2 in X and slides +1 in Z
  const raw = new Float32Array([
    0, 0, 0,  0, 0, 0,  0, 0, 0,  0, 0, 0,
    2, 0, 1,  2, 0, 1,  2, 0, 1,  2, 0, 1,
  ]);
  const b64 = Buffer.from(raw.buffer).toString('base64');
  const decoded = decodeQuadDisplacements(b64, 2);
  assert.deepEqual(Array.from(decoded), Array.from(raw));

  const deformed = deformedQuadPoints(baseQuadPoints, b64, 5);
  // Shared bottom corner: Quad 0 corner 1 stays at [10, 0, 0], Quad 1 corner 0 moves to [20, 0, 5]
  assert.deepEqual(deformed[0][1], [10, 0, 0]);
  assert.deepEqual(deformed[1][0], [20, 0, 5]);
});

test('mismatched, nonfinite, and negative deformation inputs are rejected', () => {
  const nodes = [{ point: [0, 0, 0] }];
  assert.throws(() => deformedPoints(nodes, [], 1));
  assert.throws(() => deformedPoints(nodes, [[NaN, 0, 0]], 1));
  assert.throws(() => deformedPoints(nodes, [[0, 0, 0]], -1));
  assert.throws(() => deformedPoints(nodes, [[0, 0, 0]], Infinity));
  assert.throws(() => decodeQuadDisplacements('AAAA', 1));
  assert.throws(() => deformedQuadPoints([[[0,0,0],[1,0,0],[1,1,0],[0,1,0]]], new Float32Array(12), -1));
});

test('displacementColormap produces valid RGB across 0 to 1 range', () => {
  const blue = displacementColormap(0);
  assert.equal(blue[0], 0.10);
  assert.equal(blue[2], 0.85);

  const red = displacementColormap(1);
  assert.equal(red[0], 0.90);
  assert.equal(red[2], 0.10);

  const mid = displacementColormap(0.5);
  assert.ok(mid[1] > 0.8, 'Middle stop should be predominantly green');
});

test('computeDisplacementContours computes component ranges and per-quad colors', () => {
  const quads = [
    { nodeKeys: ['1', '2', '3', '4'] },
    { nodeKeys: ['2', '5', '6', '3'] },
  ];
  const nodeKeyToIndex = new Map([
    ['1', 0], ['2', 1], ['3', 2], ['4', 3], ['5', 4], ['6', 5]
  ]);
  // Displacements in cm: node 1 fixed, node 2 moves in X by 0.2 cm (2 mm), node 5 settles in Z by -0.5 cm (-5 mm)
  const nodeDisplacements = [
    [0, 0, 0],
    [0.2, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, -0.5],
    [0, 0, -0.5]
  ];

  // Test Z component
  const resZ = computeDisplacementContours({
    quads,
    nodeKeyToIndex,
    nodeDisplacements,
    component: 'z'
  });
  assert.equal(resZ.min, -5); // -0.5 cm = -5 mm
  assert.equal(resZ.max, 0);  // 0 mm
  assert.equal(resZ.quadColors.length, 2);
  assert.equal(resZ.quadColors[0].length, 4);

  // Test Magnitude component
  const resMag = computeDisplacementContours({
    quads,
    nodeKeyToIndex,
    nodeDisplacements,
    component: 'magnitude'
  });
  assert.equal(resMag.min, 0);
  assert.equal(resMag.max, 5); // sqrt(0^2 + 0^2 + (-0.5)^2) * 10 = 5 mm

  // Test X component
  const resX = computeDisplacementContours({
    quads,
    nodeKeyToIndex,
    nodeDisplacements,
    component: 'x'
  });
  assert.equal(resX.min, 0);
  assert.equal(resX.max, 2); // 0.2 cm * 10 = 2 mm
});

test('computeScalarContours maps per-corner Von Mises values to Quad colours', () => {
  const quads = [{ nodeKeys: [1, 2, 3, 4] }, { nodeKeys: [4, 3, 5, 6] }];
  const res = computeScalarContours({
    quads,
    values: [0, 1, 2, 3, 4, 5, 6, 7],
    min: 0,
    max: 8
  });
  assert.equal(res.min, 0);
  assert.equal(res.max, 8);
  assert.equal(res.quadColors.length, 2);
  assert.equal(res.quadColors[0].length, 4);
  assert.notDeepEqual(res.quadColors[0][0], res.quadColors[1][3]);
  assert.throws(() => computeScalarContours({ quads, values: [0, 1], min: 0, max: 1 }), /four corners/);
});

test('C# Von Mises palette runs dark blue -> lime -> red', () => {
  assert.deepEqual(csharpStressColormap(0), [0, 0, 0.55]);
  assert.deepEqual(csharpStressColormap(0.5), [0, 1, 0]);
  assert.deepEqual(csharpStressColormap(1), [1, 0, 0]);
});

