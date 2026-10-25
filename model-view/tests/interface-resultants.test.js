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
