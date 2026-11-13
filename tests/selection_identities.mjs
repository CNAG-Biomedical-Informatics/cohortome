import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const dataUrl = text => `data:text/javascript;base64,${Buffer.from(text).toString('base64')}`;
const identityUrl = dataUrl(readFileSync(new URL('../static/js/identities.js', import.meta.url), 'utf8'));
const { identityKey } = await import(identityUrl);
const helpers = readFileSync(new URL('../static/js/app_helpers.js', import.meta.url), 'utf8')
  .replace('./identities.js', identityUrl);
const { normalizeSelectionMetadata, createSelectionMetadata, selectionScopeLabel } = await import(dataUrl(helpers));
const members = ['a', 'b'].map(dataset_id => ({dataset_id, patient_id:'P001', sample_id:'unrelated-sample'}));
const selection = normalizeSelectionMetadata({members, dataset_ids:['a', 'b']});
assert.equal(selection.patient_count, 2);
assert.equal(new Set(selection.patient_ids).size, 2);
assert.equal(new Set(selection.sample_ids).size, 2);
const single = normalizeSelectionMetadata({dataset_ids:['a'], patient_ids:['P001']});
assert.deepEqual(single.patient_ids, [identityKey('a', 'patient', 'P001')]);
assert.deepEqual(single.sample_ids, []); // A patient is not a sample.
const sample = normalizeSelectionMetadata({dataset_ids:['a'], sample_ids:['unrelated-sample']});
assert.deepEqual(sample.patient_ids, []); // No patient linkage guessed from the name.
assert.deepEqual(sample.sample_ids, [identityKey('a', 'sample', 'unrelated-sample')]);
console.log('Canonical selection identity checks passed.');
assert.deepEqual(normalizeSelectionMetadata({members}).dataset_ids, ['a', 'b']);
assert.equal(createSelectionMetadata({sampleIds:['S1']}).id_type, 'sample');
assert.equal(selectionScopeLabel(createSelectionMetadata({members, idType:'patient'})), '2 patients');
assert.equal(selectionScopeLabel(createSelectionMetadata({sampleIds:['S1']})), '1 sample');
assert.equal(selectionScopeLabel(createSelectionMetadata({patientIds:['P:visit-1']})), '1 patient');
assert.equal(selectionScopeLabel(createSelectionMetadata({queryResultHandle:'all-results', patientCount:605, idType:'patient'})), '605 patients');
assert.equal(selectionScopeLabel(createSelectionMetadata({selection_active:true, idType:'patient'})), '0 patients');
assert.equal(selectionScopeLabel({}), '');
const origin = {kind:'patients', prompt:'Blood samples'};
assert.deepEqual(createSelectionMetadata({members, source:origin}).source, origin);
globalThis.document = {documentElement:{dataset:{}}, getElementById:()=>null, addEventListener:()=>{}};
const workspaceCode = readFileSync(new URL('../static/js/workspace_ui.js', import.meta.url), 'utf8')
  .replace('./app_helpers.js', dataUrl(helpers));
const {createWorkspaceUi} = await import(dataUrl(workspaceCode));
const state = {currentDatasetScopeId:'a', currentDashboardSubtab:'multimodal', savedCohorts:[],
  phenoSelectedSavedCohortIds:[], analysisScopeMetadata:createSelectionMetadata({patientIds:['Q1'], datasetIds:['a']})};
const ui = createWorkspaceUi({state, refs:{}, helpers:{}, callbacks:{}});
state.activePatientScope = {workspace:'a', selection:createSelectionMetadata({members, idType:'patient'})};
assert.equal(ui.summarizeScopeForTab('dashboard'), '2 patients');
assert.equal(ui.summarizeScopeForTab('analysis'), '1 patient');
state.activePatientScope = {workspace:'a', selection:createSelectionMetadata({selection_active:true, idType:'patient'})};
assert.equal(ui.summarizeScopeForTab('dashboard'), '0 patients');
assert.equal(ui.summarizeScopeForTab('analysis'), '1 patient');
state.currentDatasetScopeId = 'b';
assert.equal(ui.summarizeScopeForTab('dashboard'), 'Full workspace');
state.currentDatasetScopeId = 'a';
state.activePatientScope = null;
assert.equal(ui.summarizeScopeForTab('dashboard'), 'Full workspace');
console.log('Applied shared scope and independent chat scope checks passed.');
