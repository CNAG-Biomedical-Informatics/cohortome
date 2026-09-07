const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

test('system preference and Plotly recolouring preserve data and zoom', async () => {
  const root = {dataset: {appearance: 'system'}, style: {}};
  const media = {matches: true, addEventListener: (_, callback) => { media.change = callback; }};
  let rendered, relayout;
  const window = {matchMedia: () => media, Plotly: {
    newPlot: (el, traces, layout) => { rendered = {traces, layout}; el._fullLayout = layout; return Promise.resolve(el); },
    relayout: (_, update) => { relayout = update; return Promise.resolve(); },
  }};
  const context = {window, document: {documentElement: root, querySelectorAll: () => []},
    getComputedStyle: () => ({getPropertyValue: key => key === '--ink' ? '#e5edf6' : '#acbdd0'})};
  vm.runInNewContext(readFileSync('static/js/theme.js', 'utf8'), context);
  assert.equal(root.dataset.theme, 'dark');
  const traces = [{type: 'heatmap', z: [[1, 2]], colorscale: 'Viridis'}];
  const base = {xaxis: {range: [2, 5], title: 'Position'}, yaxis: {type: 'log'}};
  await window.CohortomeTheme.newPlot({isConnected: true}, traces, base);
  assert.equal(rendered.traces, traces);
  assert.equal(rendered.layout.plot_bgcolor, '#172435');
  assert.deepEqual(rendered.layout.xaxis.range, [2, 5]);
  assert.equal(base.xaxis.title, 'Position');
  media.matches = false; media.change();
  assert.equal(root.dataset.theme, 'light');
  assert.equal(relayout.plot_bgcolor, '#f8fbff');
  assert.ok(!Object.keys(relayout).some(k => k.includes('range')));
  window.CohortomeTheme.apply('dark');
  media.change();
  assert.equal(root.dataset.theme, 'dark');
});
