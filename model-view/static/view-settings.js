// Shared presentation settings. Result fields and dataset-specific filters remain local.
export const VIEW_DEFAULTS = Object.freeze({ colorBy: 'material', grid: true, opacity: 1, edges: true, nodes: false, extrude: true, loads: true, restraints: true, modelPoints: true, symbolScale: 1 });

export function createViewSettings(initial = {}) {
  let state = { ...VIEW_DEFAULTS, ...initial };
  const listeners = new Set();
  return {
    get: () => ({ ...state }),
    set(patch) {
      const changed = Object.fromEntries(Object.entries(patch).filter(([key, value]) => key in VIEW_DEFAULTS && state[key] !== value));
      if (!Object.keys(changed).length) return;
      state = { ...state, ...changed };
      for (const listener of listeners) listener({ ...state }, changed);
    },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
  };
}

export const viewSettings = createViewSettings();

const fields = [
  ['colorBy', 'Color by', 'select'], ['grid', 'Ground grid', 'checkbox'],
  ['opacity', 'Mesh opacity', 'opacity'], ['edges', 'Element edges', 'checkbox'],
  ['nodes', 'Mesh nodes', 'checkbox'], ['extrude', 'Physical thickness', 'checkbox'],
  ['loads', 'Applied loads', 'checkbox'], ['restraints', 'Restraints', 'checkbox'],
  ['modelPoints', 'Model points', 'checkbox'], ['symbolScale', 'Symbol scale', 'scale'],
];
const idFor = (prefix, key) => prefix ? prefix + key[0].toUpperCase() + key.slice(1) : key;
export function viewSettingsMarkup(prefix = '', { result = false } = {}) {
  return fields.map(([key, label, type]) => {
    const id = idFor(prefix, key);
    const unavailable = result && ['loads', 'restraints', 'symbolScale'].includes(key);
    const note = unavailable ? ' title="Changes apply to Build and View; this overlay is not drawn in Results"' : '';
    if (type === 'select') return `<label class="field">${label}<select id="${id}" aria-label="${label}"><option value="material">Material</option><option value="layer">Layer</option><option value="parent">Parent element</option><option value="thickness">Thickness</option><option value="single">Uniform</option></select>${result ? '<small>Used when the result color map is set to Uniform.</small>' : ''}</label>`;
    if (type === 'checkbox') return `<div class="toggle-row"><label for="${id}">${label}${unavailable ? ' (Build / View only)' : ''}</label><input id="${id}" type="checkbox"${note}></div>`;
    const attrs = type === 'opacity' ? 'min="0.1" max="1" step="0.05"' : 'min="0.25" max="3" step="0.25"';
    return `<label class="field range-field">${label} <output id="${id}Value"></output><input id="${id}" type="range" ${attrs}${note}></label>`;
  }).join('');
}

export function bindViewSettings(root, prefix = '', store = viewSettings) {
  const controls = fields.map(([key, , type]) => [key, type, root.querySelector(`#${idFor(prefix, key)}`)]).filter(([, , input]) => input);
  for (const [key, type, input] of controls) input.addEventListener(type === 'checkbox' || type === 'select' ? 'change' : 'input', () => store.set({ [key]: type === 'checkbox' ? input.checked : type === 'select' ? input.value : Number(input.value) }));
  const sync = state => {
    for (const [key, type, input] of controls) {
      if (type === 'checkbox') input.checked = state[key]; else input.value = state[key];
      const output = root.querySelector(`#${idFor(prefix, key)}Value`);
      if (output) output.value = type === 'opacity' ? `${Math.round(state[key] * 100)}%` : `${state[key]}×`;
    }
  };
  sync(store.get());
  return store.subscribe(sync);
}

export function applyViewerSettings(viewer, state, { rebuild = true } = {}) {
  if (!viewer) return;
  const { colorBy, opacity, edges, nodes, extrude, modelPoints, grid } = state;
  viewer.setOptions({ colorBy, opacity, edges, nodes, extrude, modelPoints }, { rebuild });
  viewer.grid.visible = grid;
  viewer.needsRender = true;
}
