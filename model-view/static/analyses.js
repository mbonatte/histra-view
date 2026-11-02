import {
  ANALYSIS_TYPE_LABELS,
  STATE_LABELS,
  STATE_SHORT_LABELS,
  STATE_CODES,
  ARC_LENGTH_PROCEDURE_LABELS,
  PDELTA_LABELS,
  CONVERGENCE_CRITERIA_LABELS,
  MODAL_PROCEDURE_LABELS,
  MODAL_CONVERGENCE_LABELS,
  DYNAMIC_INTEGRATION_LABELS,
  LOAD_DISTRIBUTION_LABELS,
  PUSH_MODAL_TYPE_LABELS,
  attr,
  boolText,
  formatStartFrom,
  formatControlPoint,
  formatDirectionSummary,
  decomposeIterativeMethod,
  formatArcLengthRay,
  formatExitDescription,
  formatDiscretizationMode,
} from './analysis-properties.js';

const $ = id => document.getElementById(id);
const node = (tag, className = '', text) => {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
};

const TABS = [
  ['control', 'Control parameters'],
  ['iterative', 'Iterative strategy'],
  ['convergence', 'Convergence criteria'],
  ['points', 'Model points'],
  ['function', 'Load function'],
  ['loads', 'Loads applied'],
  ['dynamic', 'Damping & stages'],
  ['all', 'All properties'],
];

function renderLoadFunctionPreview(items = []) {
  const pts = items
    .map(item => ({ t: Number(item.pseudoTime), m: Number(item.multiplier) }))
    .filter(p => Number.isFinite(p.t) && Number.isFinite(p.m));
  const box = node('section', 'hysteresis-preview');
  box.append(node('h2', '', 'Load function curve — Multiplier vs Pseudo-time'));
  if (!pts.length) {
    box.append(node('p', 'material-note', 'No serialized LoadFunctionItem points found for this analysis.'));
    return box;
  }
  const plot = node('div', 'hysteresis-plot');
  const width = 640;
  const height = 230;
  const padL = 58;
  const padR = 26;
  const padT = 22;
  const padB = 42;
  const minT = Math.min(0, ...pts.map(p => p.t));
  const maxT = Math.max(1, ...pts.map(p => p.t));
  const minM = Math.min(0, ...pts.map(p => p.m));
  const maxM = Math.max(1, ...pts.map(p => p.m));
  const spanT = maxT - minT || 1;
  const spanM = maxM - minM || 1;
  const x = t => padL + ((t - minT) / spanT) * (width - padL - padR);
  const y = m => height - padB - ((m - minM) / spanM) * (height - padT - padB);

  const polyPoints = pts.map(p => `${x(p.t).toFixed(1)},${y(p.m).toFixed(1)}`).join(' ');
  const circles = pts
    .map(p => `<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.m).toFixed(1)}" r="4.5" class="plot-marker"><title>(${p.t}, ${p.m})</title></circle>`)
    .join('');

  plot.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Load function multiplier vs pseudo-time">
      <line x1="${padL}" y1="${padT}" x2="${width - padR}" y2="${padT}" class="plot-grid"/>
      <line x1="${padL}" y1="${(padT + height - padB) / 2}" x2="${width - padR}" y2="${(padT + height - padB) / 2}" class="plot-grid"/>
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" class="plot-zero"/>
      <line x1="${padL}" y1="${height - padB}" x2="${width - padR}" y2="${height - padB}" class="plot-zero"/>
      <text x="${padL - 8}" y="${padT + 4}" text-anchor="end" class="plot-tick">${maxM}</text>
      <text x="${padL - 8}" y="${height - padB}" text-anchor="end" class="plot-tick">${minM}</text>
      <text x="${padL}" y="${height - 16}" text-anchor="start" class="plot-tick">${minT}</text>
      <text x="${width - padR}" y="${height - 16}" text-anchor="end" class="plot-tick">${maxT}</text>
      <text x="${(padL + width - padR) / 2}" y="${height - 6}" text-anchor="middle" class="plot-label">Time (pseudoTime)</text>
      <text x="16" y="${(padT + height - padB) / 2}" text-anchor="middle" class="plot-label" transform="rotate(-90 16 ${(padT + height - padB) / 2})">Multiplier</text>
      <polyline points="${polyPoints}" class="hysteresis-curve"/>
      ${circles}
    </svg>
  `;
  box.append(plot);
  box.append(node('p', 'material-note', 'Plotted directly from saved <LoadFunctionItem> pseudoTime and multiplier pairs (mirrors C# GrapichsUserControl1).'));
  return box;
}

export class AnalysesPage {
  constructor() {
    this.analyses = [];
    this.selected = null;
    this.tab = 'control';
    this.subComboRowKey = null;
    if ($('analysisSearch')) $('analysisSearch').oninput = () => this.renderList();
    if ($('executedAnalysesOnly')) $('executedAnalysesOnly').onchange = () => this.renderList();
    if ($('mobileAnalysisSelect')) {
      $('mobileAnalysisSelect').onchange = () => {
        this.selected = this.analyses.find(a => String(a.key) === String($('mobileAnalysisSelect').value));
        this.subComboRowKey = null;
        this.render();
      };
    }
  }

  setModel(model) {
    this.analyses = model?.analyses || [];
    const prevKey = this.selected?.key;
    this.selected = this.analyses.find(a => String(a.key) === String(prevKey))
      || this.analyses.find(a => a.isExecuted)
      || this.analyses[0]
      || null;
    this.subComboRowKey = null;
    if ($('analysisSearch')) $('analysisSearch').value = '';
    this.render();
  }

  open(key) {
    const selected = this.analyses.find(a => String(a.key) === String(key));
    if (selected) {
      this.selected = selected;
      this.subComboRowKey = null;
      this.render();
    }
    const doc = $('analysesPage')?.querySelector('.material-document');
    if (doc) doc.scrollTop = 0;
    location.hash = 'analyses';
  }

  renderList() {
    const list = $('analysisLibraryList');
    if (!list) return;
    const query = ($('analysisSearch')?.value || '').trim().toLowerCase();
    const executedOnly = Boolean($('executedAnalysesOnly')?.checked);
    const rows = this.analyses.filter(a => {
      if (executedOnly && !a.isExecuted) return false;
      if (!query) return true;
      const haystack = `${a.name} ${a.key} ${a.type} ${a.description || ''} ${a.loadCombinationName || ''} ${a.state?.State || ''}`.toLowerCase();
      return haystack.includes(query);
    });
    if ($('analysisLibraryCount')) {
      $('analysisLibraryCount').textContent = `${rows.length}/${this.analyses.length}`;
    }
    list.replaceChildren();
    for (const analysis of rows) {
      const isSelected = String(this.selected?.key) === String(analysis.key);
      const button = node('button', 'library-material');
      button.classList.toggle('selected', isSelected);
      button.setAttribute('aria-pressed', String(isSelected));
      const swatch = node('span', 'swatch');
      swatch.style.background = analysis.isExecuted ? '#60d9c5' : '#586d7d';
      const info = node('span');
      const startFrom = formatStartFrom(analysis);
      info.append(
        node('strong', '', analysis.name || `Analysis ${analysis.key}`),
        node('small', '', `${analysis.type} · #${analysis.key} · from ${startFrom}`)
      );
      const stateRaw = analysis.state?.State || '';
      const shortState = STATE_SHORT_LABELS[stateRaw] || stateRaw || 'Unset';
      const code = STATE_CODES[stateRaw] ? `${STATE_CODES[stateRaw]} · ` : '';
      const badge = node('span', 'assignment-badge', `${code}${shortState}`);
      badge.title = STATE_LABELS[stateRaw] || stateRaw || 'No saved state';
      button.append(swatch, info, badge);
      button.onclick = () => {
        this.selected = analysis;
        this.subComboRowKey = null;
        this.render();
      };
      list.append(button);
    }
    if (!rows.length) {
      list.append(node('p', 'material-note', this.analyses.length ? 'No matching analyses.' : 'No analyses are defined in this model.'));
    }
  }

  render() {
    this.renderList();
    const analysis = this.selected;
    const header = $('analysisDocumentHeader');
    const tablist = $('analysisMechanismTabs');
    const mobileSelect = $('mobileAnalysisSelect');
    const content = $('analysisContent');
    if (!header || !tablist || !content) return;

    if (!analysis) {
      header.replaceChildren();
      tablist.replaceChildren();
      if (mobileSelect) mobileSelect.replaceChildren();
      content.replaceChildren(node('p', 'material-note', 'No analyses are defined in this model.'));
      return;
    }

    const a = analysis.attributes || {};
    const stateRaw = analysis.state?.State || '';
    const stateText = STATE_LABELS[stateRaw] || stateRaw || 'Not executed';

    if (mobileSelect) {
      mobileSelect.replaceChildren(
        ...this.analyses.map(item => {
          const st = STATE_SHORT_LABELS[item.state?.State] || item.state?.State || 'Unset';
          return new Option(`${item.name} · #${item.key} · ${item.type} (${st})`, item.key, false, String(item.key) === String(analysis.key));
        })
      );
    }

    header.replaceChildren();
    const heading = node('div', 'material-heading');
    const title = node('div');
    title.append(
      node('div', 'eyebrow', 'ANALYSIS DEFINITION'),
      node('h1', '', analysis.name || `Analysis ${analysis.key}`),
      node('p', '', analysis.description || `${analysis.type} — ${stateText}`)
    );
    const badge = node('span', 'material-mode', `${analysis.type} · ${STATE_SHORT_LABELS[stateRaw] || stateRaw || 'Unset'}`);
    heading.append(title, badge);

    const meta = node('div', 'material-meta');
    const chip = node('span', 'material-color-chip');
    chip.style.background = analysis.isExecuted ? '#60d9c5' : '#586d7d';
    const comboLabel = analysis.analysisType === '5' ? 'Mass source' : 'Load combo';
    const comboVal = analysis.loadCombinationName
      ? `${analysis.loadCombinationName} (#${analysis.loadCombinationKey})`
      : attr(a, 'LoadCombinationKey');
    meta.append(
      chip,
      node('span', '', `Key ${analysis.key}`),
      node('span', '', `Start from: ${formatStartFrom(analysis)}`),
      node('span', '', `${comboLabel}: ${comboVal}`),
      node('span', '', `Seismic: ${boolText(a.IsSeismic)}`),
      node('span', '', `Direction: ${formatDirectionSummary(a)}`),
      node('span', '', `Control point: ${formatControlPoint(analysis)}`),
      node('span', '', `Step: ${analysis.state?.Step ?? '0'} · Fo: ${analysis.state?.Fo ?? '0'} kN`)
    );
    header.append(heading, meta);

    if (!TABS.some(([key]) => key === this.tab)) this.tab = 'control';
    tablist.replaceChildren();
    for (const [key, label] of TABS) {
      let suffix = '';
      if (key === 'points') {
        const activeCount = (analysis.modelPoints || []).filter(p => p.active === 'true').length;
        suffix = ` (${activeCount}/${(analysis.modelPoints || []).length})`;
      } else if (key === 'function' && analysis.loadFunction?.items?.length) {
        suffix = ` (${analysis.loadFunction.items.length})`;
      }
      const button = node('button', '', `${label}${suffix}`);
      button.setAttribute('role', 'tab');
      button.id = `analysis-group-${key}`;
      button.setAttribute('aria-controls', 'analysisContent');
      button.setAttribute('aria-selected', String(key === this.tab));
      button.onclick = () => {
        this.tab = key;
        this.render();
      };
      tablist.append(button);
    }
    content.setAttribute('aria-labelledby', `analysis-group-${this.tab}`);
    content.replaceChildren();

    if (this.tab === 'iterative') this.renderIterative(analysis, content);
    else if (this.tab === 'convergence') this.renderConvergence(analysis, content);
    else if (this.tab === 'points') this.renderModelPoints(analysis, content);
    else if (this.tab === 'function') this.renderLoadFunction(analysis, content);
    else if (this.tab === 'loads') this.renderLoadsApplied(analysis, content);
    else if (this.tab === 'dynamic') this.renderDynamicAndStages(analysis, content);
    else if (this.tab === 'all') this.renderAll(analysis, content);
    else this.renderControl(analysis, content);

    content.append(
      node(
        'p',
        'material-footnote',
        'Read-only HRX inspection · Replicates C# WindowAnalysesDefinition and MainGridAnalysisElementItem fields · HRX base units: kN, cm, deg, s · — = not serialized. Opening or inspecting an analysis never prepares or executes the solver.'
      )
    );
  }

  sectionTable(title, groups, columns = ['Serialized / resolved value']) {
    const section = node('section', 'property-section');
    section.append(node('h2', '', title));
    const wrap = node('div', 'property-table-wrap');
    const table = node('table', 'material-table');
    const head = node('thead');
    const tr = node('tr');
    for (const label of ['Parameter', 'Unit', ...columns]) {
      const th = node('th', '', label);
      th.scope = 'col';
      tr.append(th);
    }
    head.append(tr);
    table.append(head);

    for (const [group, rows] of groups) {
      const body = node('tbody');
      if (group) {
        const row = node('tr', 'property-group');
        const cell = node('th', '', group);
        cell.colSpan = columns.length + 2;
        row.append(cell);
        body.append(row);
      }
      for (const [label, value, unit = '—', titleText = ''] of rows) {
        const row = node('tr');
        const th = node('th', '', label);
        th.scope = 'row';
        row.append(th);
        row.append(node('td', 'property-unit', unit));
        const strVal = value === undefined || value === null || value === '' ? '—' : String(value);
        const td = node('td', '', strVal);
        if (titleText) td.title = titleText;
        if (strVal === '—') td.classList.add('missing-value');
        td.style.whiteSpace = 'pre-wrap';
        row.append(td);
        body.append(row);
      }
      table.append(body);
    }
    wrap.append(table);
    section.append(wrap);
    return section;
  }

  renderControl(analysis, content) {
    const a = analysis.attributes || {};
    const st = analysis.state || {};
    const stateCode = st.State || '';

    content.append(
      node(
        'p',
        'mechanism-description',
        'Control parameters and execution state matching the C# Define Analyses window (MainGridAnalysisElementItem summary columns and TabItemControlParameters for Static, Modal, and Dynamic analyses).'
      )
    );

    const generalGroups = [
      ['Main analysis grid summary (MainGridAnalysisElementItem)', [
        ['Executed (IsExecuted)', boolText(analysis.isExecuted), 'bool', 'True when State is ExecutedCompleted, ExecutedNotCompleted, or ExecutedNotStarted'],
        ['Name (Name)', analysis.name || attr(a, 'Name'), '—', 'Name'],
        ['Type analysis (AnalysisType)', `${ANALYSIS_TYPE_LABELS[analysis.analysisType] || analysis.type} (${attr(a, 'AnalysisType')})`, '—', 'AnalysisType'],
        ['Start from (InitialAnalysisKey)', formatStartFrom(analysis), '—', 'InitialAnalysisKey (-100 = Zero)'],
        ['Start from combination (InitialCombinationAnalysisKey)', attr(a, 'InitialCombinationAnalysisKey'), '—', 'InitialCombinationAnalysisKey'],
        ['Start also if previous analysis is not completed (IsRestartExecutedNotCompleted)', boolText(a.IsRestartExecutedNotCompleted), 'bool', 'IsRestartExecutedNotCompleted'],
        ['Load combo / Mass source (LoadCombinationKey)', analysis.loadCombinationName ? `${analysis.loadCombinationName} (#${analysis.loadCombinationKey})` : attr(a, 'LoadCombinationKey'), '—', 'LoadCombinationKey'],
        ['Seismic (IsSeismic)', boolText(a.IsSeismic), 'bool', 'IsSeismic'],
        ['Direction summary', formatDirectionSummary(a), '—', 'DirX, DirY, DirZ'],
        ['Distribution (TypeLoadDistribution)', LOAD_DISTRIBUTION_LABELS[a.TypeLoadDistribution] || attr(a, 'TypeLoadDistribution'), '—', 'TypeLoadDistribution'],
        ['Description (Description)', analysis.description || '—', '—', 'Description'],
      ]],
    ];
    content.append(this.sectionTable('General analysis identity & chain', generalGroups));

    if (analysis.analysisType === '5') {
      const modalGroups = [
        ['Modal solver parameters (TabItemModal)', [
          ['Number of eigenmodes (NumberOfEigenModes)', attr(a, 'NumberOfEigenModes'), '1', 'NumberOfEigenModes'],
          ['Number of Lanczos eigenvectors (NumberOfLanczosEigenVectors)', attr(a, 'NumberOfLanczosEigenVectors'), '1', 'NumberOfLanczosEigenVectors'],
          ['Max number of iterations (MaxIterations)', attr(a, 'MaxIterations'), '1', 'MaxIterations'],
          ['Mass source (LoadCombinationKey)', analysis.loadCombinationName ? `${analysis.loadCombinationName} (#${analysis.loadCombinationKey})` : attr(a, 'LoadCombinationKey'), '—', 'LoadCombinationKey'],
          ['Modal procedure (ModalProcedure)', MODAL_PROCEDURE_LABELS[a.ModalProcedure] || attr(a, 'ModalProcedure'), '—', 'ModalProcedure'],
        ]],
        ['Modal convergence criteria', [
          ['Convergence criterion (ModalConvergenceCriteria)', MODAL_CONVERGENCE_LABELS[a.ModalConvergenceCriteria] || attr(a, 'ModalConvergenceCriteria'), '—', 'ModalConvergenceCriteria'],
          ['Eigenvalue tolerance (ConvergenceTolerance)', attr(a, 'ConvergenceTolerance'), '%', 'ConvergenceTolerance'],
          ['Eigenvector tolerance (ResidualVectorTolerance)', attr(a, 'ResidualVectorTolerance'), '%', 'ResidualVectorTolerance'],
        ]],
      ];
      content.append(this.sectionTable('Control parameters — Modal (TabItemModal)', modalGroups));
    } else if (analysis.analysisType === '3' || analysis.analysisType === '4') {
      const dynamicGroups = [
        ['Time-integration procedure (TabItemDynamic)', [
          ['Numerical procedure (IntegrationMethod)', DYNAMIC_INTEGRATION_LABELS[a.IntegrationMethod] || attr(a, 'IntegrationMethod'), '—', 'IntegrationMethod'],
          ['α — Alfa (DynamicAlfa)', attr(a, 'DynamicAlfa'), '1', 'DynamicAlfa'],
          ['β — Beta (DynamicBeta)', attr(a, 'DynamicBeta'), '1', 'DynamicBeta'],
          ['γ — Gamma (DynamicGamma)', attr(a, 'DynamicGamma'), '1', 'DynamicGamma'],
          ['θ — Theta (DynamicTheta)', attr(a, 'DynamicTheta'), '1', 'DynamicTheta'],
          ['Control point (MasterPoint)', formatControlPoint(analysis), '—', 'MasterPoint'],
          ['Analysis step size (AnalysisStepSize)', attr(a, 'AnalysisStepSize'), 's', 'AnalysisStepSize'],
          ['Mass source (LoadCombinationKey)', analysis.loadCombinationName ? `${analysis.loadCombinationName} (#${analysis.loadCombinationKey})` : attr(a, 'LoadCombinationKey'), '—', 'LoadCombinationKey'],
          ['Save results every N steps, N (StepSave)', attr(a, 'StepSave'), 'steps', 'StepSave'],
        ]],
        ['Adaptic dynamic parameters', [
          ['Adaptic integration scheme (AdapticIntegrationScheme)', attr(a, 'AdapticIntegrationScheme'), '—', 'AdapticIntegrationScheme'],
          ['Adaptic mass damping parameter (AdapticMassDampingParameter)', attr(a, 'AdapticMassDampingParameter'), '1', 'AdapticMassDampingParameter'],
          ['Adaptic stiffness damping parameter (AdapticStiffDampingParameter)', attr(a, 'AdapticStiffDampingParameter'), '1', 'AdapticStiffDampingParameter'],
        ]],
      ];
      content.append(this.sectionTable('Control parameters — Dynamic (TabItemDynamic)', dynamicGroups));
    } else {
      const forceControl = a.ForceControl === 'true';
      const staticGroups = [
        ['Load & displacement control (TabItemStatic)', [
          ['Type of load distribution (TypeLoadDistribution)', LOAD_DISTRIBUTION_LABELS[a.TypeLoadDistribution] || attr(a, 'TypeLoadDistribution'), '—', 'TypeLoadDistribution'],
          ['Force / displacement control enabled (ForceImposed)', boolText(a.ForceImposed), 'bool', 'ForceImposed (false = imposed displacements at model points)'],
          ['Control mode (ForceControl)', forceControl ? 'Load control (ForceControl = true)' : 'Displacement control (ForceControl = false)', '—', 'ForceControl'],
          ['Rate of load to be applied (Mult)', attr(a, 'Mult'), '1', 'Mult (used when ForceControl = true)'],
          ['Target displacement (TargetDisplacement)', attr(a, 'TargetDisplacement'), 'cm', 'TargetDisplacement (used when ForceControl = false)'],
          ['Stop analysis if occurs a load reduction (LoadReductionRatioToStop)', boolText(a.LoadReductionRatioToStop), 'bool', 'LoadReductionRatioToStop'],
          ['Load reduction ratio to stop (LoadReductionRatioToStopValue)', attr(a, 'LoadReductionRatioToStopValue'), '1', 'LoadReductionRatioToStopValue'],
          ['Save results every N steps, N (StepSave)', attr(a, 'StepSave'), 'steps', 'StepSave'],
          ['Control point (MasterPoint)', formatControlPoint(analysis), '—', 'MasterPoint (-10 = MaxDisplacement)'],
        ]],
      ];
      content.append(this.sectionTable('Control parameters — Static (TabItemStatic)', staticGroups));
    }

    const directionGroups = [
      ['Direction specification (GroupBoxDirection)', [
        ['Direction mode (Typedirection)', attr(a, 'Typedirection'), '—', 'Simple, Cartesian, or Polar'],
        ['Simple direction (+x, -x, +y, -y, +z, -z)', formatDirectionSummary(a), '—', 'Derived from DirX, DirY, DirZ'],
        ['Cartesian X (DirX)', attr(a, 'DirX'), '1', 'DirX'],
        ['Cartesian Y (DirY)', attr(a, 'DirY'), '1', 'DirY'],
        ['Cartesian Z (DirZ)', attr(a, 'DirZ'), '1', 'DirZ'],
        ['Polar Azimuth θ (DirectionAzimut)', attr(a, 'DirectionAzimut'), 'deg', 'DirectionAzimut'],
        ['Polar Zenith φ (DirectionZenit)', attr(a, 'DirectionZenit'), 'deg', 'DirectionZenit'],
        ['Displacement direction (DirXDisp; DirYDisp; DirZDisp)', `${attr(a, 'DirXDisp')}; ${attr(a, 'DirYDisp')}; ${attr(a, 'DirZDisp')}`, '1', 'DirXDisp, DirYDisp, DirZDisp'],
        ['Eccentricity (Eccentricity)', attr(a, 'Eccentricity'), 'cm', 'Eccentricity'],
        ['Seismic: set direction of all loads to selected direction (IsSeismic)', boolText(a.IsSeismic), 'bool', 'IsSeismic'],
      ]],
    ];
    content.append(this.sectionTable('Direction & Seismic settings', directionGroups));

    const stateGroups = [
      ['Saved state record (<States><State .../>)', [
        ['State (State)', stateCode ? `${STATE_LABELS[stateCode] || stateCode} (${stateCode})` : '—', '—', 'State'],
        ['Short state code', STATE_CODES[stateCode] || '—', '—', 'AnalysisStateToString(true)'],
        ['Combination (Combination)', attr(st, 'Combination'), '1', 'Combination'],
        ['Last converged step (Step)', attr(st, 'Step'), 'steps', 'Step'],
        ['Reference load Fo (Fo)', attr(st, 'Fo'), 'kN', 'Fo'],
        ['Exit reason (Exit)', attr(st, 'Exit'), '—', 'Exit'],
        ['Exit description (ExitDescription)', formatExitDescription(st.ExitDescription), '—', 'ExitDescription (@ formatted as newlines)'],
      ]],
    ];
    content.append(this.sectionTable('Saved execution state', stateGroups));
  }

  renderIterative(analysis, content) {
    const a = analysis.attributes || {};
    const methodInfo = decomposeIterativeMethod(a.Method);

    content.append(
      node(
        'p',
        'mechanism-description',
        'Nonlinear solution algorithm, line search, automatic load stepping (ALS), arc-length control, and P-Delta settings from C# TabItemIterativeStrategyHistra.'
      )
    );

    const groups = [
      ['Iterative procedure & Newton-Raphson strategy', [
        ['Integration method (IntegrationMethod)', attr(a, 'IntegrationMethod'), '—', 'IntegrationMethod'],
        ['Effective static integration mode', a.ForceControl === 'true' ? 'LoadControl (ForceControl = true)' : 'ArcLength (ForceControl = false)', '—', 'Derived from ForceControl in InitIntegrationMethod()'],
        ['Serialized numerical method (Method)', methodInfo.raw, '—', 'Method'],
        ['Newton-Raphson strategy', methodInfo.newtonType, '—', 'ComboBoxIterationProcedure in C#'],
        ['Line search enabled', methodInfo.lineSearch, 'bool', 'CheckBoxLineSearch in C#'],
        ['Line search type', methodInfo.lineSearchType, '—', 'ComboBoxLineSearchType in C#'],
        ['Switch to modified strategy when stiffness < initial (CheckSecantStiffness)', boolText(a.CheckSecantStiffness), 'bool', 'CheckSecantStiffness'],
        ['Percentage to switch Standard to Modified N-R (SecantStiffnessRatio)', attr(a, 'SecantStiffnessRatio'), '1', 'SecantStiffnessRatio'],
        ['Max number of iterations (MaxIterations)', attr(a, 'MaxIterations'), '1', 'MaxIterations'],
        ['P-Delta effect (PdeltaEffect)', PDELTA_LABELS[a.PdeltaEffect] || attr(a, 'PdeltaEffect'), '—', 'PdeltaEffect'],
      ]],
      ['Line search parameters (GroupBoxLineSearchParameters)', [
        ['Tolerance (LineSearchTolerance)', attr(a, 'LineSearchTolerance'), '1', 'LineSearchTolerance'],
        ['Max number of iterations (LineSearchMaxIterations)', attr(a, 'LineSearchMaxIterations'), '1', 'LineSearchMaxIterations'],
        ['Max Eta (LineSearchMaxEta)', attr(a, 'LineSearchMaxEta'), '1', 'LineSearchMaxEta'],
        ['Min Eta (LineSearchMinEta)', attr(a, 'LineSearchMinEta'), '1', 'LineSearchMinEta'],
      ]],
      ['Load control method — advanced parameters (GroupBoxLoadControlAdvancedParameters)', [
        ['Automatic load step (ALS)', boolText(a.ALS), 'bool', 'ALS'],
        ['Max number of load reductions (MaxNumberALS)', attr(a, 'MaxNumberALS'), '1', 'MaxNumberALS'],
        ['Load factor reduction (LoadFactorALS)', attr(a, 'LoadFactorALS'), '1', 'LoadFactorALS'],
      ]],
      ['Arc length method — advanced parameters (GroupBoxArcLengthAdvancedParameters)', [
        ['Compute dλ as function of (ArcLengthProcedure)', ARC_LENGTH_PROCEDURE_LABELS[a.ArcLengthProcedure] || attr(a, 'ArcLengthProcedure'), '—', 'ArcLengthProcedure'],
        ['Arc length ray, dr = √Dr2', formatArcLengthRay(a.Dr2), 'cm', 'TextBoxArcLengthRay displays Math.Sqrt(Dr2)'],
        ['Raw squared arc length ray (Dr2)', attr(a, 'Dr2'), 'cm²', 'Dr2'],
        ['Initialize from discretization (InitFromDiscretization)', boolText(a.InitFromDiscretization), 'bool', 'InitFromDiscretization'],
        ['Initial force-controlled phase (InitialForceControlledPhase)', boolText(a.InitialForceControlledPhase), 'bool', 'InitialForceControlledPhase'],
        ['Max load increment dλ enabled (IsMaxArcLengthRay)', boolText(a.IsMaxArcLengthRay), 'bool', 'IsMaxArcLengthRay'],
        ['Max load increment, dλ (MaxArcLengthRay)', attr(a, 'MaxArcLengthRay'), '1', 'MaxArcLengthRay'],
        ['Modify arc length ray during analysis (UpdateDr2)', boolText(a.UpdateDr2), 'bool', 'UpdateDr2'],
        ['Number of iterations desired (DesiredIterations)', attr(a, 'DesiredIterations'), '1', 'DesiredIterations'],
        ['Restart arc length (IsRestartArcLength)', boolText(a.IsRestartArcLength), 'bool', 'IsRestartArcLength'],
        ['Max restart arc length (MaxRestartArcLength)', attr(a, 'MaxRestartArcLength'), '1', 'MaxRestartArcLength'],
        ['Reduce ray arc length (ReduceRayArcLength)', attr(a, 'ReduceRayArcLength'), '1', 'ReduceRayArcLength'],
      ]],
      ['Adaptic / additional iterative parameters', [
        ['Initial reformations (InitialReformations)', attr(a, 'InitialReformations'), '1', 'InitialReformations'],
        ['Step reduction (StepReduction)', attr(a, 'StepReduction'), '1', 'StepReduction'],
        ['Divergence iteration (DivergenceIteration)', attr(a, 'DivergenceIteration'), '1', 'DivergenceIteration'],
        ['Total relax level (TotalRelaxLevel)', attr(a, 'TotalRelaxLevel'), '1', 'TotalRelaxLevel'],
        ['Maximum convergence (MaximumConvergence)', attr(a, 'MaximumConvergence'), '1', 'MaximumConvergence'],
        ['Arc flow iterations (ArcFlowIterations)', attr(a, 'ArcFlowIterations'), '1', 'ArcFlowIterations'],
        ['Scaled iterations (ScaledIterations)', attr(a, 'ScaledIterations'), '1', 'ScaledIterations'],
      ]],
    ];
    content.append(this.sectionTable('Iterative strategy parameters', groups));
  }

  renderConvergence(analysis, content) {
    const a = analysis.attributes || {};
    content.append(
      node(
        'p',
        'mechanism-description',
        'Convergence criteria, maximum displacement limits, and SDB frame element tolerances from C# TabItemAdapticConvergenceCriteria.'
      )
    );

    const groups = [
      ['Primary convergence criteria (TabItemAdapticConvergenceCriteria)', [
        ['Convergence criterion (AdapticConvergenceCriteria)', CONVERGENCE_CRITERIA_LABELS[a.AdapticConvergenceCriteria] || attr(a, 'AdapticConvergenceCriteria'), '—', 'AdapticConvergenceCriteria'],
        ['Tolerance (ConvergenceTolerance)', attr(a, 'ConvergenceTolerance'), '1', 'ConvergenceTolerance'],
        ['Max displacement (maxU)', attr(a, 'maxU'), 'cm', 'maxU'],
      ]],
      ['Component tolerances & work reference', [
        ['Force tolerance (ConvergenceToleranceForce)', attr(a, 'ConvergenceToleranceForce'), '1', 'ConvergenceToleranceForce'],
        ['Moment tolerance (ConvergenceToleranceMoment)', attr(a, 'ConvergenceToleranceMoment'), '1', 'ConvergenceToleranceMoment'],
        ['Displacement tolerance (ConvergenceToleranceDisplacement)', attr(a, 'ConvergenceToleranceDisplacement'), '1', 'ConvergenceToleranceDisplacement'],
        ['Rotation tolerance (ConvergenceToleranceRotation)', attr(a, 'ConvergenceToleranceRotation'), '1', 'ConvergenceToleranceRotation'],
        ['Work reference (WorkReference)', attr(a, 'WorkReference'), 'kN·cm', 'WorkReference'],
        ['Max rotations (MaximumTolerance)', attr(a, 'MaximumTolerance'), 'rad', 'MaximumTolerance'],
      ]],
      ['SDB frame element convergence parameters', [
        ['Tolerance (SDB_Tolerance)', attr(a, 'SDB_Tolerance'), '1', 'SDB_Tolerance'],
        ['Max number of iterations (SDB_MaxIterations)', attr(a, 'SDB_MaxIterations'), '1', 'SDB_MaxIterations'],
      ]],
      ['Modal convergence criteria', [
        ['Modal convergence criterion (ModalConvergenceCriteria)', MODAL_CONVERGENCE_LABELS[a.ModalConvergenceCriteria] || attr(a, 'ModalConvergenceCriteria'), '—', 'ModalConvergenceCriteria'],
        ['Eigenvalue tolerance (ConvergenceTolerance)', attr(a, 'ConvergenceTolerance'), '%', 'ConvergenceTolerance'],
        ['Eigenvector tolerance (ResidualVectorTolerance)', attr(a, 'ResidualVectorTolerance'), '%', 'ResidualVectorTolerance'],
      ]],
    ];
    content.append(this.sectionTable('Convergence criteria parameters', groups));
  }

  renderModelPoints(analysis, content) {
    const a = analysis.attributes || {};
    const points = analysis.modelPoints || [];

    content.append(
      node(
        'p',
        'mechanism-description',
        'Model points table matching C# DataGridModelPoints (Active, Id, Element, Position, Description, and Displacement [cm]), joined with the 3D coordinates from <ModelPoint>.'
      )
    );

    content.append(
      this.sectionTable('Control point & model point settings', [
        ['Control point & arc-length participation', [
          ['Control point (MasterPoint)', formatControlPoint(analysis), '—', 'MasterPoint'],
          ['Active model points', `${points.filter(p => p.active === 'true').length} of ${points.length}`, 'points', 'ActiveModelPoints'],
          ['Force / displacement control mode (ForceImposed)', a.ForceImposed === 'false' ? 'Imposed displacements at model points (false)' : 'Force / displacement control (true)', 'bool', 'ForceImposed'],
          ['Compute dλ as function of (ArcLengthProcedure)', ARC_LENGTH_PROCEDURE_LABELS[a.ArcLengthProcedure] || attr(a, 'ArcLengthProcedure'), '—', 'ArcLengthProcedure'],
        ]],
      ])
    );

    const section = node('section', 'property-section');
    section.append(node('h2', '', `Model points (${points.length})`));
    if (!points.length) {
      section.append(node('p', 'material-note', 'No model points are defined in this HRX model.'));
      content.append(section);
      return;
    }

    const wrap = node('div', 'property-table-wrap');
    const table = node('table', 'material-table');
    const thead = node('thead');
    const trHead = node('tr');
    for (const col of ['Id', 'Active', 'Element', 'Position', 'Coordinates (X; Y; Z) [cm]', 'Description', 'Displacement [cm]']) {
      const th = node('th', '', col);
      th.scope = 'col';
      trHead.append(th);
    }
    thead.append(trHead);
    const tbody = node('tbody');
    for (const mp of points) {
      const tr = node('tr');
      const thId = node('th', '', `#${mp.key}${mp.isMaster ? ' ★ Control point' : ''}`);
      thId.scope = 'row';
      const coords = mp.point ? mp.point.map(v => Number(v.toFixed(3))).join('; ') : (mp.pointRaw || '—');
      tr.append(
        thId,
        node('td', '', mp.active === 'true' ? 'true (Active)' : 'false'),
        node('td', '', mp.elementLabel || '—'),
        node('td', '', mp.positionLabel || '—'),
        node('td', '', coords),
        node('td', '', mp.description || mp.name || '—'),
        node('td', '', mp.displacement ?? '0')
      );
      tbody.append(tr);
    }
    table.append(thead, tbody);
    wrap.append(table);
    section.append(wrap);
    content.append(section);
  }

  renderLoadFunction(analysis, content) {
    const fn = analysis.loadFunction;
    const items = fn?.items || [];

    content.append(
      node(
        'p',
        'mechanism-description',
        'Load function discretization parameters, curve preview, and (Time, Multiplier) table matching C# TabItemLoadFunction.'
      )
    );

    content.append(renderLoadFunctionPreview(items));

    content.append(
      this.sectionTable('Load function discretization (TabItemLoadFunction)', [
        ['Discretization settings (<LoadFunction>)', [
          ['Load function key (LoadFunctionKey)', analysis.loadFunctionKey || '—', '—', 'LoadFunctionKey'],
          ['Max discretization (DiscrVal)', fn ? attr(fn.attributes, 'DiscrVal') : (analysis.loadFunctionDiscr || '—'), '1', 'DiscrVal'],
          ['Discretization mode (typeDiscr)', formatDiscretizationMode(fn?.typeDiscr), '—', 'false = pseudo-time, true = load multiplier'],
          ['Number of points', String(items.length), 'points', 'LoadFunctionItem count'],
        ]],
      ])
    );

    const section = node('section', 'property-section');
    section.append(node('h2', '', `Load function points (${items.length})`));
    const wrap = node('div', 'property-table-wrap');
    const table = node('table', 'material-table');
    const thead = node('thead');
    const trHead = node('tr');
    for (const col of ['#', 'Item key', 'Time (pseudoTime)', 'Multiplier (multiplier)']) {
      const th = node('th', '', col);
      th.scope = 'col';
      trHead.append(th);
    }
    thead.append(trHead);
    const tbody = node('tbody');
    items.forEach((item, index) => {
      const tr = node('tr');
      const th = node('th', '', String(index + 1));
      th.scope = 'row';
      tr.append(
        th,
        node('td', '', item.key || '—'),
        node('td', '', item.pseudoTime ?? '—'),
        node('td', '', item.multiplier ?? '—')
      );
      tbody.append(tr);
    });
    table.append(thead, tbody);
    wrap.append(table);
    section.append(wrap);
    content.append(section);
  }

  renderLoadsApplied(analysis, content) {
    const a = analysis.attributes || {};
    const combo = analysis.loadCombination;
    const subCombos = combo?.subCombinations || [];

    content.append(
      node(
        'p',
        'mechanism-description',
        'Load combination coefficients (C# TabItemLoadsApplied / DataGridLoadsApplied) and Multi-Modal Pushover parameters (C# TabItemPushModal).'
      )
    );

    content.append(
      this.sectionTable('Load combination & Multi-Modal Pushover', [
        ['Load combination (<LoadCombination>)', [
          ['Load combination key (LoadCombinationKey)', analysis.loadCombinationKey || '—', '—', 'LoadCombinationKey'],
          ['Name (Name)', combo?.name || analysis.loadCombinationName || '—', '—', 'LoadCombination.Name'],
          ['Limit state (LimitState)', combo?.limitState || '—', '—', 'LoadCombination.LimitState'],
          ['Description (Description)', combo?.description || '—', '—', 'LoadCombination.Description'],
          ['Sub-combinations count', String(subCombos.length), '1', 'Distinct RowKey count in LoadCombination/Item'],
        ]],
        ['Multi-Modal Pushover parameters (TabItemPushModal)', [
          ['Type of load distribution (TypeLoadDistribution)', LOAD_DISTRIBUTION_LABELS[a.TypeLoadDistribution] || attr(a, 'TypeLoadDistribution'), '—', 'TypeLoadDistribution'],
          ['Modal analysis (PushModal_ModalAnalysisKey)', analysis.pushModalAnalysisName ? `${analysis.pushModalAnalysisName} (#${analysis.pushModalAnalysisKey})` : attr(a, 'PushModal_ModalAnalysisKey'), '—', 'PushModal_ModalAnalysisKey'],
          ['Design spectrum (PushModal_Spectrum)', attr(a, 'PushModal_Spectrum'), '—', 'PushModal_Spectrum'],
          ['Distribution type (PushModal_Type)', PUSH_MODAL_TYPE_LABELS[a.PushModal_Type] || attr(a, 'PushModal_Type'), '—', 'PushModal_Type'],
          ['Single mode (PushModal_SingleMode)', attr(a, 'PushModal_SingleMode'), '1', 'PushModal_SingleMode'],
          ['Min participating modal mass (PushModalMassMin)', attr(a, 'PushModalMassMin'), '1', 'PushModalMassMin'],
          ['Modal mass calculated (PushModalMass)', attr(a, 'PushModalMass'), '1', 'PushModalMass'],
          ['Modal combination rule (ModalCombinationRule)', attr(a, 'ModalCombinationRule'), '—', 'ModalCombinationRule'],
        ]],
      ])
    );

    const section = node('section', 'property-section');
    section.append(node('h2', '', 'Loads applied — Load condition coefficients (DataGridLoadsApplied)'));
    if (!subCombos.length) {
      section.append(node('p', 'material-note', 'No serialized <LoadCombination><Item> entries found for this analysis.'));
      content.append(section);
      return;
    }

    if (!subCombos.some(r => String(r.rowKey) === String(this.subComboRowKey))) {
      this.subComboRowKey = subCombos[0].rowKey;
    }
    const activeSub = subCombos.find(r => String(r.rowKey) === String(this.subComboRowKey)) || subCombos[0];

    if (subCombos.length > 1) {
      const selectorWrap = node('label', 'material-unit-selector', 'Sub-combination');
      selectorWrap.style.padding = '12px 16px 0';
      const select = node('select');
      for (const sc of subCombos) {
        select.add(new Option(`#${sc.rowKey} — ${sc.name} (Schema: ${sc.schema || 'NoSchema'})`, sc.rowKey, false, String(sc.rowKey) === String(activeSub.rowKey)));
      }
      select.onchange = () => {
        this.subComboRowKey = select.value;
        this.render();
      };
      selectorWrap.append(select);
      section.append(selectorWrap);
    }

    const wrap = node('div', 'property-table-wrap');
    const table = node('table', 'material-table');
    const thead = node('thead');
    const trHead = node('tr');
    for (const col of ['Load condition', 'Coefficient (TypeData)', 'Value (C# GetCoefficient)', 'Raw Val', 'SecondaryTypeData']) {
      const th = node('th', '', col);
      th.scope = 'col';
      trHead.append(th);
    }
    thead.append(trHead);
    const tbody = node('tbody');
    for (const item of activeSub.items) {
      const tr = node('tr');
      const th = node('th', '', `${item.conditionName} (#${item.conditionKey})`);
      th.scope = 'row';
      tr.append(
        th,
        node('td', '', item.coefficient || '—'),
        node('td', '', item.value ?? '—'),
        node('td', '', item.val ?? '—'),
        node('td', '', item.secondaryTypeData || '—')
      );
      tbody.append(tr);
    }
    table.append(thead, tbody);
    wrap.append(table);
    section.append(wrap);
    content.append(section);
  }

  renderDynamicAndStages(analysis, content) {
    const a = analysis.attributes || {};
    content.append(
      node(
        'p',
        'mechanism-description',
        'Damping settings (TabItemDamping), Dynamic loads (TabItemDynamicLoads), Construction stages (TabItemStagesDefinition), Adaptic phases, and output parameters.'
      )
    );

    const groups = [
      ['Damping matrix & Rayleigh / Caughey parameters (TabItemDamping)', [
        ['Classic damping matrix (DampingMatrixClassic)', boolText(a.DampingMatrixClassic), 'bool', 'DampingMatrixClassic'],
        ['Non-classic damping matrix (DampingMatrixNonClassic)', boolText(a.DampingMatrixNonClassic), 'bool', 'DampingMatrixNonClassic'],
        ['Damping criterion (DampingCriterion)', attr(a, 'DampingCriterion'), '—', 'DampingCriterion'],
        ['Damping ratio 1 (DampingRatio1)', attr(a, 'DampingRatio1'), '1', 'DampingRatio1'],
        ['Damping ratio 2 (DampingRatio2)', attr(a, 'DampingRatio2'), '1', 'DampingRatio2'],
        ['Specification mode (DampingMode)', a.DampingMode === 'true' ? 'Modal analysis modes (true)' : 'Frequencies (false)', 'bool', 'DampingMode'],
        ['Modal analysis (PushModal_ModalAnalysisKey)', analysis.pushModalAnalysisName ? `${analysis.pushModalAnalysisName} (#${analysis.pushModalAnalysisKey})` : attr(a, 'PushModal_ModalAnalysisKey'), '—', 'PushModal_ModalAnalysisKey'],
        ['Mode 1 (Damping_ModalAnalysis_Mode1)', attr(a, 'Damping_ModalAnalysis_Mode1'), '1', 'Damping_ModalAnalysis_Mode1'],
        ['Mode 2 (Damping_ModalAnalysis_Mode2)', attr(a, 'Damping_ModalAnalysis_Mode2'), '1', 'Damping_ModalAnalysis_Mode2'],
        ['First frequency (FirstFrequency)', attr(a, 'FirstFrequency'), 'Hz', 'FirstFrequency'],
        ['Second frequency (SecondFrequency)', attr(a, 'SecondFrequency'), 'Hz', 'SecondFrequency'],
      ]],
      ['Dynamic loads, stages & output options', [
        ['Set initial accelerations (SetInitialAccelerations)', boolText(a.SetInitialAccelerations), 'bool', 'SetInitialAccelerations'],
        ['Dynamic loads count (<DynamicLoads>)', String((analysis.dynamicLoads || []).length), '1', 'DynamicLoad items'],
        ['Stage definitions count (<StageDefinitions>)', String((analysis.stageDefinitions || []).length), '1', 'StageDefinition items'],
        ['Equilibrium stage items count (<StageItems>)', String((analysis.stageItems || []).length), '1', 'StageItem items'],
        ['Adaptic phases count (<AdapticPhases>)', String((analysis.adapticPhases || []).length), '1', 'AdapticPhase items'],
        ['Output frequency (OutputFrequency)', attr(a, 'OutputFrequency'), 'steps', 'OutputFrequency'],
        ['Local displacement (LocalDisplacement)', boolText(a.LocalDisplacement), 'bool', 'LocalDisplacement'],
        ['Has stress output (hasStress)', boolText(a.hasStress), 'bool', 'hasStress'],
        ['Use partition modeling (UsePartitionModeling)', boolText(a.UsePartitionModeling), 'bool', 'UsePartitionModeling'],
        ['Main group (MainGroupKey)', analysis.mainGroupName ? `${analysis.mainGroupName} (#${attr(a, 'MainGroupKey')})` : attr(a, 'MainGroupKey'), '—', 'MainGroupKey'],
      ]],
    ];
    content.append(this.sectionTable('Damping, stages & output parameters', groups));
  }

  renderAll(analysis, content) {
    const a = analysis.attributes || {};
    const rows = Object.keys(a)
      .sort((x, y) => x.localeCompare(y))
      .map(key => [key, a[key], 'raw', key]);
    content.append(
      this.sectionTable(`All serialized HRX Analysis attributes (${rows.length})`, [
        ['XML attributes on <Analysis>', rows],
      ])
    );
  }
}
