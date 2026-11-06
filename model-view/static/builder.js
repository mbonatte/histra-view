import { PDELTA_LABELS, isDynamicOnlyAnalysisField } from './analysis-properties.js';
import { unitSets, unitFor, convertedValue, toNativeValue, dimension } from './material-units.js';

const ANALYSIS_GROUPS = [
  ['control', 'Control parameters', ['Name', 'Description', 'AnalysisType', 'InitialAnalysisKey', 'Mult', 'LoadCombinationKey', 'MasterPoint', 'ForceControl', 'Direction', 'DirX', 'DirY', 'DirZ']],
  ['iterative', 'Iterative strategy', ['PdeltaEffect', 'IntegrationMethod', 'Method', 'MaxIterations', 'CheckSecantStiffness', 'SecantStiffnessRatio', 'LineSearchTolerance', 'LineSearchMaxIterations', 'LineSearchMaxEta', 'LineSearchMinEta', 'ALS', 'MaxNumberALS', 'LoadFactorALS', 'ArcLengthProcedure', 'Dr2', 'InitFromDiscretization', 'InitialForceControlledPhase', 'IsMaxArcLengthRay', 'MaxArcLengthRay', 'UpdateDr2', 'DesiredIterations', 'IsRestartArcLength', 'MaxRestartArcLength', 'ReduceRayArcLength']],
  ['convergence', 'Convergence criteria', ['AdapticConvergenceCriteria', 'ConvergenceTolerance', 'ConvergenceToleranceForce', 'ConvergenceToleranceMoment', 'ConvergenceToleranceDisplacement', 'ConvergenceToleranceRotation', 'WorkReference', 'maxU', 'MaximumTolerance', 'SDB_Tolerance', 'SDB_MaxIterations']],
  ['modal', 'Modal settings', ['ModalProcedure', 'ModalConvergenceCriteria', 'NumberOfModes', 'NumModes', 'NumberOfEigenModes', 'NumberOfLanczosEigenVectors', 'ResidualVectorTolerance']],
  ['advanced', 'Other properties', []],
];
const ANALYSIS_LABELS = {
  PdeltaEffect: 'P-Delta effect', AnalysisType: 'Analysis type', InitialAnalysisKey: 'Start from analysis',
  MaxIterations: 'Maximum iterations', Method: 'Solution method', IntegrationMethod: 'Integration method',
  ConvergenceTolerance: 'Convergence tolerance', AdapticConvergenceCriteria: 'Convergence criterion',
  ForceControl: 'Force control', Mult: 'Load multiplier', MasterPoint: 'Control model point',
};
export function analysisPropertyGroups(attributes = {}) {
  const analysisType = String(attributes.AnalysisType ?? '2');
  const isModal = analysisType === '5';
  const modalKeys = new Set(ANALYSIS_GROUPS.find(g => g[0] === 'modal')?.[2] || []);
  const assigned = new Set(ANALYSIS_GROUPS.flatMap(group => group[2]));

  return ANALYSIS_GROUPS
    .filter(([id]) => {
      if (id === 'modal' && !isModal) return false;
      if (isModal && (id === 'iterative' || id === 'convergence')) return false;
      return true;
    })
    .map(([id, title, keys]) => ({
      id,
      title,
      keys: id === 'advanced'
        ? Object.keys(attributes).filter(key => {
            if (assigned.has(key)) return false;
            if (isDynamicOnlyAnalysisField(key)) return false;
            if (!isModal && modalKeys.has(key)) return false;
            return true;
          })
        : keys.filter(key => Object.hasOwn(attributes, key))
    }))
    .filter(group => group.keys.length);
}

const isMasonryItem = item => {
  const a = item?.attributes || item?.nodes?.[0]?.attributes || {};
  return a.PurposeType === 'MasonryMaterial' || a.Ehor !== undefined;
};

const labels = {
  name: 'Download filename',
  nl: 'Mesh size',
  width: 'Width',
  height: 'Height',
  material_key: 'Material',
  material_pulvino_key: 'Pulvino material',
  material_foundation_key: 'Foundation material',
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
  circolare: 'Arch shape',
  H: 'Height',
  Hf: 'Foundation height',
  b1: 'b1 (left widening)',
  b2: 'Pier length along bridge (b2)',
  b3: 'b3 (right widening)',
  w1: 'w1 (left impost widening)',
  w2: 'Pier width across bridge (w2)',
  w3: 'w3 (right impost widening)',
  shoulder_height: 'Rectangular shoulder height',
  vertical_alignment: 'Alignment',
  beta1: 'Beta 1',
  beta2: 'Beta 2',
  is_reinf_left: 'Apply reinforcement left',
  is_reinf_right: 'Apply reinforcement right',
  TreinfTopLeft: 'Reinforcement top left',
  TreinfBotLeft: 'Reinforcement bottom left',
  TreinfTopRight: 'Reinforcement top right',
  TreinfBotRight: 'Reinforcement bottom right',
  material_reinforcement_left_key: 'Reinforcement material (left)',
  material_reinforcement_right_key: 'Reinforcement material (right)',
  material_geo1_key: 'Geotechnical material (left)',
  material_geo2_key: 'Geotechnical material (right)',
  spinta_passiva_sx: 'Add lateral restraint left',
  spinta_passiva_dx: 'Add lateral restraint right',
  Hsp1: 'Lateral restraint height left',
  Hsp2: 'Lateral restraint height right',
  B1f: 'Foundation left',
  B3f: 'Foundation right',
  W1f: 'Foundation extension across bridge (side 1)',
  W3f: 'Foundation extension across bridge (side 2)',
  H1: 'Height 1',
  H2: 'Height 2',
  H3: 'Height 3',
  layer1_material_key: 'Layer 1 material',
  layer2_material_key: 'Layer 2 material',
  layer3_material_key: 'Layer 3 material',
  load_position: 'Live load position',
  load_value: 'Line load (kN/cm)',
};

const FIELD_OPTIONS = {
  load_position: [
    ['none', 'None'],
    ['1/4', '1/4 Span'],
    ['1/2', '1/2 Span (Crown)'],
    ['3/4', '3/4 Span'],
  ],
  circolare: [
    ['false', 'C# elliptical (Asx/Adx)'],
    ['true', 'True circular (viewer extension)'],
  ],
  vertical_alignment: [
    ['Center', 'Center'],
    ['Top', 'Top'],
    ['Bottom', 'Bottom'],
  ],
  law_s: [
    ['Constant', 'Constant'],
    ['Linear', 'Linear'],
    ['Parabolic', 'Parabolic'],
  ],
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
  ['vehicle_load', 'Vehicles (train load models)'],
  ['line_load', 'Line loads'],
  ['schema', 'Load schemas'],
  ['load_function', 'Load functions'],
  ['load_function_item', 'Load function points'],
  ['load_combination', 'Load combinations'],
  ['load_combination_item', 'Load combination items'],
  ['load_condition', 'Load conditions'],
];

// Human labels for the native C# wizard fields.  The screenshot tabs use
// these names, and keeping them here means the editor stays readable without
// hiding any serialized attribute.
const WIZARD_LABELS = {
  Width: 'Width of the bridge, W',
  WidthTopPile: 'Width of the bridge at impost level',
  IsWidthTopPileCustom: 'Custom width at impost level',
  Nl: 'Max mesh length, Nl',
  Nt: 'Max mesh thickness, Nt',
  InclinationAngle: 'Inclination angle of abutments/piers',
  Slope: 'Slope of the bridge',
  Zlevel: 'Deck level, Zlevel',
  ThicknessBallast: 'Ballast thickness',
  ThicknessRiempimento: 'Backfill thickness',
  VehicleLoadName: 'Train load',
  IsVehicleLoad: 'Generate vehicle load',
  NumVehicles: 'Number of vehicles',
  DynamicCoefficientProcedure: 'Dynamic coefficient procedure',
  Mode: 'Dynamic mode',
  Velocity: 'Vehicle velocity',
  H: 'Height, H',
  Hf: 'Foundation height, Hf',
  b1: 'b1',
  b2: 'Length along bridge, b2',
  b3: 'b3',
  w1: 'w1',
  w2: 'Width across bridge, w2',
  w3: 'w3',
  B1f: 'Foundation b1f',
  B3f: 'Foundation b3f',
  W1f: 'Foundation w1f',
  W3f: 'Foundation w3f',
  VerticalAllignment: 'Alignment',
  AbutmentKind: 'Abutment side',
  MaterialKey: 'Abutment material',
  MaterialFoundationKey: 'Foundation material',
  MaterialGeo1Key: 'Geotechnical material (left)',
  MaterialGeo2Key: 'Geotechnical material (right)',
  ReinforcementLeft: 'Apply reinforcement left',
  ReinforcementRight: 'Apply reinforcement right',
  TreinfTopLeft: 'Tick at top, Tr2L',
  TreinfBotLeft: 'Tick at bottom, Tr1L',
  TreinfTopRight: 'Tick at top, Tr2R',
  TreinfBotRight: 'Tick at bottom, Tr1R',
  MaterialReinforcementLeftKey: 'Reinforcement material left',
  MaterialReinforcementRightKey: 'Reinforcement material right',
  HiStrAShoulderHeight: 'Rectangular shoulder height',
  Hsp1: 'Height, Hsp1',
  Hsp2: 'Height, Hsp2',
  SpintaPassivaSX: 'Add lateral restraint left',
  SpintaPassivaDX: 'Add lateral restraint right',
  Kx: 'Kx',
  Ky: 'Ky',
  Kz: 'Subgrade modulus, Kz',
  Krx: 'Krx',
  Kry: 'Kry',
  Krz: 'Krz',
  IsFixDirX: 'Fix Ux',
  IsFixDirY: 'Fix Uy',
  IsFixDirZ: 'Fix Uz',
  IsFixRotDirX: 'Fix Rx',
  IsFixRotDirY: 'Fix Ry',
  IsFixRotDirZ: 'Fix Rz',
  L: 'Span length, L',
  L1: 'L1',
  L2: 'L2',
  W: 'Width, W',
  f: 'Rise, f',
  f2: 'f2',
  Tb: 'Thickness Tb',
  Tt: 'Thickness Tt',
  Tb1: 'Tb1',
  Tb2: 'Tb2',
  Treinf: 'Reinforcement thickness, Tr',
  Asx: 'Angle α left, Asx',
  Adx: 'Angle α right, Adx',
  S1: 'S1',
  S2: 'S2',
  Dz: 'Dz',
  LawS: 'Thickness law',
  dcMax: 'Max discretization, dcMax',
  Circolare: 'Shape (Circolare)',
  IsChkAdvancedMode: 'Advanced span mode',
  MaterialPulvinoKey: 'Piercap material',
  MaterialReinforcementKey: 'Reinforcement material',
  Name: 'Name',
  Description: 'Description',
  Height: 'Wall height',
  AllowVehicle: 'Train load',
  Layer1: 'Backfill layer 1',
  Layer2: 'Backfill layer 2',
  Layer3: 'Backfill layer 3',
  MaterialKey2: 'Material 2',
  UniformMaterial: 'Uniform material',
  RowIndexMaterial: 'Number of rows for material 1',
  GenerateComputationalElements: 'Generate computational elements',
  IsStratigraphyVariable: 'Variable stratigraphy',
  X: 'X position',
  H1: 'H1',
  H2: 'H2',
  H3: 'H3',
};

const LOAD_LABELS = {
  Name: 'Name',
  Description: 'Description',
  X: 'X',
  Y: 'Y',
  Length: 'Length',
  Width: 'Width',
  LoadValue: 'Load value',
  Psi0: 'ψ0',
  Psi1: 'ψ1',
  Psi2: 'ψ2',
  DirX: 'Direction X',
  DirY: 'Direction Y',
  DirZ: 'Direction Z',
  IdTypeLoad: 'Type of load',
  IdLoadCondition: 'Load condition',
  LoadAbscissa: 'Load abscissa',
  IsLoadAbscissaNormalized: 'Normalized abscissa',
  Vehicle: 'Vehicle',
  AreaLoad: 'Area load',
  LineLoad: 'Line load',
  Nposition: 'N. positions',
  LineLoadL1: 'Line load L1',
  LineLoadL2: 'Line load L2',
  AreaLoadL1: 'Area load L1',
  AreaLoadL2: 'Area load L2',
  Opposite: 'Opposite',
  NumVehicles: 'N. vehicles',
  Corsia: 'Lane',
  Abscissa: 'Abscissa',
  Position: 'Position',
  DynamicCoefficient: 'Dynamic coefficient',
  D1: 'Distance d1',
  D2: 'Distance d2',
  D3: 'Distance d3',
  D4: 'Distance d4',
  Schema: 'Schema',
  TypeSchema: 'Schema type',
  SchemaPosition: 'Position definition',
  VehicleCoeff: 'Vehicle coefficient',
  SerpeggioCoeff: 'Swaying coefficient',
  FrenaturaCoeff: 'Braking coefficient',
  CentrifugaCoeff: 'Centrifugal coefficient',
  excludeAreaLoadInVehicleArea: 'Exclude area load in vehicle area',
  excludeLineLoadInVehicleArea: 'Exclude line load in vehicle area',
};

const CONFIG_LABELS = {
  Name: 'Building name',
  Address: 'Address',
  Country: 'Country',
  Region: 'Region / State',
  Province: 'Province',
  City: 'City',
  CAP: 'CAP / ZIP',
  Latitude: 'Latitude',
  Longitude: 'Longitude',
  StructureTypology: 'Structure typology',
  Regulation: 'Code',
  LC: 'Life class, LC',
  Damping: 'Damping',
  CatSuolo: 'Soil category',
  CatTopo: 'Topographic category',
  TipoDiCostruzione: 'Construction type',
  ClasseDiUso: 'Use class',
  PeriodoDiRiferimento: 'Reference period',
  VitaNominale: 'Nominal life',
  CoefficienteUso: 'Use coefficient',
  Solver: 'Solver type',
  SolverParallel: 'Use parallel solver',
  SaveAllSpringStatus: 'Save all links status',
  MassMatrixType: 'Mass matrix',
  ToleranceNode: 'Tolerance to check node coincidence',
  TolerancePlane: 'Tolerance to check if a point is on a plane',
  InterfaceNrow: 'Number of links rows',
  InterfaceImax: 'Max links distance',
  DisableGeoLinksOnLoadingLateralEarthPressure: 'Geotechnical links disabled on loading lateral earth pressure',
};

labels.arch_layers = 'Elements through arch thickness';
WIZARD_LABELS.HiStrAArchLayers = 'Elements through arch thickness';
FIELD_OPTIONS.arch_layers = [[1, '1'], [2, '2'], [3, '3'], [4, '4']];

const MIRRORED_FIELDS = Object.fromEntries([
  ['b1', 'b3'], ['w1', 'w3'], ['B1f', 'B3f'], ['W1f', 'W3f'],
  ['Hsp1', 'Hsp2'], ['beta1', 'beta2'], ['S1', 'S2'], ['Asx', 'Adx'],
  ['spinta_passiva_sx', 'spinta_passiva_dx'], ['SpintaPassivaSX', 'SpintaPassivaDX'],
  ['material_geo1_key', 'material_geo2_key'], ['MaterialGeo1Key', 'MaterialGeo2Key'],
  ['is_reinf_left', 'is_reinf_right'], ['ReinforcementLeft', 'ReinforcementRight'],
  ['TreinfTopLeft', 'TreinfTopRight'], ['TreinfBotLeft', 'TreinfBotRight'],
  ['material_reinforcement_left_key', 'material_reinforcement_right_key'],
  ['MaterialReinforcementLeftKey', 'MaterialReinforcementRightKey'],
].flatMap(([a, b]) => [[a, b], [b, a]]));

export class Builder {
  constructor(container, showModel) {
    this.root = container;
    this.showModel = showModel;
    this.geometryLinks = { abutments: false, piers: false, spans: false };
    this.geometryInputs = new WeakMap();
    this.wizardInputs = new Map();
    this.mode = 'create';
    this.payload = null;
    this.catalog = null;
    this.materialUnits = 'engineering';
    // Edit-mode state
    this.source = null;
    this.sourceName = null;
    this.materials = [];
    this.analyses = [];
    this.collections = {};
    this.changes = new Map();
    this.editSteps = [];
    this.appliedGeometryChanges = false;
    this.geometryPreviewRevision = 0;
    this.geometryPreviewTimer = null;
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
    this.analysisEditorGroup = 'control';
    this.selectedLoadKind = 'vehicle_load';
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
        if (!this.viewerSource) this.scheduleGeometryPreview();
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

  isMaterialKey(key) {
    return /material.*key|layer[123]_material_key/i.test(key) || key === 'MaterialKey';
  }

  materialOptions() {
    const materials = (this.mode === 'create'
      ? (this.createMaterials?.length ? this.createMaterials : this.materials)
      : (this.materials?.length ? this.materials : this.createMaterials))
      || [];
    const options = [['0', 'None (0)']];
    for (const material of materials) {
      const keyStr = String(material.key);
      const name = material.name || `Material #${keyStr}`;
      options.push([keyStr, `${name} (${keyStr})`]);
    }
    return options;
  }

  field(parent, object, key, fallbackValue, onChange = null) {
    if (object[key] === undefined && fallbackValue !== undefined) {
      object[key] = fallbackValue;
    }
    const label = node('label', labels[key] || key);
    let input;
    if (this.isMaterialKey(key)) {
      input = node('select');
      const currentVal = String(object[key] ?? fallbackValue ?? '0');
      const opts = this.materialOptions();
      let hasCurrent = false;
      for (const [val, txt] of opts) {
        if (String(val) === currentVal) hasCurrent = true;
        input.add(new Option(txt, String(val)));
      }
      if (!hasCurrent && currentVal !== '' && currentVal !== 'undefined') {
        input.add(new Option(`Unknown material (${currentVal})`, currentVal));
      }
      input.value = currentVal;
      input.addEventListener('change', () => {
        object[key] = Number(input.value);
        this.propagateCreateLink(object, key);
        if (onChange) onChange();
        this.scheduleGeometryPreview();
      });
    } else if (FIELD_OPTIONS[key]) {
      input = node('select');
      for (const [val, txt] of FIELD_OPTIONS[key]) {
        input.add(new Option(txt, val));
      }
      input.value = String(object[key] ?? fallbackValue ?? FIELD_OPTIONS[key][0][0]);
      input.addEventListener('change', () => {
        object[key] = key === 'arch_layers' ? Number(input.value) : input.value;
        this.propagateCreateLink(object, key);
        if (onChange) onChange();
        this.scheduleGeometryPreview();
      });
    } else if (/^(is_|Is[A-Z]|spinta_)/.test(key) || typeof object[key] === 'boolean' || ['true', 'false'].includes(String(object[key]))) {
      input = node('select');
      input.add(new Option('Yes', 'true'));
      input.add(new Option('No', 'false'));
      input.value = String(object[key] ?? fallbackValue ?? false);
      input.addEventListener('change', () => {
        object[key] = input.value === 'true';
        this.propagateCreateLink(object, key);
        if (onChange) onChange();
        this.scheduleGeometryPreview();
      });
    } else {
      input = node('input');
      input.type = typeof object[key] === 'number' ? 'number' : 'text';
      if (input.type === 'number') input.step = 'any';
      input.value = object[key] ?? '';
      input.addEventListener('input', () => {
        object[key] = input.type === 'number' ? (input.value === '' ? null : Number(input.value)) : input.value;
        this.propagateCreateLink(object, key);
        if (onChange) onChange();
        this.scheduleGeometryPreview();
      });
    }
    if (!this.geometryInputs.has(object)) this.geometryInputs.set(object, new Map());
    this.geometryInputs.get(object).set(key, input);
    label.append(input);
    parent.append(label);
  }

  propagateCreateLink(object, key) {
    let targets = [];
    let targetKey = key;
    if (this.geometryLinks.spans && this.payload.spans?.includes(object)) targets = this.payload.spans;
    else if (this.geometryLinks.piers && this.payload.piers?.includes(object)) targets = this.payload.piers;
    else if (this.geometryLinks.abutments && [this.payload.left_abutment, this.payload.right_abutment].includes(object)) {
      targets = [this.payload.left_abutment, this.payload.right_abutment];
      targetKey = MIRRORED_FIELDS[key] || key;
    }
    for (const target of targets) {
      if (!target || target === object) continue;
      target[targetKey] = object[key];
      const input = this.geometryInputs.get(target)?.get(targetKey);
      if (input) input.value = String(object[key] ?? "");
    }
  }

  renderGeometryLinkControl(key, title, parent, hint = null) {
    const wrap = node('div');
    wrap.className = 'builder-link-wrap';
    const label = node('label');
    label.className = 'builder-link-checkbox';
    const input = node('input');
    input.type = 'checkbox';
    input.checked = Boolean(this.geometryLinks[key]);
    input.addEventListener('change', () => { this.geometryLinks[key] = input.checked; });
    label.append(input, document.createTextNode(' ' + title));
    wrap.append(label);
    if (hint) {
      const help = node('span', hint);
      help.className = 'builder-link-help';
      wrap.append(help);
    }
    parent.append(wrap);
  }

  renderGeometryLinks(parent) {
    for (const [key, title] of [['spans', 'Link spans'], ['piers', 'Link piers and foundations'], ['abutments', 'Link abutments']]) {
      this.renderGeometryLinkControl(key, title, parent);
    }
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
      clearTimeout(this.geometryPreviewTimer);
      this.geometryPreviewRevision++;
      this.render();
      if (this.mode === 'create') this.scheduleGeometryPreview();
      else if (this.source) this.scheduleGeometryPreview();
    });
    this.root.append(mode);

    const actions = node('div');
    actions.className = 'builder-actions';
    this.button('Download HRX', () => this.run(), actions).className = 'primary';
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
        'Define a parametric masonry bridge and customize its materials, analyses, and load settings. The view updates as you edit.'
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
        item => {
          const mats = this.createMaterials || [];
          const m = mats.find(mat => String(mat.key) === String(item.material_key));
          const matSuffix = m ? ` · ${m.name}` : (item.material_key && item.material_key !== 0 ? ` · Mat ${item.material_key}` : '');
          return `W ${item.width ?? '—'} · H ${item.height ?? '—'}${matSuffix}`;
        },
      ],
      [
        'spans',
        'Spans',
        'Span',
        ['L', 'W', 'f', 'Tb', 'Tt', 'arch_layers', 'Tb1', 'Tb2', 'Treinf', 'Asx', 'Adx', 'S1', 'S2', 'Dz', 'L1', 'f2', 'circolare', 'material_key', 'material_pulvino_key', 'material_reinforcement_key', 'load_position', 'load_value'],
        { material_key: 18, material_pulvino_key: 22, circolare: 'false', load_position: 'none', load_value: 0.01 },
        item => `L ${item.L ?? '—'} · f ${item.f ?? '—'} · ${String(item.circolare) === 'true' ? 'Circular' : 'Elliptical'}${item.load_position && item.load_position !== 'none' ? ` · Load ${item.load_position}` : ''}`,
      ],
      [
        'piers',
        'Piers',
        'Pier',
        ['H', 'Hf', 'shoulder_height', 'b1', 'b2', 'b3', 'w1', 'w2', 'w3', 'B1f', 'B3f', 'W1f', 'W3f', 'vertical_alignment', 'beta1', 'beta2', 'material_key', 'material_foundation_key', 'material_geo1_key', 'material_geo2_key', 'Kx', 'Ky', 'Kz', 'Krx', 'Kry', 'Krz', 'spinta_passiva_sx', 'Hsp1', 'spinta_passiva_dx', 'Hsp2', 'is_reinf_left', 'TreinfTopLeft', 'TreinfBotLeft', 'material_reinforcement_left_key', 'is_reinf_right', 'TreinfTopRight', 'TreinfBotRight', 'material_reinforcement_right_key'],
        { shoulder_height: 0, material_key: 18, material_foundation_key: 141, material_geo1_key: 60, material_geo2_key: 60, vertical_alignment: 'Center', Kz: 0.1 },
        item => `H ${item.H ?? '—'} · b2 ${item.b2 ?? '—'} · ${item.vertical_alignment ?? 'Center'}`,
      ],
    ];
    for (const [key, groupTitle, itemTitle, fieldKeys, defaultsMap, metaFn] of collections) {
      const items = this.payload[key] || [];
      const groupBody = this.collapsibleGroup(key, groupTitle, items.length);
      if (key === 'spans') {
        this.renderGeometryLinkControl('spans', 'Link spans', groupBody, 'Link edits across all spans.');
      } else if (key === 'piers') {
        this.renderGeometryLinkControl('piers', 'Link piers and foundations', groupBody, 'Link edits across matching piers and foundations.');
      }
      if (!items.length) {
        groupBody.append(node('p', 'No intermediate piers (single-span bridge).'));
      }
      items.forEach((item, i) => {
        const itemId = `${key}:${i}`;
        const { body: itemBody, updateMeta } = this.collapsibleItem(itemId, `${itemTitle} ${i + 1}`, () => metaFn(item), groupBody);
        const basicKeys = key === 'spans'
          ? ['L', 'f', 'Tb', 'Tt', 'arch_layers', 'circolare', 'Asx', 'Adx', 'material_key']
          : key === 'piers'
            ? ['H', 'Hf', 'b2', 'w2', 'shoulder_height', 'material_key', 'material_foundation_key']
            : fieldKeys;
        this.fieldsGrid(item, basicKeys, itemBody, defaultsMap, updateMeta);
        if (key === 'piers') itemBody.append(node('p', 'Rectangular shoulders use pier masonry and occupy the pier width outside the deck. Set height to 0 to disable.'));
        const advancedKeys = fieldKeys.filter(fieldKey => !basicKeys.includes(fieldKey));
        if (advancedKeys.length) {
          const advanced = this.collapsibleGroup(`${itemId}:advanced`, 'Additional parameters', '', itemBody);
          this.fieldsGrid(item, advancedKeys, advanced, defaultsMap, updateMeta);
        }
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
                this.scheduleGeometryPreview();
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
            this.scheduleGeometryPreview();
          },
          controls
        );
        groupBody.append(controls);
      }
    }

    const abutmentsBody = this.collapsibleGroup('abutments', 'Abutments', '2');
    this.renderGeometryLinkControl('abutments', 'Link abutments', abutmentsBody, 'Link edits across abutments (mirrors left and right).');
    for (const [key, title] of [['left_abutment', 'Left abutment'], ['right_abutment', 'Right abutment']]) {
      const item = this.payload[key];
      const { body: itemBody, updateMeta } = this.collapsibleItem(
        `abutments:${key}`,
        title,
        () => `H ${item.H ?? '—'} · b2 ${item.b2 ?? '—'}`,
        abutmentsBody
      );
      const supportDefaults = { material_key: 18, material_foundation_key: 141, material_geo1_key: 60, material_geo2_key: 60, vertical_alignment: 'Center', Kz: 0.1 };
      this.fieldsGrid(item, ['H', 'Hf', 'b2', 'w2', 'material_key', 'material_foundation_key'], itemBody, supportDefaults, updateMeta);
      const advanced = this.collapsibleGroup(`abutments:${key}:advanced`, 'Additional parameters', '', itemBody);
      this.fieldsGrid(item, ['b1', 'b3', 'w1', 'w3', 'B1f', 'B3f', 'W1f', 'W3f', 'vertical_alignment', 'material_geo1_key', 'material_geo2_key', 'Kx', 'Ky', 'Kz', 'Krx', 'Kry', 'Krz', 'spinta_passiva_sx', 'Hsp1', 'spinta_passiva_dx', 'Hsp2', 'is_reinf_left', 'TreinfTopLeft', 'TreinfBotLeft', 'material_reinforcement_left_key', 'is_reinf_right', 'TreinfTopRight', 'TreinfBotRight', 'material_reinforcement_right_key'], advanced, supportDefaults, updateMeta);
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
    clearTimeout(this.geometryPreviewTimer);
    this.geometryPreviewRevision++;
    const revision = this.geometryPreviewRevision;
    const opened = await this.json('/api/builder/open', { source: encoded, name });
    if (revision !== this.geometryPreviewRevision) return;
    const data = opened.inspection;
    const preserveView = encoded === this.viewerSource;
    this.source = encoded;
    this.sourceName = name;
    this.viewerSource = encoded;
    this.viewerSourceName = name;
    this.materials = data.materials;
    this.analyses = data.analyses;
    this.collections = data.collections;
    this.changes.clear();
    this.editSteps = [];
    this.appliedGeometryChanges = Boolean(opened.needsBackfillRegeneration);
    this.selectedKind = this.selectedKind || 'material';
    this.selectedObject = index;
    this.selectedNode = 0;
    this.render();
    this.showModel(opened.model, { preserveView });
    if (this.appliedGeometryChanges) this.scheduleGeometryPreview();
    else this.status.textContent = 'Model loaded.';
  }

  renderEdit() {
    this.root.append(
      node(
        'p',
        'Edit the native C# wizard geometry, masonry materials, vehicles/line loads/schemas, analyses and model configuration. Add, duplicate or delete materials and analyses. Enter valid native values; fields are not engineering-validated. Recompute results after changes.'
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
        ['geometry', 'Geometry'],
        ['material', `Materials (${masonryCount})`],
        ['loads', 'Loads'],
        ['analysis', `Analyses (${this.analyses.length})`],
        ['configuration', 'Configuration'],
      ],
      this.editSection,
      section => {
        this.editSection = section;
        if (section === 'material' || section === 'analysis') {
          this.selectedKind = section;
          this.selectedObject = 0;
          this.selectedNode = 0;
        } else if (section === 'loads') {
          this.selectedKind = this.selectedLoadKind || 'vehicle_load';
          this.selectedObject = 0;
          this.selectedNode = 0;
        }
        this.render();
      }
    );
    if (this.editSection === 'geometry') {
      this.renderWizardEditor();
      return;
    }
    if (this.editSection === 'configuration') {
      this.renderConfigurationEditor();
      return;
    }
    this.renderCollectionEditor({
      collections: this.collections,
      changes: this.changes,
      isCreate: false,
      fixedCategory: this.editSection === 'loads' ? null : this.editSection,
    });
  }

  // -- Native C# wizard / configuration editor -----------------------------

  wizardRecord(kind, index) {
    return (this.collections[kind] || [])[index];
  }

  wizardRootNode(record) {
    return record?.nodes?.find(entry => entry.path.length === 0) || record?.nodes?.[0];
  }

  wizardCurrent(kind, index, key, entryPath = []) {
    const record = this.wizardRecord(kind, index);
    const entry = record?.nodes?.find(item => JSON.stringify(item.path) === JSON.stringify(entryPath));
    const id = `${kind}:${index}:${entryPath.join('.')}:${key}`;
    return this.changes.get(id)?.value ?? entry?.attributes?.[key];
  }

  wizardSet(kind, index, key, value, entryPath = []) {
    this.setWizardValue(kind, index, key, value, entryPath);
    const group = { wizard_abutment: 'abutments', wizard_pier: 'piers', wizard_span: 'spans' }[kind];
    if (group && this.geometryLinks[group] && !entryPath.length && key !== 'AbutmentKind') {
      const targetKey = group === 'abutments' ? (MIRRORED_FIELDS[key] || key) : key;
      (this.collections[kind] || []).forEach((_, other) => {
        if (other === index) return;
        this.setWizardValue(kind, other, targetKey, value, []);
        const input = this.wizardInputs.get(`${kind}:${other}::${targetKey}`);
        if (input) input.value = value;
      });
    }
    this.scheduleGeometryPreview();
  }

  setWizardValue(kind, index, key, value, entryPath = []) {
    const record = this.wizardRecord(kind, index);
    const entry = record?.nodes?.find(item => JSON.stringify(item.path) === JSON.stringify(entryPath));
    if (!entry || !(key in entry.attributes)) return;
    const id = `${kind}:${index}:${entryPath.join('.')}:${key}`;
    if (String(value) === String(entry.attributes[key])) this.changes.delete(id);
    else {
      this.changes.set(id, {
        collection: kind,
        index,
        node: entryPath,
        attribute: key,
        value: String(value),
      });
    }
  }

  scheduleGeometryPreview() {
    if (this.mode === 'edit' && !this.source) return;
    const revision = ++this.geometryPreviewRevision;
    clearTimeout(this.geometryPreviewTimer);
    this.status.classList.remove('error');
    this.status.textContent = 'Updating model view…';
    this.geometryPreviewTimer = setTimeout(async () => {
      try {
        const isEdit = this.mode === 'edit';
        const geometryEdited = isEdit && (this.appliedGeometryChanges || [...this.changes.values()].some(change => change.collection.startsWith('wizard_')));
        const request = isEdit
          ? { mode: 'edit', source: this.source, steps: this.editSteps, changes: [...this.changes.values()], rebuild_geometry: geometryEdited }
          : { mode: 'create', payload: this.payload, steps: this.createSteps, changes: [...this.createChanges.values()] };
        const model = await this.json('/api/builder/preview', request);
        if (revision !== this.geometryPreviewRevision) return;
        this.showModel(model, { preserveView: true });
        this.status.textContent = geometryEdited ? 'Model view regenerated. Download HRX to save the updated mesh; original loads and analysis data are not shown in this view.' : 'Model view updated.';
      } catch (error) {
        if (revision !== this.geometryPreviewRevision) return;
        this.status.classList.add('error');
        this.status.textContent = error.message;
      }
    }, 500);
  }

  renderBackfillStripOverrides(parent, corsias) {
    const overriding = corsias.map((_, index) => index).filter(index => {
      const key = this.wizardCurrent('wizard_corsia', index, 'MaterialKey');
      return this.materials.some(material => String(material.key) === String(key) &&
        material.attributes?.PurposeType === 'MasonryMaterial');
    });
    if (!overriding.length) {
      parent.append(node('p', 'All strips use the backfill layer materials.'));
      return;
    }
    parent.append(node('p', 'A strip with a masonry material uses that material through all backfill layers. Spandrel walls normally use this setting. Select only strips that should use the layer materials.'));
    const selections = [];
    for (const index of overriding) {
      const materialKey = this.wizardCurrent('wizard_corsia', index, 'MaterialKey');
      const material = this.materials.find(item => String(item.key) === String(materialKey));
      const name = this.wizardCurrent('wizard_corsia', index, 'Name') || `Strip ${index + 1}`;
      const label = node('label');
      const checkbox = node('input');
      checkbox.type = 'checkbox';
      checkbox.checked = false;
      label.append(checkbox, node('span', `${name} — ${material?.name || `Material #${materialKey}`}`));
      parent.append(label);
      selections.push({ index, checkbox });
    }
    this.button('Use layer materials for selected strips', () => {
      const chosen = selections.filter(item => item.checkbox.checked);
      if (!chosen.length) return;
      for (const item of chosen) this.wizardSet('wizard_corsia', item.index, 'MaterialKey', '0');
      this.render();
    }, parent);
  }

  wizardField(parent, kind, index, key, options = null, note = null, entryPath = [], labelText = null) {
    const record = this.wizardRecord(kind, index);
    const entry = record?.nodes?.find(item => JSON.stringify(item.path) === JSON.stringify(entryPath));
    const original = entry?.attributes?.[key];
    if (original === undefined) return false;
    const label = node('label', labelText || WIZARD_LABELS[key] || CONFIG_LABELS[key] || key.replace(/([a-z])([A-Z])/g, '$1 $2'));
    let input;
    const materialKeys = [
      'MaterialKey', 'MaterialKey2', 'MaterialFoundationKey', 'MaterialGeo1Key', 'MaterialGeo2Key',
      'MaterialPulvinoKey', 'MaterialReinforcementKey', 'MaterialReinforcementLeftKey',
      'MaterialReinforcementRightKey',
    ];
    if (key === 'HiStrAArchLayers') options = [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']];
    if (options) {
      input = node('select');
      for (const [value, text] of options) input.add(new Option(text, value));
    } else if (materialKeys.includes(key)) {
      input = node('select');
      for (const [value, text] of this.materialOptions()) input.add(new Option(text, value));
      if (![...input.options].some(option => option.value === original)) {
        input.add(new Option(`Unknown material (#${original})`, original));
      }
    } else if (['true', 'false'].includes(String(original))) {
      input = node('select');
      input.add(new Option('Yes', 'true'));
      input.add(new Option('No', 'false'));
    } else {
      input = node('input');
      if (Number.isFinite(Number(original)) && original !== '') input.type = 'number';
      input.step = 'any';
    }
    input.value = this.wizardCurrent(kind, index, key, entryPath) ?? original;
    this.wizardInputs.set(`${kind}:${index}:${entryPath.join('.')}:${key}`, input);
    input.addEventListener(input.tagName === 'INPUT' ? 'input' : 'change', () => this.wizardSet(kind, index, key, input.value, entryPath));
    label.append(input);
    parent.append(label);
    if (note) {
      const help = node('small', note);
      help.className = 'builder-help';
      parent.append(help);
    }
    return true;
  }

  renderWizardFields(record, kind, index, keys, parent, options = {}, notes = {}, labels = {}) {
    const grid = node('div');
    grid.className = 'builder-grid';
    const used = new Set();
    for (const key of keys) {
      if (this.wizardField(grid, kind, index, key, options[key], notes[key], [], labels[key] || null)) used.add(key);
    }
    if (grid.childElementCount) parent.append(grid);
    return used;
  }

  renderWizardEditor() {
    this.root.append(
      node(
        'p',
        'Edit the bridge geometry and materials. The view regenerates as you change geometry, and the downloaded HRX includes the updated mesh.'
      )
    );
    const definition = this.wizardRecord('wizard_definition', 0);
    if (definition) {
      const body = this.collapsibleGroup('wizard:general', 'General / bridge definition', `${this.collections.wizard_corsia?.length || 0} lanes`);
      const used = this.renderWizardFields(
        definition,
        'wizard_definition',
        0,
        ['Nl', 'InclinationAngle', 'Slope', 'Width', 'WidthTopPile', 'IsWidthTopPileCustom', 'Zlevel', 'ThicknessBallast', 'ThicknessRiempimento', 'VehicleLoadName', 'IsVehicleLoad', 'NumVehicles', 'DynamicCoefficientProcedure', 'Mode', 'Velocity'],
        body,
        {},
        {
          Width: 'Total deck width, measured in the C# native units (cm for this model).',
          WidthTopPile: 'Width at the impost/cap level. The C# mesher widens the edge strips when this differs from Width.',
          IsWidthTopPileCustom: 'Use a custom width at the impost level instead of the deck width.',
          Nl: 'Maximum mesh length used by the bridge and wall meshers.',
          InclinationAngle: 'Skew angle in degrees. The C# mesher shifts X by Y·tan(angle) and widens strip thickness by 1/cos(angle).',
          Slope: 'Longitudinal grade. The C# mesher adds X·slope to Z after meshing.',
        }
      );
    }

    const corsias = this.collections.wizard_corsia || [];
    const sectionBody = this.collapsibleGroup('wizard:cross-section', 'Definition of the bridge cross-section', `${corsias.length} lanes`);
    if (!corsias.length) sectionBody.append(node('p', 'This model has no Corsia lanes.'));
    corsias.forEach((record, index) => {
      const entry = this.wizardRootNode(record);
      const title = entry?.attributes?.Name || `Lane ${index + 1}`;
      const { body } = this.collapsibleItem(`wizard:corsia:${index}`, title, () => `${entry?.attributes?.Width ?? '—'} × ${entry?.attributes?.Height ?? '—'}`, sectionBody);
      const used = this.renderWizardFields(
        record,
        'wizard_corsia',
        index,
        ['Name', 'Description', 'Width', 'Height', 'AllowVehicle', 'MaterialKey'],
        body,
        {},
        {
          Width: 'Lane width. The sum of all lane widths is the bridge width.',
          Height: 'Extra strip height above the top of the third backfill layer. A positive value adds a fourth layer.',
          AllowVehicle: 'Marks this lane as carrying the train/vehicle load in the schema.',
          MaterialKey: 'A masonry material is used for every backfill layer in this strip, including a spandrel wall. None uses the layer materials.',
        },
        { Width: 'Lane width', Height: 'Wall height', AllowVehicle: 'Train load', MaterialKey: 'Strip material' }
      );
    });

    const abutments = this.collections.wizard_abutment || [];
    const abutmentBody = this.collapsibleGroup('wizard:abutments', 'Abutments', `${abutments.length}`);
    this.renderGeometryLinkControl('abutments', 'Link abutments', abutmentBody, 'Link edits across abutments (mirrors left and right).');
    const { body: supportsBody } = this.collapsibleItem('wizard:end-supports', 'Abutment end restraints', () => '', abutmentBody);
    supportsBody.append(node('p', 'Fully fix each outer vertical end face through the deck level, in all translations and rotations.'));
    this.button('Add fixed restraints to both ends', () => this.addAbutmentEndRestraints(), supportsBody);
    abutments.forEach((record, index) => {
      const entry = this.wizardRootNode(record);
      const { body } = this.collapsibleItem(
        `wizard:abutment:${index}`,
        entry?.attributes?.AbutmentKind === 'Destra' ? 'Right abutment' : 'Left abutment',
        () => `H ${entry?.attributes?.H ?? '—'} · b2 ${entry?.attributes?.b2 ?? '—'}`,
        abutmentBody
      );
      const used = this.renderWizardFields(
        record,
        'wizard_abutment',
        index,
        ['H', 'Hf', 'b1', 'b2', 'b3', 'w1', 'w2', 'w3', 'B1f', 'B3f', 'W1f', 'W3f', 'VerticalAllignment', 'AbutmentKind', 'MaterialKey', 'MaterialFoundationKey', 'SpintaPassivaSX', 'Hsp1', 'MaterialGeo1Key', 'SpintaPassivaDX', 'Hsp2', 'MaterialGeo2Key', 'ReinforcementLeft', 'TreinfTopLeft', 'TreinfBotLeft', 'MaterialReinforcementLeftKey', 'ReinforcementRight', 'TreinfTopRight', 'TreinfBotRight', 'MaterialReinforcementRightKey', 'Kx', 'Ky', 'Kz', 'Krx', 'Kry', 'Krz', 'IsFixDirX', 'IsFixDirY', 'IsFixDirZ', 'IsFixRotDirX', 'IsFixRotDirY', 'IsFixRotDirZ'],
        body,
        {
          VerticalAllignment: [['Center', 'Center'], ['Top', 'Top'], ['Bottom', 'Bottom']],
          AbutmentKind: [['Sinistra', 'Left (Sinistra)'], ['Destra', 'Right (Destra)']],
        },
        {
          b1: 'Left widening of the abutment shaft.', b3: 'Right widening of the abutment shaft.',
          w1: 'Left widening at the impost/cap level.', w3: 'Right widening at the impost/cap level.',
          Hsp1: 'Height of the left lateral earth-pressure surface.', Hsp2: 'Height of the right lateral earth-pressure surface.',
          SpintaPassivaSX: 'Adds the left passive earth-pressure surface restraint (geotechnical link).',
          SpintaPassivaDX: 'Adds the right passive earth-pressure surface restraint (geotechnical link).',
        }
      );
    });

    const spans = this.collections.wizard_span || [];
    const spanBody = this.collapsibleGroup('wizard:spans', 'Spans / vaults', `${spans.length}`);
    this.renderGeometryLinkControl('spans', 'Link spans', spanBody, 'Link edits across all spans.');
    spans.forEach((record, index) => {
      const entry = this.wizardRootNode(record);
      const { body } = this.collapsibleItem(
        `wizard:span:${index}`,
        `Span ${index + 1}`,
        () => `L ${entry?.attributes?.L ?? '—'} · f ${entry?.attributes?.f ?? '—'} · ${entry?.attributes?.Circolare === 'true' ? 'Circolare' : 'Elliptical'}`,
        spanBody
      );
      const used = this.renderWizardFields(
        record,
        'wizard_span',
        index,
        ['L', 'W', 'f', 'Circolare', 'LawS', 'Tb', 'Tt', 'HiStrAArchLayers', 'Tb1', 'Tb2', 'Treinf', 'Asx', 'Adx', 'S1', 'S2', 'Dz', 'L1', 'L2', 'f2', 'dcMax', 'MaterialKey', 'MaterialPulvinoKey', 'MaterialReinforcementKey'],
        body,
        {
          Circolare: [['false', 'Elliptical'], ['true', 'Circular (C# wizard flag)']],
          LawS: [['Constant', 'Constant'], ['Linear', 'Linear'], ['Parabolic', 'Parabolic']],
        },
        {
          Circolare: 'This edits the C# wizard flag. The saved mesh is unchanged; re-mesh in HiStrA to apply wizard changes.',
          f: 'Intrados rise at the crown. The C# wizard allows rise greater than L/2 (for example L=200, f=350 in the benchmark model).',
          Asx: 'Left springing angle. It trims the ellipse and controls the pulvino at the springing.',
          Adx: 'Right springing angle. The C# mesher uses Adx for the arch parameter block on both halves.',
          LawS: 'Thickness law between the springing thickness Tb and the crown thickness Tt.',
          Tb: 'Arch thickness at the springing.', Tt: 'Arch thickness at the crown.',
          S1: 'Left setback of the arch springing.', S2: 'Right setback of the arch springing.',
          Dz: 'Drops the intrados while keeping the extrados crown, increasing the effective crown thickness.',
        }
      );
    });

    const piers = this.collections.wizard_pier || [];
    const pierBody = this.collapsibleGroup('wizard:piers', 'Piers', `${piers.length}`);
    this.renderGeometryLinkControl('piers', 'Link piers and foundations', pierBody, 'Link edits across matching piers and foundations.');
    if (!piers.length) pierBody.append(node('p', 'No intermediate piers.'));
    piers.forEach((record, index) => {
      const entry = this.wizardRootNode(record);
      const { body } = this.collapsibleItem(
        `wizard:pier:${index}`,
        `Pier ${index + 1}`,
        () => `H ${entry?.attributes?.H ?? '—'} · b2 ${entry?.attributes?.b2 ?? '—'}`,
        pierBody
      );
      const used = this.renderWizardFields(
        record,
        'wizard_pier',
        index,
        ['H', 'Hf', 'HiStrAShoulderHeight', 'b1', 'b2', 'b3', 'w1', 'w2', 'w3', 'B1f', 'B3f', 'W1f', 'W3f', 'VerticalAllignment', 'MaterialKey', 'MaterialFoundationKey', 'SpintaPassivaSX', 'Hsp1', 'MaterialGeo1Key', 'SpintaPassivaDX', 'Hsp2', 'MaterialGeo2Key', 'Tr1', 'Tr2', 'ReinforcementLeft', 'TreinfTopLeft', 'TreinfBotLeft', 'MaterialReinforcementLeftKey', 'ReinforcementRight', 'TreinfTopRight', 'TreinfBotRight', 'MaterialReinforcementRightKey', 'Kz', 'IsFixDirX', 'IsFixDirY', 'IsFixDirZ', 'IsFixRotDirX', 'IsFixRotDirY', 'IsFixRotDirZ'],
        body,
        {
          VerticalAllignment: [['Center', 'Center'], ['Top', 'Top'], ['Bottom', 'Bottom']],
        },
        {
          b1: 'Left widening of the pier shaft.', b3: 'Right widening of the pier shaft.',
          w1: 'Left widening at the pier cap.', w3: 'Right widening at the pier cap.',
          HiStrAShoulderHeight: 'Optional rectangular masonry above each transverse pier extension. Uses the pier material; 0 disables. For an average of a triangular shoulder, enter half its height. Straight, level bridges and centered, untapered piers only.',
        }
      );
    });

    const elevation = this.wizardRecord('wizard_elevation', 0);
    const layers = this.collections.wizard_layer || [];
    const backfillBody = this.collapsibleGroup('wizard:backfill', 'Backfill heights and layers', `${layers.length} layers`);
    this.renderBackfillStripOverrides(backfillBody, corsias);
    if (elevation) {
      const used = this.renderWizardFields(
        elevation,
        'wizard_elevation',
        0,
        ['IsStratigraphyVariable'],
        backfillBody,
        {},
        { IsStratigraphyVariable: 'When true, the elevation table is read section by section instead of using one constant section.' }
      );
      const sections = elevation.nodes.filter(entry => entry.tag === 'Elevation');
      if (sections.length) {
        const table = node('table');
        const head = node('thead');
        const row = node('tr');
        for (const heading of ['Section', 'X', 'H1', 'H2', 'H3']) row.append(node('th', heading));
        head.append(row);
        table.append(head);
        const tbody = node('tbody');
        sections.forEach((section, index) => {
          const tr = node('tr');
          tr.append(node('th', String(index + 1)));
          for (const key of ['X', 'H1', 'H2', 'H3']) {
            const cell = node('td');
            this.wizardField(cell, 'wizard_elevation', 0, key, null, null, section.path, key);
            tr.append(cell);
          }
          tbody.append(tr);
        });
        table.append(tbody);
        backfillBody.append(table);
      }
    }
    layers.forEach((record, index) => {
      const { body } = this.collapsibleItem(`wizard:layer:${index}`, `Backfill layer ${index + 1}`, () => '', backfillBody);
      const used = this.renderWizardFields(
        record,
        'wizard_layer',
        index,
        ['MaterialKey', 'MaterialKey2', 'UniformMaterial', 'RowIndexMaterial', 'GenerateComputationalElements'],
        body,
        {},
        {
          UniformMaterial: 'Use one material across the whole layer. When false the layer is split between Material 1 and Material 2.',
          RowIndexMaterial: 'Number of rows assigned to material 1 before switching to material 2.',
          GenerateComputationalElements: 'Generate the computational quads/triangles for this layer.',
        },
        { MaterialKey: 'Material 1', MaterialKey2: 'Material 2' }
      );
    });

    const trunks = this.collections.wizard_trunk || [];
    if (trunks.length) {
      const trunkBody = this.collapsibleGroup('wizard:trunks', 'Trunks (curvature)', `${trunks.length}`);
      trunks.forEach((record, index) => {
        const { body } = this.collapsibleItem(`wizard:trunk:${index}`, `Trunk ${index + 1}`, () => '', trunkBody);
        const used = this.renderWizardFields(record, 'wizard_trunk', index, Object.keys(this.wizardRootNode(record)?.attributes || {}), body);
      });
    }
  }

  async addAbutmentEndRestraints() {
    if (this.busy) return;
    if (this.appliedGeometryChanges || [...this.changes.values()].some(change => change.collection.startsWith('wizard_'))) {
      this.status.classList.add('error');
      this.status.textContent = 'Regenerate and reopen the model before adding end restraints.';
      return;
    }
    this.busy = true;
    this.status.classList.remove('error');
    this.status.textContent = 'Adding fixed abutment end restraints…';
    try {
      const data = await this.json('/api/builder/abutment-restraints', {
        mode: 'edit', source: this.source, steps: this.editSteps, changes: [...this.changes.values()],
      });
      this.source = data.source;
      this.viewerSource = data.source;
      this.viewerSourceName = this.sourceName;
      this.collections = data.inspection.collections;
      this.materials = data.inspection.materials;
      this.analyses = data.inspection.analyses;
      this.changes.clear();
      this.editSteps = [];
      this.showModel(data.model, { preserveView: true });
      this.render();
      this.status.textContent = 'Fixed restraints added to both abutment ends. Download HRX to save.';
    } catch (error) {
      this.status.classList.add('error');
      this.status.textContent = error.message;
    } finally {
      this.busy = false;
    }
  }

  renderConfigurationEditor() {
    this.root.append(
      node(
        'p',
        'Model information and advanced solver/mesher options stored in ModelProperty and AdvancedOptionsDefault. These are model-wide settings; they do not change the saved results by themselves.'
      )
    );
    const settings = this.collections.model_settings?.[0];
    if (settings) {
      const body = this.collapsibleGroup('config:model', 'Model settings', 'HiStrA root');
      const used = this.renderWizardFields(
        settings,
        'model_settings',
        0,
        Object.keys(settings.attributes || {}),
        body,
        {},
        {
          DisableGeoLinksOnLoadingLateralEarthPressure: 'When checked, geotechnical links are disabled while lateral earth pressure is applied (C# Advanced options → Bridge).',
        }
      );
    }

    for (const [index, record] of (this.collections.model_property || []).entries()) {
      const body = this.collapsibleGroup(`config:property:${index}`, record.name, `${record.nodes.length} groups`);
      const used = this.renderWizardFields(record, 'model_property', index, Object.keys(record.attributes || {}), body);
    }

    const advanced = this.collections.advanced_options?.[0];
    if (advanced) {
      const body = this.collapsibleGroup('config:advanced', 'Advanced options', 'Solver / mesher');
      const used = this.renderWizardFields(
        advanced,
        'advanced_options',
        0,
        Object.keys(advanced.attributes || {}),
        body,
        {},
        {
          Solver: 'Internal solver selected in C# Advanced options → Solver.',
          SolverParallel: 'Use the parallel solver.',
          SaveAllSpringStatus: 'Save all link/spring status history.',
          MassMatrixType: 'Lumped or consistent mass matrix.',
          ToleranceNode: 'Tolerance used to check node coincidence.',
          TolerancePlane: 'Tolerance used to check whether a point lies on a plane.',
          InterfaceNrow: 'Number of link rows generated at an interface.',
          InterfaceImax: 'Maximum link distance used by the interface mesher.',
        }
      );
    }
  }

  loadEntryValue(kind, index, entry, key) {
    const id = `${kind}:${index}:${entry.path.join('.')}:${key}`;
    return this.changes.get(id)?.value ?? entry.attributes?.[key];
  }

  loadInput(entry, kind, index, key, options = null) {
    const original = entry.attributes?.[key];
    let input;
    if (options) {
      input = node('select');
      for (const [value, text] of options) input.add(new Option(text, value));
    } else if (['true', 'false'].includes(String(original))) {
      input = node('select');
      input.add(new Option('Yes', 'true'));
      input.add(new Option('No', 'false'));
    } else {
      input = node('input');
      if (Number.isFinite(Number(original)) && original !== '') input.type = 'number';
      input.step = 'any';
    }
    input.value = this.loadEntryValue(kind, index, entry, key) ?? original ?? '';
    input.addEventListener('change', () => this.wizardSet(kind, index, key, input.value, entry.path));
    return input;
  }

  loadDirectionValue(entry) {
    const x = Number(entry.attributes?.DirX ?? 0);
    const y = Number(entry.attributes?.DirY ?? 0);
    const z = Number(entry.attributes?.DirZ ?? 0);
    if (x === 0 && y === 0 && z < 0) return 'Gravity (-Z)';
    if (x === 1) return '+X';
    if (x === -1) return '-X';
    if (y === 1) return '+Y';
    if (y === -1) return '-Y';
    if (z === 1) return '+Z';
    if (z === -1) return '-Z';
    return `${x}, ${y}, ${z}`;
  }

  loadDirectionInput(entry, kind, index) {
    const select = node('select');
    for (const [value, text] of [
      ['0,0,-1', 'Gravity (-Z)'], ['1,0,0', '+X'], ['-1,0,0', '-X'],
      ['0,1,0', '+Y'], ['0,-1,0', '-Y'], ['0,0,1', '+Z'], ['0,0,-1', '-Z'],
    ]) select.add(new Option(text, value));
    const current = [entry.attributes?.DirX, entry.attributes?.DirY, entry.attributes?.DirZ].join(',');
    select.value = current;
    if (!select.value) select.selectedIndex = 0;
    select.addEventListener('change', () => {
      const [x, y, z] = select.value.split(',');
      this.wizardSet(kind, index, 'DirX', x, entry.path);
      this.wizardSet(kind, index, 'DirY', y, entry.path);
      this.wizardSet(kind, index, 'DirZ', z, entry.path);
    });
    return select;
  }

  renderLoadTemplateEditor(kind, index) {
    const record = this.collections[kind]?.[index];
    if (!record) return;
    const isVehicle = kind === 'vehicle_load';
    const body = this.collapsibleGroup(`loads:${kind}:header`, isVehicle ? 'Vehicle definition' : 'Line-load definition', record.name);
    const headerKeys = isVehicle
      ? ['Name', 'Description', 'DynamicCoefficient', 'D1', 'D2', 'D3', 'D4']
      : ['Name', 'Description', 'DynamicCoefficient'];
    const used = this.renderWizardFields(record, kind, index, headerKeys, body, {}, {
      DynamicCoefficient: 'Dynamic amplification factor applied to this load model.',
      D1: 'Distance d1 (C# vehicle header).', D2: 'Distance d2 (C# vehicle header).',
      D3: 'Distance d3 (C# vehicle header).', D4: 'Distance d4 (C# vehicle header).',
    });

    const rows = record.nodes.filter(entry => entry.tag === 'LoadTemplateItem');
    const tableBody = this.collapsibleGroup(`loads:${kind}:rows`, isVehicle ? 'Axle / point loads' : 'Line-load rows', `${rows.length} rows`);
    if (!rows.length) {
      tableBody.append(node('p', 'This load template has no rows.'));
      return;
    }
    const wrap = node('div');
    wrap.className = 'builder-table-wrap';
    const table = node('table');
    table.className = 'builder-table';
    const head = node('thead');
    const headRow = node('tr');
    const columns = isVehicle
      ? ['Name', 'Load condition', 'Direction', 'X', 'Y', 'Length', 'Width', 'Load value', 'ψ0', 'ψ1', 'ψ2']
      : ['Name', 'Load condition', 'Direction', 'Abscissa', 'X', 'Y', 'Load value', 'ψ0', 'ψ1', 'ψ2'];
    for (const label of columns) headRow.append(node('th', label));
    head.append(headRow);
    table.append(head);
    const tbody = node('tbody');
    for (const entry of rows) {
      const row = node('tr');
      row.append(node('td', entry.attributes?.Name || ''));
      row.append(this.cell(this.loadInput(entry, kind, index, 'IdLoadCondition')));
      row.append(this.cell(this.loadDirectionInput(entry, kind, index)));
      const keys = isVehicle
        ? ['X', 'Y', 'Length', 'Width', 'LoadValue', 'Psi0', 'Psi1', 'Psi2']
        : ['LoadAbscissa', 'X', 'Y', 'LoadValue', 'Psi0', 'Psi1', 'Psi2'];
      for (const key of keys) row.append(this.cell(this.loadInput(entry, kind, index, key)));
      tbody.append(row);
    }
    table.append(tbody);
    wrap.append(table);
    tableBody.append(wrap);
  }

  cell(content) {
    const td = node('td');
    if (content instanceof Node) td.append(content);
    else td.textContent = content ?? '';
    return td;
  }

  renderSchemaEditor(index) {
    const record = this.collections.schema?.[index];
    if (!record) return;
    const body = this.collapsibleGroup('loads:schema:header', 'Schema definition', record.name);
    const used = this.renderWizardFields(
      record,
      'schema',
      index,
      ['Name', 'Description', 'TypeSchema', 'SchemaPosition', 'NumPositions', 'VehicleCoeff', 'SerpeggioCoeff', 'FrenaturaCoeff', 'CentrifugaCoeff'],
      body,
      {
        TypeSchema: [['Gr1Schema1', 'Gr1Schema1'], ['Gr1Schema2', 'Gr1Schema2'], ['Gr2', 'Gr2']],
        SchemaPosition: [['WorthSections', 'Worth sections and additional positions'], ['EquallySpaced', 'Equally spaced']],
      },
      {
        NumPositions: 'Number of vehicle abscissa positions (0 means the worth-section table is used).',
        VehicleCoeff: 'Combination coefficient for vehicle loads (GC).',
        SerpeggioCoeff: 'Combination coefficient for swaying action.',
        FrenaturaCoeff: 'Combination coefficient for braking action.',
        CentrifugaCoeff: 'Combination coefficient for centrifugal action.',
      }
    );

    const paths = record.nodes.filter(entry => entry.tag === 'Path');
    const pathBody = this.collapsibleGroup('loads:schema:paths', 'Lane paths', `${paths.length} lanes`);
    if (paths.length) {
      const wrap = node('div');
      wrap.className = 'builder-table-wrap';
      const table = node('table');
      table.className = 'builder-table';
      const head = node('thead');
      const headRow = node('tr');
      for (const label of ['Lane', 'Vehicle', 'NumVehicle', 'Opposite', 'AreaLoad', 'Exclude area', 'L1', 'L2', 'LineLoad', 'Exclude line', 'L1', 'L2']) {
        headRow.append(node('th', label));
      }
      head.append(headRow);
      table.append(head);
      const tbody = node('tbody');
      for (const entry of paths) {
        const row = node('tr');
        row.append(node('td', entry.attributes?.Name || ''));
        for (const key of ['Vehicle', 'NumVehicles', 'Opposite', 'AreaLoad', 'excludeAreaLoadInVehicleArea', 'AreaLoadL1', 'AreaLoadL2', 'LineLoad', 'excludeLineLoadInVehicleArea', 'LineLoadL1', 'LineLoadL2']) {
          row.append(this.cell(this.loadInput(entry, 'schema', index, key)));
        }
        tbody.append(row);
      }
      table.append(tbody);
      wrap.append(table);
      pathBody.append(wrap);
    } else {
      pathBody.append(node('p', 'No lane paths.'));
    }

    const positions = record.nodes.filter(entry => entry.tag === 'Position');
    const positionBody = this.collapsibleGroup('loads:schema:positions', 'Vehicle abscissa positions', `${positions.length} positions`);
    if (positions.length) {
      const wrap = node('div');
      wrap.className = 'builder-table-wrap';
      const table = node('table');
      table.className = 'builder-table';
      const head = node('thead');
      const headRow = node('tr');
      for (const label of ['Position', 'Lane', 'Abscissa']) headRow.append(node('th', label));
      head.append(headRow);
      table.append(head);
      const tbody = node('tbody');
      for (const entry of positions) {
        const row = node('tr');
        row.append(node('td', entry.attributes?.Position || ''));
        row.append(this.cell(this.loadInput(entry, 'schema', index, 'Corsia')));
        row.append(this.cell(this.loadInput(entry, 'schema', index, 'Abscissa')));
        tbody.append(row);
      }
      table.append(tbody);
      wrap.append(table);
      positionBody.append(wrap);
    } else {
      positionBody.append(node('p', 'No explicit positions (equally spaced or worth sections only).'));
    }
  }

  renderCollectionEditor({ collections, changes, isCreate, fixedCategory = null }) {
    let activeKind = fixedCategory || this.selectedKind || 'material';
    if (!fixedCategory) {
      const kind = node('select');
      kind.setAttribute('aria-label', 'Property category');
      const loadCategories = COLLECTIONS.filter(([value]) => !['material', 'analysis'].includes(value));
      for (const [value, label] of loadCategories) kind.add(new Option(label, value));
      if (!loadCategories.some(([value]) => value === activeKind)) {
        activeKind = 'vehicle_load';
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

    const validSelected = indexedItems.some(({ idx }) => idx === this.selectedObject)
      ? this.selectedObject
      : indexedItems[0].idx;
    this.selectedObject = validSelected;

    if (['material', 'analysis'].includes(activeKind) && this.catalog) {
      const addBar = node('div');
      addBar.className = 'builder-add-bar';
      const addLabel = node('label');
      addLabel.className = 'builder-inline-label';
      addLabel.append(node('span', activeKind === 'material' ? 'Add material from catalog:' : 'Add analysis from catalog:'));
      const addSelect = node('select');
      addSelect.setAttribute('aria-label', activeKind === 'material' ? 'Material template' : 'Analysis template');
      if (activeKind === 'analysis') {
        for (const name of this.catalog.analyses) addSelect.add(new Option(name, name));
      } else {
        const masonryTemplates = this.catalog.materials.filter(t => !t.type || t.type.endsWith('.MasonryMaterial'));
        for (const template of masonryTemplates) addSelect.add(new Option(`${template.name} [${template.key}]`, template.key));
      }
      addLabel.append(addSelect);
      addBar.append(addLabel);
      this.button(
        activeKind === 'material' ? '+ Add material' : '+ Add analysis',
        () => this.apply({ op: activeKind === 'analysis' ? 'add_analysis' : 'add_material', template: addSelect.value }, allItems.length, isCreate),
        addBar
      );
      this.root.append(addBar);
    }

    const selectionBar = node('div');
    selectionBar.className = 'builder-selection-bar';
    const selectLabel = node('label');
    selectLabel.className = 'builder-current-label';
    const currentTitle = activeKind === 'material' ? 'Selected material:' : activeKind === 'analysis' ? 'Selected analysis:' : 'Selected entry:';
    selectLabel.append(node('span', currentTitle));
    const select = node('select');
    select.setAttribute('aria-label', 'Model entry');
    indexedItems.forEach(({ item, idx }) => select.add(new Option(`${item.name} [${item.key}]`, idx)));
    select.value = validSelected;
    select.addEventListener('change', () => {
      this.selectedObject = Number(select.value);
      this.selectedNode = 0;
      this.render();
    });
    selectLabel.append(select);
    selectionBar.append(selectLabel);

    if (['material', 'analysis'].includes(activeKind) && this.catalog) {
      const itemActions = node('div');
      itemActions.className = 'builder-item-actions';
      this.button(
        'Duplicate',
        () => this.apply({ op: activeKind === 'analysis' ? 'duplicate_analysis' : 'duplicate_material', duplicate: validSelected }, allItems.length, isCreate),
        itemActions
      );
      this.button(
        'Delete',
        () => this.apply({ op: activeKind === 'analysis' ? 'delete_analysis' : 'delete_material', index: validSelected }, Math.max(0, validSelected - 1), isCreate),
        itemActions
      );
      selectionBar.append(itemActions);
    }
    this.root.append(selectionBar);

    const item = allItems[validSelected];
    if (activeKind === 'vehicle_load' || activeKind === 'line_load') {
      this.renderLoadTemplateEditor(activeKind, validSelected);
      return;
    }
    if (activeKind === 'schema') {
      this.renderSchemaEditor(validSelected);
      return;
    }
    if (!item.nodes.length) {
      this.root.append(node('p', 'No editable attributes.'));
      return;
    }

    if (activeKind === 'material') {
      this.renderMaterialEditor(item, validSelected, changes);
      return;
    }
    if (activeKind === 'analysis') {
      this.renderAnalysisEditor(item, validSelected, changes);
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
      const label = node('label', LOAD_LABELS[key] || CONFIG_LABELS[key] || key);
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
        this.scheduleGeometryPreview();
      });
      label.append(input);
      grid.append(label);
    }
    this.root.append(grid);
  }

  renderAnalysisEditor(item, index, changes) {
    const rootEntry = item.nodes.find(entry => !entry.path.length);
    if (!rootEntry) { this.root.append(node('p', 'This analysis has no editable properties.')); return; }
    const currentAttrs = { ...rootEntry.attributes };
    const typeChange = changes.get(`analysis:${index}::AnalysisType`);
    if (typeChange) currentAttrs.AnalysisType = typeChange.value;
    const groups = analysisPropertyGroups(currentAttrs);
    if (item.nodes.some(entry => entry.path.length && !entry.tag.toLowerCase().includes('dynamic'))) groups.push({ id: 'nested', title: 'Additional sections', keys: [] });
    if (!groups.some(group => group.id === this.analysisEditorGroup)) this.analysisEditorGroup = groups[0]?.id;
    this.renderTabs(groups.map(group => [group.id, group.title]), this.analysisEditorGroup, group => {
      this.analysisEditorGroup = group; this.render();
    });
    let entry = rootEntry;
    let keys = groups.find(group => group.id === this.analysisEditorGroup)?.keys || [];
    if (this.analysisEditorGroup === 'nested') {
      const children = item.nodes.filter(candidate => candidate.path.length && !candidate.tag.toLowerCase().includes('dynamic'));
      const section = node('select'); section.setAttribute('aria-label', 'Additional analysis section');
      children.forEach((candidate, i) => section.add(new Option(`${candidate.tag} (${candidate.path.join('.')})`, i)));
      const current = Math.max(0, Math.min(this.selectedNode || 0, children.length - 1));
      section.value = current;
      section.addEventListener('change', () => { this.selectedNode = Number(section.value); this.render(); });
      this.root.append(section); entry = children[current]; keys = Object.keys(entry.attributes);
    }
    const panel = node('section'); panel.className = 'builder-property-section';
    panel.append(node('h3', groups.find(group => group.id === this.analysisEditorGroup)?.title || 'Analysis properties'));
    if (keys.includes('PdeltaEffect')) {
      const note = node('p', 'This changes the saved analysis setting. The Analysis run panel also has a separate P-Delta setting for a run.');
      note.className = 'builder-property-note'; panel.append(note);
    }
    const grid = node('div'); grid.className = 'builder-property-grid';
    if (this.analysisEditorGroup === 'control' && ['1', '2'].includes(String(changes.get(`analysis:${index}::AnalysisType`)?.value ?? rootEntry.attributes.AnalysisType))) {
      this.renderAnalysisSteps(item, index, changes, grid);
    }
    for (const key of keys) {
      const original = String(entry.attributes[key]);
      const id = `analysis:${index}:${entry.path.join('.')}:${key}`;
      const row = node('label'); row.className = 'builder-property-row';
      const title = node('span', ANALYSIS_LABELS[key] || key.replace(/([a-z0-9])([A-Z])/g, '$1 $2'));
      title.title = key; row.append(title);
      let input;
      if (key === 'AnalysisType' && !entry.path.length && ['1', '2', '3', '4', '5'].includes(original)) {
        input = node('select');
        for (const [value, text] of [['1', 'Static linear'], ['2', 'Static nonlinear'], ['3', 'Dynamic linear'], ['4', 'Dynamic nonlinear'], ['5', 'Modal']]) input.add(new Option(text, value));
      } else if (ENUMS[key]) {
        input = node('select');
        for (const value of [...new Set([...ENUMS[key], original])]) {
          if (key === 'IntegrationMethod' && ['NewmarkMethod', 'HHTmethod', 'WilsonMethod'].includes(value) && value !== original) continue;
          input.add(new Option(key === 'PdeltaEffect' ? (PDELTA_LABELS[value] || value) : value, value));
        }
      } else if (['true', 'false'].includes(original)) {
        input = node('select'); input.add(new Option('Yes', 'true')); input.add(new Option('No', 'false'));
      } else input = node('input');
      input.value = changes.get(id)?.value ?? original;
      input.addEventListener('change', () => {
        if (input.value === original) changes.delete(id);
        else changes.set(id, { collection: 'analysis', index, node: entry.path, attribute: key, value: input.value });
        if (key === 'AnalysisType') this.render();
        this.scheduleGeometryPreview();
      });
      row.append(input); grid.append(row);
    }
    panel.append(grid); this.root.append(panel);
  }

  renderAnalysisSteps(item, index, changes, parent) {
    const attrs = item.nodes.find(entry => !entry.path.length)?.attributes || {};
    const key = changes.get(`analysis:${index}::LoadFunctionKey`)?.value ?? attrs.LoadFunctionKey;
    const collections = this.mode === 'create' ? this.createCollections : this.collections;
    const functions = collections.load_function || [];
    const functionIndex = functions.findIndex(record => String(record.key) === String(key));
    const fn = functions[functionIndex];
    if (!fn) return;
    const fnAttrs = fn.nodes.find(entry => !entry.path.length)?.attributes || {};
    const points = (collections.load_function_item || []).filter(record => String(record.attributes?.loadFunctionKey ?? record.attributes?.LoadFunctionKey) === String(key));
    const type = String(fnAttrs.typeDiscr ?? fnAttrs.TypeDiscr ?? 'false');
    const field = Object.hasOwn(fnAttrs, 'DiscrVal') ? 'DiscrVal' : 'discrVal';
    const changeId = `load_function:${functionIndex}::${field}`;
    const value = Number(changes.get(changeId)?.value ?? fnAttrs[field]);
    const ordered = [...points].sort((a, b) => Number(a.attributes.pseudoTime) - Number(b.attributes.pseudoTime));
    const axis = type === 'true' ? 'multiplier' : 'pseudoTime';
    const span = ordered.length === 2 ? Math.abs(Number(ordered[1].attributes[axis]) - Number(ordered[0].attributes[axis])) : NaN;
    if (type !== 'false' || !Number.isFinite(span) || span <= 0 || !Number.isFinite(value) || value <= 0) {
      const message = node('p', 'Step count is unavailable for this load function. Edit its discretization under Loads → Load functions.');
      message.className = 'builder-property-note'; parent.append(message); return;
    }
    const row = node('label'); row.className = 'builder-property-row';
    const title = node('span', 'Number of analysis steps'); row.append(title);
    const input = node('input'); input.type = 'number'; input.min = '1'; input.max = '100000'; input.step = '1';
    input.value = String(Math.max(1, Math.ceil(span / value - 1e-10)));
    input.addEventListener('change', () => {
      const count = Number(input.value);
      if (!Number.isSafeInteger(count) || count < 1 || count > 100000) {
        input.setCustomValidity('Enter a whole number between 1 and 100000.'); input.reportValidity(); return;
      }
      input.setCustomValidity('');
      // A tiny upward adjustment avoids floating-point ceil producing N+1 steps.
      const next = String((span / count) * (1 + 1e-12));
      if (Math.abs(Number(fnAttrs[field]) - Number(next)) < Math.abs(Number(next)) * 1e-11) changes.delete(changeId);
      else changes.set(changeId, { collection: 'load_function', index: functionIndex, node: [], attribute: field, value: next });
      this.scheduleGeometryPreview();
    });
    row.append(input); parent.append(row);
    const shared = (collections.analysis || []).filter((record, analysisIndex) =>
      String(changes.get(`analysis:${analysisIndex}::LoadFunctionKey`)?.value ?? record.attributes?.LoadFunctionKey) === String(key)).length;
    const scourNote = /^scour/i.test(attrs.Name || '') ? ' The soil material changes before the first step; increasing steps does not divide that change.' : '';
    const note = node('p', `Sets the load-function discretization${shared > 1 ? ` shared by ${shared} analyses` : ''}. This controls solver increments, not the number of load-function points.${scourNote}`);
    note.className = 'builder-property-note'; parent.append(note);
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
      this.scheduleGeometryPreview();
    };

    const formatPoisson = () => {
      const eVal = Number(getVal('Ehor') ?? getVal('E'));
      const gVal = Number(getVal('Gd') ?? getVal('G'));
      if (Number.isFinite(eVal) && Number.isFinite(gVal) && gVal > 0) {
        const nu = eVal / (2 * gVal) - 1;
        if (Number.isFinite(nu)) {
          return ` (v=${Number(nu.toFixed(2)).toString()})`;
        }
      }
      return '';
    };

    const addAttrField = (parent, labelText, key, customOptions = null, rerenderOnChange = false) => {
      if (!key || attrs[key] === undefined) return;
      const original = attrs[key];

      const isDim = Boolean(dimension(key));
      const u = isDim ? unitFor(key, this.materialUnits) : null;
      const uSuffix = u && u !== '—' ? ` [${u}]` : '';

      const getFullLabel = () => {
        let text = labelText;
        if (key === 'Gd') {
          text += formatPoisson();
        }
        text += uSuffix;
        return text;
      };

      const label = node('label');
      const labelSpan = node('span', getFullLabel());
      if (key === 'Gd') labelSpan.setAttribute('data-poisson-gd', 'true');
      label.append(labelSpan);

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
        if (isDim || typeof original === 'number' || Number.isFinite(Number(original))) {
          input.type = 'number';
          input.step = 'any';
        }
      }

      const rawVal = getVal(key);
      const displayVal = isDim ? convertedValue(rawVal, key, this.materialUnits) : (rawVal ?? '');
      input.value = displayVal ?? '';

      input.addEventListener('change', () => {
        let saveVal = input.value;
        if (isDim && input.value !== '') {
          saveVal = toNativeValue(input.value, key, this.materialUnits);
        }
        setVal(key, saveVal);
        if (rerenderOnChange || key === 'Ehor' || key === 'Gd') this.render();
      });

      if (key === 'Ehor' || key === 'Gd') {
        input.addEventListener('input', () => {
          const gdLabels = this.root.querySelectorAll('[data-poisson-gd]');
          for (const gdLabel of gdLabels) {
            let eVal = Number(key === 'Ehor' ? (isDim ? toNativeValue(input.value, 'Ehor', this.materialUnits) : input.value) : (getVal('Ehor') ?? getVal('E')));
            let gVal = Number(key === 'Gd' ? (isDim ? toNativeValue(input.value, 'Gd', this.materialUnits) : input.value) : (getVal('Gd') ?? getVal('G')));
            let pStr = '';
            if (Number.isFinite(eVal) && Number.isFinite(gVal) && gVal > 0) {
              const nu = eVal / (2 * gVal) - 1;
              if (Number.isFinite(nu)) {
                pStr = ` (v=${Number(nu.toFixed(2)).toString()})`;
              }
            }
            const gdUnit = unitFor('Gd', this.materialUnits);
            const gdUnitSuffix = gdUnit && gdUnit !== '—' ? ` [${gdUnit}]` : '';
            gdLabel.textContent = `Shear modulus, G${pStr}${gdUnitSuffix}`;
          }
        });
      }

      label.append(input);
      parent.append(label);
    };

    const unitBar = node('div');
    unitBar.className = 'builder-unit-bar';
    const unitLabel = node('label');
    unitLabel.className = 'builder-unit-label';
    unitLabel.append(node('span', 'Display units:'));
    const unitSelect = node('select');
    unitSelect.setAttribute('aria-label', 'Material display units');
    for (const [uKey, uDef] of Object.entries(unitSets)) {
      unitSelect.add(new Option(uDef.label, uKey, false, uKey === this.materialUnits));
    }
    unitSelect.addEventListener('change', () => {
      this.materialUnits = unitSelect.value;
      this.render();
    });
    unitLabel.append(unitSelect);
    unitBar.append(unitLabel);
    this.root.append(unitBar);

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
      addAttrField(behaviorGrid, 'Check contact area for the evaluation of the shear strength', 'CheckContactArea');
      const contactHelp = node(
        'small',
        'When checked, the sliding spring uses the current contact area instead of the full interface area. As the joint opens, the cohesion term and the shear limit are scaled by contactArea/Area. Unchecked, the full area is used.'
      );
      contactHelp.className = 'builder-help';
      this.root.append(behaviorGrid, contactHelp);

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
    const footnote = node('p', 'HRX models are always exported in default native units (kN, cm, kN/cm²). Display unit conversion applies to view and edition.');
    footnote.className = 'builder-help';
    this.root.append(footnote);
  }

  renderManage(kind, items, index, isCreate = false) {
    // Managed actions (Add / Duplicate / Delete) are rendered in renderCollectionEditor
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
        this.status.textContent = 'Change applied to bridge definition.';
      } else {
        const pendingChanges = [...this.changes.values()];
        const geometryEdited = pendingChanges.some(change => change.collection.startsWith('wizard_'));
        const data = await this.json('/api/builder/apply', {
          mode: 'edit',
          source: this.source,
          steps: this.editSteps,
          changes: pendingChanges,
          operations: [operation],
        });
        this.editSteps.push({ changes: pendingChanges, operations: [operation] });
        this.appliedGeometryChanges ||= geometryEdited;
        this.collections = data.inspection.collections;
        this.materials = data.inspection.materials;
        this.analyses = data.inspection.analyses;
        this.changes.clear();
        this.selectedObject = Math.max(0, Math.min(selected, (this.collections[this.selectedKind || 'material'] || []).length - 1));
        this.selectedNode = 0;
        this.render();
        this.status.textContent = 'Change applied.';
      }
      this.scheduleGeometryPreview();
    } catch (e) {
      this.status.textContent = e.message;
      this.status.classList.add('error');
    } finally {
      this.busy = false;
    }
  }

  async run() {
    if (this.busy) return;
    if (this.mode === 'edit' && !this.source) {
      this.status.textContent = 'Choose an HRX file first.';
      return;
    }
    const geometryEdited = this.mode === 'edit' && (this.appliedGeometryChanges || [...this.changes.values()].some(change => change.collection.startsWith('wizard_')));
    this.busy = true;
    this.status.classList.remove('error');
    this.status.textContent = 'Preparing HRX…';
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
            steps: this.editSteps,
            changes: [...this.changes.values()],
            rebuild_geometry: geometryEdited,
          };
    try {
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
    } catch (e) {
      this.status.textContent = e.message;
      this.status.classList.add('error');
    } finally {
      this.busy = false;
    }
  }
}
