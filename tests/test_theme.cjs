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
  const context = {structuredClone, window, document: {documentElement: root, querySelectorAll: () => []},
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

test('palettes are opt-in, reversible and keep centred heatmaps and semantic colours', async () => {
  let rendered;
  const updates = [];
  const window = {matchMedia: () => ({matches: false, addEventListener() {}}), Plotly: {
    newPlot(el, traces) { rendered = traces; el._fullLayout = {}; return Promise.resolve(el); },
    restyle(el, patch, indexes) { updates.push({patch, indexes}); return Promise.resolve(); },
  }};
  vm.runInNewContext(readFileSync('static/js/theme.js', 'utf8'), {
    structuredClone, window, document: {documentElement: {dataset: {}, style: {}}, querySelectorAll: () => []},
    getComputedStyle: () => ({getPropertyValue: () => '#123456'}),
  });
  const traces = [
    {type: 'scatter', meta: {cohortome_group: 0}, line: {color: '#2563eb'}, x: [1], y: [2]},
    {type: 'scatter', marker: {color: '#dc2626'}, name: 'Significant'},
    {type: 'heatmap', z: [[-1, 1]], zmid: 0, colorscale: 'RdBu'},
    {type: 'heatmap', z: [[0, 2]], colorscale: 'Blues'},
  ];
  window.CohortomeTheme.applyPalettes({plot_palette: 'okabe-ito', heatmap_palette: 'viridis', diverging_palette: 'blue-orange'});
  await window.CohortomeTheme.newPlot({isConnected: true}, traces);
  assert.equal(rendered[0].line.color, '#0072b2');
  assert.equal(rendered[1].marker.color, '#dc2626');
  assert.equal(rendered[2].zmid, 0);
  assert.equal(rendered[2].colorscale[1][0], 0.5);
  assert.equal(rendered[3].colorscale, 'Viridis');
  assert.equal(traces[0].line.color, '#2563eb');
  assert.equal(rendered[0].x, traces[0].x);
  window.CohortomeTheme.applyPalettes({plot_palette: 'default', heatmap_palette: 'default', diverging_palette: 'default'});
  assert.equal(updates[0].patch.line[0].color, '#2563eb');
  assert.equal(updates[1].patch.colorscale[0], 'RdBu');
  assert.equal(updates[2].patch.colorscale[0], 'Blues');
  assert.ok(updates.every(({patch}) => !('zmid' in patch) && !('x' in patch) && !('y' in patch)));
});
