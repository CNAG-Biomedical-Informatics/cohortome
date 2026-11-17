import { fallbackCopyText } from './shared.js';
import {createScriptEditorView} from './react/ui.js';

export function createScriptEditor({ host, state, getContext, onChange }) {
  const panel = document.createElement('section');
  panel.className = 'analysis-script-editor';
  panel.hidden = true;
  host.appendChild(panel);
  let feedback='';
  const scriptValue=()=>state.analysisScriptDraft?.script || '';
  const languageValue=()=>state.analysisScriptDraft?.language || 'python';
  const edit=(key,value)=>{feedback='';state.analysisScriptDraft={...(state.analysisScriptDraft || {}),[key]:value};onChange();};
  const view=createScriptEditorView(panel,{
    language:value=>edit('language',value),script:value=>edit('script',value),
    prepare:generateTemplate,inputs:checkInputs,basic:useBasic,copy:copyTemplate,
  });
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
    return {contract,compare:!!context.compare_mode,rows:[
      ['Language',contract?.language || (context.script_language==='r' ? 'R' : 'Python')],
      ['Packages',packages],['Cohort A',`${aName} · ${count(contract?.cohort_a)}`],
      ['Cohort B',bName+(context.compare_mode ? ` · ${count(contract?.cohort_b)}` : '')],
    ]};
  }
  async function prepareInputs(replaceScript = false) {
    if (busy) throw Error('Input preparation is already running.');
    if (missingCohort()) throw Error(missingCohort());
    const key = contextKey();
    const script = scriptValue();
    busy = true; error = ''; state.analysisScriptDraft = { script: scriptValue(), language: languageValue() };
    onChange();
    try {
      const response = await fetch('/analysis/script-template', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: key});
      const payload = await response.json();
      if (!response.ok) throw Error(payload.detail || 'Cannot prepare script inputs.');
      if (contextKey() !== key) throw Error('Inputs changed while preparing. Prepare the template again.');
      template = payload.template;
      templateKey = key;
      state.analysisScriptDraft = { key, language: languageValue(), script: replaceScript ? template : script, contract_id: payload.contract_id,
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
  async function generateTemplate() {
    if (scriptValue() && !window.confirm('Replace your code with a data-aware template?')) return;
    try { await prepareInputs(true); } catch (_) { /* shown by render */ }
  }
  async function checkInputs() {
    try { await prepareInputs(); } catch (_) { /* shown by render */ }
  }
  function useBasic() {
    if (scriptValue() && !window.confirm('Replace your code with the 60-second background test?')) return;
    const script = languageValue() === 'r'
      ? "# 60-second background test; no scientific analysis.\ncat('Waiting 60 seconds. Keep the app open.\\n')\nSys.sleep(60)\noutput <- '/work/output'\ndir.create(output, recursive=TRUE, showWarnings=FALSE)\nwriteLines('Background test succeeded.', file.path(output, 'diagnostic.txt'))\ncat('Completed.\\n')\n"
      : "# 60-second background test; no scientific analysis.\nfrom pathlib import Path\nimport time\nprint('Waiting 60 seconds. Keep the app open.', flush=True)\ntime.sleep(60)\noutput = Path('/work/output')\noutput.mkdir(parents=True, exist_ok=True)\n(output / 'diagnostic.txt').write_text('Background test succeeded.\\n')\nprint('Completed.')\n";
    error = '';
    state.analysisScriptDraft = {...(state.analysisScriptDraft || {}), language: languageValue(), script};
    onChange();
  }
  async function copyTemplate() {
    if (busy || missingCohort() || templateKey !== contextKey()) return;
    try {
      let copied = false;
      if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(template); copied = true; } catch (_) { /* fallback for HTTP */ }
      }
      if (!copied && !fallbackCopyText(template)) throw Error('Clipboard unavailable.');
      feedback = 'Template copied. Ask your AI to complete the analysis section, then paste its code here.';
    } catch (exc) { feedback = exc.message; }
    render(true);
  }
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
    view.render({language:languageValue(),script:scriptValue(),busy,missing:!!missingCohort(),
      copyDisabled:busy || !!missingCohort() || !template || templateKey!==contextKey() || state.analysisScriptDraft?.key!==contextKey(),
      summary:renderSummary(),status:feedback || status().detail});
  }

  async function prepareForRun() {
    if (!scriptValue().trim()) throw Error('Paste a complete script or choose Use 60-second test.');
    await prepareInputs();
    const check = status();
    if (!check.complete) throw Error(check.detail);
  }
  return { render, status, prepareForRun };
}
