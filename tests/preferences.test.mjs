import test from "node:test";
import assert from "node:assert/strict";
import { preferences, enabledProviders, visibleWindows, toggleProvider, toggleWindow } from "../mods/plan-usage/preferences.js";

test("initial display keeps Codex and Claude and suppresses the requested extras", () => {
  const prefs = preferences();
  assert.deepEqual(enabledProviders(prefs), ["Codex", "Claude"]);
  assert.deepEqual(visibleWindows({name: "Claude", windows: [{label: "7d"}, {label: "Fable · 7d"}]}, prefs), [{label: "7d"}]);
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
  const prefs = toggleWindow(preferences(), "Claude", "Fable · 7d", true);
  const provider = {name: "Claude", windows: [{label: "Fable · 7d"}]};
  assert.equal(visibleWindows(provider, prefs).length, 1);
  assert.equal(visibleWindows(provider, toggleWindow(prefs, "Claude", "Fable · 7d", false)).length, 0);
  assert.equal(visibleWindows({name: "Codex", windows: provider.windows}, preferences()).length, 1);
});

test("saved settings survive default additions and all providers can be hidden", () => {
  let prefs = preferences({ hiddenProviders: [], hiddenWindows: {}, exactTimes: false });
  assert.equal(prefs.exactTimes, false);
  assert.equal(prefs.bars, true);
  for (const name of enabledProviders(prefs)) prefs = toggleProvider(prefs, name, false);
  assert.deepEqual(enabledProviders(prefs), []);
});
