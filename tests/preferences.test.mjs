import test from "node:test";
import assert from "node:assert/strict";
import { preferences, enabledProviders, visibleWindows, toggleProvider, toggleWindow } from "../mods/plan-usage/preferences.js";

test("initial display includes the Fable weekly limit alongside the Claude weekly limit", () => {
  const prefs = preferences();
  assert.deepEqual(enabledProviders(prefs), ["Codex", "Claude"]);
  const windows = [{label: "7d"}, {label: "Fable · 7d"}];
  assert.deepEqual(visibleWindows({name: "Claude", windows}, prefs), windows);
});

test("provider switches can re-enable and hide without losing window selections", () => {
  const prefs = preferences();
  const enabled = toggleProvider(prefs, "Antigravity", true);
  assert.ok(enabledProviders(enabled).includes("Antigravity"));
  assert.ok(!enabledProviders(toggleProvider(enabled, "Antigravity", false)).includes("Antigravity"));
  assert.deepEqual(enabled.hiddenWindows, prefs.hiddenWindows);
  assert.ok(!enabledProviders(prefs).includes("Antigravity"));
});

test("individual limits can be restored and do not affect other providers", () => {
  const provider = {name: "Claude", windows: [{label: "Fable · 7d"}]};
  const hidden = toggleWindow(preferences(), "Claude", "Fable · 7d", false);
  assert.equal(visibleWindows(provider, preferences(hidden)).length, 0);
  assert.equal(visibleWindows(provider, toggleWindow(hidden, "Claude", "Fable · 7d", true)).length, 1);
  assert.equal(visibleWindows({name: "Codex", windows: provider.windows}, hidden).length, 1);
});

test("saved settings survive default additions and all providers can be hidden", () => {
  let prefs = preferences({ hiddenProviders: [], hiddenWindows: {}, exactTimes: false });
  assert.equal(prefs.exactTimes, false);
  assert.equal(prefs.bars, true);
  for (const name of enabledProviders(prefs)) prefs = toggleProvider(prefs, name, false);
  assert.deepEqual(enabledProviders(prefs), []);
});
