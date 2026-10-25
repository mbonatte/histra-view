import assert from 'node:assert/strict';
import { test } from 'node:test';
import { convertedValue, dimension, unitFor } from '../static/material-units.js';

test('C# kN/cm² stiffness and strength convert to MPa', () => {
  assert.equal(convertedValue('1620', 'Ehor'), '16200');
  assert.equal(convertedValue('2.68', 'FmHor'), '26.8');
  assert.equal(convertedValue('2.68', 'FmHor', 'si'), '26800');
  assert.equal(unitFor('FmHor'), 'MPa');
});
test('specific weight and fracture energy have different dimensional conversions', () => {
  assert.equal(convertedValue('2.24E-05', 'w'), '22.4');
  assert.equal(unitFor('w'), 'kN/m³');
  assert.equal(convertedValue('0.0002', 'Gt'), '0.02');
  assert.equal(unitFor('Gt'), 'N/mm');
  assert.equal(dimension('FractureEnergyShear'), 'stress');
});
test('ratios, missing values, sentinels, and the native representation are preserved', () => {
  assert.equal(convertedValue('0.5', 'FrictionRatioShear'), '0.5');
  assert.equal(convertedValue('—', 'Gd'), '—');
  assert.equal(convertedValue('-1', 'Gc'), '-1');
  assert.equal(convertedValue('2.2400E-05', 'w', 'native'), '2.2400E-05');
});
