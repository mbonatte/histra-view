import assert from 'node:assert/strict';
import { test } from 'node:test';
import { curveSeries } from '../static/result-charts.js';

const analysis = { steps: [
  {step:0, controlDisplacement:1, appliedVerticalForce:0, loadFactor:0, reactions:[1,2,3], elasticEnergy:null, dissipatedEnergy:null},
  {step:1, controlDisplacement:2, appliedVerticalForce:10, loadFactor:20, reactions:[4,5,6], elasticEnergy:-2, dissipatedEnergy:3},
  {step:2, controlDisplacement:1.5, appliedVerticalForce:8, loadFactor:16, reactions:[7,8,9], elasticEnergy:-3, dissipatedEnergy:4},
] };
test('force curve uses physical force and preserves the saved nonmonotonic path', () => {
  assert.deepEqual(curveSeries(analysis, 'force')[0].points.map(p => [p.x,p.y]), [[1,0],[2,10],[1.5,8]]);
  assert.deepEqual(curveSeries(analysis, 'load', 'step')[0].points.map(p => [p.x,p.y]), [[0,0],[1,20],[2,16]]);
});
test('reaction signs are preserved and missing energies do not become zeros', () => {
  assert.equal(curveSeries(analysis, 'reactions').length, 3);
  assert.deepEqual(curveSeries(analysis, 'energy')[0].points.map(p => p.y), [-2,-3]);
  assert.deepEqual(curveSeries(analysis, 'energy')[1].points.map(p => p.index), [1,2]);
});

test('model point curves use saved point histories and align them to saved steps', async () => {
  const { modelPointSeries } = await import('../static/result-charts.js');
  const a = { ...analysis, modelPoints: { step: [0, 2, 9], points: [{key: 7, available: true, displacement_cm: {ux:[0,1,9], uy:[2,3,9], uz:[4,5,9]}}] } };
  assert.deepEqual(modelPointSeries(a, 7)[0].points.map(p => [p.x,p.y,p.index]), [[0,0,0],[2,1,2]]);
  assert.deepEqual(modelPointSeries(a, 7, 'displacement')[1].points.map(p => [p.x,p.y]), [[1,2],[1.5,3]]);
  assert.deepEqual(modelPointSeries(a, 8), []);
});
