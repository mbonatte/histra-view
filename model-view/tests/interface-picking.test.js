import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import * as THREE from 'three';

// Exercise the production picking/build methods with Three's actual raycaster.
// Only the DOM/WebGL viewer constructor is omitted in this headless test.
let source=await readFile(new URL('../static/interface-stress-view.js',import.meta.url),'utf8');
source=source.replace("import { QuadViewer } from './mesh-viewer.js';",'const QuadViewer = class {};')
  .replace("from 'three'",`from '${new URL('../node_modules/three/build/three.module.js',import.meta.url).href}'`);
for(const file of ['interface-resultants.js','stress-data.js']) source=source.replace(`from './${file}'`,`from '${new URL('../static/'+file,import.meta.url).href}'`);
const {InterfaceStressView}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('raycast selects the correct saved interface and fibre, including nonzero buffer offsets',()=>{
  const view=Object.create(InterfaceStressView.prototype);
  view.viewer={scene:new THREE.Scene()};
  const positions=[];
  for(let x=0;x<4;x++) positions.push(x,0,0,x+1,0,0,x+1,1,0,x,1,0);
  view.data={cellCount:4,positions:new Float32Array(positions),groups:[
    {key:813,start:0,count:2,corners:[[0,0,0],[2,0,0],[2,1,0],[0,1,0]]},
    {key:884,start:2,count:2,corners:[[2,0,0],[4,0,0],[4,1,0],[2,1,0]]}]};
  view.build(); view.pickMeshes=view.groupMeshes;
  const ray=new THREE.Raycaster(new THREE.Vector3(3.6,.4,2),new THREE.Vector3(0,0,-1));
  assert.deepEqual(view.pick(ray),{key:884,cell:3});
  ray.ray.origin.x=2.3;
  assert.deepEqual(view.pick(ray),{key:884,cell:2});
  view.pickMeshes=[view.groupMeshes[0]];
  assert.equal(view.pick(ray),null,'hidden interfaces cannot intercept clicks');
  view.surface.visible=false;
  assert.equal(view.pick(ray),null,'unavailable stress snapshots cannot be picked');
  view.groupMeshes.forEach(m=>m.geometry.dispose());view.surface.geometry.dispose();view.surface.material.dispose();
});
