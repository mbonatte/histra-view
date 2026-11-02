const labels = {name:'Download filename', nl:'Mesh size', width:'Width', height:'Height', material_key:'Material key', L:'Length', f:'Rise', Tb:'Bottom thickness', Tt:'Top thickness', Asx:'Left springing angle', Adx:'Right springing angle', S1:'Left offset', S2:'Right offset', Dz:'Elevation offset', H:'Height', Hf:'Foundation height', b2:'Width', B1f:'Foundation left', B3f:'Foundation right', W1f:'Foundation front', W3f:'Foundation back', H1:'Height 1', H2:'Height 2', H3:'Height 3'};
// C# enum values serialized in the HRX schema. Keep the authored value as an
// extra option so opening a file never silently rewrites an unknown setting.
const ENUMS = {
  ValueSetting: ['Min','Med','Max'], ValueSettingStrength: ['Min','Med','Max'],
  ConstitutiveLawFlex: ['ElastoPlasticDuctilityFixed','ElastoPlasticFracturalEnergyFixed','Linear'],
  ConstitutiveLawMasonryShear: ['Elastic','ElastoPlastic','ElastoPlasticDuctilityFixed','ElastoPlasticAndSoftening','ElastoPlasticFractureEnergyFixed','ElastoPlasticEnergySigmaInterpolation'],
  TensileCurveType: ['Elastic','LinearHardening','LinearSoftening','Exponential'],
  TensileCurveTypeVertical: ['Elastic','LinearHardening','LinearSoftening','Exponential'],
  CompressiveCurveType: ['Elastic','LinearHardening','LinearSoftening','Parabolic'],
  CompressiveCurveTypeVertical: ['Elastic','LinearHardening','LinearSoftening','Parabolic'],
  CriterioSnervamento: ['Linear','Coulomb','Cacovic'],
  SlidingYieldingDomainHor: ['Linear','Coulomb','Cacovic'],
  SlidingYieldingDomainVert: ['Linear','Coulomb','Cacovic'],
  SlidingYieldingDomainDir3: ['Linear','Coulomb','Cacovic'],
  UnloadTractionRockingHor: ['Nothing','Initial','Origin'], UnloadTractionRockingVer: ['Nothing','Initial','Origin'],
  UnloadCompressionRockingHor: ['Nothing','Initial','Origin'], UnloadCompressionRockingVer: ['Nothing','Initial','Origin'],
  UnloadShear: ['Nothing','Initial','Origin'],
  Method: ['LinearStep','DisplacementImposed','IndirectDisplacementControl','StandardNewtonRaphson','ModifiedNewtonRaphson','ArcLength','ArcLengthModified','StandardSecantLineSearch','StandardRegulaFalsiLineSearch','StandardBisectionLineSearch','StandardInitialInterpolatedLineSearch','ModifiedSecantLineSearch','ModifiedRegulaFalsiLineSearch','ModifiedBisectionLineSearch','ModifiedInitialInterpolatedLineSearch','KrylovNewton','Broyden','BFGS','AcceleratedNewton','PeriodicNewton'],
  IntegrationMethod: ['LoadControl','ArcLength','ArcLengthLinear','NewmarkMethod','HHTmethod','WilsonMethod'],
  ArcLengthProcedure: ['OnlyControlPoint','OnlyModelPointsSelected','AllDegreesOfFreedom'],
  AdapticConvergenceCriteria: ['ForceMoment','DispRotation','Work'],
  AdapticIntegrationScheme: ['Newmark','HHT'],
  TypeLoadDistribution: ['Force','Modal','Triangular','Adaptive','ShearFloor','LoadCombination'],
  ModalProcedure: ['SubspaceIterations','InverseIterations'],
  ModalConvergenceCriteria: ['Frquency','EigenVector'],
  DampingCriterion: ['Rayleigh','Stiffness','Caughey'],
  Typedirection: ['Simple','Cartesian','Polar'],
  Direction: ['X','Y','Z','Custom','Total','Analysis'],
  PdeltaEffect: ['None','EachStep','EachIteration'],
  PushModal_Type: ['Mass','Single','Custom'],
};
const node = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
const COLLECTIONS = [['material','Materials'], ['analysis','Analyses'], ['load_function','Load functions'], ['load_function_item','Load function points'], ['load_combination','Load combinations'], ['load_combination_item','Load combination items'], ['load_condition','Load conditions']];

export class Builder {
  constructor(container, showModel) { this.root = container; this.showModel = showModel; this.mode = 'create'; this.payload = null; this.catalog = null; this.source = null; this.materials = []; this.analyses = []; this.collections = {}; this.changes = new Map(); this.busy = false; this.initialized = false; }
  async activate() {
    if (this.initialized) return;
    this.initialized = true;
    try {
      this.payload = await this.json('/api/builder/defaults');
      try { this.catalog = await this.json('/api/builder/catalog'); } catch { this.catalog = null; }
      this.render();
    } catch (e) { this.root.textContent = e.message; this.initialized = false; }
  }
  async json(url, data) {
    const response = await fetch(url, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const body = await response.json(); if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`); return body;
  }
  field(parent, object, key) {
    const label = node('label', labels[key] || key), input = node('input');
    input.type = typeof object[key] === 'number' ? 'number' : 'text';
    if (input.type === 'number') input.step = 'any';
    input.value = object[key];
    input.addEventListener('change', () => { object[key] = input.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value; });
    label.append(input); parent.append(label);
  }
  fields(title, object, keys, parent = this.root) {
    const section = node('section'); section.className = 'builder-group'; section.append(node('h3', title));
    const grid = node('div'); grid.className = 'builder-grid';
    for (const key of keys) this.field(grid, object, key);
    section.append(grid); parent.append(section);
  }
  button(label, action, parent) { const b = node('button', label); b.type = 'button'; b.addEventListener('click', action); parent.append(b); return b; }
  render() {
    this.root.replaceChildren(); this.root.append(node('h2', 'Build an HRX model'));
    const mode = node('select'); mode.setAttribute('aria-label', 'Builder mode');
    mode.add(new Option('Create a bridge', 'create')); mode.add(new Option('Edit existing HRX', 'edit')); mode.value = this.mode;
    mode.addEventListener('change', () => { this.mode = mode.value; this.render(); }); this.root.append(mode);
    const actions = node('div'); actions.className = 'builder-actions';
    this.button('Preview model', () => this.run(false), actions).className = 'primary';
    this.button('Download HRX', () => this.run(true), actions); this.root.append(actions);
    this.status = node('p'); this.status.className = 'builder-status'; this.status.setAttribute('role', 'status'); this.root.append(this.status);
    if (this.mode === 'create') this.renderCreate(); else this.renderEdit();
  }
  renderCreate() {
    this.root.append(node('p', 'Define a parametric masonry bridge. Values use the builder’s native units. Preview generates the same HRX that will be downloaded.'));
    this.fields('General', this.payload, ['name', 'nl']);
    const collections = [['strips','Deck strip', ['width','height','material_key']], ['spans','Span',['L','f','Tb','Tt','Asx','Adx','S1','S2','Dz']], ['piers','Pier',['H','Hf','b2','B1f','B3f','W1f','W3f']]];
    for (const [key, title, fields] of collections) {
      this.payload[key].forEach((item, i) => {
        this.fields(`${title} ${i+1}`, item, fields);
        if (key !== 'piers') { const controls = node('div'); controls.className = 'builder-actions'; this.button(`Remove ${title.toLowerCase()}`, () => { if (this.payload[key].length > 1) { this.payload[key].splice(i, 1); if (key === 'spans') this.payload.piers.splice(Math.min(i, this.payload.piers.length - 1), 1); this.render(); } }, controls); this.root.append(controls); }
      });
      if (key !== 'piers') { const controls = node('div'); controls.className = 'builder-actions'; this.button(`+ Add ${title.toLowerCase()}`, () => { this.payload[key].push(structuredClone(this.payload[key].at(-1))); if (key === 'spans') this.payload.piers.push(structuredClone(this.payload.piers.at(-1) || {H:150,Hf:60,b2:70,B1f:30,B3f:30,W1f:20,W3f:20})); this.render(); }, controls); this.root.append(controls); }
    }
    for (const [key,title] of [['left_abutment','Left abutment'],['right_abutment','Right abutment']]) this.fields(title, this.payload[key], ['H','Hf','b2','B1f','B3f','W1f','W3f']);
    this.fields('Elevation', this.payload.elevation, ['H1','H2','H3']);
  }
  async loadSource(encoded, name, index = 0) {
    const data = await this.json('/api/builder/inspect', {source: encoded});
    this.source = encoded; this.sourceName = name; this.materials = data.materials; this.analyses = data.analyses;
    this.collections = data.collections; this.changes.clear(); this.selectedKind = this.selectedKind || 'material';
    this.selectedObject = index; this.selectedNode = 0; this.render();
  }
  renderEdit() {
    this.root.append(node('p', 'Edit masonry materials, analyses and load settings. Add, duplicate or delete materials and analyses. Enter valid native values; fields are not engineering-validated. Recompute results after changes.'));
    const file = node('input'); file.type = 'file'; file.accept = '.hrx,.xml'; file.setAttribute('aria-label', 'Open HRX to edit');
    file.addEventListener('change', async () => {
      const selected = file.files[0]; if (!selected) return;
      try {
        if (selected.size > 32 * 1024 * 1024) throw new Error('Choose an HRX file of at most 32 MiB.');
        const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('Could not read file.')); reader.readAsDataURL(selected); });
        await this.loadSource(encoded, selected.name);
      } catch (e) { this.status.textContent = e.message; this.status.classList.add('error'); }
    }); this.root.append(file);
    if (!this.source) return;
    this.root.append(node('p', `${this.sourceName} · ${this.materials.length} materials · ${this.analyses.length} analyses`));
    const kind = node('select'); kind.setAttribute('aria-label', 'Property category');
    for (const [value, label] of COLLECTIONS) kind.add(new Option(label, value));
    kind.value = this.selectedKind || 'material';
    kind.addEventListener('change', () => { this.selectedKind = kind.value; this.selectedObject = 0; this.selectedNode = 0; this.render(); }); this.root.append(kind);
    const items = this.collections[kind.value];
    if (!items.length) { this.root.append(node('p', 'No entries in this file.')); return; }
    const select = node('select'); select.setAttribute('aria-label', 'Model entry');
    items.forEach((item, i) => select.add(new Option(`${item.name} [${item.key}]`, i)));
    select.value = this.selectedObject || 0; select.addEventListener('change', () => { this.selectedObject = Number(select.value); this.selectedNode = 0; this.render(); }); this.root.append(select);
    const i = this.selectedObject || 0, item = items[i];
    this.renderManage(kind.value, items, i);
    if (!item.nodes.length) { this.root.append(node('p', 'No editable attributes.')); return; }
    const section = node('select'); section.setAttribute('aria-label', 'Settings section');
    item.nodes.forEach((entry, n) => section.add(new Option(entry.path.length ? `${entry.tag} (${entry.path.join('.')})` : 'General settings', n)));
    section.value = this.selectedNode || 0; section.addEventListener('change', () => { this.selectedNode = Number(section.value); this.render(); }); this.root.append(section);
    const entry = item.nodes[this.selectedNode || 0], grid = node('div'); grid.className = 'builder-grid';
    for (const [key, original] of Object.entries(entry.attributes)) {
      const id = `${kind.value}:${i}:${entry.path.join('.')}:${key}`, label = node('label', key);
      let input;
      if (kind.value === 'analysis' && !entry.path.length && key === 'AnalysisType' && ['1','2','3','4','5'].includes(original)) {
        input = node('select');
        for (const [value, text] of [['1','Static linear'],['2','Static nonlinear'],['3','Dynamic linear'],['4','Dynamic nonlinear'],['5','Modal']]) input.add(new Option(text, value));
      } else if (ENUMS[key]) {
        input = node('select');
        for (const value of [...new Set([...ENUMS[key], original])]) input.add(new Option(value, value));
      } else if (['true', 'false'].includes(original)) {
        input = node('select'); input.add(new Option('True', 'true')); input.add(new Option('False', 'false'));
      } else input = node('input');
      input.value = this.changes.get(id)?.value ?? original;
      input.addEventListener('change', () => { if (input.value === original) this.changes.delete(id); else this.changes.set(id, {collection:kind.value, index:i, node:entry.path, attribute:key, value:input.value}); });
      label.append(input); grid.append(label);
    }
    this.root.append(grid);
  }
  renderManage(kind, items, index) {
    if (!['material', 'analysis'].includes(kind) || !this.catalog) return;
    const actions = node('div'); actions.className = 'builder-actions';
    if (kind === 'analysis') {
      const add = node('select'); add.setAttribute('aria-label', 'Analysis template');
      for (const name of this.catalog.analyses) add.add(new Option(name, name));
      actions.append(add); this.button('Add analysis', () => this.apply({op:'add_analysis', template:add.value}, items.length), actions);
    } else {
      const add = node('select'); add.setAttribute('aria-label', 'Material template');
      for (const template of this.catalog.materials) add.add(new Option(`${template.name} [${template.key}]`, template.key));
      actions.append(add); this.button('Add material', () => this.apply({op:'add_material', template:add.value}, items.length), actions);
    }
    this.button('Duplicate', () => this.apply({op:kind === 'analysis' ? 'duplicate_analysis' : 'duplicate_material', duplicate:index}, items.length), actions);
    this.button('Delete', () => this.apply({op:kind === 'analysis' ? 'delete_analysis' : 'delete_material', index}, Math.max(0, index - 1)), actions);
    this.root.append(actions);
  }
  async apply(operation, selected) {
    if (this.busy) return;
    this.busy = true; this.status.classList.remove('error'); this.status.textContent = 'Applying change…';
    try {
      const data = await this.json('/api/builder/apply', {mode:'edit', source:this.source, changes:[...this.changes.values()], operations:[operation]});
      this.source = data.source; this.collections = data.inspection.collections;
      this.materials = data.inspection.materials; this.analyses = data.inspection.analyses;
      this.changes.clear(); this.selectedObject = Math.max(0, Math.min(selected, (this.collections[this.selectedKind] || []).length - 1)); this.selectedNode = 0;
      this.render(); this.status.textContent = 'Change applied. Download HRX to save.';
    } catch (e) { this.status.textContent = e.message; this.status.classList.add('error'); }
    finally { this.busy = false; }
  }
  async run(download) {
    if (this.busy) return;
    if (this.mode === 'edit' && !this.source) { this.status.textContent = 'Choose an HRX file first.'; return; }
    this.busy = true; this.status.classList.remove('error'); this.status.textContent = download ? 'Preparing HRX…' : 'Generating preview…';
    const request = this.mode === 'create' ? {mode:'create', payload:this.payload} : {mode:'edit', source:this.source, changes:[...this.changes.values()]};
    try {
      if (download) {
        const response = await fetch('/api/builder/export', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(request)});
        if (!response.ok) throw new Error((await response.json()).error || 'Export failed.');
        const url = URL.createObjectURL(await response.blob()), a = node('a'); a.href = url; a.download = this.mode === 'edit' ? this.sourceName.replace(/\.(hrx|xml)$/i, '') + '-edited.hrx' : (this.payload.name || 'bridge').replace(/[^a-z0-9_-]/gi, '_') + '.hrx'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        this.status.textContent = 'HRX downloaded.';
      } else { const model = await this.json('/api/builder/preview', request); this.showModel(model); this.status.textContent = 'Preview ready. Download HRX to save your changes.'; }
    } catch (e) { this.status.textContent = e.message; this.status.classList.add('error'); }
    finally { this.busy = false; }
  }
}
