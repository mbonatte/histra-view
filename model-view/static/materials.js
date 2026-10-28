import { rockingGroups, shearGroups, slidingGroups, displayValue, curveImage, shearImage, slidingImage } from './material-properties.js';
import { unitSets, unitFor, convertedValue } from './material-units.js';
import { HysteresisPreview } from './hysteresis.js';

const $ = id => document.getElementById(id);
const node = (tag, className, text) => {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
};

export class MaterialsPage {
  constructor() {
    this.materials = [];
    this.tab = 'general';
    this.units = 'engineering';
    this.preview = new HysteresisPreview();
    $('materialSearch').oninput = () => this.renderList();
    $('assignedMaterialsOnly').onchange = () => this.renderList();
    $('mobileMaterialSelect').onchange = () => {
      this.selected = this.materials.find(m => m.key === $('mobileMaterialSelect').value);
      this.render();
    };
  }

  setModel(model) {
    this.materials = (model.materialLibrary ?? model.materials).filter(material =>
      material.attributes.PurposeType === 'MasonryMaterial'
      || material.attributes.TypeOf?.endsWith('.MasonryMaterial'));
    this.selected = this.materials.find(m => m.quadCount > 0) ?? this.materials[0];
    this.tab = this.selected?.attributes.SimpleMode === 'false' ? 'rocking' : 'general';
    $('materialSearch').value = '';
    this.render();
  }

  open(key) {
    const selected = this.materials.find(m => String(m.key) === String(key));
    if (selected) { this.selected = selected; this.render(); }
    $('materialsPage').querySelector('.material-document').scrollTop = 0;
    location.hash = 'materials';
  }

  renderList() {
    const list = $('materialLibraryList');
    const query = $('materialSearch').value.trim().toLowerCase();
    const rows = this.materials.filter(m => (!$('assignedMaterialsOnly').checked || m.quadCount > 0)
      && `${m.name} ${m.key} ${m.attributes.PurposeType}`.toLowerCase().includes(query));
    $('materialLibraryCount').textContent = `${rows.length}/${this.materials.length}`;
    list.replaceChildren();
    for (const material of rows) {
      const button = node('button', 'library-material');
      button.classList.toggle('selected', this.selected?.key === material.key);
      button.setAttribute('aria-pressed', String(this.selected?.key === material.key));
      const swatch = node('span', 'swatch');
      swatch.style.background = material.color;
      const info = node('span');
      info.append(node('strong', '', material.name), node('small', '', `${material.attributes.PurposeType?.replace('Material', '') || 'Material'} · #${material.key}`));
      const badge = node('span', 'assignment-badge', material.quadCount ? material.quadCount.toLocaleString() : 'Unused');
      badge.title = `${material.quadCount} assigned quads`;
      button.append(swatch, info, badge);
      button.onclick = () => { this.selected = material; this.render(); };
      list.append(button);
    }
    if (!rows.length) list.append(node('p', 'material-note', 'No matching materials.'));
  }

  render() {
    this.renderList();
    const material = this.selected;
    if (!material) {
      $('materialDocumentHeader').replaceChildren();
      $('materialMechanismTabs').replaceChildren();
      $('mobileMaterialSelect').replaceChildren();
      $('materialContent').replaceChildren(node('p', 'material-note', 'No masonry materials are defined in this model.'));
      return;
    }
    const a = material.attributes;
    $('mobileMaterialSelect').replaceChildren(...this.materials.map(m => new Option(`${m.name} · #${m.key}${m.quadCount ? '' : ' · unused'}`, m.key, false, m.key === material.key)));
    const masonry = a.PurposeType === 'MasonryMaterial' || a.TypeOf?.endsWith('.MasonryMaterial');
    const header = $('materialDocumentHeader');
    header.replaceChildren();
    const heading = node('div', 'material-heading');
    const title = node('div');
    title.append(node('div', 'eyebrow', 'MATERIAL PROPERTIES'), node('h1', '', material.name), node('p', '', a.Description || a.PurposeType || 'Material definition'));
    const badge = node('span', 'material-mode', masonry ? `${a.SimpleMode === 'true' ? 'Simple' : a.SimpleMode === 'false' ? 'Advanced' : 'Unspecified'} mode · saved` : a.PurposeType || 'Material');
    heading.append(title, badge);
    const meta = node('div', 'material-meta');
    const chip = node('span', 'material-color-chip');
    chip.style.background = material.color;
    meta.append(chip, node('span', '', `Key ${material.key}`), node('span', '', `${material.quadCount.toLocaleString()} assigned quads`), node('span', '', `Specific weight, W: ${convertedValue(a.w ?? a.Gamma ?? '—', 'w', this.units)} ${unitFor('w', this.units)}`));
    header.append(heading, meta);
    const unitsLabel = node('label', 'material-unit-selector', 'Display units');
    const units = node('select'); units.setAttribute('aria-label', 'Material display units');
    for (const [key, definition] of Object.entries(unitSets)) units.add(new Option(definition.label, key, false, key === this.units));
    units.onchange = () => { this.units = units.value; this.render(); };
    unitsLabel.append(units); header.append(unitsLabel);
    const tabs = masonry ? [['general', 'General'], ['rocking', 'Rocking mechanism'], ['shear', 'Shear mechanism'], ['sliding', 'Sliding mechanism'], ['all', 'All properties']]
      : [['general', 'General'], ['all', 'All properties']];
    if (!tabs.some(([key]) => key === this.tab)) this.tab = 'general';
    const tablist = $('materialMechanismTabs');
    tablist.replaceChildren();
    for (const [key, label] of tabs) {
      const button = node('button', '', label);
      button.setAttribute('role', 'tab');
      button.id = `material-group-${key}`;
      button.setAttribute('aria-controls', 'materialContent');
      button.setAttribute('aria-selected', String(key === this.tab));
      button.onclick = () => { this.tab = key; this.render(); };
      tablist.append(button);
    }
    $('materialContent').setAttribute('aria-labelledby', `material-group-${this.tab}`);
    const content = $('materialContent');
    content.replaceChildren();
    if (this.tab === 'rocking') this.rocking(a, content);
    else if (this.tab === 'shear') this.shear(a, content);
    else if (this.tab === 'sliding') this.sliding(a, content);
    else if (this.tab === 'all') this.all(a, content);
    else this.general(a, content, masonry);
    content.append(node('p', 'material-footnote', 'Display conversion only · HRX base units: kN and cm · 1 = dimensionless · — = not serialized. All properties preserves the original values. Reference diagrams are schematic; the hysteresis preview is calculated using Python spring laws.'));
  }

  table(title, columns, groups, attributes, raw = false, showUnits = true) {
    const unitColumn = !raw && showUnits;
    const section = node('section', 'property-section');
    section.append(node('h2', '', title));
    const wrap = node('div', 'property-table-wrap');
    const table = node('table', 'material-table');
    const head = node('thead');
    const tr = node('tr');
    for (const label of ['Parameter', ...(unitColumn ? ['Unit'] : []), ...columns]) { const th = node('th', '', label); th.scope = 'col'; tr.append(th); }
    head.append(tr);
    table.append(head);
    for (const [group, rows] of groups) {
      const body = node('tbody');
      if (group) {
        const row = node('tr', 'property-group');
        const cell = node('th', '', group);
        cell.colSpan = columns.length + 1 + (unitColumn ? 1 : 0);
        row.append(cell); body.append(row);
      }
      for (const [label, ...keys] of rows) {
        const row = node('tr');
        const labelCell = node('th', '', label);
        labelCell.scope = 'row';
        row.append(labelCell);
        if (unitColumn) {
          const key = keys[0];
          let unit = unitFor(key, this.units);
          if (unit === '—' && attributes[key] !== undefined && attributes[key] !== '' && Number.isFinite(Number(attributes[key]))) unit = '1';
          row.append(node('td', 'property-unit', unit));
        }
        for (let index = 0; index < columns.length; index++) {
          const key = keys[index];
          const value = displayValue(attributes, key);
          const cell = node('td', '', raw ? value : convertedValue(value, key, this.units));
          cell.title = key ? `${key} · stored: ${attributes[key] ?? 'not serialized'}` : 'Not applicable';
          if (attributes[key] === undefined) cell.classList.add('missing-value');
          row.append(cell);
        }
        body.append(row);
      }
      table.append(body);
    }
    wrap.append(table); section.append(wrap);
    return section;
  }

  reference(title, file, caption = '') {
    const figure = node('figure', 'material-reference');
    if (file && !file.startsWith('meccanismo_')) figure.classList.add('constitutive-reference');
    figure.append(node('h3', '', title));
    if (file) {
      const image = node('img');
      image.src = `/static/${file}`;
      image.alt = `${title} — original HiStrA reference diagram`;
      image.loading = 'lazy';
      figure.append(image);
    } else figure.append(node('p', 'material-note', 'No reference diagram for the saved law.'));
    if (caption) figure.append(node('figcaption', '', caption));
    return figure;
  }

  layout(content, tables, diagrams) {
    const layout = node('div', 'mechanism-layout');
    const parameters = node('div', 'mechanism-parameters');
    parameters.append(...tables);
    const references = node('aside', 'mechanism-references');
    references.setAttribute('aria-label', 'C# reference diagrams');
    references.append(...diagrams);
    layout.append(parameters, references);
    content.append(layout);
  }

  rocking(a, content) {
    this.preview.mount(content, a, 'rocking', this.units);
    const behavior = a.ortpf === 'true' ? 'Orthotropic' : a.ortpf === 'false' ? 'Isotropic' : 'Not serialized';
    content.append(node('div', 'mechanism-description', `Rocking behavior: ${behavior} · directions follow the element’s local reference system.`));
    const diagrams = [this.reference('Rocking mechanism', 'meccanismo_pressfless1.png'),
      this.reference('Tensile constitutive law', curveImage('tensile', a.TensileCurveType), displayValue(a, 'TensileCurveType')),
      this.reference('Compressive constitutive law', curveImage('compressive', a.CompressiveCurveType), displayValue(a, 'CompressiveCurveType'))];
    if (a.ortpf === 'true') diagrams.push(
      this.reference('Tensile law · local direction 2', curveImage('tensile', a.TensileCurveTypeVertical)),
      this.reference('Compressive law · local direction 2', curveImage('compressive', a.CompressiveCurveTypeVertical)));
    const table = this.table('Parameters', ['Local directions 1 & 3', 'Local direction 2'], rockingGroups, a);
    this.layout(content, [table], diagrams);
  }

  shear(a, content) {
    this.preview.mount(content, a, 'shear', this.units);
    content.append(node('div', 'mechanism-description', 'Diagonal shear mechanism · constitutive law, yielding domain, and nonlinear parameters.'));
    this.layout(content, [this.table('Parameters', ['Saved value'], shearGroups, a)], [
      this.reference('Shear mechanism', 'meccanismo_taglio.png'),
      this.reference('Shear constitutive law', shearImage(a.ConstitutiveLawMasonryShear), displayValue(a, 'ConstitutiveLawMasonryShear'))]);
  }

  sliding(a, content) {
    this.preview.mount(content, a, 'sliding', this.units);
    content.append(node('div', 'mechanism-description', `Orthotropic behavior: ${displayValue(a, 'ortsc')} · Check contact area: ${displayValue(a, 'CheckContactArea')}`));
    this.layout(content, [this.table('Parameters', ['Faces 1–3 · Dir. 1', 'Faces 2–4 · Dir. 2', 'Faces 5–6 · Dir. 3'], slidingGroups, a)], [
      this.reference('Sliding mechanism', 'meccanismo_scorr.png'),
      this.reference('Sliding law · direction 1', slidingImage(a)),
      ...(a.ortsc === 'true' ? [this.reference('Sliding law · direction 2', slidingImage(a, 'scorrvert', 'SlidingFractureEnergyVer')),
        this.reference('Sliding law · direction 3', slidingImage(a, 'scorrDir3', 'SlidingFractureEnergyDir3'))] : []),
    ]);
  }

  general(a, content, masonry) {
    if (masonry) {
      // The General tab is deliberately limited to the quantities a structural
      // engineer reads first. Reference ranges and NTC improvement options are
      // not mixed into this summary; the serialized values remain in All properties.
      const basic = [
        ['Specific weight, W', a.w !== undefined ? 'w' : 'Gamma'],
        ['Young’s modulus, E', 'Ehor'],
        ['Shear modulus, G', 'Gd'],
        ['Compressive strength, fm', 'FmHor'],
        ['Tensile strength, ft', 'FtmHor'],
        ['Shear strength, τ₀', 'fvk0d'],
        ['Cohesion, c', 'CohesionSlidingHor'],
        ['Friction coefficient, μ (sliding)', 'FrictionRatioSlidingHor'],
        ['Friction ratio, μ (shear)', 'FrictionRatioShear'],
      ];
      content.append(this.table('Basic properties', ['Design value'], [['', basic]], a));
      content.append(this.table('Identification', ['Value'], [['', [
        ['Name', 'Name'], ['Description', 'Description'], ['Material type', 'PurposeType'],
      ]]], a, false, false));
      content.append(this.table('Assessment basis', ['Value'], [['', [
        ['Masonry typology', 'existentMasonryMaterial'],
        ['Existing masonry', 'IsExistent'],
        ['Knowledge level', 'LC_'],
        ['Partial safety factor, γM', 'gammam'],
      ]]], a, false, false));
      if (a.SimpleMode === 'true') {
        const corrections = [
          ['Malta', 'Good mortar', 'MaltaValue'],
          ['Giunti', 'Thin joints (< 10 mm)', 'GiuntiValue'],
          ['Ricorsi', 'Brick rows or listature', 'RicorsiValue'],
          ['Connessioni', 'Transverse connections', 'ConnessioniValue'],
          ['Nucleo', 'Poor-quality or large core', 'NucleoValue'],
          ['Iniezioni', 'Grout injection', 'IniezioniValue'],
          ['Intonaco', 'Reinforced plaster', 'IntonacoValue'],
          ['Diatoni', 'Artificial diatoni', 'DiatoniValue'],
          ['Ristilatura', 'Reinforced stitching', 'RistilaturaValue'],
        ].filter(([, , valueKey]) => Number(a[valueKey]) >= 0);
        const details = node('details', 'material-advanced-details');
        details.append(node('summary', '', 'NTC simple-mode improvement options'));
        details.append(node('p', 'material-note', 'Flags serialized by HiStrA’s NTC simple-mode editor (Circ. 2019 n. 7). “Coefficient if applied” is the saved multiplier for that option; the viewer does not recalculate the combined coefficient.'));
        if (corrections.length) {
          details.append(this.table('Improvement options', ['Applied', 'Coefficient if applied'],
            [['', corrections.map(([flag, label, valueKey]) => [label, flag, valueKey])]], a, false, false));
        } else {
          details.append(node('p', 'material-note', 'No improvement options are applicable to the saved typology.'));
        }
        content.append(details);
      } else {
        content.append(node('p', 'material-note', 'Advanced-mode material: NTC simple-mode improvement options are not applied to the saved design values. All serialized fields remain in All properties.'));
      }
      content.append(node('p', 'material-note', 'Values are the saved design values in HRX; changing units is display-only. Directional/orthotropic values remain in the Rocking, Shear, and Sliding tabs. This viewer does not recompute the material.'));
    } else {
      const fields = [['Young’s modulus, E', 'E'], ['Shear modulus, G', 'G'], ['Poisson ratio, ν', 'Poisson'], ['Thermal expansion, α', 'Alfa'],
        ['Compressive strength', 'fykCompr'], ['Tensile strength', 'fykTraz'], ['Steel law', 'SteelType']].filter(([, key]) => a[key] !== undefined);
      if (fields.length) {
        content.append(this.table('Basic properties', ['Design value'], [['', [['Specific weight, W', a.w !== undefined ? 'w' : 'Gamma'], ...fields]]], a));
      }
      content.append(this.table('Identification', ['Value'], [['', [
        ['Name', 'Name'], ['Description', 'Description'], ['Material type', 'PurposeType'],
      ]]], a, false, false));
    }
  }

  all(attributes, content) {
    content.append(node('p', 'material-note', 'Complete serialized definition. Hover a value in the mechanism tables to see its HRX attribute name.'));
    const rows = Object.keys(attributes).sort().map(key => [key, key]);
    // Raw view deliberately preserves the exact serialized strings.
    const section = this.table('All HRX attributes', ['Serialized value'], [['', rows]], attributes, true);
    const cells = section.querySelectorAll('td');
    rows.forEach(([, key], i) => { cells[i].textContent = attributes[key]; });
    content.append(section);
  }
}
