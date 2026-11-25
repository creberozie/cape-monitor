// Small shared helpers: downloads (CSV and JSON exports), the watchlist kept in this browser, and chart pieces.
import { esc, fmt } from "./i18n";
import { exportLimit, can, FREE_EXPORT_ROWS, proNote } from "./auth/entitlements";

const csvCell = (v: any) => { if (v == null) return ""; const s = Array.isArray(v) ? v.join("; ") : typeof v === "object" ? JSON.stringify(v) : String(v); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
export function download(name: string, text: string, type = "text/csv") {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: type + ";charset=utf-8" })); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
/** CSV with a first comment line naming the source, so an exported file carries its provenance */
export function exportCSV(name: string, header: string[], rows: any[][], source = "") {
  const lines = [...(source ? [`# ${source.replace(/\n/g, " ")}`] : []), header.map(csvCell).join(","), ...rows.map((r) => r.map(csvCell).join(","))];
  download(name.replace(/[^\w.-]+/g, "_") + ".csv", "﻿" + lines.join("\r\n"));
}
/** a table export: on the free tier the first FREE_EXPORT_ROWS rows, with a note saying so in the file and on screen */
export function exportTable(name: string, header: string[], rows: any[][], source = "") {
  const n = exportLimit(rows.length);
  const cut = n < rows.length;
  exportCSV(name, header, rows.slice(0, n), source + (cut ? ` First ${FREE_EXPORT_ROWS} of ${rows.length} rows (free tier); every row is visible in the app.` : ""));
  if (cut) toast(proNote("bulkExport") + ` This file has the first ${FREE_EXPORT_ROWS} of ${fmt(rows.length)} rows.`);
}
export function toast(msg: string) {
  const t = document.getElementById("toast"); if (!t) return;
  t.textContent = msg; t.hidden = false; clearTimeout((t as any)._tm); (t as any)._tm = setTimeout(() => (t.hidden = true), 6000);
}
export { can };
export const exportJSON = (name: string, obj: any) => download(name.replace(/[^\w.-]+/g, "_") + ".json", JSON.stringify(obj, null, 1), "application/json");

// ---------------------------------------------------------------- watchlist (this browser only)
export interface Watch { kind: "supplier" | "plot" | "tender" | "department" | "flag" | "record"; id: string; label: string; district?: string; n: number; seen: number; added: string }
const KEY = "cm-watch";
export const watches = (): Watch[] => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
const save = (w: Watch[]) => localStorage.setItem(KEY, JSON.stringify(w));
export const isWatched = (kind: string, id: string) => watches().some((w) => w.kind === kind && w.id === id);
export function toggleWatch(w: Omit<Watch, "seen" | "added">) {
  const all = watches(); const k = all.findIndex((x) => x.kind === w.kind && x.id === w.id);
  if (k >= 0) all.splice(k, 1); else all.push({ ...w, seen: w.n, added: new Date().toISOString().slice(0, 10) });
  save(all); return k < 0;
}
/** record what the user has now seen for a watched item */
export function markSeen(kind: string, id: string, n: number) { const all = watches(); const w = all.find((x) => x.kind === kind && x.id === id); if (w) { w.n = n; w.seen = n; save(all); } }
export function updateCount(kind: string, id: string, n: number) { const all = watches(); const w = all.find((x) => x.kind === kind && x.id === id); if (w && w.n !== n) { w.n = n; save(all); } }
export const watchButton = (kind: string, id: string, label: string, n: number, district = "") =>
  `<button class="mini" data-watch="${esc(JSON.stringify({ kind, id, label, n, district }))}">${isWatched(kind, id) ? "★ Watching" : "☆ Watch"}</button>`;
export function bindWatch(root: HTMLElement) {
  root.addEventListener("click", (e) => { const b = (e.target as HTMLElement).closest("[data-watch]") as HTMLElement | null; if (!b) return;
    const on = toggleWatch(JSON.parse(b.dataset.watch!)); b.textContent = on ? "★ Watching" : "☆ Watch"; });
}

// ---------------------------------------------------------------- charts
export const bars = (rows: [string, number][], max = 12, f: (n: number) => string = fmt, click = "") => { const top = rows.slice(0, max); const m = Math.max(1, ...top.map((r) => r[1]));
  return top.map(([l, v]) => `<div class="bar" ${click ? `data-${click}="${esc(l)}" style="cursor:pointer"` : ""}><span class="lab" title="${esc(l)}">${esc(l)}</span><span class="track"><span class="fill" style="width:${(v / m * 100).toFixed(1)}%"></span></span><span class="v">${f(v)}</span></div>`).join(""); };
export const columns = (rows: [string, number][], f: (n: number) => string = fmt) => { if (!rows.length) return ""; const m = Math.max(1, ...rows.map((r) => r[1])); const W = 300, H = 70, bw = W / rows.length;
  return `<svg class="chart" viewBox="0 0 ${W} ${H + 12}" role="img" aria-label="chart">${rows.map(([l, v], k) => `<rect x="${(k * bw + 1).toFixed(1)}" y="${(H - v / m * (H - 2)).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${(v / m * (H - 2)).toFixed(1)}" class="col"><title>${esc(l)}: ${esc(f(v))}</title></rect>`).join("")}
    <text x="0" y="${H + 11}" class="ax">${esc(rows[0][0])}</text><text x="${W}" y="${H + 11}" class="ax" text-anchor="end">${esc(rows[rows.length - 1][0])}</text></svg>`; };
export const short = (n: number) => n >= 1e9 ? `R${(n / 1e9).toFixed(1)}bn` : n >= 1e6 ? `R${(n / 1e6).toFixed(1)}m` : n >= 1e3 ? `R${(n / 1e3).toFixed(0)}k` : `R${Math.round(n)}`;
