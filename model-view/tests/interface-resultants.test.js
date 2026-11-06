import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resultantAt, normalTolerance, eccentricities, thrustPosition } from '../static/interface-resultants.js';

const analysis = { interfaceOrder: [100, 42], steps: [
  {interfaceResultants: [[0,0,0,0,0,0], [1,-10,2,20,3,-30]]},
  {interfaceResultants: [[0,1e-10,0,1,2,3], [1,-20,2,40,3,-60]]},
] };
test('interface IDs use the explicit ordering, retaining all moment signs', () => {
  assert.deepEqual(resultantAt(analysis, 0, 42), {forces:[1,-10,2], moments:[20,3,-30]});
  assert.equal(resultantAt(analysis, 0, 99), null);
});
test('eccentricities reject near-zero normal force and distinguish tension', () => {
  assert.equal(eccentricities(resultantAt(analysis, 0, 100), normalTolerance(analysis,100)), null);
  assert.equal(eccentricities(resultantAt(analysis, 1, 100), normalTolerance(analysis,100)), null);
  assert.deepEqual(eccentricities(resultantAt(analysis, 0, 42), 1e-8), {ex:3, ey:-2, compression:true});
  assert.equal(eccentricities({forces:[0,10,0], moments:[2,0,3]},1e-8).compression, false);
});
test('thrust position includes the half-length origin shift and native positive intrinsic Y', () => {
  const g = { length:22, reference_origin:[502,126,-119.6], reference_e1:[-1,0,0], reference_e3:[0,1,0] };
  assert.deepEqual(thrustPosition(g,{ex:3,ey:-2,compression:true}),[488,124,-119.6]);
  assert.equal(thrustPosition(g,{ex:3,ey:-2,compression:false}),null);
});

test('interface resultants stitch across multiple chained analysis stages', () => {
  const stage1 = {
    name: 'Vert',
    interfaceOrder: [42],
    steps: [
      { step: 0, interfaceResultants: [[0, -10, 0, 10, 0, -20]] },
      { step: 1, interfaceResultants: [[0, -20, 0, 20, 0, -40]] },
    ]
  };
  const stage2 = {
    name: 'LiveLoad',
    interfaceOrder: [42],
    steps: [
      { step: 0, interfaceResultants: [[0, -20, 0, 20, 0, -40]] },
      { step: 1, interfaceResultants: [[0, -50, 0, 60, 0, -120]] },
    ]
  };

  const stages = [stage1, stage2];
  const allResultants = [];
  stages.forEach(st => {
    st.steps.forEach((s, i) => {
      allResultants.push({
        analysis: st.name,
        step: s.step,
        r: resultantAt(st, i, 42)
      });
    });
  });

  assert.equal(allResultants.length, 4);
  assert.deepEqual(allResultants[0].r, { forces: [0, -10, 0], moments: [10, 0, -20] });
  assert.deepEqual(allResultants[1].r, { forces: [0, -20, 0], moments: [20, 0, -40] });
  assert.deepEqual(allResultants[2].r, { forces: [0, -20, 0], moments: [20, 0, -40] });
  assert.deepEqual(allResultants[3].r, { forces: [0, -50, 0], moments: [60, 0, -120] });

  // Eccentricities along history:
  const e1 = eccentricities(allResultants[1].r, 1e-8);
  const e3 = eccentricities(allResultants[3].r, 1e-8);
  assert.equal(e1.compression, true);
  assert.equal(e1.ex, 2);
  assert.equal(e1.ey, -1);
  assert.equal(e3.compression, true);
  assert.equal(e3.ex, 2.4);
  assert.equal(e3.ey, -1.2);
});
