// CI-only observer. The shipped view, helper and settings render unchanged.
import PlanUsage from "./production.js";
import { shared, setShared } from "herdr";

export default class ObservedUsage extends PlanUsage {
  render(cx) {
    const result = super.render(cx);
    const report = {
      settings: this.isSettings,
      width: this.width || 0,
      height: this.panelHeight || 0,
      contentHeight: this.contentHeight || 0,
      error: this.error || null,
      busy: !!this.busy,
      data: this.data || null,
    };
    const key = this.isSettings ? "ci.settings" : "ci.panel";
    if (JSON.stringify(shared(key)) !== JSON.stringify(report)) setShared(key, report);
    return result;
  }
}
