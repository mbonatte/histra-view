import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decodeContours, contourGroups, stressColor } from '../static/stress-data.js';

const pack = values => { const b = Buffer.alloc(values.length * 4); values.forEach((v,i) => b.writeFloatLE(v,i*4)); return b.toString('base64'); };
const fixture = () => ({ encoding:'base64-little-endian', stressUnit:'MPa', cellCount:2,
  positions:pack([0,0,0,1,0,0,1,1,0,0,1,0, 2,0,0,3,0,0,3,1,0,2,1,0]),
  stress:pack([-2,1]), force:pack([-4,2]), area:pack([20,20]), displacement:pack([-.01,.02]),
  phase:Buffer.from([0,1]).toString('base64'), phaseNames:['Elastic','Plastic_t'],
  groups:[{key:813,start:0,count:1,nrow:1,ncol:1,restrained:true},{key:1,start:1,count:1,nrow:1,ncol:1,restrained:false}] });

test('little-endian contour data preserves signed MPa and cell coordinates', () => {
  const data=decodeContours(fixture());
  assert.deepEqual([...data.stress],[-2,1]); assert.deepEqual([...data.positions.slice(12,15)],[2,0,0]);
  assert.deepEqual([...data.strain].map(v => Math.round(v * 100) / 100),[-.01,.02]);
  assert.deepEqual(contourGroups(data,'supports',1).map(g=>g.key),[813]);
  assert.deepEqual(contourGroups(data,'all',1).map(g=>g.key),[813,1]);
  assert.deepEqual(contourGroups(data,'selected',1).map(g=>g.key),[1]);
});
test('optional sliding stress and phase arrays decode with the same cell mapping', () => {
  const f = fixture();
  f.slidingStress = pack([.5, .7]);
  f.slidingOutOfPlaneStress = pack([.1, .2]);
  f.slidingPhase = Buffer.from([0, 1]).toString('base64');
  f.slidingOutOfPlanePhase = Buffer.from([1, 0]).toString('base64');
  const data = decodeContours(f);
  assert.ok(Math.abs(data.slidingStress[0] - .5) < 1e-6);
  assert.ok(Math.abs(data.slidingStress[1] - .7) < 1e-6);
  assert.ok(Math.abs(data.slidingOutOfPlaneStress[0] - .1) < 1e-6);
  assert.ok(Math.abs(data.slidingOutOfPlaneStress[1] - .2) < 1e-6);
  assert.deepEqual([...data.slidingPhase], [0, 1]);
  assert.deepEqual([...data.slidingOutOfPlanePhase], [1, 0]);
  const bad = fixture();
  bad.slidingStress = pack([.5]);
  assert.throws(() => decodeContours(bad), /sizes/);
});

test('rejects invalid lengths, nonfinite values and ambiguous interface mappings', () => {
  for (const mutate of [f=>f.positions=pack([0]), f=>f.stress=pack([NaN,1]), f=>f.groups[1].start=0, f=>f.groups[1].key=813, f=>f.phase=Buffer.from([0,9]).toString('base64')]) {
    const f=fixture();mutate(f);assert.throws(()=>decodeContours(f));
  }
});
test('shared symmetric color scale distinguishes compression, zero and tension', () => {
  assert.deepEqual(stressColor(0,2),[.9,.92,.94]);
  const negative=stressColor(-2,2), positive=stressColor(2,2);
  assert.ok(negative[2]>negative[0]); assert.ok(positive[0]>positive[2]);
  assert.deepEqual(stressColor(-20,2),negative);
  assert.ok(stressColor(-1,2)[0]>negative[0], 'half the compression is nearer neutral on the shared scale');

  // Custom min and max ranges
  assert.deepEqual(stressColor(0, -10, 5), [.9, .92, .94]);
  const fullBlue = stressColor(-10, -10, 5);
  const fullRed = stressColor(5, -10, 5);
  assert.deepEqual(stressColor(-15, -10, 5), fullBlue);
  assert.deepEqual(stressColor(10, -10, 5), fullRed);
  assert.ok(fullBlue[2] > fullBlue[0]);
  assert.ok(fullRed[0] > fullRed[2]);
});

test('bridge-scale color range does not spread half a million arguments', async () => {
  const {maximumMagnitude, phaseColors}=await import('../static/stress-data.js');
  const values=new Float32Array(549666);values[500000]=-8.5;
  assert.equal(maximumMagnitude(values),8.5);
  assert.ok(phaseColors.RuptureTraz);
});
