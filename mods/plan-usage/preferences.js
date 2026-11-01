export const PROVIDERS = ["Codex", "Claude", "Gemini chat", "Antigravity"];
export const PREFERENCE_KEY = "plan-usage.preferences";

export function preferences(saved) {
  return {
    hiddenProviders: ["Gemini chat", "Antigravity"],
    hiddenWindows: { Claude: ["Fable · 7d"] },
    bars: true,
    countdowns: true,
    exactTimes: true,
    freshness: true,
    autoFit: true,
    ...saved,
  };
}

export function enabledProviders(prefs) {
  return PROVIDERS.filter(name => !prefs.hiddenProviders.includes(name));
}

export function windowKey(row) {
  return row.id || row.label;
}

export function visibleWindows(provider, prefs) {
  const hidden = prefs.hiddenWindows[provider.name] || [];
  return (provider.windows || []).filter(row => !hidden.includes(windowKey(row)));
}

export function toggleProvider(prefs, name, enabled) {
  const hidden = prefs.hiddenProviders.filter(value => value !== name);
  return { ...prefs, hiddenProviders: enabled ? hidden : [...hidden, name] };
}

export function toggleWindow(prefs, provider, key, enabled) {
  const hidden = (prefs.hiddenWindows[provider] || []).filter(value => value !== key);
  return { ...prefs, hiddenWindows: { ...prefs.hiddenWindows, [provider]: enabled ? hidden : [...hidden, key] } };
}
