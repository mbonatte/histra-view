import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';

const DEFAULT_OPTIONS = {
  background: 0x111820,
  edges: true,
  nodes: false,
  modelPoints: true,
  extrude: true,
  thicknessScale: 1,
  opacity: 0.94,
  colorBy: 'material',
};

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
}

function parseVector(value, fallback = [0, 0, 0]) {
  if (Array.isArray(value)) {
    const parts = value.map(Number);
    return parts.length === 3 && parts.every(Number.isFinite)
      ? new THREE.Vector3(parts[0], parts[1], parts[2])
      : new THREE.Vector3(...fallback);
  }
  if (!value) return new THREE.Vector3(...fallback);
  const parts = String(value).split(';').map(Number);
  return parts.length === 3 && parts.every(Number.isFinite)
    ? new THREE.Vector3(parts[0], parts[1], parts[2])
    : new THREE.Vector3(...fallback);
}

function computedNormal(points) {
  const a = points[1].clone().sub(points[0]);
  const b = points[3].clone().sub(points[0]);
  const normal = a.cross(b);
  if (normal.lengthSq() <= 1e-18) {
    normal.copy(points[2]).sub(points[0]).cross(points[3].clone().sub(points[1]));
  }
  return normal.lengthSq() > 1e-18 ? normal.normalize() : new THREE.Vector3(0, -1, 0);
}

function hashString(value) {
  let hash = 2166136261;
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function normalizePreviewMesh(mesh, name = 'Server preview') {
  const nodes = new Map();
  for (const node of mesh?.nodes ?? []) {
    const key = Number(node.key);
    if (Number.isInteger(key)) nodes.set(key, parseVector(node.point));
  }
  const quads = [];
  for (const item of mesh?.quads ?? []) {
    const nodeKeys = (item.nodeKeys ?? []).map(Number);
    if (nodeKeys.length !== 4 || nodeKeys.some(key => !nodes.has(key))) continue;
    const points = nodeKeys.map(key => nodes.get(key));
    const normals = (item.normals ?? []).filter(Boolean).map(n => parseVector(n));
    const normal = normals.length ? normals.reduce((v, n) => v.add(n), new THREE.Vector3()).normalize() : computedNormal(points);
    quads.push({
      key: finiteNumber(item.key),
      name: String(item.name ?? ''),
      nodeKeys,
      material: String(item.materialKey ?? '0'),
      layer: finiteNumber(item.layerKey, 0),
      parentType: String(item.parentTypeElement ?? 'Bridge'),
      parentKey: finiteNumber(item.parentKey, 1),
      thicknesses: item.thicknesses ?? [0, 1, 2, 3].map(() => finiteNumber(item.thickness, 0)),
      normal,
      normals: item.normals?.map(n => n ? parseVector(n).normalize() : normal.clone()),
      group: String(item.group ?? 'mesh'),
      lane: String(item.transverseBandName ?? item.transverseRole ?? '—'),
      transverseRole: String(item.transverseRole ?? '—'),
      sourceIndex: item.sourceIndex,
      attributes: item.attributes ?? {},
    });
  }
  return { name, nodes, quads };
}

export async function decodeLocalFile(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
    return new TextDecoder('utf-16le').decode(bytes.subarray(2));
  }
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    const swapped = new Uint8Array(bytes.length - 2);
    for (let index = 2; index + 1 < bytes.length; index += 2) {
      swapped[index - 2] = bytes[index + 1];
      swapped[index - 1] = bytes[index];
    }
    return new TextDecoder('utf-16le').decode(swapped);
  }
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return new TextDecoder('utf-8').decode(bytes.subarray(3));
  }
  const sampleLength = Math.min(bytes.length, 4096);
  let nulCount = 0;
  for (let index = 0; index < sampleLength; index += 1) if (bytes[index] === 0) nulCount += 1;
  return new TextDecoder(sampleLength > 0 && nulCount / sampleLength > 0.10 ? 'utf-16le' : 'utf-8').decode(bytes);
}

export function parseHrxXml(xmlText, name = 'HRX model') {
  const cleanText = String(xmlText).replace(/^\s*<\?xml[^?]*\?>/i, '');
  const xml = new DOMParser().parseFromString(cleanText, 'application/xml');
  const parseError = xml.querySelector('parsererror');
  if (parseError) throw new Error(`XML parse error: ${parseError.textContent.trim()}`);

  const nodes = new Map();
  for (const element of xml.getElementsByTagName('Node')) {
    const key = Number(element.getAttribute('Key'));
    const point = element.getAttribute('Point');
    if (Number.isInteger(key) && point) nodes.set(key, parseVector(point));
  }

  const quads = [];
  for (const element of xml.getElementsByTagName('Quad')) {
    const nodeKeys = [1, 2, 3, 4].map(index => Number(element.getAttribute(`NodeKey${index}`)));
    if (nodeKeys.some(key => !Number.isInteger(key))) continue;
    const missing = nodeKeys.filter(key => !nodes.has(key));
    if (missing.length) {
      throw new Error(`Quad ${element.getAttribute('Key') ?? '?'} references missing nodes: ${missing.join(', ')}`);
    }
    const normals = [1, 2, 3, 4].map(index => parseVector(element.getAttribute(`Normal${index}`)));
    const normal = normals.reduce((sum, item) => sum.add(item), new THREE.Vector3());
    if (normal.lengthSq() > 1e-18) normal.normalize();
    else normal.copy(computedNormal(nodeKeys.map(key => nodes.get(key))));
    quads.push({
      key: finiteNumber(element.getAttribute('Key')),
      name: element.getAttribute('Name') ?? '',
      nodeKeys,
      material: String(element.getAttribute('MaterialKey') ?? '0'),
      layer: finiteNumber(element.getAttribute('LayerKey')),
      parentType: element.getAttribute('ParentTypeElement') ?? '',
      parentKey: finiteNumber(element.getAttribute('ParentKey')),
      thicknesses: [1, 2, 3, 4].map(index => finiteNumber(element.getAttribute(`Thickness${index}`))),
      normal,
      group: element.getAttribute('ParentTypeElement') ?? 'Quad',
      lane: `Y ${mean(nodeKeys.map(key => nodes.get(key).y)).toFixed(3)}`,
      transverseRole: '',
      sourceIndex: null,
    });
  }
  if (!nodes.size) throw new Error('No valid <Node> elements were found.');
  if (!quads.length) throw new Error('No valid <Quad> elements were found.');
  return { name, nodes, quads };
}

export class QuadViewer {
  constructor(container, options = {}) {
    if (!container) throw new Error('QuadViewer requires a container element.');
    this.container = container;
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.callbacks = { selection: null, stats: null, legend: null, message: null };
    this.visibleQuad = () => true;
    this.materialDefinitions = new Map();
    this.layerDefinitions = new Map();
    this.state = {
      name: '',
      nodes: new Map(),
      quads: [],
      modelPoints: [],
      mesh: null,
      edgeLines: null,
      nodePoints: null,
      modelPointPoints: null,
      selectionLine: null,
      triangleToQuad: [],
      selectedQuadIndex: null,
      bounds: new THREE.Box3(),
      categoryColors: new Map(),
    };

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(this.options.background);
    this.perspCamera = new THREE.PerspectiveCamera(42, 1, 0.01, 1e9);
    this.perspCamera.up.set(0, 0, 1);
    this.orthoCamera = new THREE.OrthographicCamera(-100, 100, 100, -100, -1e6, 1e9);
    this.orthoCamera.up.set(0, 0, 1);
    this._orthoHalfHeight = 100;
    this.projection = this.options.projection === 'ortho' ? 'ortho' : 'perspective';
    this.camera = this.projection === 'ortho' ? this.orthoCamera : this.perspCamera;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.style.position = 'absolute';
    this.renderer.domElement.style.inset = '0';
    this.container.prepend(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this._configureControls();

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x283343, 2.1));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
    keyLight.position.set(-1, -2, 3);
    this.scene.add(keyLight);

    this.axes = new THREE.AxesHelper(35);
    this.axes.renderOrder = 5;
    this.scene.add(this.axes);

    this.grid = new THREE.GridHelper(1200, 24, 0x536175, 0x293241);
    this.grid.rotation.x = Math.PI / 2;
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.34;
    this.grid.material.depthWrite = false;
    this.scene.add(this.grid);

    this.modelGroup = new THREE.Group();
    this.scene.add(this.modelGroup);
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this._pointerStart = null;
    this._resizeObserver = new ResizeObserver(() => this.resize());
    this._resizeObserver.observe(this.container);
    this.renderer.domElement.addEventListener('pointerdown', event => this._onPointerDown(event));
    this.renderer.domElement.addEventListener('pointerup', event => this._onPointerUp(event));
    this.resize();
    this._animate();
  }

  _configureControls() {
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    // Wheel input calls OrbitControls.update() before the next animation frame.
    // Its change event must invalidate that frame even if update() then returns false.
    this.controls.addEventListener('change', () => { this.needsRender = true; });
  }

  on(event, callback) {
    if (!(event in this.callbacks)) throw new Error(`Unknown viewer event: ${event}`);
    this.callbacks[event] = callback;
    return this;
  }

  emit(event, value) {
    this.callbacks[event]?.(value);
  }

  loadPreview(mesh, { name = 'Server preview', modelPoints = [] } = {}) {
    const normalized = normalizePreviewMesh(mesh, name);
    this._loadNormalized(normalized, modelPoints);
  }

  loadHrxText(xmlText, name = 'HRX model') {
    const normalized = parseHrxXml(xmlText, name);
    this._loadNormalized(normalized, []);
  }

  clear() {
    this._disposeObject(this.state.mesh);
    this._disposeObject(this.state.edgeLines);
    this._disposeObject(this.state.nodePoints);
    this._disposeObject(this.state.modelPointPoints);
    this._disposeObject(this.state.selectionLine);
    this.state = { ...this.state, name: '', nodes: new Map(), quads: [], modelPoints: [], mesh: null, edgeLines: null, nodePoints: null, modelPointPoints: null, selectionLine: null, triangleToQuad: [], selectedQuadIndex: null, bounds: new THREE.Box3(), categoryColors: new Map() };
    this.emit('stats', this.getStats());
  }

  getStats() {
    return {
      name: this.state.name,
      nodes: this.state.nodes.size,
      quads: this.state.quads.length,
      materials: new Set(this.state.quads.map(item => item.material)).size,
      layers: new Set(this.state.quads.map(item => item.layer)).size,
      modelPoints: this.state.modelPoints.length,
    };
  }

  setOptions(patch, { rebuild = true, preserveView = true } = {}) {
    this.needsRender = true;
    this.options = { ...this.options, ...patch };
    if ('edges' in patch && this.state.edgeLines) this.state.edgeLines.visible = Boolean(this.options.edges);
    if ('nodes' in patch && this.state.nodePoints) this.state.nodePoints.visible = Boolean(this.options.nodes);
    if ('modelPoints' in patch && this.state.modelPointPoints) this.state.modelPointPoints.visible = Boolean(this.options.modelPoints);
    if ('opacity' in patch && this.state.mesh) {
      this.state.mesh.material.opacity = Number(this.options.opacity);
      this.state.mesh.material.transparent = Number(this.options.opacity) < 1;
      this.state.mesh.material.depthWrite = Number(this.options.opacity) >= 0.99;
      this.state.mesh.material.needsUpdate = true;
    }
    const geometryKeys = ['extrude', 'thicknessScale', 'colorBy'];
    if (rebuild && geometryKeys.some(key => key in patch) && this.state.quads.length) this.rebuild({ preserveView });
  }

  _updateOrthoFrustum(aspect = this.perspCamera?.aspect || this.camera?.aspect || 1) {
    if (!this.orthoCamera) return;
    const h = Math.max(this._orthoHalfHeight || 100, 1e-4);
    const w = h * aspect;
    this.orthoCamera.left = -w;
    this.orthoCamera.right = w;
    this.orthoCamera.top = h;
    this.orthoCamera.bottom = -h;
    this.orthoCamera.updateProjectionMatrix();
  }

  setProjection(mode = 'perspective') {
    const next = mode === 'ortho' ? 'ortho' : 'perspective';
    if (!this.perspCamera) {
      this.perspCamera = this.camera?.isPerspectiveCamera ? this.camera : new THREE.PerspectiveCamera(42, 1, 0.01, 1e9);
    }
    if (!this.orthoCamera) {
      this.orthoCamera = new THREE.OrthographicCamera(-100, 100, 100, -100, -1e6, 1e9);
      this.orthoCamera.up.copy(this.perspCamera.up);
    }
    const target = this.controls ? this.controls.target : new THREE.Vector3();
    const tanV = Math.tan(THREE.MathUtils.degToRad((this.perspCamera.fov || 42) / 2));

    if (next === 'ortho' && this.camera !== this.orthoCamera) {
      const dist = Math.max(this.perspCamera.position.distanceTo(target), 1e-3);
      this._orthoHalfHeight = dist * tanV;
      this.orthoCamera.position.copy(this.perspCamera.position);
      this.orthoCamera.up.copy(this.perspCamera.up);
      this.orthoCamera.zoom = 1;
      this.orthoCamera.near = -Math.max(dist * 20, 10000);
      this.orthoCamera.far = Math.max(dist * 100, 10000);
      this._updateOrthoFrustum(this.perspCamera.aspect || 1);
      this.camera = this.orthoCamera;
    } else if (next === 'perspective' && this.camera !== this.perspCamera) {
      const effectiveHalfH = (this._orthoHalfHeight || 100) / Math.max(this.orthoCamera.zoom || 1, 1e-6);
      const dist = Math.max(effectiveHalfH / tanV, 1e-3);
      const dir = this.orthoCamera.position.clone().sub(target);
      if (dir.lengthSq() > 1e-12) dir.normalize();
      else dir.set(0, -1, 0);
      this.perspCamera.up.copy(this.orthoCamera.up);
      this.perspCamera.position.copy(target).addScaledVector(dir, dist);
      this.perspCamera.near = Math.max(dist / 10000, 0.001);
      this.perspCamera.far = Math.max(dist * 100, 1000);
      this.perspCamera.updateProjectionMatrix();
      this.camera = this.perspCamera;
    }

    this.projection = next;
    if (this.controls) {
      this.controls.object = this.camera;
      this.controls.update();
    }
    this.needsRender = true;
    return this.projection;
  }

  setView(kind = 'iso') {
    this.needsRender = true;
    if (this.state.bounds.isEmpty()) return;
    const center = this.state.bounds.getCenter(new THREE.Vector3());
    const directions = {
      front: new THREE.Vector3(0, -1, 0),
      back: new THREE.Vector3(0, 1, 0),
      top: new THREE.Vector3(0, 0, 1),
      side: new THREE.Vector3(1, 0, 0),
      iso: new THREE.Vector3(1, -1, 0.72).normalize(),
    };
    const direction = directions[kind] ?? directions.iso;
    const upVec = Math.abs(direction.z) > 0.999 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1);
    const right = upVec.clone().cross(direction).normalize();
    const up = direction.clone().cross(right).normalize();
    const fov = this.perspCamera?.fov ?? this.camera.fov ?? 42;
    const aspect = this.perspCamera?.aspect ?? this.camera.aspect ?? 1;
    const tanV = Math.tan(THREE.MathUtils.degToRad(fov / 2));
    const tanH = tanV * aspect;
    let distance = 1;
    for (const x of [this.state.bounds.min.x, this.state.bounds.max.x]) {
      for (const y of [this.state.bounds.min.y, this.state.bounds.max.y]) {
        for (const z of [this.state.bounds.min.z, this.state.bounds.max.z]) {
          const corner = new THREE.Vector3(x, y, z).sub(center);
          const depth = corner.dot(direction);
          distance = Math.max(distance, depth + Math.abs(corner.dot(right)) / tanH, depth + Math.abs(corner.dot(up)) / tanV);
        }
      }
    }
    distance *= 1.2;
    for (const cam of new Set([this.perspCamera, this.orthoCamera, this.camera].filter(Boolean))) {
      cam.up.copy(upVec);
      cam.position.copy(center).addScaledVector(direction, distance);
    }
    if (this.perspCamera) {
      this.perspCamera.near = Math.max(distance / 10000, 0.001);
      this.perspCamera.far = Math.max(distance * 100, 1000);
      this.perspCamera.updateProjectionMatrix();
    } else {
      this.camera.near = Math.max(distance / 10000, 0.001);
      this.camera.far = Math.max(distance * 100, 1000);
    }
    if (this.orthoCamera) {
      this._orthoHalfHeight = distance * tanV;
      this.orthoCamera.zoom = 1;
      this.orthoCamera.near = -Math.max(distance * 20, 10000);
      this.orthoCamera.far = Math.max(distance * 100, 10000);
      this._updateOrthoFrustum(aspect);
    }
    this.controls.target.copy(center);
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  fit() { this.setView('iso'); }

  clearSelection() { this.selectQuad(null); }

  resize() {
    this.needsRender = true;
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(width, height, false);
    const aspect = width / height;
    if (this.perspCamera) {
      this.perspCamera.aspect = aspect;
      this.perspCamera.updateProjectionMatrix();
    } else if (this.camera) {
      this.camera.aspect = aspect;
      this.camera.updateProjectionMatrix();
    }
    this._updateOrthoFrustum(aspect);
  }

  rebuild({ preserveView = true } = {}) {
    this.needsRender = true;
    if (!this.state.quads.length) return;
    const target = this.controls.target.clone();
    const cameraPosition = this.camera.position.clone();
    const selected = this.state.selectedQuadIndex;

    this._disposeObject(this.state.mesh);
    this._disposeObject(this.state.edgeLines);
    this._disposeObject(this.state.nodePoints);
    this._disposeObject(this.state.modelPointPoints);
    this._disposeObject(this.state.selectionLine);
    this.state.mesh = this.state.edgeLines = this.state.nodePoints = this.state.modelPointPoints = this.state.selectionLine = null;

    const { geometry, edgeGeometry, triangleToQuad } = this._geometryForModel();
    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.76,
      metalness: 0.02,
      transparent: Number(this.options.opacity) < 1,
      opacity: Number(this.options.opacity),
      depthWrite: Number(this.options.opacity) >= 0.99,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    });
    this.state.mesh = new THREE.Mesh(geometry, material);
    this.state.mesh.name = 'Quads';
    this.modelGroup.add(this.state.mesh);
    this.state.triangleToQuad = triangleToQuad;

    this.state.edgeLines = new THREE.LineSegments(
      edgeGeometry,
      new THREE.LineBasicMaterial({ color: 0x0a0d12, transparent: true, opacity: 0.82 }),
    );
    this.state.edgeLines.visible = Boolean(this.options.edges);
    this.state.edgeLines.renderOrder = 2;
    this.modelGroup.add(this.state.edgeLines);

    const visibleQuads = this.state.quads.filter(quad => this.visibleQuad(quad));
    const nodePositions = [];
    if (visibleQuads.some(quad => quad.points)) {
      for (const quad of visibleQuads) {
        const pts = quad.points ?? quad.nodeKeys.map(key => this.state.nodes.get(key));
        for (const point of pts) nodePositions.push(point.x, point.y, point.z);
      }
    } else {
      const referencedNodes = [...new Set(visibleQuads.flatMap(quad => quad.nodeKeys))];
      for (const key of referencedNodes) {
        const point = this.state.nodes.get(key);
        nodePositions.push(point.x, point.y, point.z);
      }
    }
    const nodeGeometry = new THREE.BufferGeometry();
    nodeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(nodePositions, 3));
    this.state.nodePoints = new THREE.Points(nodeGeometry, new THREE.PointsMaterial({ color: 0xffffff, size: 4, sizeAttenuation: false, depthTest: false }));
    this.state.nodePoints.visible = Boolean(this.options.nodes);
    this.state.nodePoints.renderOrder = 4;
    this.modelGroup.add(this.state.nodePoints);

    const pointPositions = [];
    for (const pointRecord of this.state.modelPoints) {
      const point = this.state.nodes.get(Number(pointRecord.nodeKey));
      if (point) pointPositions.push(point.x, point.y, point.z);
    }
    const mpGeometry = new THREE.BufferGeometry();
    mpGeometry.setAttribute('position', new THREE.Float32BufferAttribute(pointPositions, 3));
    this.state.modelPointPoints = new THREE.Points(mpGeometry, new THREE.PointsMaterial({ color: 0xffe66d, size: 8, sizeAttenuation: false, depthTest: false }));
    this.state.modelPointPoints.visible = Boolean(this.options.modelPoints);
    this.state.modelPointPoints.renderOrder = 6;
    this.modelGroup.add(this.state.modelPointPoints);

    if (!this.state.bounds.isEmpty() && preserveView) { /* Keep full-model framing when filtering. */ }
    else this.state.bounds.setFromPoints([...this.state.nodes.values()]);
    this._updateGrid();
    this._emitLegend();
    if (selected != null) this.selectQuad(selected);
    if (!preserveView) this.setView('front');
    else {
      this.camera.position.copy(cameraPosition);
      this.controls.target.copy(target);
      this.controls.update();
    }
  }

  selectQuad(index) {
    this.needsRender = true;
    this._disposeObject(this.state.selectionLine);
    this.state.selectionLine = null;
    if (index == null || !this.state.quads[index]) {
      this.state.selectedQuadIndex = null;
      this.emit('selection', null);
      return;
    }
    this.state.selectedQuadIndex = index;
    const quad = this.state.quads[index];
    const outline = this._selectedOutlinePoints(quad);
    const positions = [];
    for (const loop of outline.loops) {
      for (let item = 0; item < 4; item += 1) this._addSegment(positions, loop[item], loop[(item + 1) % 4]);
    }
    for (const [a, b] of outline.sides) this._addSegment(positions, a, b);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    this.state.selectionLine = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: 0xffff66, depthTest: false }));
    this.state.selectionLine.renderOrder = 10;
    this.modelGroup.add(this.state.selectionLine);
    this.emit('selection', { index, quad });
  }

  destroy() {
    this.destroyed = true;
    this.controls.dispose();
    this._resizeObserver.disconnect();
    this.renderer.dispose();
    this.container.removeChild(this.renderer.domElement);
  }

  _loadNormalized(model, modelPoints) {
    this.state.bounds.makeEmpty();
    this.state.name = model.name;
    this.state.nodes = model.nodes;
    this.state.quads = model.quads;
    this.state.modelPoints = modelPoints ?? [];
    this.state.selectedQuadIndex = null;
    this.rebuild({ preserveView: false });
    this.clearSelection();
    this.emit('stats', this.getStats());
  }

  _categoryValue(quad) {
    switch (this.options.colorBy) {
      case 'material': return `${this.materialDefinitions.get(quad.material)?.name || 'Material'} [${quad.material}]`;
      case 'layer': return `${this.layerDefinitions.get(String(quad.layer))?.name || 'Layer'} [${quad.layer}]`;
      case 'parent': return `${quad.parentType || 'Parent'} ${quad.parentKey}`;
      case 'thickness': return `Thickness ${mean(quad.thicknesses).toFixed(4)}`;
      case 'quad': return `Quad ${quad.key}`;
      case 'group': return quad.group || 'Component';
      case 'lane': return quad.lane || 'Lane';
      case 'role': return quad.transverseRole || 'Role';
      default: return 'Quads';
    }
  }

  _buildColorMap() {
    const values = [...new Set(this.state.quads.map(quad => this._categoryValue(quad)))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    const colors = new Map();
    if (this.options.colorBy === 'single') colors.set('Quads', new THREE.Color(0x6fb7ff));
    else {
      for (const value of values) {
        const hue = (hashString(value) % 360) / 360;
        const match = this.options.colorBy === 'material' && [...this.materialDefinitions.values()].find(m => `${m.name || 'Material'} [${m.key}]` === value);
        colors.set(value, match ? new THREE.Color(match.color) : new THREE.Color().setHSL(hue, 0.55, 0.62));
      }
    }
    return colors;
  }

  _geometryForModel() {
    const data = { positions: [], colors: [], triangleToQuad: [], edgePositions: [] };
    const useExtrusion = Boolean(this.options.extrude) && Number(this.options.thicknessScale) > 0;
    this.state.categoryColors = this._buildColorMap();
    this.state.quads.forEach((quad, quadIndex) => {
      if (!this.visibleQuad(quad)) return;
      const base = quad.points ? quad.points.map(p => p.clone()) : quad.nodeKeys.map(key => this.state.nodes.get(key).clone());
      const color = quad.colors || quad.color || this.state.categoryColors.get(this._categoryValue(quad));
      if (!useExtrusion) {
        if (quad.faceGrids?.[0]) this._pushFaceGrid(data, base, quad.faceGrids[0], quadIndex);
        else this._pushQuadFace(data, base, quad.faceColors?.[0] ?? color, quadIndex);
        for (let index = 0; index < 4; index += 1) this._addSegment(data.edgePositions, base[index], base[(index + 1) % 4]);
        return;
      }
      const normal = quad.normal.lengthSq() > 1e-18 ? quad.normal.clone().normalize() : computedNormal(base);
      const top = base.map((point, index) => point.clone().addScaledVector(quad.normals?.[index] ?? normal, quad.thicknesses[index] * Number(this.options.thicknessScale) * 0.5));
      const bottom = base.map((point, index) => point.clone().addScaledVector(quad.normals?.[index] ?? normal, -quad.thicknesses[index] * Number(this.options.thicknessScale) * 0.5));
      // Face order matches the projected C# faces: 0 top, 1 bottom, 2..5 sides.
      const sideFaces = [0, 1, 2, 3].map(index => {
        const next = (index + 1) % 4;
        return [top[index], top[next], bottom[next], bottom[index]];
      });
      const facePoints = [top, bottom, ...sideFaces];
      const faceColors = [0, 1, 2, 3, 4, 5].map(index => {
        if (quad.faceColors?.[index]) return quad.faceColors[index];
        if (index < 2 || !Array.isArray(color)) return color;
        const side = index - 2;
        const next = (side + 1) % 4;
        return [color[side], color[next], color[next], color[side]];
      });
      for (let face = 0; face < 6; face += 1) {
        if (quad.faceGrids?.[face]) this._pushFaceGrid(data, facePoints[face], quad.faceGrids[face], quadIndex);
        else this._pushQuadFace(data, facePoints[face], faceColors[face], quadIndex, face === 1);
      }
      for (let index = 0; index < 4; index += 1) {
        this._addSegment(data.edgePositions, top[index], top[(index + 1) % 4]);
        this._addSegment(data.edgePositions, bottom[index], bottom[(index + 1) % 4]);
        this._addSegment(data.edgePositions, top[index], bottom[index]);
      }
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(data.colors, 3));
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(data.edgePositions, 3));
    return { geometry, edgeGeometry, triangleToQuad: data.triangleToQuad };
  }

  _pushTriangle(target, a, b, c, color, quadIndex) {
    const isArr = Array.isArray(color);
    const colors = isArr ? color : [color, color, color];
    for (let i = 0; i < 3; i++) {
      const point = i === 0 ? a : i === 1 ? b : c;
      const col = colors[i];
      target.positions.push(point.x, point.y, point.z);
      target.colors.push(col.r, col.g, col.b);
    }
    target.triangleToQuad.push(quadIndex);
  }

  _pushFaceGrid(target, points, grid, quadIndex) {
    const { n, m, colors } = grid;
    const pointAt = (u, v) => {
      const a = (1 - u) * (1 - v) / 4;
      const b = (1 + u) * (1 - v) / 4;
      const c = (1 + u) * (1 + v) / 4;
      const d = (1 - u) * (1 + v) / 4;
      return new THREE.Vector3(
        a * points[0].x + b * points[1].x + c * points[2].x + d * points[3].x,
        a * points[0].y + b * points[1].y + c * points[2].y + d * points[3].y,
        a * points[0].z + b * points[1].z + c * points[2].z + d * points[3].z
      );
    };
    for (let row = 0; row < n - 1; row += 1) {
      for (let column = 0; column < m - 1; column += 1) {
        const u0 = -1 + 2 * column / (m - 1);
        const u1 = -1 + 2 * (column + 1) / (m - 1);
        const v0 = -1 + 2 * row / (n - 1);
        const v1 = -1 + 2 * (row + 1) / (n - 1);
        const a = pointAt(u0, v0);
        const b = pointAt(u1, v0);
        const c = pointAt(u1, v1);
        const d = pointAt(u0, v1);
        const i0 = row * m + column;
        const i1 = i0 + 1;
        const i3 = i0 + m;
        const i2 = i3 + 1;
        this._pushTriangle(target, a, b, c, [colors[i0], colors[i1], colors[i2]], quadIndex);
        this._pushTriangle(target, a, c, d, [colors[i0], colors[i2], colors[i3]], quadIndex);
      }
    }
  }

  _pushQuadFace(target, points, color, quadIndex, reverse = false) {
    const values = reverse ? [...points].reverse() : points;
    const colors = Array.isArray(color) ? (reverse ? [...color].reverse() : color) : color;
    if (Array.isArray(colors)) {
      this._pushTriangle(target, values[0], values[1], values[2], [colors[0], colors[1], colors[2]], quadIndex);
      this._pushTriangle(target, values[0], values[2], values[3], [colors[0], colors[2], colors[3]], quadIndex);
    } else {
      this._pushTriangle(target, values[0], values[1], values[2], colors, quadIndex);
      this._pushTriangle(target, values[0], values[2], values[3], colors, quadIndex);
    }
  }

  _addSegment(array, a, b) { array.push(a.x, a.y, a.z, b.x, b.y, b.z); }

  _selectedOutlinePoints(quad) {
    const base = quad.points ? quad.points.map(p => p.clone()) : quad.nodeKeys.map(key => this.state.nodes.get(key).clone());
    if (!this.options.extrude || Number(this.options.thicknessScale) <= 0) return { loops: [base], sides: [] };
    const normal = quad.normal.lengthSq() > 1e-18 ? quad.normal.clone().normalize() : computedNormal(base);
    const top = base.map((point, index) => point.clone().addScaledVector(quad.normals?.[index] ?? normal, quad.thicknesses[index] * Number(this.options.thicknessScale) * 0.5));
    const bottom = base.map((point, index) => point.clone().addScaledVector(quad.normals?.[index] ?? normal, -quad.thicknesses[index] * Number(this.options.thicknessScale) * 0.5));
    return { loops: [top, bottom], sides: top.map((point, index) => [point, bottom[index]]) };
  }

  _disposeObject(object) {
    if (!object) return;
    this.modelGroup.remove(object);
    object.geometry?.dispose();
    if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
    else object.material?.dispose();
  }

  _updateGrid() {
    if (this.state.bounds.isEmpty()) return;
    const size = this.state.bounds.getSize(new THREE.Vector3());
    const center = this.state.bounds.getCenter(new THREE.Vector3());
    const maxSize = Math.max(size.x, size.y, size.z, 1);
    this.grid.scale.setScalar(maxSize / 1200);
    this.grid.position.set(center.x, center.y, Math.min(this.state.bounds.min.z, 0));
    this.axes.scale.setScalar(Math.max(maxSize / 350, 0.25));
    this.axes.position.copy(center);
  }

  _fitDistance() {
    const size = this.state.bounds.getSize(new THREE.Vector3());
    const radius = Math.max(size.length() * 0.5, 1);
    const verticalFov = THREE.MathUtils.degToRad(this.camera.fov);
    const verticalDistance = radius / Math.sin(verticalFov * 0.5);
    const horizontalFov = 2 * Math.atan(Math.tan(verticalFov * 0.5) * this.camera.aspect);
    const horizontalDistance = radius / Math.sin(horizontalFov * 0.5);
    return Math.max(verticalDistance, horizontalDistance) * 1.08;
  }

  _emitLegend() {
    this.emit('legend', [...this.state.categoryColors.entries()].map(([label, color]) => ({ label, color: `#${color.getHexString()}` })));
  }

  _onPointerDown(event) {
    if (event.button !== 0) return;
    this._pointerStart = { x: event.clientX, y: event.clientY };
  }

  _onPointerUp(event) {
    if (!this.state.mesh || event.button !== 0 || !this._pointerStart) return;
    const moved = Math.hypot(event.clientX - this._pointerStart.x, event.clientY - this._pointerStart.y);
    this._pointerStart = null;
    if (moved > 5) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const overlayHit = this.pickOverlay?.();
    if (overlayHit) return;
    const hit = this.raycaster.intersectObject(this.state.mesh, false)[0];
    if (!hit || hit.faceIndex == null) { this.clearSelection(); return; }
    const quadIndex = this.state.triangleToQuad[hit.faceIndex];
    if (quadIndex != null) this.selectQuad(quadIndex);
  }

  _animate() {
    if (this.destroyed) return;
    const moving = this.controls.update();
    if (moving || this.needsRender) {
      this.renderer.render(this.scene, this.camera);
      this.needsRender = false;
    }
    requestAnimationFrame(() => this._animate());
  }
}
