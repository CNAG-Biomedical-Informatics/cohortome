import assert from 'node:assert/strict';
import {downloadFile, downloadStatus} from '../static/js/shared.js';

const bytes = new Uint8Array([80, 75, 3, 4, 0, 255, 128, 10]);
globalThis.fetch = async () => new Response(bytes);
let saved = true, calls = 0;
globalThis.window = {__COHORTOME_DESKTOP__: true, __TAURI__: {core: {
  invoke: async (command, body, options) => {
    calls++;
    assert.equal(command, 'save_export_file');
    assert.deepEqual(new Uint8Array(body), bytes);
    assert.equal(options.headers['x-cohortome-filename'], 'cohort.zip');
    return saved;
  },
}}};
assert.equal(downloadStatus(await downloadFile('/export', 'cohort.zip')), 'File saved.');
saved = false;
assert.equal(downloadStatus(await downloadFile('/export', 'cohort.zip')), 'Save cancelled.');
window.__TAURI__.core.invoke = async () => { throw 'Permission denied'; };
await assert.rejects(downloadFile('/export', 'cohort.zip'), /Permission denied/);
globalThis.fetch = async () => new Response(JSON.stringify({detail: 'Access revoked'}), {status: 403});
await assert.rejects(downloadFile('/export', 'cohort.zip'), /Access revoked/);
assert.equal(calls, 2);

globalThis.fetch = async () => new Response(bytes);
window.__COHORTOME_DESKTOP__ = false;
let clicked = false, removed = false;
const link = {click() { clicked = true; }, remove() { removed = true; }};
globalThis.document = {createElement: () => link, body: {appendChild() {}}};
window.setTimeout = fn => fn();
assert.equal(downloadStatus(await downloadFile('/export', 'cohort.zip')), 'Download started.');
assert.equal(link.download, 'cohort.zip');
assert.ok(clicked && removed);
console.log('Download bridge: binary data, save/cancel/error, access failure, and browser fallback passed.');
