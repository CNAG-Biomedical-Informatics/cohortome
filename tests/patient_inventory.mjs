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
