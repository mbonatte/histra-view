import assert from 'node:assert/strict';
import { test } from 'node:test';
import { displayValue, rockingGroups, slidingGroups, curveImage, slidingImage } from '../static/material-properties.js';

test('serialized zero, precision, missing values, and sentinels remain distinguishable', () => {
  assert.equal(displayValue({ Gd: '0' }, 'Gd'), '0');
  assert.equal(displayValue({ Gd: '0.00001000' }, 'Gd'), '0.00001000');
  assert.equal(displayValue({}, 'Gd'), '—');
  assert.equal(displayValue({ Gd: '-1' }, 'Gd'), '-1');
});

test('ductility infinity follows the inverted IsDuct flags in C# InitAdvancedMode', () => {
  assert.equal(displayValue({ IsDuctCompr: 'false', DuctComprRockingHor: '1.5' }, 'DuctComprRockingHor'), '∞');
  assert.equal(displayValue({ IsDuctCompr: 'true', DuctComprRockingHor: '1.5' }, 'DuctComprRockingHor'), '1.5');
  assert.equal(displayValue({ IsDuctTraz: 'false' }, 'DuctTrazRockingHor'), '—');
});

test('directional fields map to the distinct C# horizontal, vertical, and direction 3 properties', () => {
  const rocking = rockingGroups.flatMap(([, rows]) => rows);
  assert.deepEqual(rocking.find(([label]) => label === 'Fracture energy, Gt'), ['Fracture energy, Gt', 'Gt', 'GtVer']);
  const sliding = slidingGroups.flatMap(([, rows]) => rows);
  assert.deepEqual(sliding.find(([label]) => label === 'Plastic stiffness ratio'),
    ['Plastic stiffness ratio', 'SlidingPlasticStiffnessRatioHor', 'SlidingPlasticStiffnessRatioVer', 'SlidingPlasticStiffnessRatioDir3']);
});

test('reference images match constitutive choices and unknown choices have no guessed curve', () => {
  assert.equal(curveImage('compressive', 'Parabolic'), 'compressive_parabolic.png');
  assert.equal(curveImage('tensile', 'Unknown'), null);
  assert.equal(slidingImage({ scorrhor: 'false' }), 'shear_elastic.png');
  assert.equal(slidingImage({ scorrhor: 'true', SlidingFractureEnergy: 'true' }), 'sliding_linear_softening.png');
});
