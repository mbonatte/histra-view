import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resultFieldStepIndex } from '../static/result-field-policy.js';

test('final-only maps use the final step; native C# maps retain the selected step', () => {
  assert.equal(resultFieldStepIndex(0, 11, true, false), 10);
  assert.equal(resultFieldStepIndex(0, 11, true, true), 0);
  assert.equal(resultFieldStepIndex(0, 11, false, false), 0);
});
