import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../static/js/models_admin_ui.js", import.meta.url), "utf8");
const { createModelsAdminUi } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
globalThis.CSS = { escape: (value) => value };

function setup(fetcher, callback = async () => {}) {
  const button = {}, status = {}, topStatus = {};
  const card = {
    dataset: { lmProviderCard: "system-default" },
    querySelector(selector) {
      if (selector.includes('action="save"')) return button;
      if (selector.includes("save-status")) return status;
      return { value: "", checked: true };
    },
  };
  let onInput;
  const list = {
    querySelector: () => card,
    querySelectorAll: () => [],
    addEventListener: (_, handler) => { onInput = handler; },
  };
  globalThis.fetch = fetcher;
  const ui = createModelsAdminUi({ refs: { modelsListEl: list, modelsStatusEl: topStatus },
    callbacks: { onProvidersChanged: callback } });
  return { ui, button, status, list, input: () => onInput({ target: { closest: () => card } }) };
}

test("save gives immediate progress, survives render, then shows saved and unsaved states", async () => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let calls = 0;
  const state = setup(async (_, options) => {
    calls++;
    if (options?.method === "PATCH") await pending;
    return { ok: true, json: async () => options ? { label: "Default" }
      : { providers: [{ id: "system-default", managed: true }] } };
  });
  const saving = state.ui.saveModel("system-default");
  assert.equal(state.button.textContent, "Saving…");
  assert.equal(state.button.disabled, true);
  await state.ui.saveModel("system-default");
  assert.equal(calls, 1);
  release();
  await saving;
  assert.equal(state.status.textContent, "Settings saved.");
  assert.match(state.list.innerHTML, /Settings saved\./);
  assert.equal(state.button.disabled, false);
  state.input();
  assert.equal(state.status.textContent, "Unsaved changes");
});

test("validation failure appears beside Save and allows retry", async () => {
  const state = setup(async () => ({ ok: false, json: async () => ({ detail: "Invalid URL" }) }));
  await state.ui.saveModel("system-default");
  assert.equal(state.status.textContent, "Invalid URL");
  assert.equal(state.button.disabled, false);
});

test("refresh failure does not claim a successful save failed", async () => {
  const state = setup(async () => ({ ok: true, json: async () => ({ providers: [] }) }),
    async () => { throw new Error("offline"); });
  await state.ui.saveModel("system-default");
  assert.match(state.status.textContent, /^Settings saved, but status refresh failed/);
  assert.equal(state.button.disabled, false);
});
