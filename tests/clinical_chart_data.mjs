import assert from 'node:assert/strict';
import {clinicalSexCounts, clinicalMeasurements} from '../static/js/clinical_chart_data.js';
const source = {male:3, Male:2, ' MALE ':1, female:4, Female:5, unknown:2, Unknown:1, Other:2, M:1};
const result = Object.fromEntries(clinicalSexCounts(source));
assert.deepEqual(result, {Female:9, Male:6, Other:2, M:1, Unknown:3});
assert.equal(source.male, 3);
assert.equal(Object.keys(result).at(-1), 'Unknown');
assert.deepEqual(clinicalSexCounts({}), []);
assert.deepEqual(clinicalSexCounts({'':2, Unknown:1, Male:0}), [['Unknown', 3]]);
assert.equal(Object.values(result).reduce((a, b) => a+b, 0), Object.values(source).reduce((a, b) => a+b, 0));
const datasets = ['a', 'b'].map(dataset_id => ({dataset_id, rows:[
  {kind:'number', field_id:'coded-crp-mg-l', label:'CRP', unit:'mg/L'},
  {kind:'number', field_id:dataset_id + '-uncoded', label:'Score', unit:''},
]}));
const measurements = clinicalMeasurements(datasets);
assert.equal(measurements.length, 3);
assert.equal(measurements.find(field => field.id === 'coded-crp-mg-l').sources.length, 2);
assert.equal(measurements.find(field => field.id === 'a-uncoded').sources.length, 1);
assert.deepEqual(clinicalMeasurements([]), []);
