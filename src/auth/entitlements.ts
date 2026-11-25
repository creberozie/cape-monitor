// Entitlements: which tier this browser is on, and which features each tier gets.
//
// Every published record stays free to view, search and open, including director and address data. Pro adds convenience only:
// exports of more than FREE_EXPORT_ROWS rows, watchlist alert rules, and the weekly human brief.
//
// Today the tier is always "free" unless a tester adds ?preview_tier=pro to the address (kept for this browser tab only;
// ?preview_tier=free ends it). To wire real accounts later, call setSession() from the login provider (Clerk or Supabase)
// after the server has verified the PayFast subscription (ITN webhook); nothing in the UI needs to change.
export type Tier = "free" | "pro";
export type Feature = "bulkExport" | "alertRules" | "weeklyBrief";
export interface Entitlements { tier: Tier; source: "default" | "preview" | "session"; expires?: string }

const NEEDS: Record<Feature, Tier> = { bulkExport: "pro", alertRules: "pro", weeklyBrief: "pro" };
export const FREE_EXPORT_ROWS = 500;
export const FEATURE_LABEL: Record<Feature, string> = { bulkExport: "Export of every row", alertRules: "Watchlist alert rules", weeklyBrief: "Weekly brief" };
const KEY = "cm-preview-tier";
const listeners = new Set<(e: Entitlements) => void>();

function resolve(): Entitlements {
  try {
    const q = new URLSearchParams(location.search).get("preview_tier");
    if (q === "pro") sessionStorage.setItem(KEY, "pro");
    if (q === "free") sessionStorage.removeItem(KEY);
    if (sessionStorage.getItem(KEY) === "pro") return { tier: "pro", source: "preview" };
  } catch { /* storage blocked: stay free */ }
  return { tier: "free", source: "default" };
}
let current: Entitlements = resolve();

export const entitlements = () => current;
export const tier = () => current.tier;
export const can = (f: Feature) => NEEDS[f] === "free" || current.tier === "pro";
/** for the future login provider: set the tier the server verified (never trust a client-side claim for payment) */
export function setSession(e: Entitlements) { current = e; listeners.forEach((l) => l(current)); }
export function onChange(l: (e: Entitlements) => void) { listeners.add(l); return () => listeners.delete(l); }
/** rows a CSV export may carry on this tier */
export const exportLimit = (n: number) => can("bulkExport") ? n : Math.min(n, FREE_EXPORT_ROWS);
export const proNote = (f: Feature) => `${FEATURE_LABEL[f]} is part of Cape Monitor Pro. Every record stays free to view and open.`;
