// C# UnitsManagement: force base kN, length base cm; no solver state is changed.
const stress = new Set(['E', 'Ehor', 'Ever', 'G', 'Gd', 'fmd', 'fvk0d', 'FmHor', 'FmVer', 'FtmHor', 'FtmVer',
  'CohesionSlidingHor', 'CohesionSlidingVert', 'CohesionSlidingDir3', 'FractureEnergyShear']);
const energy = new Set(['Gt', 'GtVer', 'Gc', 'GcVer', 'Gs', 'GsVer', 'GsDir3']);
export const unitSets = {
  engineering: { label: 'MPa · N/mm · kN/m³', stress: ['MPa', 10], energy: ['N/mm', 100], weight: ['kN/m³', 1e6] },
  si: { label: 'kN/m² · kN/m · kN/m³', stress: ['kN/m²', 1e4], energy: ['kN/m', 100], weight: ['kN/m³', 1e6] },
  native: { label: 'Native: kN · cm', stress: ['kN/cm²', 1], energy: ['kN/cm', 1], weight: ['kN/cm³', 1] },
};

export function dimension(key) {
  if (stress.has(key) || /^(E|G|fm|fvk0)_(min|med|max)$/.test(key || '')) return 'stress';
  if (energy.has(key)) return 'energy';
  if (key === 'w' || key === 'Gamma') return 'weight';
  return null;
}

export function unitFor(key, set = 'engineering') {
  const kind = dimension(key);
  return kind ? unitSets[set][kind][0] : '—';
}

export function convertedValue(value, key, set = 'engineering') {
  const kind = dimension(key);
  if (!kind || value === undefined || value === '' || !Number.isFinite(Number(value)) || Number(value) === -1) return value;
  if (set === 'native') return value;
  const scaled = Number(value) * unitSets[set][kind][1];
  return Number(scaled.toPrecision(9)).toString();
}
