import { escapeHtml, fallbackCopyText } from './shared.js';
import { formatAssayRequirementLabel } from './assay_labels.js';

export function createScriptEditor({ host, state, getContext, onChange }) {
  const panel = document.createElement('section');
  panel.className = 'analysis-script-editor';
  panel.hidden = true;
  panel.innerHTML = `<h4>Custom Python / R · synthetic prototype</h4>
    <label for="analysisScriptLanguage">Language</label><select id="analysisScriptLanguage"><option value="python">Python</option><option value="r">R</option></select>
    <p class="section-note">For limma-voom, choose R. To compare two groups, open Patients, turn on comparison and choose Cohort A and Cohort B before preparing.</p>
    <p class="section-note">COHORTome prepares the current cohorts and selected assays (all demo assays if none selected). The template describes the objects and includes loading code, not patient values. Only the bundled synthetic autoimmune demo is allowed.</p>
    <div class="pheno-actions"><button type="button" data-script-basic>Use 60-second test</button><button type="button" data-script-inputs>Check inputs</button><button type="button" data-script-prepare>Generate data-aware template</button><button type="button" class="query-chip" data-script-copy disabled>Copy template for AI</button></div>
    <div data-script-summary aria-live="polite"></div>
    <p class="section-note">Paste a complete script and click Run: inputs are prepared automatically without replacing your code. The 60-second test waits one minute so you can navigate elsewhere while it runs; it performs no scientific analysis. Generate a data-aware template only when you need loading code and instructions for an AI.</p>
    <label for="analysisScriptCode">Analysis script</label><textarea id="analysisScriptCode" rows="18" spellcheck="false" placeholder="Paste your complete Python or R script, or choose Use 60-second test."></textarea>
    <p class="section-note">Fixed packages; no network or installation. 90 seconds, 512 MiB. Save CSV, TXT or PNG under /work/output. Review statistical choices before running. The exact script and input contract are saved with the run.</p>
    <p data-script-status role="status"></p>`;
  host.appendChild(panel);
  const editor = panel.querySelector('textarea');
  const language = panel.querySelector('#analysisScriptLanguage');
  language.addEventListener('change', () => {
    state.analysisScriptDraft = {...(state.analysisScriptDraft || {}), language: language.value};
    onChange();
  });
  const prepare = panel.querySelector('[data-script-prepare]');
  const copy = panel.querySelector('[data-script-copy]');
  const statusEl = panel.querySelector('[data-script-status]');
  const summaryEl = panel.querySelector('[data-script-summary]');
  let template = '', templateKey = '', busy = false, error = '', lastContextKey = '';
  const contextKey = () => JSON.stringify(getContext());
  function missingCohort() {
    const context = getContext();
    if (!context.compare_mode) return '';
    if (!context.selected_patient_ids?.trim() && !context.query_result_handle) return 'Choose Cohort A in Patients to prepare this comparison.';
    if (!context.compare_selected_patient_ids?.trim()) return 'Choose Cohort B in Patients to prepare this comparison.';
    return '';
  }
  function renderSummary() {
    const context = getContext();
    const draft = state.analysisScriptDraft || {};
    const contract = draft.key === contextKey() ? draft.contract : null;
    const cohortName = id => (state.savedCohorts || []).find(item => String(item.id) === String(id || ''))?.name;
    const aName = cohortName(state.analysisSelectedSavedCohortId) || (context.selected_patient_ids || context.query_result_handle ? 'Current selection' : 'Full workspace');
    const bName = context.compare_mode ? cohortName(state.analysisCompareSavedCohortId) || (context.compare_selected_patient_ids ? 'Current selection' : 'Not selected') : 'Not used — single-cohort analysis';
    const count = value => Number.isInteger(value) ? `${value} patients` : 'Count not checked yet';
    const packages = contract ? Object.entries(contract.packages || {}).map(([name, version]) => `${name} ${version}`).join(', ') : 'Prepare the template to check the installed package list.';
    summaryEl.innerHTML = `<h4>Check before copying</h4><dl>
      <dt>Language</dt><dd>${escapeHtml(contract?.language || (context.script_language === 'r' ? 'R' : 'Python'))}</dd>
      <dt>Packages</dt><dd>${escapeHtml(packages)}</dd>
      <dt>Cohort A</dt><dd>${escapeHtml(aName)} · ${count(contract?.cohort_a)}</dd>
      <dt>Cohort B</dt><dd>${escapeHtml(bName)}${context.compare_mode ? ` · ${count(contract?.cohort_b)}` : ''}</dd></dl>
      ${!context.compare_mode ? '<p class="section-note">This template does not define a Cohort B. For an A-versus-B question, enable comparison in Patients and prepare again.</p>' : ''}
      ${contract ? `<div class="query-result-table-scroll"><table><thead><tr><th>Assay</th><th>A samples</th>${context.compare_mode ? '<th>B samples</th>' : ''}<th>Features</th></tr></thead><tbody>${Object.entries(contract.assays || {}).map(([name, assay]) => `<tr><td>${escapeHtml(formatAssayRequirementLabel(name))}</td><td>${escapeHtml(assay.cohort_a_samples ?? 'Not checked')}</td>${context.compare_mode ? `<td>${escapeHtml(assay.cohort_b_samples ?? 'Not checked')}</td>` : ''}<td>${escapeHtml(assay.features ?? 'Not checked')}</td></tr>`).join('')}</tbody></table></div>
      ${(contract.omitted_assays || []).map(assay => `<p class="section-note">${escapeHtml(formatAssayRequirementLabel(assay.modality))}: not included — ${escapeHtml(assay.reason)}</p>`).join('')}
      ${context.compare_mode && Object.values(contract.assays || {}).some(assay => !assay.cohort_a_samples || !assay.cohort_b_samples) ? '<p class="section-note">Some assays have no samples in one group. They cannot support an A/B comparison; choose an assay with samples in both groups.</p>' : ''}` : '<p class="section-note">Assay coverage has not been checked. Prepare the template to see the matched sample counts.</p>'}`;
  }
  editor.addEventListener('input', () => {
    state.analysisScriptDraft = { ...(state.analysisScriptDraft || {}), script: editor.value };
    onChange();
  });
  async function prepareInputs(replaceScript = false) {
    if (busy) throw Error('Input preparation is already running.');
    if (missingCohort()) throw Error(missingCohort());
    const key = contextKey();
    const script = editor.value;
    busy = true; error = ''; state.analysisScriptDraft = { script: editor.value, language: language.value };
    onChange();
    try {
      const response = await fetch('/analysis/script-template', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: key});
      const payload = await response.json();
      if (!response.ok) throw Error(payload.detail || 'Cannot prepare script inputs.');
      if (contextKey() !== key) throw Error('Inputs changed while preparing. Prepare the template again.');
      template = payload.template;
      templateKey = key;
      state.analysisScriptDraft = { key, language: language.value, script: replaceScript ? template : script, contract_id: payload.contract_id,
        contract: {language: payload.contract.language, packages: payload.contract.packages,
          cohort_a: payload.contract.cohort_a, cohort_b: payload.contract.cohort_b,
          omitted_assays: payload.contract.omitted_assays,
          assays: Object.fromEntries(Object.entries(payload.contract.assays || {}).map(([name, assay]) =>
            [name, {features: assay.features, cohort_a_samples: assay.cohort_a_samples, cohort_b_samples: assay.cohort_b_samples}]))},
        image_id: payload.sandbox.image_id || '', summary: `${payload.contract.patients} patients; ${Object.keys(payload.contract.assays).length} assays.`,
        unavailable: payload.sandbox.message || '' };
    } catch (exc) { error = exc.message || 'Cannot prepare script inputs.'; throw exc; }
    finally { busy = false; onChange(); }
  }
  prepare.addEventListener('click', async () => {
    if (editor.value && !window.confirm('Replace your code with a data-aware template?')) return;
    try { await prepareInputs(true); } catch (_) { /* shown by render */ }
  });
  panel.querySelector('[data-script-inputs]').addEventListener('click', async () => {
    try { await prepareInputs(); } catch (_) { /* shown by render */ }
  });
  panel.querySelector('[data-script-basic]').addEventListener('click', () => {
    if (editor.value && !window.confirm('Replace your code with the 60-second background test?')) return;
    const script = language.value === 'r'
      ? "# 60-second background test; no scientific analysis.\ncat('Waiting 60 seconds. Keep the app open.\\n')\nSys.sleep(60)\noutput <- '/work/output'\ndir.create(output, recursive=TRUE, showWarnings=FALSE)\nwriteLines('Background test succeeded.', file.path(output, 'diagnostic.txt'))\ncat('Completed.\\n')\n"
      : "# 60-second background test; no scientific analysis.\nfrom pathlib import Path\nimport time\nprint('Waiting 60 seconds. Keep the app open.', flush=True)\ntime.sleep(60)\noutput = Path('/work/output')\noutput.mkdir(parents=True, exist_ok=True)\n(output / 'diagnostic.txt').write_text('Background test succeeded.\\n')\nprint('Completed.')\n";
    error = '';
    state.analysisScriptDraft = {...(state.analysisScriptDraft || {}), language: language.value, script};
    onChange();
  });
  copy.addEventListener('click', async () => {
    if (busy || missingCohort() || templateKey !== contextKey()) return;
    try {
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(template); copied = true; } catch (_) { /* fallback for HTTP */ }
      }
      if (!copied && !fallbackCopyText(template)) throw Error('Clipboard unavailable.');
      statusEl.textContent = 'Template copied. Ask your AI to complete the analysis section, then paste its code here.';
    } catch (exc) { statusEl.textContent = exc.message; }
  });
  function status() {
    const draft = state.analysisScriptDraft || {};
    if (missingCohort()) return {complete: false, detail: missingCohort()};
    if (busy) return {complete: false, detail: 'Preparing input structures…'};
    if (!draft.script?.trim()) return {complete: false, detail: error || 'Paste a complete script or choose Use 60-second test.'};
    if (draft.key !== contextKey()) return {complete: true, detail: error || 'Inputs will be checked automatically when you run. Your code will not be replaced.'};
    if (!draft.image_id) return {complete: false, detail: draft.unavailable || 'The sandbox is unavailable.'};
    return {complete: true, detail: `${draft.summary} Script ready to submit. This does not validate the analysis.`};
  }
  function render(required) {
    panel.hidden = !required;
    if (!required) return;
    if (lastContextKey !== contextKey()) { error = ''; lastContextKey = contextKey(); }
    language.value = state.analysisScriptDraft?.language || 'python';
    language.disabled = busy;
    editor.disabled = busy;
    panel.querySelector('[data-script-basic]').disabled = busy;
    panel.querySelector('[data-script-inputs]').disabled = busy || Boolean(missingCohort());
    if (editor.value !== (state.analysisScriptDraft?.script || '')) editor.value = state.analysisScriptDraft?.script || '';
    prepare.disabled = busy || Boolean(missingCohort());
    copy.disabled = busy || Boolean(missingCohort()) || !template || templateKey !== contextKey() || state.analysisScriptDraft?.key !== contextKey();
    renderSummary();
    statusEl.textContent = status().detail;
  }
  async function prepareForRun() {
    if (!editor.value.trim()) throw Error('Paste a complete script or choose Use 60-second test.');
    await prepareInputs();
    const check = status();
    if (!check.complete) throw Error(check.detail);
  }
  return { render, status, prepareForRun };
}
