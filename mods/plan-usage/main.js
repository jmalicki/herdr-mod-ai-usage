import { View, div, svg } from "gpui-kit";
import { h_flex, v_flex, Checkbox } from "gpui-base";
import { exec, theme, appHome, readTextFile, shared, setShared, openOverlay, closeOverlay, props, run, nextCommand, settings as appSettings } from "herdr";
import { PROVIDERS, PREFERENCE_KEY, preferences, enabledProviders, visibleWindows, windowKey, toggleProvider, toggleWindow } from "./preferences.js";

function countdown(seconds) {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

// Herdr 0.1.11 reports element measurements after applying the UI zoom.
function uiScale() { return Number(appSettings().zoom) || 1; }

export default class PlanUsage extends View {
  init(_props, cx) {
    if (!shared(PREFERENCE_KEY)) setShared(PREFERENCE_KEY, preferences());
    if (shared("plan-usage.measurement")) setShared("plan-usage.measurement", null);
    this.isSettings = !!props()?.settings;
    if (this.isSettings) return;
    this.data = null;
    this.busy = false;
    this.error = null;
    this.refresh(cx);
    cx.timer.every(60000, cx => this.refresh(cx));
    cx.spawn(async cx => {
      for (;;) {
        const command = await nextCommand();
        if (command === "refresh") this.refresh(cx);
        if (command === "settings") this.showSettings();
        if (command === "fit") {
          setShared(PREFERENCE_KEY, { ...preferences(shared(PREFERENCE_KEY)), autoFit: true });
          this.requestedHeight = null;
          this.fitPanel();
        }
        cx.notify();
      }
    });
  }

  showSettings() {
    openOverlay({ mod: "plan-usage", kind: "dialog", width: 440, height: 620,
      props: { settings: true, catalog: this.data?.providers || [] } });
  }

  fitPanel() {
    if (this.contentHeight == null || !preferences(shared(PREFERENCE_KEY)).autoFit) return;
    // Padding, the two gaps, and the measured header/footer surround the content.
    const height = Math.max(80, Math.min(310, Math.ceil(
      this.contentHeight + (this.headerHeight || 22) + (this.footerHeight || 11) + 40)));
    if (height !== this.requestedHeight) {
      this.requestedHeight = height;
      this.pendingAutoResize = true;
      run("layout.resize", { id: "plan-usage-panel", px: height });
    }
  }

  refresh(cx, force = false) {
    if (this.busy) return;
    this.busy = true;
    cx.notify();
    cx.spawn(async cx => {
      try {
        const config = JSON.parse(await readTextFile(`${appHome()}/mods/plan-usage/runner.json`));
        const args = [config.collector, "--state", `${appHome()}/data/plan-usage`];
        if (force) args.push("--force");
        args.push("--providers", ...enabledProviders(preferences(shared(PREFERENCE_KEY))));
        const result = await exec(config.python, args);
        if (result.code !== 0) throw new Error("Usage helper could not run");
        this.data = JSON.parse(result.stdout);
        this.error = null;
      } catch (e) {
        this.error = String(e.message || e);
      } finally {
        this.busy = false;
        cx.notify();
      }
    });
  }

  provider(provider, t, prefs) {
    const now = Date.now() / 1000;
    const age = provider.observed_at ? now - provider.observed_at : null;
    const stale = !!provider.error || age === null || age > 600;
    const head = h_flex().justify_between().items_center()
      .child(div().font_semibold().text_color(t.foreground).child(provider.name))
      .when(prefs.freshness, el => el.child(div().text_size(10).text_color(stale ? t.blocked : t.dim)
        .child(provider.error ? ((provider.windows || []).length ? "stale" : "unavailable") : age === null ? "unavailable" : `${age < 60 ? "just now" : countdown(age) + " ago"}`)));
    const rows = [head];
    if (provider.error) rows.push(div().text_size(10).text_color(t.blocked).child(provider.error));
    for (const row of visibleWindows(provider, prefs)) {
      const expired = row.resets_at != null && row.resets_at <= now;
      const color = expired || stale ? t.dim : row.used >= 95 ? t.blocked : row.used >= 80 ? t.ansi3 : t.accent;
      const reset = row.resets_at == null ? "reset unknown" : expired ? "awaiting new window" : `resets in ${countdown(row.resets_at - now)}`;
      const date = row.resets_at == null ? null : new Date(row.resets_at * 1000);
      // Herdr's JS runtime ignores Intl formatting options, so format this compactly.
      const month = date ? ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][date.getMonth()] : "";
      const exact = date ? `${month} ${date.getDate()}, ${date.getHours() % 12 || 12}:${String(date.getMinutes()).padStart(2, "0")} ${date.getHours() < 12 ? "AM" : "PM"}` : null;
      rows.push(v_flex().gap(3)
        .child(h_flex().justify_between().gap(5)
          .child(div().text_color(t.muted).child(row.label))
          .child(div().text_color(color).child(expired ? "—" : `${Math.round(row.used)}% used${stale ? " · stale" : ""}`)))
        .when(prefs.bars, el => el.child(h_flex().w_full().h(3).rounded(2).bg(t.border)
          .child(div().h(3).w(expired ? 0 : Math.round(row.used / 100 * Math.max(0, (this.width || 268) - 28))).rounded(2).bg(color))))
        .when(prefs.countdowns || (prefs.exactTimes && Boolean(exact)), el => el.child(
          ((this.width || 268) >= 240 ? h_flex().justify_between().gap(8) : v_flex().gap(2))
            .w_full().text_size(10).text_color(t.dim)
            .when(prefs.countdowns, line => line.child(div().flex_shrink_0().child(reset)))
            .when(prefs.exactTimes && Boolean(exact), line => line.child(div().flex_shrink_0().child(exact))))));
    }
    if (!provider.error && !visibleWindows(provider, prefs).length) rows.push(div().text_size(10).text_color(t.dim).child("All limits hidden in Settings"));
    return v_flex().gap(7).children(rows);
  }

  settings(t) {
    const prefs = preferences(shared(PREFERENCE_KEY));
    const catalog = props()?.catalog || [];
    const toggle = (id, label, checked, change, disabled = false) =>
      Checkbox.new(id).checked(checked).disabled(disabled).on_change(change)
        .w_full().px(8).py(7).rounded(5).text_color(disabled ? t.dim : t.foreground)
        .hover(s => s.bg(t.hover))
        .child(h_flex().items_center().gap(10)
          .child(h_flex().w(16).h(16).flex_shrink_0().items_center().justify_center().rounded(3).border_1().border_color(checked ? t.accent : t.border)
            .bg(checked ? t.accent : t.surface).text_color(t.accent_foreground)
            .when(checked, box => box.child(svg("mods/plan-usage/check.svg").size(12))))
          .child(label));
    const sections = PROVIDERS.map(name => {
      const enabled = enabledProviders(prefs).includes(name);
      const provider = catalog.find(p => p.name === name);
      const windows = provider?.windows || [];
      return v_flex().gap(2)
        .child(toggle(`provider-${name}`, name, enabled, value => {
          setShared(PREFERENCE_KEY, toggleProvider(prefs, name, value));
          run("plan-usage.refresh");
        }))
        .child(v_flex().pl(26).children(windows.map(row => toggle(
          `window-${name}-${windowKey(row)}`, row.label,
          !(prefs.hiddenWindows[name] || []).includes(windowKey(row)),
          value => setShared(PREFERENCE_KEY, toggleWindow(prefs, name, windowKey(row), value)), !enabled))));
    });
    return v_flex().id("usage-settings").size_full().p(18).gap(12).bg(t.popover).text_size(13)
      .child(h_flex().justify_between().items_center()
        .child(div().font_semibold().text_color(t.foreground).child("Usage display settings"))
        .child(div().id("usage-settings-done").px(10).py(5).rounded(5).bg(t.raised).text_color(t.foreground)
          .on_click(() => closeOverlay(props().overlay)).child("Done")))
      .child(div().text_size(11).text_color(t.muted).child("Changes save automatically. Hidden providers stop refreshing."))
      .child(v_flex().id("usage-settings-scroll").flex_1().min_h(0).gap(10).overflow_y_scrollbar()
        .child(div().text_color(t.dim).text_size(11).child("PROVIDERS AND LIMITS"))
        .children(sections)
        .child(div().mt(8).text_color(t.dim).text_size(11).child("DETAILS"))
        .children([
          ["bars", "Progress bars"], ["countdowns", "Reset countdowns"],
          ["exactTimes", "Exact reset dates and times"], ["freshness", "Last updated labels"],
          ["autoFit", "Fit panel to content"],
        ].map(([key, label]) => toggle(`detail-${key}`, label, prefs[key],
          value => {
            setShared(PREFERENCE_KEY, { ...prefs, [key]: value });
            if (key === "autoFit" && value) run("plan-usage.fit");
          }))));
  }

  render(cx) {
    const t = theme();
    if (this.isSettings) return this.settings(t);
    const prefs = preferences(shared(PREFERENCE_KEY));
    const displayed = (this.data?.providers || []).filter(p => enabledProviders(prefs).includes(p.name));
    const refresh = div().id("usage-refresh").px(6).py(3).rounded(4)
      .text_color(t.muted).hover(s => s.bg(t.hover))
      .on_click((_e, cx) => this.refresh(cx, true)).child(this.busy ? "Updating…" : "Refresh");
    return v_flex().id("plan-usage").on_size_change((size, cx) => {
      const width = size.width / uiScale();
      const height = size.height / uiScale();
      const widthChanged = this.width !== width;
      if (this.pendingAutoResize && Math.abs(height - this.requestedHeight) < 2) {
        this.pendingAutoResize = false;
      } else if (!this.pendingAutoResize && !widthChanged && this.panelHeight != null && Math.abs(height - this.panelHeight) > 2) {
        const current = preferences(shared(PREFERENCE_KEY));
        if (current.autoFit) setShared(PREFERENCE_KEY, { ...current, autoFit: false });
      }
      this.panelHeight = height;
      if (widthChanged) { this.width = width; cx.notify(); }
    }).size_full().px(14).py(10).gap(10)
      .border_t(1).border_color(t.border).bg(t.chrome).text_size(11)
      .child(h_flex().items_center().justify_between().flex_shrink_0().on_size_change(size => {
        this.headerHeight = size.height / uiScale();
        this.fitPanel();
      })
        .child(div().font_semibold().text_color(t.foreground).child("Plan usage"))
        .child(h_flex().gap(2).items_center()
          .child(div().id("usage-settings-open").px(6).py(3).rounded(4).text_color(t.muted)
            .hover(s => s.bg(t.hover)).on_click(() => this.showSettings()).child("Settings"))
          .child(refresh)))
      .child(v_flex().id("usage-scroll").flex_1().min_h(0).overflow_y_scrollbar()
        .child(v_flex().w_full().flex_shrink_0().gap(14).on_size_change(size => {
          this.contentHeight = size.height / uiScale();
          this.fitPanel();
        })
          .when(!!this.error, el => el.child(div().text_color(t.blocked).child(this.error)))
          .when(!this.data && !this.error, el => el.child(div().text_color(t.dim).child("Reading account limits…")))
          .when(!!this.data && !displayed.length, el => el.child(div().text_color(t.dim).child("No providers selected. Open Settings to choose.")))
          .children(displayed.map(p => this.provider(p, t, prefs)))))
      .child(div().flex_shrink_0().on_size_change(size => {
        this.footerHeight = size.height / uiScale();
        this.fitPanel();
      }).text_size(9).text_color(t.dim).child("Account allowances · checked every 5m"));
  }
}
