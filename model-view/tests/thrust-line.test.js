import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildWidthGroups, computeInterfaceThrust, computeThrustLines } from '../static/thrust-line.js';

test('computeInterfaceThrust rejects tension and zero normal force', () => {
  const iface = { nodeKeys: ['1', '2'], length: 20 };
  const nodes = k => k === '1' ? [0, 0, 0] : [20, 0, 0];

  assert.equal(computeInterfaceThrust(iface, [0, 10, 0, 0, 0, 0], nodes), null, 'tensile N2 rejected');
  assert.equal(computeInterfaceThrust(iface, [0, 0, 0, 0, 0, 0], nodes), null, 'zero N2 rejected');
  assert.equal(computeInterfaceThrust(iface, [0, -1e-6, 0, 0, 0, 0], nodes), null, 'negligible N2 rejected');
});

test('computeInterfaceThrust places central thrust at midpoint and evaluates eccentricities', () => {
  const iface = { nodeKeys: ['1', '2'], length: 20 };
  const nodes = k => k === '1' ? [0, 10, 0] : [20, 10, 0];

  // Pure compression, zero moment -> center (10, 10, 0)
  const resCenter = computeInterfaceThrust(iface, [0, -100, 0, 0, 0, 0], nodes);
  assert.equal(resCenter.ex, -0);
  assert.equal(resCenter.eta, 0);
  assert.equal(resCenter.xi, 0.5);
  assert.deepEqual(resCenter.point, [10, 10, 0]);
  assert.equal(resCenter.isHinge, false);

  // Eccentricity towards node 2: Mz = -500, N2 = -100 => ex = +5 cm
  // L = 20 => eta = 2 * 5 / 20 = 0.5 => xi = 0.5 + 5/20 = 0.75
  const resEcc = computeInterfaceThrust(iface, [0, -100, 0, 0, 0, -500], nodes);
  assert.equal(resEcc.ex, 5);
  assert.equal(resEcc.eta, 0.5);
  assert.equal(resEcc.xi, 0.75);
  assert.deepEqual(resEcc.point, [15, 10, 0]);
  assert.equal(resEcc.isHinge, false);
});

test('computeInterfaceThrust detects plastic hinge when eccentricity exceeds threshold', () => {
  const iface = { nodeKeys: ['1', '2'], length: 20 };
  const nodes = k => k === '1' ? [0, 0, 0] : [20, 0, 0];

  // ex = +9 cm on L = 20 => eta = 18 / 20 = 0.90 >= 0.85
  const resHingeRight = computeInterfaceThrust(iface, [0, -100, 0, 0, 0, -900], nodes, 0.85);
  assert.equal(resHingeRight.isHinge, true);
  assert.deepEqual(resHingeRight.hingePoint, [20, 0, 0]); // node 2

  // ex = -9 cm on L = 20 => eta = 0.90 >= 0.85
  const resHingeLeft = computeInterfaceThrust(iface, [0, -100, 0, 0, 0, 900], nodes, 0.85);
  assert.equal(resHingeLeft.isHinge, true);
  assert.deepEqual(resHingeLeft.hingePoint, [0, 0, 0]); // node 1
});

test('computeThrustLines connects opposite interfaces and forms valid segments', () => {
  const mesh = {
    thrustPairs: [
      [101, 1, 2, 'masonry'],
      [102, 3, 4, 'backfill']
    ],
    interfaces: {
      '1': { nodeKeys: ['1', '2'], length: 20 },
      '2': { nodeKeys: ['3', '4'], length: 20 },
      '3': { nodeKeys: ['5', '6'], length: 20 },
      '4': { nodeKeys: ['7', '8'], length: 20 },
    }
  };

  const nodes = {
    '1': [0, 0, 0], '2': [20, 0, 0],
    '3': [0, 10, 0], '4': [20, 10, 0],
    '5': [0, 20, 0], '6': [20, 20, 0],
    '7': [0, 30, 0], '8': [20, 30, 0],
  };
  const nodeMap = k => nodes[k];

  // Quad 101 has interfaces 1 and 2 in compression
  // Interface 1: pure compression -> (10, 0, 0)
  // Interface 2: ex = +9 (hinge at node 4) -> (19, 10, 0)
  // Quad 102 has interface 3 in compression, 4 in tension (no segment)
  const step = {
    interfaceResultants: [
      [0, -100, 0, 0, 0, 0],    // slot 0 (iface 1)
      [0, -100, 0, 0, 0, -900], // slot 1 (iface 2)
      [0, -100, 0, 0, 0, 0],    // slot 2 (iface 3)
      [0, 50, 0, 0, 0, 0],      // slot 3 (iface 4, tension)
    ]
  };
  const slotMap = k => Number(k) - 1;

  const res = computeThrustLines(mesh, step, slotMap, nodeMap, { hingeThreshold: 0.85 });
  assert.equal(res.segmentCount, 1);
  assert.equal(res.positions.length, 6);
  assert.deepEqual(Array.from(res.positions), [10, 0, 0, 19, 10, 0]);
  assert.equal(res.hingeCount, 1);
  assert.equal(res.hinges[0].key, 2);
  assert.deepEqual(res.hinges[0].position, [20, 10, 0]); // node 4

  // Material filtering
  const resFiltered = computeThrustLines(mesh, step, slotMap, nodeMap, { materialFilter: 'backfill' });
  assert.equal(resFiltered.segmentCount, 0, 'backfill has no valid pair due to tension');
});

test('computeThrustLines with combineWidth computes force-weighted width centroid and hinges', () => {
  const mesh = {
    thrustPairs: [
      // Slice 1: y = +10
      [101, 1, 2, 'masonry'],
      // Slice 2: y = -10
      [102, 3, 4, 'masonry'],
    ],
    interfaces: {
      '1': { nodeKeys: ['1', '2'], length: 20 },
      '2': { nodeKeys: ['3', '4'], length: 20 },
      '3': { nodeKeys: ['5', '6'], length: 20 },
      '4': { nodeKeys: ['7', '8'], length: 20 },
    }
  };

  const nodes = {
    // Slice 1 (y = +10)
    '1': [0, 10, 0], '2': [20, 10, 0],
    '3': [0, 10, 10], '4': [20, 10, 10],
    // Slice 2 (y = -10)
    '5': [0, -10, 0], '6': [20, -10, 0],
    '7': [0, -10, 10], '8': [20, -10, 10],
  };
  const nodeMap = k => nodes[k];

  // Symmetric compression: N2 = -100 on both slices
  const stepSymm = {
    interfaceResultants: [
      [0, -100, 0, 0, 0, 0], // iface 1: center (10, 10, 0)
      [0, -100, 0, 0, 0, 0], // iface 2: center (10, 10, 10)
      [0, -100, 0, 0, 0, 0], // iface 3: center (10, -10, 0)
      [0, -100, 0, 0, 0, 0], // iface 4: center (10, -10, 10)
    ]
  };
  const slotMap = k => Number(k) - 1;

  // Uncombined: 2 segments
  const resIndiv = computeThrustLines(mesh, stepSymm, slotMap, nodeMap, { combineWidth: false });
  assert.equal(resIndiv.segmentCount, 2);

  // Combined: 1 centerline segment at y = 0
  const resSymm = computeThrustLines(mesh, stepSymm, slotMap, nodeMap, { combineWidth: true });
  assert.equal(resSymm.segmentCount, 1);
  assert.deepEqual(Array.from(resSymm.positions), [10, 0, 0, 10, 0, 10]);

  // Asymmetric compression: N2 = -300 on slice 1 (y=+10), N2 = -100 on slice 2 (y=-10)
  // Expected y = (300*10 + 100*(-10)) / 400 = 5
  const stepAsymm = {
    interfaceResultants: [
      [0, -300, 0, 0, 0, 0],
      [0, -300, 0, 0, 0, 0],
      [0, -100, 0, 0, 0, 0],
      [0, -100, 0, 0, 0, 0],
    ]
  };
  const resAsymm = computeThrustLines(mesh, stepAsymm, slotMap, nodeMap, { combineWidth: true });
  assert.equal(resAsymm.segmentCount, 1);
  assert.deepEqual(Array.from(resAsymm.positions), [10, 5, 0, 10, 5, 10]);

  // Combined plastic hinge detection:
  // Both slices have Mz = -900, N2 = -100 at interface 1 => ex = +9 => eta = 0.90 >= 0.85
  const stepHinge = {
    interfaceResultants: [
      [0, -100, 0, 0, 0, -900], // iface 1
      [0, -100, 0, 0, 0, 0],    // iface 2
      [0, -100, 0, 0, 0, -900], // iface 3
      [0, -100, 0, 0, 0, 0],    // iface 4
    ]
  };
  const resHinge = computeThrustLines(mesh, stepHinge, slotMap, nodeMap, { combineWidth: true, hingeThreshold: 0.85 });
  assert.equal(resHinge.hingeCount, 1);
  assert.deepEqual(resHinge.hinges[0].position, [20, 0, 0]); // node 2 / node 6 average at centerline
  assert.deepEqual(resHinge.hinges[0].thrustPoint, [19, 0, 0]);
});

test('width groups merge collinear through-thickness columns into one section line', () => {
  const mesh = {
    thrustPairs: [
      [101, 1, 2, 'masonry'], [102, 3, 4, 'masonry'],
      [103, 5, 6, 'masonry'], [104, 7, 8, 'masonry'],
    ],
    interfaces: {
      '1': { nodeKeys: ['1', '2'], length: 20 }, '2': { nodeKeys: ['3', '4'], length: 20 },
      '3': { nodeKeys: ['5', '6'], length: 20 }, '4': { nodeKeys: ['7', '8'], length: 20 },
      '5': { nodeKeys: ['11', '12'], length: 20 }, '6': { nodeKeys: ['13', '14'], length: 20 },
      '7': { nodeKeys: ['15', '16'], length: 20 }, '8': { nodeKeys: ['17', '18'], length: 20 },
    },
  };
  const nodes = {
    // Slice 1 (y = +10): two columns through the thickness
    '1': [0, 10, 0], '2': [20, 10, 0], '3': [0, 10, 10], '4': [20, 10, 10],
    '5': [20, 10, 0], '6': [40, 10, 0], '7': [20, 10, 10], '8': [40, 10, 10],
    // Slice 2 (y = -10)
    '11': [0, -10, 0], '12': [20, -10, 0], '13': [0, -10, 10], '14': [20, -10, 10],
    '15': [20, -10, 0], '16': [40, -10, 0], '17': [20, -10, 10], '18': [40, -10, 10],
  };
  const nodeMap = k => nodes[k];
  const step = {
    interfaceResultants: [
      [0, -100, 0, 0, 0, 0], [0, -100, 0, 0, 0, 0],
      [0, -100, 0, 0, 0, 0], [0, -100, 0, 0, 0, 0],
      [0, -100, 0, 0, 0, 0], [0, -100, 0, 0, 0, 0],
      [0, -100, 0, 0, 0, 0], [0, -100, 0, 0, 0, 0],
    ],
  };

  const groups = buildWidthGroups(mesh, nodeMap);
  assert.equal(groups.size, 1, 'two thickness columns and two width slices form one section');
  assert.equal(Array.from(groups.values())[0].pairs.length, 4);

  const res = computeThrustLines(mesh, step, k => Number(k) - 1, nodeMap, { combineWidth: true });
  assert.equal(res.segmentCount, 1);
  assert.deepEqual(Array.from(res.positions), [20, 0, 0, 20, 0, 10]);
});

test('buildWidthGroups clusters with reference nodes when the viewer map is deformed', () => {
  const mesh = {
    nodes: [
      { key: '1', point: { x: 0, y: 10, z: 0 } }, { key: '2', point: { x: 20, y: 10, z: 0 } },
      { key: '3', point: { x: 0, y: 10, z: 10 } }, { key: '4', point: { x: 20, y: 10, z: 10 } },
      { key: '5', point: { x: 0, y: -10, z: 0 } }, { key: '6', point: { x: 20, y: -10, z: 0 } },
      { key: '7', point: { x: 0, y: -10, z: 10 } }, { key: '8', point: { x: 20, y: -10, z: 10 } },
    ],
    thrustPairs: [[101, 1, 2, 'masonry'], [102, 3, 4, 'masonry']],
    interfaces: {
      '1': { nodeKeys: ['1', '2'], length: 20 },
      '2': { nodeKeys: ['3', '4'], length: 20 },
      '3': { nodeKeys: ['5', '6'], length: 20 },
      '4': { nodeKeys: ['7', '8'], length: 20 },
    },
  };
  // Playback deformation shifts the two slices differently in X and Z. Grouping
  // from this map would split them into two cross-sections.
  const deformed = {
    '1': [0.4, 10, 0], '2': [20.3, 10, 0.2], '3': [0.4, 10, 10], '4': [20.3, 10, 10.2],
    '5': [-0.6, -10, 0], '6': [19.7, -10, -0.3], '7': [-0.6, -10, 10], '8': [19.7, -10, 9.7],
  };
  const nodeMap = k => deformed[k];

  const groups = buildWidthGroups(mesh, nodeMap);
  assert.equal(groups.size, 1, 'reference geometry keeps one width group across playback');
  assert.equal(Array.from(groups.values())[0].pairs.length, 2);

  const step = {
    interfaceResultants: [
      [0, -100, 0, 0, 0, 0], [0, -100, 0, 0, 0, 0],
      [0, -100, 0, 0, 0, 0], [0, -100, 0, 0, 0, 0],
    ],
  };
  const res = computeThrustLines(mesh, step, k => Number(k) - 1, nodeMap, { combineWidth: true });
  assert.equal(res.segmentCount, 1, 'deformed display still produces one centroid segment');
});

test('buildWidthGroups clusters cross-section quad pairs across the width', () => {
  const mesh = {
    thrustPairs: [
      [101, 1, 2, 'arch'],
      [102, 3, 4, 'arch'],
      [201, 5, 6, 'pier'],
    ],
    interfaces: {
      '1': { nodeKeys: ['1', '2'], length: 20 },
      '2': { nodeKeys: ['3', '4'], length: 20 },
      '3': { nodeKeys: ['5', '6'], length: 20 },
      '4': { nodeKeys: ['7', '8'], length: 20 },
      '5': { nodeKeys: ['9', '10'], length: 40 },
      '6': { nodeKeys: ['11', '12'], length: 40 },
    }
  };
  const nodes = {
    // Arch slice 1 (y=+20)
    '1': [0, 20, 0], '2': [20, 20, 0],
    '3': [0, 20, 10], '4': [20, 20, 10],
    // Arch slice 2 (y=-20)
    '5': [0, -20, 0], '6': [20, -20, 0],
    '7': [0, -20, 10], '8': [20, -20, 10],
    // Pier (distinct geometry)
    '9': [100, 0, 0], '10': [140, 0, 0],
    '11': [100, 0, 50], '12': [140, 0, 50],
  };
  const nodeMap = k => nodes[k];

  const groups = buildWidthGroups(mesh, nodeMap);
  assert.equal(groups.size, 2, 'two distinct cross sections');
  const groupArr = Array.from(groups.values());
  const archGroup = groupArr.find(g => g.matKey === 'arch');
  const pierGroup = groupArr.find(g => g.matKey === 'pier');
  assert.equal(archGroup.pairs.length, 2, 'two arch slices clustered into one cross-section group');
  assert.equal(pierGroup.pairs.length, 1, 'single pier slice');
});
