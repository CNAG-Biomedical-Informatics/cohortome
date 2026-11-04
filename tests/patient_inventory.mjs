import assert from 'node:assert/strict';
import {patientInventoryMarkup} from '../static/js/patient_inventory.js';

const samples = ['10', '2', '1'].map(n => ({
  sample_id:`S${n}`, visit:`visit_${n}`, modality:'proteomics', assay:'Protein panel',
}));
const clinical = ['10', '2', '1'].map(n => ({
  visit_id:`visit_${n}`, record:{info:{}},
}));
const html = patientInventoryMarkup(samples, String, clinical);
const records = [...html.matchAll(/data-clinical-index="(\d+)"/g)].map(m => m[1]);
assert.deepEqual(records, ['2', '1', '0']); // Preserve original detail identity.
assert(html.indexOf('<code>S1</code>') < html.indexOf('<code>S2</code>'));
assert(html.indexOf('<code>S2</code>') < html.indexOf('<code>S10</code>'));
assert.deepEqual(clinical.map(r => r.visit_id), ['visit_10', 'visit_2', 'visit_1']);
assert.deepEqual([...html.matchAll(/data-visit="([^"]*)"/g)].map(m => m[1]),
  ['visit_1', 'visit_2', 'visit_10']);
assert.equal([...html.matchAll(/class="inventory-visit-label"><svg/g)].length, 3);
assert(html.indexOf('data-clinical-index="2"') < html.indexOf('<code>S1</code>'));
assert(html.indexOf('<code>S1</code>') < html.indexOf('data-visit="visit_2"'));
assert(html.indexOf('<code>S2</code>') < html.indexOf('data-visit="visit_10"'));
const unlinked = patientInventoryMarkup([
  {sample_id:'no-visit', collection_date:'2026-01-01'},
  {sample_id:'same-sample', visit:'V2'},
  {sample_id:'same-sample', visit:'V1'},
], String, [{visit_id:'V1', event_date:'2026-01-01', record:{}}]);
assert.deepEqual([...unlinked.matchAll(/data-visit="([^"]*)"/g)].map(m => m[1]), ['V1', 'V2', '']);
assert.equal([...unlinked.matchAll(/<code>same-sample<\/code>/g)].length, 2);
assert(unlinked.indexOf('Visit not recorded') < unlinked.indexOf('<code>no-visit</code>'));
const missing = patientInventoryMarkup([
  {sample_id:'unknown'}, {sample_id:'known', visit:'visit_1'},
], String);
assert(missing.indexOf('<code>known</code>') < missing.indexOf('<code>unknown</code>'));
console.log('Patient inventory natural ordering passed');

const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const specimens = patientInventoryMarkup(['one', 'two'].map(id => ({sample_id:id,
  biosample_id:`specimen-${id}`, biosample_clarid:{entity:'biosample', subject_id:41,
    human_id:'shared', stub_id:'shared-stub', tissue:'Blood', condition_name:'<script>',
    condition:'C22.0', tools_version:'0.05', codebook_version:'0.04'}})), esc);
assert.equal((specimens.match(/data-clarid-toggle/g) || []).length, 2);
assert(specimens.includes('specimen-one') && specimens.includes('specimen-two'));
assert(specimens.includes('ClarID biosample') && specimens.includes('Tissue:</b> Blood'));
assert(!specimens.includes('<script>') && specimens.includes('&lt;script>'));
const combined = patientInventoryMarkup([{sample_id:'unlabelled', sample_clarid:'not-a-verified-specimen'}], esc,
  [{visit_id:'V1', record:{}}], {human_id:'subject-label', stub_id:'subject-stub', subject_id:96});
assert(combined.includes('<th scope="col">ClarID</th>'));
assert(!combined.includes('Patient link') && !combined.includes('Metadata table'));
assert.equal((combined.match(/data-clarid-toggle/g) || []).length, 1);
assert(combined.includes('ClarID subject 96'));
assert(!combined.includes('not-a-verified-specimen'));
assert.match(combined, /<td><span class="clarid-identity is-compact">/);
assert.match(specimens, /<td><span class="clarid-identity is-compact">/);
