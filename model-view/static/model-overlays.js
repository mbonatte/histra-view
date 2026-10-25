import * as THREE from 'three';

const cyan = 0x60d9c5;
const amber = 0xffbc66;

export class ModelOverlays {
  constructor(viewer, onSelect) {
    this.viewer = viewer;
    this.onSelect = onSelect;
    this.group = new THREE.Group();
    viewer.scene.add(this.group);
    viewer.pickOverlay = () => this.pick();
  }

  clear() {
    this.group.traverse(object => {
      object.geometry?.dispose();
      if (Array.isArray(object.material)) object.material.forEach(m => m.dispose());
      else object.material?.dispose();
    });
    this.group.clear();
  }

  update(model, options) {
    this.clear();
    this.viewer.needsRender = true;
    this.options = options;
    this.size = Math.max(...model.bounds.max.map((v, i) => v - model.bounds.min[i]), 1);
    if (options.restraints) {
      for (const restraint of model.restraints) this.restraint(restraint);
    }
    if (options.loads) {
      const selected = model.loads.filter(load => load.drawable && (!options.condition || load.conditionKey === options.condition));
      const max = Math.max(...selected.map(load => Math.abs(load.value)), 1e-30);
      for (const load of selected) this.load(load, max);
    }
  }

  line(points, tint, record, kind, loop = false) {
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color: tint, depthTest: false, transparent: true, opacity: 0.85 });
    const line = loop ? new THREE.LineLoop(geometry, material) : new THREE.Line(geometry, material);
    line.renderOrder = 15;
    line.userData = { record, kind };
    this.group.add(line);
    return line;
  }

  restraint(record) {
    const points = record.points.map(p => new THREE.Vector3(...p));
    if (!points.length) return;
    if (points.length > 1) this.line(points, cyan, record, 'restraint', points.length > 2);
    const positions = points.length === 2
      ? [points[0], points[0].clone().lerp(points[1], 0.5), points[1]]
      : [points.reduce((v, p) => v.add(p), new THREE.Vector3()).divideScalar(points.length)];
    const size = this.size * 0.008 * this.options.symbolScale;
    for (const p of positions) {
      // A neutral octahedral marker avoids implying a pinned/fixed support type.
      // Exact mechanical behavior is available in the six-DOF inspector.
      const marker = new THREE.Mesh(new THREE.OctahedronGeometry(size), new THREE.MeshBasicMaterial({ color: cyan, wireframe: true, depthTest: false }));
      marker.position.copy(p);
      marker.userData = { record, kind: 'restraint' };
      marker.renderOrder = 16;
      this.group.add(marker);
    }
  }

  load(record, maximum) {
    const points = record.points.map(p => new THREE.Vector3(...p));
    let locations = points;
    if (record.kind === 'LineLoad') {
      if (points.length < 2) return;
      locations = Array.from({ length: 5 }, (_, i) => points[0].clone().lerp(points[1], i / 4));
    } else if (record.kind === 'AreaLoad') {
      locations = [...points, points.reduce((v, p) => v.add(p), new THREE.Vector3()).divideScalar(points.length)];
    }
    const direction = new THREE.Vector3(...record.direction).multiplyScalar(Math.sign(record.value));
    if (direction.lengthSq() === 0) return;
    const ratio = Math.abs(record.value) / maximum;
    const length = this.size * 0.075 * this.options.symbolScale * ratio;
    const tails = [];
    for (const point of locations) {
      const tail = point.clone().addScaledVector(direction, -length);
      tails.push(tail);
      const arrow = new THREE.ArrowHelper(direction, tail, length, amber, length * 0.22, length * 0.1);
      arrow.traverse(object => {
        object.userData = { record, kind: 'load' };
        object.renderOrder = 20;
        if (object.material) object.material.depthTest = false;
      });
      this.group.add(arrow);
    }
    if (points.length > 1) this.line(points, amber, record, 'load', points.length > 2);
    if (tails.length > 1) this.line(tails.slice(0, points.length > 2 ? points.length : tails.length), amber, record, 'load', points.length > 2);
  }

  pick() {
    this.viewer.raycaster.params.Line.threshold = this.size * 0.003;
    const hit = this.viewer.raycaster.intersectObjects(this.group.children, true)[0];
    if (!hit?.object.userData.record) return false;
    const { record, kind } = hit.object.userData;
    this.viewer.clearSelection();
    this.onSelect(kind, record);
    return true;
  }
}
