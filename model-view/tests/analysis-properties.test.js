import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  formatStartFrom,
  formatControlPoint,
  formatDirectionSummary,
  decomposeIterativeMethod,
  formatArcLengthRay,
  formatExitDescription,
  formatDiscretizationMode,
} from '../static/analysis-properties.js';

test('formatStartFrom replicates C# Zero sentinel for -100 and names linked analyses', () => {
  assert.equal(formatStartFrom({ initialAnalysisKey: '-100', initialAnalysisName: '' }), 'Zero');
  assert.equal(formatStartFrom({ initialAnalysisKey: '1', initialAnalysisName: 'Vert' }), 'Vert (#1)');
  assert.equal(formatStartFrom({ initialAnalysisKey: '99', initialAnalysisName: '' }), 'Zero (#99)');
});

test('formatControlPoint handles -10 MaxDisplacement sentinel and named model points', () => {
  assert.equal(formatControlPoint({ masterPoint: '-10', masterPointName: 'MaxDisplacement' }), 'MaxDisplacement (-10)');
  assert.equal(formatControlPoint({ masterPoint: '3', masterPointName: 'Span1_Half' }), 'Span1_Half (#3)');
});

test('formatDirectionSummary matches C# GetDirectionAsString for principal axes and vectors', () => {
  assert.equal(formatDirectionSummary({ DirX: '1', DirY: '0', DirZ: '0' }), '+X');
  assert.equal(formatDirectionSummary({ DirX: '-1', DirY: '0', DirZ: '0' }), '-X');
  assert.equal(formatDirectionSummary({ DirX: '0', DirY: '1', DirZ: '0' }), '+Y');
  assert.equal(formatDirectionSummary({ DirX: '0', DirY: '0', DirZ: '-1' }), '-Z');
  assert.equal(formatDirectionSummary({ DirX: '0.707', DirY: '0.707', DirZ: '0' }), '0.707, 0.707, 0');
});

test('decomposeIterativeMethod splits Newton-Raphson strategy and Line Search type like C# InitComboBoxIterationProcedure', () => {
  assert.deepEqual(decomposeIterativeMethod('StandardNewtonRaphson'), {
    raw: 'StandardNewtonRaphson',
    newtonType: 'Standard Newton-Raphson',
    lineSearch: 'No (false)',
    lineSearchType: 'None',
  });
  assert.deepEqual(decomposeIterativeMethod('StandardSecantLineSearch'), {
    raw: 'StandardSecantLineSearch',
    newtonType: 'Standard Newton-Raphson',
    lineSearch: 'Yes (true)',
    lineSearchType: 'Secant',
  });
  assert.deepEqual(decomposeIterativeMethod('ModifiedRegulaFalsiLineSearch'), {
    raw: 'ModifiedRegulaFalsiLineSearch',
    newtonType: 'Modified Newton-Raphson',
    lineSearch: 'Yes (true)',
    lineSearchType: 'Regula-Falsi',
  });
});

test('formatArcLengthRay computes dr = sqrt(Dr2) and preserves raw Dr2', () => {
  assert.equal(formatArcLengthRay('0.25'), '0.5 (Dr2 = 0.25)');
  assert.equal(formatArcLengthRay('0.010000001'), '0.1 (Dr2 = 0.010000001)');
  assert.equal(formatArcLengthRay(''), '—');
});

test('formatExitDescription converts @ separators into line breaks and formatDiscretizationMode labels typeDiscr', () => {
  assert.equal(formatExitDescription('Line 1@ > Line 2'), 'Line 1\n > Line 2');
  assert.equal(formatDiscretizationMode('false'), 'Discretization by pseudo-time (false)');
  assert.equal(formatDiscretizationMode('true'), 'Discretization by load multiplier (true)');
});
