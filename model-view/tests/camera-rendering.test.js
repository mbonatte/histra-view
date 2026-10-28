import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { PerspectiveCamera, OrthographicCamera, Box3, Vector3 } from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// Use the same renderer module in Node; only browser import-map URLs are resolved here.
const source = (await readFile(new URL('../static/mesh-viewer.js', import.meta.url), 'utf8'))
  .replace("from 'three'", `from '${new URL('../node_modules/three/build/three.module.js', import.meta.url).href}'`)
  .replace("from '/vendor/OrbitControls.js'", `from '${new URL('../node_modules/three/examples/jsm/controls/OrbitControls.js', import.meta.url).href}'`);
const { QuadViewer } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

class CanvasTarget extends EventTarget {
  style = {};
  clientHeight = 600;
  clientWidth = 800;
  ownerDocument = new EventTarget();
  getRootNode() { return this.ownerDocument; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 600 }; }
}

for (const [name, deltaY] of [['zoom in', -120], ['zoom out', 120]]) {
  test(`${name} redraws on the next frame even when the camera update happened in the wheel handler`, () => {
    const viewer = Object.create(QuadViewer.prototype);
    viewer.camera = new PerspectiveCamera(42, 800 / 600, 0.01, 10000);
    viewer.camera.position.set(0, -100, 50);
    const canvas = new CanvasTarget();
    viewer.controls = new OrbitControls(viewer.camera, canvas);
    viewer._configureControls();
    viewer.needsRender = false;
    const originalDistance = viewer.camera.position.length();
    const wheel = new Event('wheel', { cancelable: true });
    Object.assign(wheel, { deltaY, deltaMode: 0, clientX: 400, clientY: 300 });
    canvas.dispatchEvent(wheel);
    const distance = viewer.camera.position.length();
    assert.ok(deltaY < 0 ? distance < originalDistance : distance > originalDistance);
    assert.equal(viewer.controls.update(), false, 'the wheel handler has already consumed the camera update');
    let renders = 0;
    viewer.renderer = { render: () => { renders++; } };
    const previousRaf = globalThis.requestAnimationFrame;
    globalThis.requestAnimationFrame = () => {};
    try {
      viewer._animate();
      assert.equal(renders, 1, 'the updated camera is presented without another user interaction');
      viewer._animate();
      assert.equal(renders, 1, 'an idle camera does not redraw continuously');
    } finally {
      globalThis.requestAnimationFrame = previousRaf;
      viewer.controls.dispose();
    }
  });
}

test('selectNode adds and clears a focused node marker', () => {
  const viewer = Object.create(QuadViewer.prototype);
  viewer.state = {
    nodes: new Map([[7, new Vector3(10, 20, 30)]]),
    bounds: new Box3(new Vector3(0, 0, 0), new Vector3(100, 100, 100)),
  };
  viewer.scene = { add: object => { viewer.markerAdded = object; }, remove: object => { viewer.markerRemoved = object; } };
  viewer.needsRender = false;

  viewer.selectNode(7);
  assert.ok(viewer.nodeMarker);
  assert.equal(viewer.nodeMarker.position.x, 10);
  assert.equal(viewer.nodeMarker.position.y, 20);
  assert.equal(viewer.nodeMarker.position.z, 30);
  assert.equal(viewer.markerAdded, viewer.nodeMarker);
  assert.equal(viewer.needsRender, true);

  viewer.clearNodeSelection();
  assert.equal(viewer.nodeMarker, null);
  assert.ok(viewer.markerRemoved);
});

test('setProjection switches between PerspectiveCamera and OrthographicCamera while preserving view scale and orientation', () => {
  const viewer = Object.create(QuadViewer.prototype);
  viewer.container = { clientWidth: 800, clientHeight: 600 };
  viewer.perspCamera = new PerspectiveCamera(42, 800 / 600, 0.01, 10000);
  viewer.orthoCamera = new OrthographicCamera(-100, 100, 100, -100, -10000, 10000);
  viewer.camera = viewer.perspCamera;
  viewer.projection = 'perspective';
  viewer._orthoHalfHeight = 100;
  viewer.camera.position.set(0, -200, 100);
  viewer.camera.up.set(0, 0, 1);

  const canvas = new CanvasTarget();
  viewer.controls = new OrbitControls(viewer.camera, canvas);
  viewer.controls.target.set(10, 20, 30);
  viewer._configureControls();

  const initialDist = viewer.camera.position.distanceTo(viewer.controls.target);
  const expectedHalfHeight = initialDist * Math.tan((42 * Math.PI / 180) / 2);

  viewer.needsRender = false;
  viewer.setProjection('ortho');

  assert.equal(viewer.projection, 'ortho');
  assert.equal(viewer.camera, viewer.orthoCamera);
  assert.equal(viewer.controls.object, viewer.orthoCamera);
  assert.ok(Math.abs(viewer._orthoHalfHeight - expectedHalfHeight) < 1e-6);
  assert.equal(viewer.orthoCamera.zoom, 1);
  assert.ok(viewer.needsRender);

  // Simulate zooming in by 2x in orthographic mode, then switching back to perspective
  viewer.orthoCamera.zoom = 2;
  viewer.needsRender = false;
  viewer.setProjection('perspective');

  assert.equal(viewer.projection, 'perspective');
  assert.equal(viewer.camera, viewer.perspCamera);
  assert.equal(viewer.controls.object, viewer.perspCamera);
  const newDist = viewer.perspCamera.position.distanceTo(viewer.controls.target);
  assert.ok(Math.abs(newDist - initialDist / 2) < 1e-5, 'perspective camera distance reflects orthographic zoom');
  assert.ok(viewer.needsRender);

  viewer.controls.dispose();
});

