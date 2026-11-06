import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile, writeFile, mkdir, rm, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { curveSeries, modelPointSeries, nodeDisplacementSeries } from '../static/result-charts.js';

const tmp = join(tmpdir(), 'test-histra-history-' + Date.now() + '-' + Math.random().toString(36).slice(2));
await mkdir(tmp, { recursive: true });

const threeHref = new URL('../node_modules/three/build/three.module.js', import.meta.url).href;
const orbitHref = new URL('../node_modules/three/examples/jsm/controls/OrbitControls.js', import.meta.url).href;

const staticDir = new URL('../static/', import.meta.url);
const files = await readdir(staticDir);
for (const file of files) {
  if (file.endsWith('.js')) {
    let content = await readFile(new URL(file, staticDir), 'utf8');
    content = content.replace(/from 'three'/g, `from '${threeHref}'`);
    content = content.replace(/from '\/vendor\/OrbitControls\.js'/g, `from '${orbitHref}'`);
    await writeFile(join(tmp, file), content);
  }
}

const { ResultsPage } = await import('file://' + join(tmp, 'results.js'));
await rm(tmp, { recursive: true, force: true });

test('resolveAnalysisChain traces predecessor analyses via initialAnalysisKey', () => {
  const dummyResults = Object.create(ResultsPage.prototype);
  dummyResults.data = {
    analysisCatalog: [
      { key: 1, name: 'Vert', initialAnalysisKey: -100 },
      { key: 23, name: 'scour_1', initialAnalysisKey: 1 },
      { key: 22, name: 'LiveLoad_1', initialAnalysisKey: 23 },
      { key: 99, name: 'Modal_1', initialAnalysisKey: -100 },
    ],
  };

  assert.deepEqual(dummyResults.resolveAnalysisChain('Vert'), ['Vert']);
  assert.deepEqual(dummyResults.resolveAnalysisChain('scour_1'), ['Vert', 'scour_1']);
  assert.deepEqual(dummyResults.resolveAnalysisChain('LiveLoad_1'), ['Vert', 'scour_1', 'LiveLoad_1']);
  assert.deepEqual(dummyResults.resolveAnalysisChain('__all__'), ['Vert', 'scour_1', 'LiveLoad_1']);
});

test('buildChainedAnalysis concatenates steps and builds chainStages metadata', () => {
  const dummyResults = Object.create(ResultsPage.prototype);

  const stage1 = {
    name: 'Vert',
    key: 1,
    steps: [
      { step: 0, controlDisplacement: 0, appliedVerticalForce: 0, displacements: [[0, 0, 0], [0, 0, -0.1]] },
      { step: 1, controlDisplacement: 0.2, appliedVerticalForce: 50, displacements: [[0, 0, 0], [0.01, 0, -0.2]] },
    ],
    interfaces: [{ key: 10, forces: [0, -100, 0], restrained: true }],
    modelPoints: {
      step: [0, 1],
      points: [
        { key: 5, name: 'Crown', available: true, displacement_cm: { ux: [0, 0.01], uy: [0, 0], uz: [0, -0.2] } }
      ]
    }
  };

  const stage2 = {
    name: 'LiveLoad_1',
    key: 22,
    steps: [
      { step: 0, controlDisplacement: 0.2, appliedVerticalForce: 50, displacements: [[0, 0, 0], [0.01, 0, -0.2]] },
      { step: 1, controlDisplacement: 0.5, appliedVerticalForce: 120, displacements: [[0.02, 0, 0.01], [0.05, 0, -0.6]] },
      { step: 2, controlDisplacement: 0.9, appliedVerticalForce: 180, displacements: [[0.04, 0, 0.02], [0.09, 0, -1.1]] },
    ],
    interfaces: [{ key: 10, forces: [0, -180, 0], restrained: true }],
    modelPoints: {
      step: [0, 1, 2],
      points: [
        { key: 5, name: 'Crown', available: true, displacement_cm: { ux: [0.01, 0.05, 0.09], uy: [0, 0, 0], uz: [-0.2, -0.6, -1.1] } }
      ]
    }
  };

  const chained = dummyResults.buildChainedAnalysis([stage1, stage2]);
  assert.equal(chained.isChain, true);
  assert.equal(chained.chainStages.length, 2);
  assert.deepEqual(chained.chainStages[0], { name: 'Vert', key: 1, stepCount: 2, startIndex: 0, endIndex: 1 });
  assert.deepEqual(chained.chainStages[1], { name: 'LiveLoad_1', key: 22, stepCount: 3, startIndex: 2, endIndex: 4 });

  assert.equal(chained.steps.length, 5);
  assert.equal(chained.steps[0].cumulativeStep, 0);
  assert.equal(chained.steps[0].stageStep, 0);
  assert.equal(chained.steps[0].analysisName, 'Vert');

  assert.equal(chained.steps[2].cumulativeStep, 2);
  assert.equal(chained.steps[2].stageStep, 0);
  assert.equal(chained.steps[2].analysisName, 'LiveLoad_1');

  assert.equal(chained.steps[4].cumulativeStep, 4);
  assert.equal(chained.steps[4].stageStep, 2);
  assert.equal(chained.steps[4].analysisName, 'LiveLoad_1');

  // Verify merged model points
  assert.equal(chained.modelPoints.points.length, 1);
  const mp = chained.modelPoints.points[0];
  assert.equal(mp.key, 5);
  assert.deepEqual(mp.displacement_cm.uz, [0, -0.2, -0.2, -0.6, -1.1]);
});

test('nodeDisplacementSeries extracts Ux, Uy, Uz across chained steps for selected node', () => {
  const mesh = {
    nodes: [
      { key: 101, point: [0, 0, 0] },
      { key: 202, point: [100, 0, 50] },
    ]
  };

  const chained = {
    name: 'Chained',
    steps: [
      { cumulativeStep: 0, stageStep: 0, analysisName: 'Vert', controlDisplacement: 0, displacements: [[0, 0, 0], [0.1, -0.2, -0.3]] },
      { cumulativeStep: 1, stageStep: 1, analysisName: 'Vert', controlDisplacement: 0.5, displacements: [[0, 0, 0], [0.2, -0.4, -0.7]] },
      { cumulativeStep: 2, stageStep: 0, analysisName: 'Live', controlDisplacement: 0.5, displacements: [[0, 0, 0], [0.2, -0.4, -0.7]] },
      { cumulativeStep: 3, stageStep: 1, analysisName: 'Live', controlDisplacement: 1.2, displacements: [[0, 0, 0], [0.5, -0.9, -1.5]] },
    ]
  };

  const series = nodeDisplacementSeries(chained, 202, mesh, 'step');
  assert.equal(series.length, 3);
  assert.equal(series[0].name, 'Ux');
  assert.equal(series[1].name, 'Uy');
  assert.equal(series[2].name, 'Uz');

  assert.deepEqual(series[0].points.map(p => [p.x, p.y, p.cumulativeStep, p.analysisName]), [
    [0, 0.1, 0, 'Vert'],
    [1, 0.2, 1, 'Vert'],
    [2, 0.2, 2, 'Live'],
    [3, 0.5, 3, 'Live'],
  ]);

  assert.deepEqual(series[2].points.map(p => p.y), [-0.3, -0.7, -0.7, -1.5]);

  // Non-existent node key returns empty series
  assert.deepEqual(nodeDisplacementSeries(chained, 999, mesh), []);
});
