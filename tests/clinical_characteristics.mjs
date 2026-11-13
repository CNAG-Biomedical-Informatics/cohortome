import assert from 'node:assert/strict';
import { characteristicsMarkup } from '../static/js/clinical_characteristics.js';
const escape = value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const html = characteristicsMarkup([{label:'Example <dataset>', patients:4, rows:[
  {label:'Age', unit:'years', kind:'number', median:32.5, q1:25, q3:40, recorded:2, missing:2},
  {label:'Category', kind:'category', recorded:1, missing:3, categories:[{label:'<value>', count:1}]},
]}], escape);
assert.ok(html.includes('Example &lt;dataset&gt;'));
assert.ok(html.includes('<strong>32.5</strong> <span>[25–40]</span>'));
assert.ok(html.includes('&lt;value&gt;'));
assert.ok(html.includes('(25%)'));
assert.ok(html.includes('clinical-stats-table'));
assert.ok(html.includes('has-missing'));
assert.ok(html.includes('not baseline values'));
assert.ok(characteristicsMarkup([], escape).includes('unavailable'));
const datasets = ['a', 'b'].map(dataset_id => ({dataset_id, label:dataset_id, patients:1,
  rows:[{label:'Only in ' + dataset_id, kind:'number', median:1, q1:1, q3:1, recorded:1, missing:0}]}));
assert.ok(characteristicsMarkup(datasets, escape, 'b').includes('Only in b'));
assert.ok(!characteristicsMarkup(datasets, escape, 'b').includes('Only in a'));
assert.ok(characteristicsMarkup(datasets, escape, 'missing').includes('Only in a'));
