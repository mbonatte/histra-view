import * as THREE from 'three';

const cyan = 0x60d9c5;
const amber = 0xffbc66;
const gold = 0xffd166;
const goldWire = 0xffe680;

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
    if (options.modelPoints && model.modelPoints) {
      for (const point of model.modelPoints) this.modelPoint(point, model);
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

  modelPoint(record, model) {
    let p = null;
    if (record.point && Array.isArray(record.point) && record.point.length === 3) {
      p = new THREE.Vector3(...record.point);
    } else if (record.elementKey) {
      const node = model.nodes?.find(n => String(n.key) === String(record.elementKey));
      if (node?.point) p = new THREE.Vector3(...node.point);
    }
    if (!p) return;

    const size = this.size * 0.009 * this.options.symbolScale;

    // Outer diamond / octahedron wireframe
    const outer = new THREE.Mesh(
      new THREE.OctahedronGeometry(size * 1.3),
      new THREE.MeshBasicMaterial({ color: goldWire, wireframe: true, depthTest: false })
    );
    outer.position.copy(p);
    outer.userData = { record, kind: 'modelPoint' };
    outer.renderOrder = 17;
    this.group.add(outer);

    // Inner solid sphere
    const inner = new THREE.Mesh(
      new THREE.SphereGeometry(size * 0.65, 12, 8),
      new THREE.MeshBasicMaterial({ color: gold, depthTest: false })
    );
    inner.position.copy(p);
    inner.userData = { record, kind: 'modelPoint' };
    inner.renderOrder = 18;
    this.group.add(inner);

    // Text badge sprite: e.g. "P1", "P2" ...
    const label = this.modelPointLabel(String(record.key));
    if (label) {
      label.position.copy(p);
      label.position.z += size * 1.8;
      label.scale.set(size * 2.8, size * 1.4, 1);
      label.userData = { record, kind: 'modelPoint' };
      label.renderOrder = 19;
      this.group.add(label);
    }
  }

  modelPointLabel(key) {
    if (typeof document === 'undefined') return null;
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    ctx.fillStyle = 'rgba(17, 24, 32, 0.85)';
    ctx.strokeStyle = '#ffd166';
    ctx.lineWidth = 4;
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(4, 4, 120, 56, 12);
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.fillRect(4, 4, 120, 56);
      ctx.strokeRect(4, 4, 120, 56);
    }

    ctx.fillStyle = '#ffd166';
    ctx.font = 'bold 32px monospace, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`P${key}`, 64, 32);

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const material = new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true });
    return new THREE.Sprite(material);
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
