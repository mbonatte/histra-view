const isMasonryItem = item => {
  const a = item?.attributes || item?.nodes?.[0]?.attributes || {};
  return a.PurposeType === 'MasonryMaterial' || a.Ehor !== undefined;
};

const labels = {
  name: 'Download filename',
  nl: 'Mesh size',
  width: 'Width',
  height: 'Height',
  material_key: 'Material key',
  material_pulvino_key: 'Pulvino material key',
  material_foundation_key: 'Foundation material key',
  Kz: 'Subgrade modulus Kz',
  L: 'Length',
  f: 'Rise',
  Tb: 'Bottom thickness',
  Tt: 'Top thickness',
  Asx: 'Left springing angle',
  Adx: 'Right springing angle',
  S1: 'Left offset',
  S2: 'Right offset',
  Dz: 'Elevation offset',
  H: 'Height',
  Hf: 'Foundation height',
  b2: 'Width',
  B1f: 'Foundation left',
  B3f: 'Foundation right',
  W1f: 'Foundation front',
  W3f: 'Foundation back',
  H1: 'Height 1',
  H2: 'Height 2',
  H3: 'Height 3',
  layer1_material_key: 'Layer 1 material key',
  layer2_material_key: 'Layer 2 material key',
  layer3_material_key: 'Layer 3 material key',
};

// C# enum values serialized in the HRX schema. Keep the authored value as an
// extra option so opening a file never silently rewrites an unknown setting.
const ENUMS = {
  ValueSetting: ['Min', 'Med', 'Max'],
  ValueSettingStrength: ['Min', 'Med', 'Max'],
  ConstitutiveLawFlex: ['ElastoPlasticDuctilityFixed', 'ElastoPlasticFracturalEnergyFixed', 'Linear'],
  ConstitutiveLawMasonryShear: ['Elastic', 'ElastoPlastic', 'ElastoPlasticDuctilityFixed', 'ElastoPlasticAndSoftening', 'ElastoPlasticFractureEnergyFixed', 'ElastoPlasticEnergySigmaInterpolation'],
  TensileCurveType: ['Elastic', 'LinearHardening', 'LinearSoftening', 'Exponential'],
  TensileCurveTypeVertical: ['Elastic', 'LinearHardening', 'LinearSoftening', 'Exponential'],
  CompressiveCurveType: ['Elastic', 'LinearHardening', 'LinearSoftening', 'Parabolic'],
  CompressiveCurveTypeVertical: ['Elastic', 'LinearHardening', 'LinearSoftening', 'Parabolic'],
  CriterioSnervamento: ['Linear', 'Coulomb', 'Cacovic'],
  SlidingYieldingDomainHor: ['Linear', 'Coulomb', 'Cacovic'],
  SlidingYieldingDomainVert: ['Linear', 'Coulomb', 'Cacovic'],
  SlidingYieldingDomainDir3: ['Linear', 'Coulomb', 'Cacovic'],
  UnloadTractionRockingHor: ['Nothing', 'Initial', 'Origin'],
  UnloadTractionRockingVer: ['Nothing', 'Initial', 'Origin'],
  UnloadCompressionRockingHor: ['Nothing', 'Initial', 'Origin'],
  UnloadCompressionRockingVer: ['Nothing', 'Initial', 'Origin'],
  UnloadShear: ['Nothing', 'Initial', 'Origin'],
  Method: ['LinearStep', 'DisplacementImposed', 'IndirectDisplacementControl', 'StandardNewtonRaphson', 'ModifiedNewtonRaphson', 'ArcLength', 'ArcLengthModified', 'StandardSecantLineSearch', 'StandardRegulaFalsiLineSearch', 'StandardBisectionLineSearch', 'StandardInitialInterpolatedLineSearch', 'ModifiedSecantLineSearch', 'ModifiedRegulaFalsiLineSearch', 'ModifiedBisectionLineSearch', 'ModifiedInitialInterpolatedLineSearch', 'KrylovNewton', 'Broyden', 'BFGS', 'AcceleratedNewton', 'PeriodicNewton'],
  IntegrationMethod: ['LoadControl', 'ArcLength', 'ArcLengthLinear', 'NewmarkMethod', 'HHTmethod', 'WilsonMethod'],
  ArcLengthProcedure: ['OnlyControlPoint', 'OnlyModelPointsSelected', 'AllDegreesOfFreedom'],
  AdapticConvergenceCriteria: ['ForceMoment', 'DispRotation', 'Work'],
  AdapticIntegrationScheme: ['Newmark', 'HHT'],
  TypeLoadDistribution: ['Force', 'Modal', 'Triangular', 'Adaptive', 'ShearFloor', 'LoadCombination'],
  ModalProcedure: ['SubspaceIterations', 'InverseIterations', 'SparseBlockInverseSubspace'],
  ModalConvergenceCriteria: ['Frquency', 'EigenVector'],
  DampingCriterion: ['Rayleigh', 'Stiffness', 'Caughey'],
  Typedirection: ['Simple', 'Cartesian', 'Polar'],
  Direction: ['X', 'Y', 'Z', 'Custom', 'Total', 'Analysis'],
  PdeltaEffect: ['None', 'EachStep', 'EachIteration'],
  PushModal_Type: ['Mass', 'Single', 'Custom'],
};

const node = (tag, text) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  return e;
};

const COLLECTIONS = [
  ['material', 'Materials'],
  ['analysis', 'Analyses'],
  ['load_function', 'Load functions'],
  ['load_function_item', 'Load function points'],
  ['load_combination', 'Load combinations'],
  ['load_combination_item', 'Load combination items'],
  ['load_condition', 'Load conditions'],
];

export class Builder {
  constructor(container, showModel) {
    this.root = container;
    this.showModel = showModel;
    this.mode = 'create';
    this.payload = null;
    this.catalog = null;
    // Edit-mode state
    this.source = null;
    this.sourceName = null;
    this.materials = [];
    this.analyses = [];
    this.collections = {};
    this.changes = new Map();
    // Create-mode material/analysis state
    this.createSection = 'geometry';
    this.materialTab = 'general';
    this.openGroups = new Set(['general', 'mat:general', 'mat:rocking:0', 'mat:rocking:1', 'mat:rocking:2', 'mat:shear:0', 'mat:shear:1', 'mat:shear:2', 'mat:sliding:0']);
    this.openItems = new Set(['strips:0', 'spans:0', 'piers:0', 'abutments:left_abutment']);
    this.createMaterials = [];
    this.createAnalyses = [];
    this.createCollections = {};
    this.createSteps = [];
    this.createChanges = new Map();
    // Edit-mode active section
    this.editSection = 'material';
    this.selectedLoadKind = 'load_function';
    // Currently loaded viewer HRX bytes (base64) for one-click editing
    this.viewerSource = null;
    this.viewerSourceName = null;
    this.loadingViewerSource = false;
    this.busy = false;
    this.initialized = false;
    this.activatingPromise = null;
  }

  async activate() {
    if (this.initialized) return;
    if (this.activatingPromise) return this.activatingPromise;
    this.initialized = true;
    this.activatingPromise = (async () => {
      try {
        const defaults = await this.json('/api/builder/defaults');
        const { inspection, ...payload } = defaults;
        this.payload = payload;
        if (inspection) {
          this.createMaterials = inspection.materials || [];
          this.createAnalyses = inspection.analyses || [];
          this.createCollections = inspection.collections || {};
        }
        try {
          this.catalog = await this.json('/api/builder/catalog');
        } catch {
          this.catalog = null;
        }
        this.render();
      } catch (e) {
        this.root.textContent = e.message;
        this.initialized = false;
      } finally {
        this.activatingPromise = null;
      }
    })();
    return this.activatingPromise;
  }

  async openEditor(kind = 'material', key = null) {
    location.hash = 'build';
    await this.activate();
    if (this.viewerSource) {
      this.mode = 'edit';
      if (!this.source || this.source !== this.viewerSource) {
        await this.loadSource(this.viewerSource, this.viewerSourceName || 'Model.hrx');
      }
      this.editSection = kind === 'analysis' ? 'analysis' : 'material';
      this.selectedKind = this.editSection;
      const list = this.collections[this.selectedKind] || [];
      const idx = key != null ? list.findIndex(item => String(item.key) === String(key)) : 0;
      this.selectedObject = idx >= 0 ? idx : 0;
      this.selectedNode = 0;
      this.render();
    } else {
      this.mode = 'create';
      this.createSection = kind === 'analysis' ? 'analysis' : 'material';
      this.selectedKind = this.createSection;
      const list = this.createCollections[this.selectedKind] || [];
      const idx = key != null ? list.findIndex(item => String(item.key) === String(key)) : 0;
      this.selectedObject = idx >= 0 ? idx : 0;
      this.selectedNode = 0;
      this.render();
    }
  }

  setViewerSource(encoded, name) {
    this.viewerSource = encoded;
    this.viewerSourceName = name;
    if (this.initialized && this.mode === 'edit' && !this.source) {
      this.render();
    }
  }

  async json(url, data) {
    const response = await fetch(
      url,
      data === undefined
        ? {}
        : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }
    );
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  }

  field(parent, object, key, fallbackValue, onChange = null) {
    if (object[key] === undefined && fallbackValue !== undefined) {
      object[key] = fallbackValue;
    }
    const label = node('label', labels[key] || key);
    const input = node('input');
    input.type = typeof object[key] === 'number' ? 'number' : 'text';
    if (input.type === 'number') input.step = 'any';
    input.value = object[key] ?? '';
    input.addEventListener('change', () => {
      object[key] = input.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value;
      if (onChange) onChange();
    });
    label.append(input);
    parent.append(label);
  }

  fieldsGrid(object, keys, parent, defaultsMap = {}, onChange = null) {
    const grid = node('div');
    grid.className = 'builder-grid';
    for (const key of keys) this.field(grid, object, key, defaultsMap[key], onChange);
    parent.append(grid);
  }

  collapsibleGroup(id, title, badgeText, parent = this.root) {
    const details = node('details');
    details.className = 'builder-collapse';
    details.open = this.openGroups.has(id);
    details.addEventListener('toggle', () => {
      if (details.open) this.openGroups.add(id);
      else this.openGroups.delete(id);
    });
    const summary = node('summary');
    summary.append(node('span', title));
    if (badgeText !== undefined && badgeText !== '') {
      const badge = node('span', String(badgeText));
      badge.className = 'builder-collapse-badge';
      summary.append(badge);
    }
    const body = node('div');
    body.className = 'builder-collapse-body';
    details.append(summary, body);
    parent.append(details);
    return body;
  }

  collapsibleItem(id, title, getMetaText, parent) {
    const details = node('details');
    details.className = 'builder-item-collapse';
    details.open = this.openItems.has(id);
    details.addEventListener('toggle', () => {
      if (details.open) this.openItems.add(id);
      else this.openItems.delete(id);
    });
    const summary = node('summary');
    summary.append(node('span', title));
    const meta = node('span', getMetaText ? getMetaText() : '');
    meta.className = 'builder-item-meta';
    summary.append(meta);
    const body = node('div');
    body.className = 'builder-item-body';
    details.append(summary, body);
    parent.append(details);
    return {
      body,
      updateMeta: () => {
        if (getMetaText) meta.textContent = getMetaText();
      },
    };
  }

  button(label, action, parent) {
    const b = node('button', label);
    b.type = 'button';
    b.addEventListener('click', action);
    parent.append(b);
    return b;
  }

  render() {
    this.root.replaceChildren();
    this.root.append(node('h2', 'Build an HRX model'));
    const mode = node('select');
    mode.setAttribute('aria-label', 'Builder mode');
    mode.add(new Option('Create a bridge', 'create'));
    mode.add(new Option('Edit existing HRX', 'edit'));
    mode.value = this.mode;
    mode.addEventListener('change', () => {
      this.mode = mode.value;
      this.render();
    });
    this.root.append(mode);

    const actions = node('div');
    actions.className = 'builder-actions';
    this.button('Preview model', () => this.run(false), actions).className = 'primary';
    this.button('Download HRX', () => this.run(true), actions);
    this.root.append(actions);

    this.status = node('p');
    this.status.className = 'builder-status';
    this.status.setAttribute('role', 'status');
    this.root.append(this.status);

    if (this.mode === 'create') this.renderCreate();
    else this.renderEdit();
  }

  renderTabs(tabs, current, onSelect) {
    const bar = node('div');
    bar.className = 'builder-tabs';
    bar.setAttribute('role', 'tablist');
    for (const [key, label] of tabs) {
      const btn = node('button', label);
      btn.type = 'button';
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', String(key === current));
      if (key === current) btn.className = 'active';
      btn.addEventListener('click', () => onSelect(key));
      bar.append(btn);
    }
    this.root.append(bar);
  }

  renderCreate() {
    this.root.append(
      node(
        'p',
        'Define a parametric masonry bridge and customize its materials, analyses, and load settings. Preview generates the same HRX that will be downloaded.'
      )
    );
    const masonryCount = this.createMaterials.filter(isMasonryItem).length;
    this.renderTabs(
      [
        ['geometry', 'Geometry'],
        ['material', `Materials (${masonryCount})`],
        ['analysis', `Analyses (${this.createAnalyses.length})`],
        ['loads', 'Loads'],
      ],
      this.createSection,
      section => {
        this.createSection = section;
        if (section === 'material' || section === 'analysis') {
          this.selectedKind = section;
          this.selectedObject = 0;
          this.selectedNode = 0;
        } else if (section === 'loads') {
          this.selectedKind = this.selectedLoadKind || 'load_function';
          this.selectedObject = 0;
          this.selectedNode = 0;
        }
        this.render();
      }
    );

    if (this.createSection !== 'geometry') {
      this.renderCollectionEditor({
        collections: this.createCollections,
        changes: this.createChanges,
        isCreate: true,
        fixedCategory: this.createSection === 'loads' ? null : this.createSection,
      });
      return;
    }

    const generalBody = this.collapsibleGroup('general', 'General', `nl = ${this.payload.nl ?? ''}`);
    this.fieldsGrid(this.payload, ['name', 'nl'], generalBody);

    const collections = [
      [
        'strips',
        'Deck strips',
        'Deck strip',
        ['width', 'height', 'material_key'],
        { material_key: 0 },
        item => `W ${item.width ?? '—'} · H ${item.height ?? '—'}`,
      ],
      [
        'spans',
        'Spans',
        'Span',
        ['L', 'f', 'Tb', 'Tt', 'Asx', 'Adx', 'S1', 'S2', 'Dz', 'material_key', 'material_pulvino_key'],
        { material_key: 18, material_pulvino_key: 22 },
        item => `L ${item.L ?? '—'} · f ${item.f ?? '—'}`,
      ],
      [
        'piers',
        'Piers',
        'Pier',
        ['H', 'Hf', 'b2', 'B1f', 'B3f', 'W1f', 'W3f', 'material_key', 'material_foundation_key', 'Kz'],
        { material_key: 18, material_foundation_key: 141, Kz: 0.1 },
        item => `H ${item.H ?? '—'} · b2 ${item.b2 ?? '—'}`,
      ],
    ];
    for (const [key, groupTitle, itemTitle, fieldKeys, defaultsMap, metaFn] of collections) {
      const items = this.payload[key] || [];
      const groupBody = this.collapsibleGroup(key, groupTitle, items.length);
      if (!items.length) {
        groupBody.append(node('p', 'No intermediate piers (single-span bridge).'));
      }
      items.forEach((item, i) => {
        const itemId = `${key}:${i}`;
        const { body: itemBody, updateMeta } = this.collapsibleItem(itemId, `${itemTitle} ${i + 1}`, () => metaFn(item), groupBody);
        this.fieldsGrid(item, fieldKeys, itemBody, defaultsMap, updateMeta);
        if (key !== 'piers' && items.length > 1) {
          const controls = node('div');
          controls.className = 'builder-actions';
          this.button(
            `Remove ${itemTitle.toLowerCase()} ${i + 1}`,
            () => {
              if (this.payload[key].length > 1) {
                this.payload[key].splice(i, 1);
                if (key === 'spans') this.payload.piers.splice(Math.min(i, this.payload.piers.length - 1), 1);
                this.render();
              }
            },
            controls
          );
          itemBody.append(controls);
        }
      });
      if (key !== 'piers') {
        const controls = node('div');
        controls.className = 'builder-actions';
        this.button(
          `+ Add ${itemTitle.toLowerCase()}`,
          () => {
            const newIdx = this.payload[key].length;
            this.payload[key].push(structuredClone(this.payload[key].at(-1)));
            this.openGroups.add(key);
            this.openItems.add(`${key}:${newIdx}`);
            if (key === 'spans') {
              const newPierIdx = this.payload.piers.length;
              this.payload.piers.push(
                structuredClone(
                  this.payload.piers.at(-1) || {
                    H: 150, Hf: 60, b2: 70, B1f: 30, B3f: 30, W1f: 20, W3f: 20, material_key: 18, material_foundation_key: 141, Kz: 0.1,
                  }
                )
              );
              this.openItems.add(`piers:${newPierIdx}`);
            }
            this.render();
          },
          controls
        );
        groupBody.append(controls);
      }
    }

    const abutmentsBody = this.collapsibleGroup('abutments', 'Abutments', '2');
    for (const [key, title] of [['left_abutment', 'Left abutment'], ['right_abutment', 'Right abutment']]) {
      const item = this.payload[key];
      const { body: itemBody, updateMeta } = this.collapsibleItem(
        `abutments:${key}`,
        title,
        () => `H ${item.H ?? '—'} · b2 ${item.b2 ?? '—'}`,
        abutmentsBody
      );
      this.fieldsGrid(
        item,
        ['H', 'Hf', 'b2', 'B1f', 'B3f', 'W1f', 'W3f', 'material_key', 'material_foundation_key', 'Kz'],
        itemBody,
        { material_key: 18, material_foundation_key: 141, Kz: 0.1 },
        updateMeta
      );
    }

    const elevationBody = this.collapsibleGroup(
      'elevation',
      'Elevation & layers',
      `${this.payload.elevation.H1 ?? '—'} / ${this.payload.elevation.H2 ?? '—'} / ${this.payload.elevation.H3 ?? '—'}`
    );
    this.fieldsGrid(
      this.payload.elevation,
      ['H1', 'H2', 'H3', 'layer1_material_key', 'layer2_material_key', 'layer3_material_key'],
      elevationBody,
      { layer1_material_key: 19, layer2_material_key: 20, layer3_material_key: 21 }
    );
  }

  async loadSource(encoded, name, index = 0) {
    const data = await this.json('/api/builder/inspect', { source: encoded });
    this.source = encoded;
    this.sourceName = name;
    this.materials = data.materials;
    this.analyses = data.analyses;
    this.collections = data.collections;
    this.changes.clear();
    this.selectedKind = this.selectedKind || 'material';
    this.selectedObject = index;
    this.selectedNode = 0;
    this.render();
  }

  renderEdit() {
    this.root.append(
      node(
        'p',
        'Edit masonry materials, analyses and load settings. Add, duplicate or delete materials and analyses. Enter valid native values; fields are not engineering-validated. Recompute results after changes.'
      )
    );
    const file = node('input');
    file.type = 'file';
    file.accept = '.hrx,.xml';
    file.setAttribute('aria-label', 'Open HRX to edit');
    file.addEventListener('change', async () => {
      const selected = file.files[0];
      if (!selected) return;
      try {
        if (selected.size > 32 * 1024 * 1024) throw new Error('Choose an HRX file of at most 32 MiB.');
        const encoded = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result.split(',')[1]);
          reader.onerror = () => reject(new Error('Could not read file.'));
          reader.readAsDataURL(selected);
        });
        await this.loadSource(encoded, selected.name);
      } catch (e) {
        this.status.textContent = e.message;
        this.status.classList.add('error');
      }
    });
    this.root.append(file);

    if (this.viewerSource && !this.source && !this.loadingViewerSource) {
      this.loadingViewerSource = true;
      this.loadSource(this.viewerSource, this.viewerSourceName || 'Model.hrx').finally(() => {
        this.loadingViewerSource = false;
      });
    } else if (this.viewerSource && this.source !== this.viewerSource) {
      const viewerActions = node('div');
      viewerActions.className = 'builder-actions';
      this.button(
        `Edit model open in viewer (${this.viewerSourceName || 'Model.hrx'})`,
        () => this.loadSource(this.viewerSource, this.viewerSourceName || 'Model.hrx'),
        viewerActions
      );
      this.root.append(viewerActions);
    }

    if (!this.source) return;
    const masonryCount = this.materials.filter(isMasonryItem).length;
    this.root.append(node('p', `${this.sourceName} · ${masonryCount} masonry materials · ${this.analyses.length} analyses`));
    this.renderTabs(
      [
        ['material', `Materials (${masonryCount})`],
        ['analysis', `Analyses (${this.analyses.length})`],
        ['loads', 'Loads'],
      ],
      this.editSection,
      section => {
        this.editSection = section;
        if (section === 'material' || section === 'analysis') {
          this.selectedKind = section;
          this.selectedObject = 0;
          this.selectedNode = 0;
        } else {
          this.selectedKind = this.selectedLoadKind || 'load_function';
          this.selectedObject = 0;
          this.selectedNode = 0;
        }
        this.render();
      }
    );
    this.renderCollectionEditor({
      collections: this.collections,
      changes: this.changes,
      isCreate: false,
      fixedCategory: this.editSection === 'loads' ? null : this.editSection,
    });
  }

  renderCollectionEditor({ collections, changes, isCreate, fixedCategory = null }) {
    let activeKind = fixedCategory || this.selectedKind || 'material';
    if (!fixedCategory) {
      const kind = node('select');
      kind.setAttribute('aria-label', 'Property category');
      const loadCategories = COLLECTIONS.filter(([value]) => !['material', 'analysis'].includes(value));
      for (const [value, label] of loadCategories) kind.add(new Option(label, value));
      if (!loadCategories.some(([value]) => value === activeKind)) {
        activeKind = 'load_function';
        this.selectedKind = activeKind;
      }
      kind.value = activeKind;
      kind.addEventListener('change', () => {
        this.selectedKind = kind.value;
        this.selectedLoadKind = kind.value;
        this.selectedObject = 0;
        this.selectedNode = 0;
        this.render();
      });
      this.root.append(kind);
    } else {
      this.selectedKind = fixedCategory;
    }

    const allItems = collections[activeKind] || [];
    const indexedItems = activeKind === 'material'
      ? allItems.map((item, idx) => ({ item, idx })).filter(({ item }) => isMasonryItem(item))
      : allItems.map((item, idx) => ({ item, idx }));
    if (!indexedItems.length) {
      this.root.append(node('p', 'No entries in this file.'));
      return;
    }

    const select = node('select');
    select.setAttribute('aria-label', 'Model entry');
    indexedItems.forEach(({ item, idx }) => select.add(new Option(`${item.name} [${item.key}]`, idx)));
    const validSelected = indexedItems.some(({ idx }) => idx === this.selectedObject)
      ? this.selectedObject
      : indexedItems[0].idx;
    this.selectedObject = validSelected;
    select.value = validSelected;
    select.addEventListener('change', () => {
      this.selectedObject = Number(select.value);
      this.selectedNode = 0;
      this.render();
    });
    this.root.append(select);

    const item = allItems[validSelected];
    this.renderManage(activeKind, allItems, validSelected, isCreate);
    if (!item.nodes.length) {
      this.root.append(node('p', 'No editable attributes.'));
      return;
    }

    if (activeKind === 'material') {
      this.renderMaterialEditor(item, validSelected, changes);
      return;
    }

    const section = node('select');
    section.setAttribute('aria-label', 'Settings section');
    item.nodes.forEach((entry, n) =>
      section.add(new Option(entry.path.length ? `${entry.tag} (${entry.path.join('.')})` : 'General settings', n))
    );
    const nodeIdx = Math.max(0, Math.min(this.selectedNode || 0, item.nodes.length - 1));
    section.value = nodeIdx;
    section.addEventListener('change', () => {
      this.selectedNode = Number(section.value);
      this.render();
    });
    this.root.append(section);

    const entry = item.nodes[nodeIdx];
    const grid = node('div');
    grid.className = 'builder-grid';
    for (const [key, original] of Object.entries(entry.attributes)) {
      const id = `${activeKind}:${validSelected}:${entry.path.join('.')}:${key}`;
      const label = node('label', key);
      let input;
      if (activeKind === 'analysis' && !entry.path.length && key === 'AnalysisType' && ['1', '2', '3', '4', '5'].includes(original)) {
        input = node('select');
        for (const [value, text] of [['1', 'Static linear'], ['2', 'Static nonlinear'], ['3', 'Dynamic linear'], ['4', 'Dynamic nonlinear'], ['5', 'Modal']]) {
          input.add(new Option(text, value));
        }
      } else if (ENUMS[key]) {
        input = node('select');
        for (const value of [...new Set([...ENUMS[key], original])]) input.add(new Option(value, value));
      } else if (['true', 'false'].includes(original)) {
        input = node('select');
        input.add(new Option('True', 'true'));
        input.add(new Option('False', 'false'));
      } else {
        input = node('input');
      }
      input.value = changes.get(id)?.value ?? original;
      input.addEventListener('change', () => {
        if (input.value === original) changes.delete(id);
        else changes.set(id, { collection: activeKind, index: validSelected, node: entry.path, attribute: key, value: input.value });
      });
      label.append(input);
      grid.append(label);
    }
    this.root.append(grid);
  }

  renderMaterialEditor(item, selectedIndex, changes) {
    const entry = item.nodes[0];
    const attrs = entry.attributes;
    const getVal = key => changes.get(`material:${selectedIndex}::${key}`)?.value ?? attrs[key];
    const setVal = (key, val) => {
      const id = `material:${selectedIndex}::${key}`;
      const original = attrs[key];
      if (val === original) changes.delete(id);
      else changes.set(id, { collection: 'material', index: selectedIndex, node: [], attribute: key, value: val });
      if (attrs.SimpleMode === 'true') {
        changes.set(`material:${selectedIndex}::SimpleMode`, {
          collection: 'material',
          index: selectedIndex,
          node: [],
          attribute: 'SimpleMode',
          value: 'false',
        });
      }
    };

    const addAttrField = (parent, labelText, key, customOptions = null, rerenderOnChange = false) => {
      if (!key || attrs[key] === undefined) return;
      const original = attrs[key];
      const label = node('label', labelText);
      let input;
      if (customOptions) {
        input = node('select');
        for (const [val, txt] of customOptions) input.add(new Option(txt, val));
      } else if (ENUMS[key]) {
        input = node('select');
        for (const val of [...new Set([...ENUMS[key], original])]) {
          input.add(new Option(val.replace(/([a-z])([A-Z])/g, '$1 $2'), val));
        }
      } else if (['true', 'false'].includes(original)) {
        input = node('select');
        input.add(new Option('Yes', 'true'));
        input.add(new Option('No', 'false'));
      } else {
        input = node('input');
      }
      input.value = getVal(key) ?? '';
      input.addEventListener('change', () => {
        setVal(key, input.value);
        if (rerenderOnChange) this.render();
      });
      label.append(input);
      parent.append(label);
    };

    this.renderTabs(
      [
        ['general', 'General'],
        ['rocking', 'Rocking'],
        ['shear', 'Shear'],
        ['sliding', 'Sliding'],
      ],
      this.materialTab || 'general',
      tab => {
        this.materialTab = tab;
        this.render();
      }
    );

    const tab = this.materialTab || 'general';
    if (tab === 'general') {
      const idBody = this.collapsibleGroup('mat:general', 'Identification & basic properties', 'Advanced');
      const grid = node('div');
      grid.className = 'builder-grid';
      addAttrField(grid, 'Name', 'Name');
      addAttrField(grid, 'Description', 'Description');
      addAttrField(grid, 'Specific weight, W', attrs.w !== undefined ? 'w' : 'Gamma');
      addAttrField(grid, 'Young’s modulus, E', 'Ehor');
      addAttrField(grid, 'Shear modulus, G', 'Gd');
      addAttrField(grid, 'Compressive strength, fm', 'FmHor');
      addAttrField(grid, 'Tensile strength, ft', 'FtmHor');
      addAttrField(grid, 'Shear strength, τ₀', 'fvk0d');
      addAttrField(grid, 'Cohesion, c', 'CohesionSlidingHor');
      addAttrField(grid, 'Friction ratio, μ (sliding)', 'FrictionRatioSlidingHor');
      addAttrField(grid, 'Friction ratio, μ (shear)', 'FrictionRatioShear');
      idBody.append(grid);
      return;
    }

    if (tab === 'rocking') {
      const ort = getVal('ortpf') === 'true';
      const behaviorGrid = node('div');
      behaviorGrid.className = 'builder-grid';
      addAttrField(
        behaviorGrid,
        'Behavior',
        'ortpf',
        [
          ['false', 'Isotropic'],
          ['true', 'Orthotropic'],
        ],
        true
      );
      this.root.append(behaviorGrid);

      const unloadOptions = [
        ['Initial', 'Initial (β = 0)'],
        ['Origin', 'Origin (β = 1)'],
        ['Nothing', 'Mixed (0 < β < 1)'],
      ];

      // 1. Elastic properties
      const elasticBody = this.collapsibleGroup('mat:rocking:0', 'Elastic properties', ort ? 'Dir. 1&3 / Dir. 2' : 'Isotropic');
      const elasticGrid = node('div');
      elasticGrid.className = 'builder-grid';
      if (ort) {
        addAttrField(elasticGrid, 'Young’s modulus, E (Dir. 1 & 3)', 'Ehor');
        addAttrField(elasticGrid, 'Young’s modulus, E (Dir. 2)', 'Ever');
      } else {
        addAttrField(elasticGrid, 'Young’s modulus, E', 'Ehor');
      }
      elasticBody.append(elasticGrid);

      // 2. Tensile constitutive law & law-dependent fields
      const tensileLawHor = getVal('TensileCurveType') || 'LinearSoftening';
      const tensileLawVer = getVal('TensileCurveTypeVertical') || 'LinearSoftening';
      const tensileBody = this.collapsibleGroup('mat:rocking:1', 'Tensile', ort ? `${tensileLawHor} / ${tensileLawVer}` : tensileLawHor);
      const renderTensileDirection = (container, suffix, curveKey, dirSuffixLabel) => {
        const law = getVal(curveKey) || 'LinearSoftening';
        addAttrField(container, `Constitutive law${dirSuffixLabel}`, curveKey, null, true);
        if (law === 'Elastic') return;
        addAttrField(container, `Tensile strength, ft${dirSuffixLabel}`, `Ftm${suffix}`);
        if (law === 'LinearSoftening' || law === 'Exponential') {
          addAttrField(container, `Fracture energy, Gt${dirSuffixLabel}`, suffix === 'Ver' ? 'GtVer' : 'Gt');
        }
        if (law === 'LinearHardening') {
          addAttrField(container, `Traction stiffness ratio, κt${dirSuffixLabel}`, suffix === 'Ver' ? 'RatioEtTractionVer' : 'RatioEtTraction');
          if (suffix === 'Hor') {
            addAttrField(container, 'Limit tensile ductility', 'IsDuctTraz', null, true);
          }
          if (getVal('IsDuctTraz') === 'true') {
            addAttrField(container, `Tensile ductility, μut${dirSuffixLabel}`, `DuctTrazRocking${suffix}`);
          }
        }
        const unloadKey = `UnloadTractionRocking${suffix}`;
        addAttrField(container, `Unload behavior${dirSuffixLabel}`, unloadKey, unloadOptions, true);
        if (getVal(unloadKey) === 'Nothing') {
          addAttrField(container, `Unload parameter, βt${dirSuffixLabel}`, `BetaUnloadTractionRocking${suffix}`);
        }
      };
      const tensileGrid = node('div');
      tensileGrid.className = 'builder-grid';
      renderTensileDirection(tensileGrid, 'Hor', 'TensileCurveType', ort ? ' (Dir. 1 & 3)' : '');
      if (ort) {
        renderTensileDirection(tensileGrid, 'Ver', 'TensileCurveTypeVertical', ' (Dir. 2)');
      }
      tensileBody.append(tensileGrid);

      // 3. Compression constitutive law & law-dependent fields
      const compLawHor = getVal('CompressiveCurveType') || 'LinearSoftening';
      const compLawVer = getVal('CompressiveCurveTypeVertical') || 'LinearSoftening';
      const compBody = this.collapsibleGroup('mat:rocking:2', 'Compression', ort ? `${compLawHor} / ${compLawVer}` : compLawHor);
      const renderCompressiveDirection = (container, suffix, curveKey, dirSuffixLabel) => {
        const law = getVal(curveKey) || 'LinearSoftening';
        addAttrField(container, `Constitutive law${dirSuffixLabel}`, curveKey, null, true);
        if (law === 'Elastic') return;
        addAttrField(container, `Compressive strength, fm${dirSuffixLabel}`, `Fm${suffix}`);
        if (law === 'LinearSoftening' || law === 'Parabolic') {
          addAttrField(container, `Fracture energy, Gc${dirSuffixLabel}`, suffix === 'Ver' ? 'GcVer' : 'Gc');
        }
        if (law === 'LinearHardening') {
          addAttrField(container, `Compressive stiffness ratio, κc${dirSuffixLabel}`, suffix === 'Ver' ? 'RatioEtCompressionVer' : 'RatioEtCompression');
          if (suffix === 'Hor') {
            addAttrField(container, 'Limit compressive ductility', 'IsDuctCompr', null, true);
          }
          if (getVal('IsDuctCompr') === 'true') {
            addAttrField(container, `Compressive ductility, μuc${dirSuffixLabel}`, `DuctComprRocking${suffix}`);
          }
        }
        const unloadKey = `UnloadCompressionRocking${suffix}`;
        addAttrField(container, `Unload behavior${dirSuffixLabel}`, unloadKey, unloadOptions, true);
        if (getVal(unloadKey) === 'Nothing') {
          addAttrField(container, `Unload parameter, βc${dirSuffixLabel}`, `BetaUnloadCompressionRocking${suffix}`);
        }
        addAttrField(container, `Rocking rotation limit${dirSuffixLabel}`, `RotationLimitRocking${suffix}`);
      };
      const compGrid = node('div');
      compGrid.className = 'builder-grid';
      renderCompressiveDirection(compGrid, 'Hor', 'CompressiveCurveType', ort ? ' (Dir. 1 & 3)' : '');
      if (ort) {
        renderCompressiveDirection(compGrid, 'Ver', 'CompressiveCurveTypeVertical', ' (Dir. 2)');
      }
      compBody.append(compGrid);
      return;
    }

    if (tab === 'shear') {
      const shearLaw = getVal('ConstitutiveLawMasonryShear') || 'Elastic';
      const domain = getVal('CriterioSnervamento') || 'Coulomb';
      const modelBody = this.collapsibleGroup('mat:shear:0', 'Constitutive model', shearLaw);
      const modelGrid = node('div');
      modelGrid.className = 'builder-grid';
      addAttrField(modelGrid, 'Constitutive law', 'ConstitutiveLawMasonryShear', null, true);
      addAttrField(modelGrid, 'Shear modulus, G', 'Gd');
      addAttrField(modelGrid, 'Stiffness shear/sliding ratio, α', 'AlfaShearUser');
      if (shearLaw !== 'Elastic') {
        addAttrField(modelGrid, 'Yielding domain', 'CriterioSnervamento', null, true);
        addAttrField(modelGrid, 'Shear strength, τ₀', 'fvk0d');
        if (domain === 'Coulomb') {
          addAttrField(modelGrid, 'Friction ratio, μ', 'FrictionRatioShear');
        } else if (domain === 'Cacovic') {
          addAttrField(modelGrid, 'Cacovic coefficient, b', 'Bcacovic');
        }
      }
      modelBody.append(modelGrid);

      if (shearLaw !== 'Elastic') {
        const nlBody = this.collapsibleGroup('mat:shear:1', 'Nonlinear parameters', domain);
        const nlGrid = node('div');
        nlGrid.className = 'builder-grid';
        addAttrField(nlGrid, 'Plastic stiffness ratio', 'ShearPlasticStiffnessRatio');
        if (domain === 'Coulomb') {
          addAttrField(nlGrid, 'Reload stiffness ratio, κrs', 'ShearReloadStiffnessRatio');
          addAttrField(nlGrid, 'Maximum tensile ratio', 'ShearMaxTensileRatio');
        }
        if (shearLaw === 'ElastoPlasticDuctilityFixed') {
          addAttrField(nlGrid, 'Ductility', 'DuctilityShear');
          addAttrField(nlGrid, 'Ultimate shear strain, γp', 'ShearUltimateStrain');
        } else if (shearLaw === 'ElastoPlasticAndSoftening') {
          addAttrField(nlGrid, 'Ductility', 'DuctilityShear');
          addAttrField(nlGrid, 'Second plastic stiffness ratio', 'ShearPlasticStiffnessRatio2');
          addAttrField(nlGrid, 'Plastic shear strain', 'ShearPlasticStrain');
          addAttrField(nlGrid, 'Ultimate shear strain, γp', 'ShearUltimateStrain');
        } else if (shearLaw === 'ElastoPlasticFractureEnergyFixed' || shearLaw === 'ElastoPlasticEnergySigmaInterpolation') {
          addAttrField(nlGrid, 'Strain / fracture energy', 'FractureEnergyShear');
          addAttrField(nlGrid, 'Ductility', 'DuctilityShear');
        }
        nlBody.append(nlGrid);

        const cycBody = this.collapsibleGroup('mat:shear:2', 'Cyclic behavior');
        const cycGrid = node('div');
        cycGrid.className = 'builder-grid';
        addAttrField(cycGrid, 'Kinematic cycles enabled', 'HasKinCiclShear', null, true);
        if (getVal('HasKinCiclShear') === 'true') {
          addAttrField(cycGrid, 'Kinematic parameter', 'AkinCiclShear');
        }
        addAttrField(cycGrid, 'Cyclic degradation enabled', 'CiclShear', null, true);
        if (getVal('CiclShear') === 'true') {
          addAttrField(cycGrid, 'Cyclic parameter, α', 'AlfaCiclShear');
          addAttrField(cycGrid, 'Cyclic parameter, γ', 'GammaCiclShear');
        }
        addAttrField(
          cycGrid,
          'Unload behavior',
          'UnloadShear',
          [
            ['Initial', 'Initial (β = 0)'],
            ['Origin', 'Origin (β = 1)'],
            ['Nothing', 'Mixed (0 < β < 1)'],
          ],
          true
        );
        if (getVal('UnloadShear') === 'Nothing') {
          addAttrField(cycGrid, 'Unload parameter, β', 'BetaUnloadShear');
        }
        cycBody.append(cycGrid);
      }
      return;
    }

    if (tab === 'sliding') {
      const ort = getVal('ortsc') === 'true';
      const behaviorGrid = node('div');
      behaviorGrid.className = 'builder-grid';
      addAttrField(
        behaviorGrid,
        'Behavior',
        'ortsc',
        [
          ['false', 'Isotropic'],
          ['true', 'Orthotropic'],
        ],
        true
      );
      addAttrField(behaviorGrid, 'Check contact area', 'CheckContactArea');
      this.root.append(behaviorGrid);

      const dirConfigs = [
        {
          idx: 0,
          title: ort ? 'Faces 1–3 · Dir. 1' : 'Directional properties (Isotropic)',
          scorr: 'scorrhor',
          fracture: 'SlidingFractureEnergy',
          domain: 'SlidingYieldingDomainHor',
          cohesion: 'CohesionSlidingHor',
          friction: 'FrictionRatioSlidingHor',
          plasticRatio: 'SlidingPlasticStiffnessRatioHor',
          maxTensile: 'SlidingMaxTensileRatioHor',
          gs: 'Gs',
        },
        {
          idx: 1,
          title: 'Faces 2–4 · Dir. 2',
          scorr: 'scorrvert',
          fracture: 'SlidingFractureEnergyVer',
          domain: 'SlidingYieldingDomainVert',
          cohesion: 'CohesionSlidingVert',
          friction: 'FrictionRatioSlidingVert',
          plasticRatio: 'SlidingPlasticStiffnessRatioVer',
          maxTensile: 'SlidingMaxTensileRatioVer',
          gs: 'GsVer',
        },
        {
          idx: 2,
          title: 'Faces 5–6 · Dir. 3',
          scorr: 'scorrDir3',
          fracture: 'SlidingFractureEnergyDir3',
          domain: 'SlidingYieldingDomainDir3',
          cohesion: 'CohesionSlidingDir3',
          friction: 'FrictionRatioSlidingDir3',
          plasticRatio: 'SlidingPlasticStiffnessRatioDir3',
          maxTensile: 'SlidingMaxTensileRatioDir3',
          gs: 'GsDir3',
        },
      ];
      const activeDirs = ort ? dirConfigs : [dirConfigs[0]];
      for (const cfg of activeDirs) {
        const isNonlinear = getVal(cfg.scorr) === 'true';
        const isSoftening = isNonlinear && getVal(cfg.fracture) === 'true';
        const currentLaw = !isNonlinear ? 'Elastic' : isSoftening ? 'LinearSoftening' : 'ElastoPlastic';
        const body = this.collapsibleGroup(`mat:sliding:${cfg.idx}`, cfg.title, currentLaw);
        const grid = node('div');
        grid.className = 'builder-grid';

        const lawLabel = node('label', 'Constitutive law');
        const lawSelect = node('select');
        lawSelect.add(new Option('Elastic', 'Elastic'));
        lawSelect.add(new Option('Elasto-Plastic', 'ElastoPlastic'));
        lawSelect.add(new Option('Linear softening', 'LinearSoftening'));
        lawSelect.value = currentLaw;
        lawSelect.addEventListener('change', () => {
          if (lawSelect.value === 'Elastic') {
            setVal(cfg.scorr, 'false');
            setVal(cfg.fracture, 'false');
          } else if (lawSelect.value === 'ElastoPlastic') {
            setVal(cfg.scorr, 'true');
            setVal(cfg.fracture, 'false');
          } else {
            setVal(cfg.scorr, 'true');
            setVal(cfg.fracture, 'true');
          }
          this.render();
        });
        lawLabel.append(lawSelect);
        grid.append(lawLabel);

        if (currentLaw !== 'Elastic') {
          const dom = getVal(cfg.domain) || 'Coulomb';
          addAttrField(grid, 'Yielding domain', cfg.domain, null, true);
          addAttrField(grid, 'Cohesion, c', cfg.cohesion);
          if (dom === 'Coulomb') {
            addAttrField(grid, 'Friction ratio, μ', cfg.friction);
            addAttrField(grid, 'Maximum tensile ratio', cfg.maxTensile);
          }
          addAttrField(grid, 'Plastic stiffness ratio, κ', cfg.plasticRatio);
          if (currentLaw === 'LinearSoftening') {
            addAttrField(grid, 'Fracture energy, Gs', cfg.gs);
          }
        }
        body.append(grid);
      }
    }
  }

  renderManage(kind, items, index, isCreate = false) {
    if (!['material', 'analysis'].includes(kind) || !this.catalog) return;
    const actions = node('div');
    actions.className = 'builder-actions';
    if (kind === 'analysis') {
      const add = node('select');
      add.setAttribute('aria-label', 'Analysis template');
      for (const name of this.catalog.analyses) add.add(new Option(name, name));
      actions.append(add);
      this.button('Add analysis', () => this.apply({ op: 'add_analysis', template: add.value }, items.length, isCreate), actions);
    } else {
      const add = node('select');
      add.setAttribute('aria-label', 'Material template');
      const masonryTemplates = this.catalog.materials.filter(t => !t.type || t.type.endsWith('.MasonryMaterial'));
      for (const template of masonryTemplates) add.add(new Option(`${template.name} [${template.key}]`, template.key));
      actions.append(add);
      this.button('Add material', () => this.apply({ op: 'add_material', template: add.value }, items.length, isCreate), actions);
    }
    this.button(
      'Duplicate',
      () => this.apply({ op: kind === 'analysis' ? 'duplicate_analysis' : 'duplicate_material', duplicate: index }, items.length, isCreate),
      actions
    );
    this.button(
      'Delete',
      () => this.apply({ op: kind === 'analysis' ? 'delete_analysis' : 'delete_material', index }, Math.max(0, index - 1), isCreate),
      actions
    );
    this.root.append(actions);
  }

  async apply(operation, selected, isCreate = this.mode === 'create') {
    if (this.busy) return;
    this.busy = true;
    this.status.classList.remove('error');
    this.status.textContent = 'Applying change…';
    try {
      if (isCreate) {
        const pendingChanges = [...this.createChanges.values()];
        const data = await this.json('/api/builder/apply', {
          mode: 'create',
          payload: this.payload,
          steps: this.createSteps,
          changes: pendingChanges,
          operations: [operation],
        });
        this.createSteps.push({ changes: pendingChanges, operations: [operation] });
        this.createChanges.clear();
        this.createCollections = data.inspection.collections;
        this.createMaterials = data.inspection.materials;
        this.createAnalyses = data.inspection.analyses;
        this.selectedObject = Math.max(0, Math.min(selected, (this.createCollections[this.selectedKind || 'material'] || []).length - 1));
        this.selectedNode = 0;
        this.render();
        this.status.textContent = 'Change applied to bridge definition. Preview or Download HRX to use.';
      } else {
        const data = await this.json('/api/builder/apply', {
          mode: 'edit',
          source: this.source,
          changes: [...this.changes.values()],
          operations: [operation],
        });
        this.source = data.source;
        this.collections = data.inspection.collections;
        this.materials = data.inspection.materials;
        this.analyses = data.inspection.analyses;
        this.changes.clear();
        this.selectedObject = Math.max(0, Math.min(selected, (this.collections[this.selectedKind || 'material'] || []).length - 1));
        this.selectedNode = 0;
        this.render();
        this.status.textContent = 'Change applied. Preview or Download HRX to save.';
      }
    } catch (e) {
      this.status.textContent = e.message;
      this.status.classList.add('error');
    } finally {
      this.busy = false;
    }
  }

  async run(download) {
    if (this.busy) return;
    if (this.mode === 'edit' && !this.source) {
      this.status.textContent = 'Choose an HRX file first.';
      return;
    }
    this.busy = true;
    this.status.classList.remove('error');
    this.status.textContent = download ? 'Preparing HRX…' : 'Generating preview…';
    const request =
      this.mode === 'create'
        ? {
            mode: 'create',
            payload: this.payload,
            steps: this.createSteps,
            changes: [...this.createChanges.values()],
          }
        : {
            mode: 'edit',
            source: this.source,
            changes: [...this.changes.values()],
          };
    try {
      if (download) {
        const response = await fetch('/api/builder/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
        });
        if (!response.ok) throw new Error((await response.json()).error || 'Export failed.');
        const url = URL.createObjectURL(await response.blob());
        const a = node('a');
        a.href = url;
        a.download =
          this.mode === 'edit'
            ? this.sourceName.replace(/\.(hrx|xml)$/i, '') + '-edited.hrx'
            : (this.payload.name || 'bridge').replace(/[^a-z0-9_-]/gi, '_') + '.hrx';
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        this.status.textContent = 'HRX downloaded.';
      } else {
        const model = await this.json('/api/builder/preview', request);
        this.showModel(model);
        this.status.textContent = 'Preview ready. Download HRX to save your changes.';
      }
    } catch (e) {
      this.status.textContent = e.message;
      this.status.classList.add('error');
    } finally {
      this.busy = false;
    }
  }
}
