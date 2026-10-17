import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const dataUrl = text => `data:text/javascript;base64,${Buffer.from(text).toString('base64')}`;
const identityUrl = dataUrl(readFileSync(new URL('../static/js/identities.js', import.meta.url), 'utf8'));
const { identityKey } = await import(identityUrl);
const helpers = readFileSync(new URL('../static/js/app_helpers.js', import.meta.url), 'utf8')
  .replace('./identities.js', identityUrl);
const { normalizeSelectionMetadata } = await import(dataUrl(helpers));
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
