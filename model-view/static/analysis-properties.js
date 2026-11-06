// Pure C# WindowAnalysesDefinition field mappings, labels, and formatters for HiStrA HRX analyses.

export const ANALYSIS_TYPE_LABELS = {
  '1': 'Static linear',
  '2': 'Static nonlinear',
  '3': 'Dynamic linear',
  '4': 'Dynamic nonlinear',
  '5': 'Modal',
};

export const STATE_LABELS = {
  ExecutedCompleted: 'Executed and completed',
  ExecutedNotCompleted: 'Executed and not completed',
  ExecutedNotStarted: 'Executed and not started',
  NotExecutedNotToBeExecuted: 'Not executed and not to be executed',
  NotExecutedToBeExecute: 'Not Executed',
};

export const STATE_SHORT_LABELS = {
  ExecutedCompleted: 'Completed',
  ExecutedNotCompleted: 'Incomplete',
  ExecutedNotStarted: 'Not started',
  NotExecutedNotToBeExecuted: 'Not executed',
  NotExecutedToBeExecute: 'To execute',
};

export const STATE_CODES = {
  ExecutedCompleted: 'E',
  ExecutedNotCompleted: 'I',
  ExecutedNotStarted: 'NS',
  NotExecutedNotToBeExecuted: 'NR',
  NotExecutedToBeExecute: 'NE',
};

export const ARC_LENGTH_PROCEDURE_LABELS = {
  OnlyControlPoint: 'Control point selected (DISPLACEMENT CONTROL METHOD)',
  OnlyModelPointsSelected: 'Model points selected (REDUCED ARC LENGTH METHOD)',
  AllDegreesOfFreedom: 'All degrees of freedom (ARC LENGTH METHOD)',
};

export const PDELTA_LABELS = {
  None: 'No (None)',
  EachStep: 'Update geometry at each step (EachStep)',
  EachIteration: 'Update geometry at each iteration (EachIteration)',
};

export const CONVERGENCE_CRITERIA_LABELS = {
  ForceMoment: 'Force (ForceMoment)',
  DispRotation: 'Displacement (DispRotation)',
  Work: 'Work (Work)',
};

export const MODAL_PROCEDURE_LABELS = {
  SubspaceIterations: 'Subspace iterations (SubspaceIterations)',
  InverseIterations: 'Inverse iterations (InverseIterations)',
  SparseBlockInverseSubspace: 'Sparse block inverse subspace (SparseBlockInverseSubspace)',
};

export const MODAL_CONVERGENCE_LABELS = {
  Frquency: 'Eigenvalue / Frequency (Frquency)',
  EigenVector: 'Eigenvector (EigenVector)',
};

export const DYNAMIC_INTEGRATION_LABELS = {
  NewmarkMethod: 'Newmark Method (NewmarkMethod)',
  HHTmethod: 'HHT Method (HHTmethod)',
  WilsonMethod: 'Wilson Method (WilsonMethod)',
};

export const LOAD_DISTRIBUTION_LABELS = {
  Force: 'Force (Force)',
  LoadCombination: 'Force / Load combination (LoadCombination)',
  Modal: 'Modal (Modal)',
  Triangular: 'Triangular (Triangular)',
  Adaptive: 'Adaptive (Adaptive)',
  ShearFloor: 'Shear floor (ShearFloor)',
};

export const PUSH_MODAL_TYPE_LABELS = {
  Single: 'Single mode (Single)',
  Mass: 'Multi-modal with min participating mass (Mass)',
  Custom: 'Custom multi-modal (Custom)',
};

export function attr(attributes, key) {
  const value = attributes?.[key];
  return value === undefined || value === null || value === '' ? '—' : String(value);
}

export function boolText(value) {
  if (value === 'true' || value === true) return 'Yes (true)';
  if (value === 'false' || value === false) return 'No (false)';
  return value === undefined || value === null || value === '' ? '—' : String(value);
}

export function formatStartFrom(analysis) {
  if (analysis?.initialAnalysisName) {
    return `${analysis.initialAnalysisName} (#${analysis.initialAnalysisKey})`;
  }
  const key = analysis?.initialAnalysisKey ?? analysis?.attributes?.InitialAnalysisKey;
  if (key === '-100' || key === '' || key === undefined || key === null) {
    return 'Zero';
  }
  return `Zero (#${key})`;
}

export function formatControlPoint(analysis) {
  const key = analysis?.masterPoint ?? analysis?.attributes?.MasterPoint ?? '';
  if (key === '-10') return 'MaxDisplacement (-10)';
  if (analysis?.masterPointName) return `${analysis.masterPointName} (#${key})`;
  return key ? `#${key}` : '—';
}

export function formatDirectionSummary(attributes = {}) {
  const dx = Number(attributes.DirX ?? 0);
  const dy = Number(attributes.DirY ?? 0);
  const dz = Number(attributes.DirZ ?? 0);
  if (dx === 1 && dy === 0 && dz === 0) return '+X';
  if (dx === -1 && dy === 0 && dz === 0) return '-X';
  if (dx === 0 && dy === 1 && dz === 0) return '+Y';
  if (dx === 0 && dy === -1 && dz === 0) return '-Y';
  if (dx === 0 && dy === 0 && dz === 1) return '+Z';
  if (dx === 0 && dy === 0 && dz === -1) return '-Z';
  if (attributes.DirX !== undefined || attributes.DirY !== undefined || attributes.DirZ !== undefined) {
    return `${attributes.DirX ?? 0}, ${attributes.DirY ?? 0}, ${attributes.DirZ ?? 0}`;
  }
  return '—';
}

export function decomposeIterativeMethod(methodRaw) {
  if (!methodRaw) {
    return { raw: '—', newtonType: '—', lineSearch: '—', lineSearchType: '—' };
  }
  const isModified = methodRaw.startsWith('Modified');
  const isStandard = methodRaw.startsWith('Standard');
  const newtonType = isModified
    ? 'Modified Newton-Raphson'
    : (isStandard ? 'Standard Newton-Raphson' : methodRaw);
  const noLineSearch = methodRaw === 'StandardNewtonRaphson' || methodRaw === 'ModifiedNewtonRaphson';
  let lineSearchType = 'None';
  if (methodRaw.endsWith('SecantLineSearch')) lineSearchType = 'Secant';
  else if (methodRaw.endsWith('RegulaFalsiLineSearch')) lineSearchType = 'Regula-Falsi';
  else if (methodRaw.endsWith('BisectionLineSearch')) lineSearchType = 'Bisection';
  else if (methodRaw.endsWith('InitialInterpolatedLineSearch')) lineSearchType = 'Initial Interpolated';
  return {
    raw: methodRaw,
    newtonType,
    lineSearch: noLineSearch ? 'No (false)' : 'Yes (true)',
    lineSearchType,
  };
}

export function formatArcLengthRay(dr2Raw) {
  if (dr2Raw === undefined || dr2Raw === null || dr2Raw === '') return '—';
  const num = Number(dr2Raw);
  if (!Number.isFinite(num) || num < 0) return String(dr2Raw);
  const dr = Math.sqrt(num);
  const rounded = Number(dr.toFixed(8));
  return `${rounded} (Dr2 = ${dr2Raw})`;
}

export function formatExitDescription(raw) {
  if (!raw) return '—';
  return String(raw).replace(/@/g, '\n');
}

export function formatDiscretizationMode(typeDiscr) {
  if (typeDiscr === 'false' || typeDiscr === false) {
    return 'Discretization by pseudo-time (false)';
  }
  if (typeDiscr === 'true' || typeDiscr === true) {
    return 'Discretization by load multiplier (true)';
  }
  return typeDiscr ? String(typeDiscr) : '—';
}

// Time-history-only settings are not used by static or modal analyses.
export function isDynamicOnlyAnalysisField(key) {
  return key.startsWith('Dynamic') || key.startsWith('Damping') || [
    'AnalysisStepSize', 'FirstFrequency', 'SecondFrequency', 'SetInitialAccelerations',
    'AdapticIntegrationScheme', 'AdapticMassDampingParameter', 'AdapticStiffDampingParameter',
  ].includes(key);
}
