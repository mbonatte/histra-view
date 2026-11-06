import {
  ANALYSIS_TYPE_LABELS,
  STATE_LABELS,
  STATE_SHORT_LABELS,
  STATE_CODES,
  ARC_LENGTH_PROCEDURE_LABELS,
  PDELTA_LABELS,
  isDynamicOnlyAnalysisField,
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
  ['dynamic', 'Stages & output'],
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

export function scourStagesForAnalysis(analyses, analysis) {
  const stages = analyses.filter(a => /^scour[_ ]?\d+$/i.test(a.name || ''))
    .sort((a, b) => Number(a.name.match(/\d+/)[0]) - Number(b.name.match(/\d+/)[0]));
  const name = analysis?.name || '';
  const numbered = /^(?:scour|modal)[_ ]?(\d+)$/i.exec(name);
  if (numbered) return stages.filter(a => Number(a.name.match(/\d+/)[0]) <= Number(numbered[1]));
  if (Number(analysis?.analysisType) === 5 && !/^modal[_ ]?-1$/i.test(name)) {
    const byKey = new Map(analyses.map(a => [String(a.key), a]));
    let current = analysis, maxStage = 0;
    const seen = new Set();
    while (current && !seen.has(String(current.key))) {
      seen.add(String(current.key));
      const match = /^scour[_ ]?(\d+)$/i.exec(current.name || '');
      if (match) maxStage = Math.max(maxStage, Number(match[1]));
      current = byKey.get(String(current.initialAnalysisKey));
    }
    return maxStage ? stages.filter(a => Number(a.name.match(/\d+/)[0]) <= maxStage) : stages;
  }
  return [];
}

export function masonryMaterialOptions(model) {
  const library = model?.materialLibrary || model?.materials || [];
  const materials = library.filter(m => /MasonryMaterial$/i.test(m.attributes?.PurposeType || m.attributes?.TypeOf || ''));
  const counts = new Map();
  for (const material of materials) counts.set(material.name, (counts.get(material.name) || 0) + 1);
  return materials.map(material => ({ value: String(material.key), label: counts.get(material.name) > 1 ? `${material.name} (#${material.key})` : material.name || `Material #${material.key}` }));
}

export class AnalysesPage {
  constructor(onEdit = null, solverHooks = {}) {
    this.onEdit = onEdit;
    this.getSource = solverHooks.getSource || (() => ({}));
    this.onRunComplete = solverHooks.onRunComplete || null;
    this.analyses = [];
    this.scourMaterials = [];
    this.selected = null;
    this.tab = 'control';
    this.subComboRowKey = null;
    this.solverJob = null;
    this.solverLogs = [];
    this.pdeltaEffect = 'EachStep';
    this.arcLambdaTarget = { analysisKey: null, enabled: false, value: '0' };
    this.lateralSubgrade = { enabled: false, restraintKeys: '', kx: '', ky: '' };
    this.scourWorkflow = { enabled: false, pier: '1', intactMaterial: '', scouredMaterial: '', direction: '-Y', ratios: {}, skipEquilibriumAudit: false };
    this.pollTimer = null;
    this.logExpanded = true;
    this.notifiedJobId = null;
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

  resolveDependencyChain(target) {
    if (!target) return [];
    const byKey = new Map(this.analyses.map(a => [String(a.key), a]));
    const chain = [];
    const seen = new Set();
    let current = target;
    while (current) {
      const k = String(current.key);
      if (seen.has(k)) break;
      seen.add(k);
      chain.push(current);
      const initKey = String(current.initialAnalysisKey ?? '-100');
      if (!initKey || Number(initKey) < 0) break;
      current = byKey.get(initKey) || null;
    }
    return chain.reverse();
  }

  applyAnalysisStates(analysisStates) {
    if (!analysisStates || typeof analysisStates !== 'object') return;
    let changed = false;
    for (const analysis of this.analyses) {
      const st = analysisStates[String(analysis.key)];
      if (st) {
        analysis.state = { ...(analysis.state || {}), ...st };
        analysis.isExecuted = ['ExecutedCompleted', 'ExecutedNotCompleted', 'ExecutedNotStarted'].includes(st.State);
        changed = true;
      }
    }
    if (changed) {
      this.renderList();
    }
  }

  async runAnalysis(analysis = this.selected) {
    if (!analysis) return;
    if (this.solverJob && this.solverJob.status === 'running') return;
    clearTimeout(this.pollTimer);
    this.solverLogs = [];
    this.notifiedJobId = null;
    this.logExpanded = true;
    const { source, modelName } = this.getSource() || {};
    const combinationRow = Number(this.subComboRowKey) > 0 ? Number(this.subComboRowKey) : 1;
    try {
      let lateralSubgrade = null;
      if (this.lateralSubgrade.enabled) {
        const rawKeys = this.lateralSubgrade.restraintKeys.trim();
        if (!/^\d+(?:[\s,;]+\d+)*$/.test(rawKeys)) throw new Error('Enter lateral restraint keys as positive integers separated by commas.');
        const restraintKeys = rawKeys.split(/[\s,;]+/).map(Number);
        const { kx, ky } = this.lateralSubgrade;
        if (kx.trim() === '' || ky.trim() === '') throw new Error('Enter both Kx and Ky in kN/m³.');
        lateralSubgrade = { restraintKeys, kx: Number(kx), ky: Number(ky) };
      }
      let scourWorkflow = null;
      if (this.scourWorkflow.enabled) {
        const config = this.scourWorkflow;
        const stages = scourStagesForAnalysis(this.analyses, analysis)
          .map(a => ({ analysisKey: Number(a.key), raw: config.ratios[String(a.key)] ?? '' }))
          .filter(a => a.raw !== '')
          .map(a => ({ analysisKey: a.analysisKey, ratio: Number(a.raw) / 100 }));
        if (!config.pier || !config.intactMaterial || !config.scouredMaterial || !stages.length)
          throw new Error('Choose the pier and both soil materials, then configure the scour ratio for each required scour analysis.');
        scourWorkflow = { pier: Number(config.pier), intactMaterial: Number(config.intactMaterial),
          scouredMaterial: Number(config.scouredMaterial), direction: config.direction, stages, skipEquilibriumAudit: Boolean(config.skipEquilibriumAudit) };
      }
      let arcLambdaTarget = null;
      if (this.arcLambdaTarget?.enabled && String(this.arcLambdaTarget.analysisKey) === String(analysis.key)) {
        const raw = this.arcLambdaTarget.value.trim();
        if (!raw || !Number.isFinite(Number(raw))) throw new Error('Enter a finite arc-length λ target.');
        arcLambdaTarget = Number(raw);
      }
      const response = await fetch('/api/solver/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          analysisKey: analysis.key,
          combinationRow,
          lateralSubgrade,
          scourWorkflow,
          arcLambdaTarget,
          pdeltaEffect: this.pdeltaEffect === 'model' ? null : this.pdeltaEffect,
          source: source || null,
          modelName: modelName || null,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      this.solverJob = data;
      this.solverLogs = [...(data.logs || [])];
      this.render();
      this.schedulePoll();
    } catch (err) {
      this.solverJob = {
        jobId: null,
        status: 'failed',
        targetKey: String(analysis.key),
        targetName: analysis.name || `Analysis ${analysis.key}`,
        progress: 0,
        runtimeSeconds: 0,
        message: err.message || String(err),
        error: err.message || String(err),
        stages: [],
        bundleReady: false,
      };
      this.solverLogs = [`ERROR: ${err.message || String(err)}`];
      this.render();
    }
  }

  async stopRun() {
    if (!this.solverJob || this.solverJob.status !== 'running') return;
    try {
      const response = await fetch('/api/solver/stop', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobId: this.solverJob.jobId }),
      });
      if (response.ok) { this.solverJob = { ...this.solverJob, ...await response.json() }; this.render(); }
    } catch { /* Polling will continue and the user can retry. */ }
  }

  async cancelRun() {
    if (!this.solverJob || this.solverJob.status !== 'running') return;
    try {
      const response = await fetch('/api/solver/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobId: this.solverJob.jobId }),
      });
      const data = await response.json();
      if (response.ok) {
        this.solverJob = { ...this.solverJob, ...data };
        this.updateSolverPanelInPlace();
      }
    } catch {
      // Ignore transient network errors during cancel
    }
  }

  schedulePoll() {
    clearTimeout(this.pollTimer);
    if (!this.solverJob || this.solverJob.status !== 'running') return;
    this.pollTimer = setTimeout(() => this.pollStatus(), 200);
  }

  async pollStatus() {
    if (!this.solverJob?.jobId) return;
    try {
      const offset = this.solverLogs.length;
      const response = await fetch(
        `/api/solver/status?job_id=${encodeURIComponent(this.solverJob.jobId)}&log_offset=${offset}`
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      if (Array.isArray(data.logs) && data.logs.length) {
        this.solverLogs.push(...data.logs);
      }
      const wasRunning = this.solverJob.status === 'running';
      this.solverJob = data;
      if (data.analysisStates) {
        this.applyAnalysisStates(data.analysisStates);
      }
      if (data.status === 'running') {
        this.updateSolverPanelInPlace();
        this.schedulePoll();
      } else {
        this.render();
        if (wasRunning && data.bundleReady && this.onRunComplete && this.notifiedJobId !== data.jobId) {
          this.notifiedJobId = data.jobId;
          this.onRunComplete(data, false);
        }
      }
    } catch {
      this.schedulePoll();
    }
  }

  downloadBundle(jobId = this.solverJob?.jobId) {
    const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : '';
    const link = document.createElement('a');
    link.href = `/api/solver/download${query}`;
    link.download = this.solverJob?.bundleName || 'results.histra';
    document.body.append(link);
    link.click();
    link.remove();
  }

  updateSolverPanelInPlace() {
    const job = this.solverJob;
    if (!job) return;
    const fill = $('solverProgressFill');
    if (fill) fill.style.width = `${Math.min(100, Math.max(0, Number(job.progress || 0)))}%`;
    const pct = $('solverProgressPct');
    if (pct) pct.textContent = `${Number(job.progress || 0).toFixed(1)}% · ${Number(job.runtimeSeconds || 0).toFixed(1)}s`;
    const msg = $('solverStatusMessage');
    if (msg) {
      msg.textContent = job.message || 'Running…';
    }
    const stagesBox = $('solverChainStages');
    if (stagesBox && Array.isArray(job.stages)) {
      stagesBox.replaceChildren(...this.buildStagePills(job.stages));
    }
    const stepBox = $('solverStepStream');
    if (stepBox) {
      stepBox.replaceChildren(...this.buildStepStreamNodes(job));
    }
    const logPre = $('solverLogConsole');
    if (logPre) {
      logPre.textContent = this.solverLogs.length ? this.solverLogs.join('\n') : 'Waiting for solver output…';
      logPre.scrollTop = logPre.scrollHeight;
    }
    const logCount = $('solverLogCount');
    if (logCount) logCount.textContent = `${this.solverLogs.length} lines`;
  }

  buildStepStreamNodes(job) {
    const cs = job?.currentStage;
    const stages = Array.isArray(job?.stages) ? job.stages : [];
    const activeStage = (job?.status === 'running' && cs)
      ? cs
      : ([...stages].reverse().find(s => Array.isArray(s.stepHistory) && s.stepHistory.length > 0) || cs);
    if (!activeStage || Number(activeStage.analysisType) === 5) return [];
    const history = Array.isArray(activeStage.stepHistory) ? activeStage.stepHistory : [];
    const solvingStep = job?.status === 'running' ? Number(cs?.solvingStep || 0) : 0;
    if (!history.length && !solvingStep) return [];

    const wrap = node('div', 'solver-step-stream-wrap');
    const expected = Number(activeStage.expectedSteps || activeStage.maxSteps || 0);
    const title = node(
      'div',
      'solver-step-stream-title',
      `Live step progression — ${activeStage.name || 'Stage'} (${history.length}${expected ? `/${expected}` : ''} steps committed)`
    );
    const table = node('table', 'solver-step-table');
    const thead = node('thead');
    const htr = node('tr');
    for (const col of ['Step', 'Load factor λ', 'Control |U| [cm]', 'Iterations', 'Residual', 'Status']) {
      htr.append(node('th', '', col));
    }
    thead.append(htr);
    const tbody = node('tbody');

    for (const s of history) {
      const tr = node('tr', 'step-committed');
      tr.append(
        node('td', '', `#${s.step}`),
        node('td', '', Number(s.loadFactor || 0).toFixed(4)),
        node('td', '', Number(s.displacement || 0).toExponential(3)),
        node('td', '', String(s.iterations ?? '—')),
        node('td', '', Number(s.error || 0).toExponential(2)),
        node('td', 'step-status-ok', '✓ Committed')
      );
      tbody.append(tr);
    }

    if (solvingStep > (history.at(-1)?.step || 0)) {
      const tr = node('tr', 'step-solving');
      const targetLf = Number(cs?.targetLoadFactor || 0);
      tr.append(
        node('td', '', `#${solvingStep}`),
        node('td', '', targetLf ? targetLf.toFixed(4) : '…'),
        node('td', '', '…'),
        node('td', '', '…'),
        node('td', '', '…'),
        node('td', 'step-status-running', '● Solving…')
      );
      tbody.append(tr);
    }

    table.append(thead, tbody);
    wrap.append(title, table);
    return [wrap];
  }

  buildStagePills(stages) {
    const pills = [];
    stages.forEach((st, idx) => {
      if (idx > 0) pills.push(node('span', 'solver-chain-arrow', '→'));
      const pill = node('span', `solver-stage-pill status-${st.status || 'pending'}`);
      const icon = st.status === 'completed' ? '✓ '
        : st.status === 'running' ? '● '
        : st.status === 'nonconverged' ? '⚠ '
        : st.status === 'cancelled' || st.status === 'failed' ? '✕ '
        : '';
      const stepSuffix = st.steps ? ` · ${st.steps} ${st.analysisType === 5 ? 'modes' : 'steps'}` : '';
      const timeSuffix = st.runtimeSeconds ? ` (${Number(st.runtimeSeconds).toFixed(1)}s)` : '';
      pill.textContent = `${icon}${st.name} (#${st.key})${stepSuffix}${timeSuffix}`;
      if (st.scourExtent) {
        const e = st.scourExtent;
        pill.textContent += ` · selected extent ${(100 * e.ratio).toFixed(2)}%`;
        pill.title = `Requested ${(100 * e.requestedRatio).toFixed(2)}%; selected patch extent ${e.widthCm.toFixed(2)} cm of ${e.foundationWidthCm.toFixed(2)} cm (${e.interfaceCount} interfaces).`;
      }
      pills.push(pill);
    });
    return pills;
  }

  renderSolverPanel(analysis) {
    const panel = node('div', 'solver-runner-panel');
    const job = this.solverJob;
    const isRunning = job?.status === 'running';
    const chain = this.resolveDependencyChain(analysis);

    const topRow = node('div', 'solver-runner-top');
    const chainWrap = node('div', 'solver-chain-wrap');
    chainWrap.append(node('span', 'solver-chain-label', this.scourWorkflow.enabled && !isRunning && !job?.stages?.length ? 'Scour chain is assembled from the configured stages when you run.' : `Execution chain (${chain.length} stage${chain.length !== 1 ? 's' : ''}):`));
    const stagesBox = node('div', 'solver-chain-stages');
    stagesBox.id = 'solverChainStages';

    const displayStages = (job && (isRunning || String(job.targetKey) === String(analysis.key)) && job.stages?.length)
      ? job.stages
      : chain.map((a, idx) => ({
          index: idx + 1,
          key: a.key,
          name: a.name || `Analysis ${a.key}`,
          analysisType: Number(a.analysisType || 0),
          status: a.state?.State === 'ExecutedCompleted' ? 'completed'
            : a.state?.State === 'ExecutedNotCompleted' ? 'nonconverged'
            : 'pending',
          steps: Number(a.state?.Step || 0),
          runtimeSeconds: 0,
        }));
    if (!this.scourWorkflow.enabled || isRunning || job?.stages?.length) stagesBox.append(...this.buildStagePills(displayStages));
    chainWrap.append(stagesBox);

    const actionWrap = node('div', 'solver-runner-actions');
    if (isRunning) {
      const stopBtn = node('button', 'secondary', job.stopRequested ? 'Waiting for committed step…' : '⏹ Stop and save results');
      stopBtn.type = 'button'; stopBtn.disabled = Boolean(job.stopRequested || job.cancelRequested);
      stopBtn.title = 'Stop after the current converged step and save committed results.';
      stopBtn.onclick = () => this.stopRun(); actionWrap.append(stopBtn);
      const cancelBtn = node('button', 'secondary solver-cancel-btn', job.cancelRequested ? 'Cancelling…' : 'Cancel now');
      cancelBtn.type = 'button';
      cancelBtn.disabled = Boolean(job.cancelRequested);
      cancelBtn.onclick = () => this.cancelRun();
      actionWrap.append(cancelBtn);
    } else {
      const runLabel = chain.length > 1
        ? `▶ Run analysis (${chain.length}-stage chain)`
        : `▶ Run ${analysis.name || `Analysis #${analysis.key}`}`;
      const runBtn = node('button', 'primary solver-run-btn', runLabel);
      runBtn.type = 'button';
      runBtn.onclick = () => this.runAnalysis(analysis);
      actionWrap.append(runBtn);
    }

    if (job?.bundleReady) {
      const dlBtn = node('button', 'secondary', `⬇ Save ${job.bundleName || '.histra'}`);
      dlBtn.type = 'button';
      dlBtn.title = `Saved at ${job.bundlePath || job.bundleName} — click to download a copy`;
      dlBtn.onclick = () => this.downloadBundle(job.jobId);
      actionWrap.append(dlBtn);

      if (this.onRunComplete) {
        const openResBtn = node('button', 'primary', 'Open in Results →');
        openResBtn.type = 'button';
        openResBtn.onclick = () => this.onRunComplete(job, true);
        actionWrap.append(openResBtn);
      }
    }
    topRow.append(chainWrap, actionWrap);
    panel.append(topRow);
    const pdeltaLabel = node('label', '', 'P-Delta for static stages ');
    const pdeltaSelect = node('select');
    for (const [value, title] of [['EachStep', 'On — update each step (default)'], ['EachIteration', 'On — update each iteration'], ['None', 'Off'], ['model', 'Use each analysis’s saved setting']]) {
      const option = node('option', '', title); option.value = value; pdeltaSelect.append(option);
    }
    pdeltaSelect.value = this.pdeltaEffect; pdeltaSelect.disabled = isRunning;
    pdeltaSelect.onchange = () => { this.pdeltaEffect = pdeltaSelect.value; };
    pdeltaLabel.append(pdeltaSelect); panel.append(pdeltaLabel);
    panel.append(node('p', 'material-note', 'The selected override applies to every static stage in this run. Choose saved settings to use the values edited in the model. Modal geometric stiffness is not yet supported.'));

    if (['ArcLength', 'ArcLengthLinear'].includes(analysis.attributes?.IntegrationMethod)) {
      const enabledForAnalysis = this.arcLambdaTarget.enabled && String(this.arcLambdaTarget.analysisKey) === String(analysis.key);
      const targetLabel = node('label', '', ' Stop this analysis when stage λ crosses the target ');
      const targetEnabled = node('input'); targetEnabled.type = 'checkbox'; targetEnabled.checked = enabledForAnalysis; targetEnabled.disabled = isRunning;
      const targetValue = node('input'); targetValue.type = 'number'; targetValue.step = 'any'; targetValue.value = this.arcLambdaTarget.value;
      targetValue.disabled = isRunning || !enabledForAnalysis;
      targetEnabled.onchange = () => { this.arcLambdaTarget.analysisKey = analysis.key; this.arcLambdaTarget.enabled = targetEnabled.checked; targetValue.disabled = !targetEnabled.checked; };
      targetValue.oninput = () => { this.arcLambdaTarget.value = targetValue.value; };
      targetLabel.prepend(targetEnabled); targetLabel.append(targetValue); panel.append(targetLabel);
      panel.append(node('p', 'material-note', 'Uses this stage’s incremental λ. For a target of 0, the analysis first leaves zero and stops at the first converged step that returns to or crosses it. The saved λ may differ from the target; no interpolation is performed.'));
    }


    const soil = node('details', 'solver-lateral-soil');
    const summary = node('summary', '', 'Linear lateral subgrade (optional)');
    soil.append(summary);
    soil.append(node('p', 'material-note', 'Apply to existing vertical face restraint keys. Kx and Ky are in kN/m³; springs act in tension and compression. This does not create restraint faces or model nonlinear soil.'));
    const enabledLabel = node('label', '', ' Apply lateral subgrade to this run');
    const enabled = node('input');
    enabled.type = 'checkbox';
    enabled.checked = this.lateralSubgrade.enabled;
    enabled.disabled = isRunning;
    enabled.onchange = () => { this.lateralSubgrade.enabled = enabled.checked; };
    enabledLabel.prepend(enabled);
    soil.append(enabledLabel);
    for (const [key, title, placeholder] of [
      ['restraintKeys', 'Vertical restraint keys', 'e.g. 101, 102'],
      ['kx', 'Kx (kN/m³)', '0'], ['ky', 'Ky (kN/m³)', '0'],
    ]) {
      const label = node('label', '', title);
      const input = node('input');
      input.type = key === 'restraintKeys' ? 'text' : 'number';
      if (input.type === 'number') { input.min = '0'; input.step = 'any'; }
      input.placeholder = placeholder;
      input.value = this.lateralSubgrade[key];
      input.disabled = isRunning;
      input.oninput = () => { this.lateralSubgrade[key] = input.value; };
      label.append(input);
      soil.append(label);
    }
    panel.append(soil);

    const scour = node('details', 'solver-lateral-soil');
    scour.open = this.scourWorkflow.enabled;
    scour.append(node('summary', '', 'Staged foundation scour'));
    scour.append(node('p', 'material-note', 'Assign intact masonry soil to all pier-foundation bottom interfaces before Vert. Each ratio selects whole patches by their centre, so the selected patch extent can differ from the requested width. Once the model is prepared, the run shows the actual extent from the chosen edge. Stages retain the previous equilibrium state.'));
    const toggleLabel = node('label', '', ' Enable staged scour');
    const toggle = node('input'); toggle.type = 'checkbox'; toggle.checked = this.scourWorkflow.enabled; toggle.disabled = isRunning;
    toggle.onchange = () => { this.scourWorkflow.enabled = toggle.checked; this.render(); };
    toggleLabel.prepend(toggle); scour.append(toggleLabel);
    const auditLabel = node('label', '', ' Use the analysis convergence criterion without the additional equilibrium audit');
    const auditToggle = node('input'); auditToggle.type = 'checkbox'; auditToggle.checked = this.scourWorkflow.skipEquilibriumAudit; auditToggle.disabled = isRunning;
    auditToggle.onchange = () => { this.scourWorkflow.skipEquilibriumAudit = auditToggle.checked; };
    auditLabel.prepend(auditToggle); scour.append(auditLabel);
    const pierLabel = node('label', '', 'Pier number (left to right)'), pierInput = node('input');
    pierInput.type = 'number'; pierInput.min = '1'; pierInput.step = '1';
    pierInput.value = this.scourWorkflow.pier; pierInput.disabled = isRunning;
    pierInput.oninput = () => { this.scourWorkflow.pier = pierInput.value; };
    pierLabel.append(pierInput); scour.append(pierLabel);
    for (const [key, title] of [['intactMaterial', 'Intact soil material'], ['scouredMaterial', 'Scoured soil material']]) {
      const label = node('label', '', title), select = node('select');
      select.add(new Option('Choose a masonry material…', ''));
      for (const material of this.scourMaterials) select.add(new Option(material.label, material.value));
      select.value = this.scourWorkflow[key]; select.disabled = isRunning;
      select.onchange = () => { this.scourWorkflow[key] = select.value; };
      label.append(select); scour.append(label);
    }
    if (!this.scourMaterials.length) scour.append(node('p', 'material-note', 'No masonry materials are available in this model.'));
    const directionLabel = node('label', '', 'Scour starts at');
    const direction = node('select');
    for (const [v,t] of [['-Y','-Y edge'],['+Y','+Y edge']]) direction.add(new Option(t,v));
    direction.value = this.scourWorkflow.direction; direction.disabled = isRunning;
    direction.onchange = () => { this.scourWorkflow.direction = direction.value; };
    directionLabel.append(direction); scour.append(directionLabel);
    const relevantStages = scourStagesForAnalysis(this.analyses, analysis);
    const currentScour = /^scour[_ ]?\d+$/i.test(analysis.name || '');
    if (currentScour) {
      scour.append(node('p', 'material-note', 'Set the total scoured width for this analysis. Configure earlier stages by selecting each analysis in the list.'));
      const label = node('label', '', 'Total scour for this stage (%)'), input = node('input');
      input.type = 'number'; input.min = '0'; input.max = '100'; input.step = 'any'; input.placeholder = 'Enter percentage';
      input.value = this.scourWorkflow.ratios[String(analysis.key)] ?? ''; input.disabled = isRunning;
      input.oninput = () => { this.scourWorkflow.ratios[String(analysis.key)] = input.value; };
      label.append(input); scour.append(label);
    }
    const earlier = relevantStages.filter(stage => !currentScour || String(stage.key) !== String(analysis.key));
    if (earlier.length) {
      const values = earlier.map(stage => {
        const value = this.scourWorkflow.ratios[String(stage.key)];
        return `${stage.name}: ${value === undefined || value === '' ? 'not configured' : `${value}%`}`;
      });
      scour.append(node('p', 'material-note', `Earlier stages: ${values.join(' · ')}. Select a scour analysis to change its percentage.`));
    } else if (!currentScour) {
      scour.append(node('p', 'material-note', 'Select a scour analysis to set its percentage.'));
    }
    panel.append(scour);

    if (job) {
      const progressRow = node('div', 'solver-progress-section');
      const statusHeader = node('div', 'solver-status-header');
      const statusBadge = node(
        'span',
        `solver-status-badge status-${job.status}`,
        job.status === 'running' ? 'RUNNING'
          : job.status === 'completed' ? (job.outcome === 'nonconverged' ? 'FINISHED (NON-CONVERGED)' : 'COMPLETED')
          : job.status.toUpperCase()
      );
      const statusMsg = node('span', 'solver-status-message', job.message || '');
      statusMsg.id = 'solverStatusMessage';
      const pctLabel = node(
        'span',
        'solver-progress-pct',
        `${Number(job.progress || 0).toFixed(1)}% · ${Number(job.runtimeSeconds || 0).toFixed(1)}s`
      );
      pctLabel.id = 'solverProgressPct';
      statusHeader.append(statusBadge, statusMsg, pctLabel);

      const barTrack = node('div', 'solver-progress-track');
      const barFill = node('div', `solver-progress-fill status-${job.status}`);
      barFill.id = 'solverProgressFill';
      barFill.style.width = `${Math.min(100, Math.max(0, Number(job.progress || 0)))}%`;
      barTrack.append(barFill);
      progressRow.append(statusHeader, barTrack);

      if (job.bundleReady) {
        const sizeKb = (Number(job.bundleSize || 0) / 1024).toFixed(1);
        const savedInfo = node(
          'div',
          'solver-bundle-banner',
          `✓ Saved .histra archive: ${job.bundlePath} (${sizeKb} KB) — automatically loaded into the Results tab.`
        );
        progressRow.append(savedInfo);
      }
      const stepStreamBox = node('div', 'solver-step-stream');
      stepStreamBox.id = 'solverStepStream';
      stepStreamBox.append(...this.buildStepStreamNodes(job));
      progressRow.append(stepStreamBox);
      panel.append(progressRow);

      const logDetails = node('details', 'solver-log-details');
      logDetails.open = this.logExpanded;
      logDetails.ontoggle = () => {
        this.logExpanded = logDetails.open;
      };
      const logSummary = node('summary', 'solver-log-summary');
      logSummary.append(node('span', '', 'Solver execution log (histra-python)'));
      const logCount = node('span', 'solver-log-count', `${this.solverLogs.length} lines`);
      logCount.id = 'solverLogCount';
      logSummary.append(logCount);

      const logPre = node(
        'pre',
        'solver-log-console',
        this.solverLogs.length ? this.solverLogs.join('\n') : 'Waiting for solver output…'
      );
      logPre.id = 'solverLogConsole';
      logDetails.append(logSummary, logPre);
      panel.append(logDetails);
      requestAnimationFrame(() => {
        logPre.scrollTop = logPre.scrollHeight;
      });
    }

    return panel;
  }

  setModel(model) {
    this.analyses = model?.analyses || [];
    this.scourMaterials = masonryMaterialOptions(model);
    this.scourWorkflow = { enabled: false, pier: '1', intactMaterial: '', scouredMaterial: '', direction: '-Y', ratios: {}, skipEquilibriumAudit: false };
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
      const emptyBox = node('div');
      emptyBox.append(node('p', 'material-note', 'No analyses are defined in this model.'));
      if (this.onEdit) {
        const editBtn = node('button', 'primary', '✎ Edit / Add analyses in Build model →');
        editBtn.type = 'button';
        editBtn.onclick = () => this.onEdit(null);
        emptyBox.append(editBtn);
      }
      content.replaceChildren(emptyBox);
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
    const rightGroup = node('div', 'material-header-actions');
    const badge = node('span', 'material-mode', `${analysis.type} · ${STATE_SHORT_LABELS[stateRaw] || stateRaw || 'Unset'}`);
    rightGroup.append(badge);
    if (this.onEdit) {
      const editBtn = node('button', 'secondary', '✎ Edit / Add in Build model →');
      editBtn.type = 'button';
      editBtn.onclick = () => this.onEdit(analysis.key);
      rightGroup.append(editBtn);
    }
    heading.append(title, rightGroup);

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
    header.append(heading, meta, this.renderSolverPanel(analysis));

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
        'HRX analysis definition & solver runner · Replicates C# WindowAnalysesDefinition and MainGridAnalysisElementItem fields · HRX base units: kN, cm, deg, s · — = not serialized. Executed analyses are saved to a self-contained .histra bundle and loaded into the Results tab.'
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
      content.append(node('p', 'mechanism-description', 'Dynamic-only settings are hidden.'));
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
    content.append(this.sectionTable('Stages & output parameters', [
      ['Stages and output', [
        ['Stage definitions', String((analysis.stageDefinitions || []).length), '1', 'StageDefinition'],
        ['Equilibrium stage items', String((analysis.stageItems || []).length), '1', 'StageItem'],
        ['Adaptic phases', String((analysis.adapticPhases || []).length), '1', 'AdapticPhase'],
        ['Output frequency', attr(a, 'OutputFrequency'), 'steps', 'OutputFrequency'],
        ['Local displacement', boolText(a.LocalDisplacement), 'bool', 'LocalDisplacement'],
        ['Has stress output', boolText(a.hasStress), 'bool', 'hasStress'],
        ['Use partition modeling', boolText(a.UsePartitionModeling), 'bool', 'UsePartitionModeling'],
      ]],
    ]));
  }

  renderAll(analysis, content) {
    const a = analysis.attributes || {};
    const rows = Object.keys(a)
      .filter(key => !isDynamicOnlyAnalysisField(key))
      .sort((x, y) => x.localeCompare(y))
      .map(key => [key, a[key], 'raw', key]);
    content.append(
      this.sectionTable(`All serialized HRX Analysis attributes (${rows.length})`, [
        ['XML attributes on <Analysis>', rows],
      ])
    );
  }
}
