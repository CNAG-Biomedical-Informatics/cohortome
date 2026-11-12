import test from 'node:test';
import assert from 'node:assert/strict';
import {parseClinicalFilterValues, clinicalRuleLabel} from '../static/js/clinical_filters.js';

test('clinical values preserve zero, negatives and booleans', () => {
  assert.deepEqual(parseClinicalFilterValues('number', 'eq', ['0']), [0]);
  assert.deepEqual(parseClinicalFilterValues('number', 'between', ['-1', '0']), [-1, 0]);
  assert.deepEqual(parseClinicalFilterValues('number', 'between', ['1', '1']), [1, 1]);
  assert.deepEqual(parseClinicalFilterValues('boolean', 'eq', ['false']), [false]);
  assert.deepEqual(parseClinicalFilterValues('string', 'in', ['a,b', 'c', 'a,b']), ['a,b', 'c']);
  assert.deepEqual(parseClinicalFilterValues('number', 'is_missing', []), []);
});

test('invalid numeric/date/range values fail before submitting', () => {
  for (const value of ['', 'NaN', 'Infinity', 'none']) {
    assert.throws(() => parseClinicalFilterValues('number', 'eq', [value]));
  }
  assert.throws(() => parseClinicalFilterValues('number', 'between', ['4', '2']));
  assert.throws(() => parseClinicalFilterValues('number', 'between', ['4']));
  assert.throws(() => parseClinicalFilterValues('date', 'eq', ['2025-02-30']));
  assert.throws(() => parseClinicalFilterValues('boolean', 'eq', ['yes']));
  assert.deepEqual(parseClinicalFilterValues('date', 'between', ['2025-01-01','2025-02-01']), ['2025-01-01','2025-02-01']);
});

test('rule labels include units and distinguish missing from a negative value', () => {
  assert.equal(clinicalRuleLabel({operator:'eq', values:[0]}, {label:'Marker', unit:'mg/L'}), 'Marker is 0 mg/L');
  assert.equal(clinicalRuleLabel({operator:'is_missing', values:[]}, {label:'Marker', unit:'mg/L'}), 'Marker is not recorded');
  assert.equal(clinicalRuleLabel({operator:'eq', values:[false]}, {label:'Recorded flag'}), 'Recorded flag is No');
});
