// Money and tenders: who decided, who paid, who was paid. Every row is shown as published, with its source and a link.
// Profiles (supplier, tender, department, flag) open in the right-hand panel; lists and tables in the bottom panel.
import { getJSON, METRO } from "./data";
import { track } from "./access/activity";
import { esc, fmt, money as rand } from "./i18n";
import { exportCSV, exportTable, exportJSON, watchButton, markSeen, updateCount, bars, columns, short } from "./util";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
let MP = METRO + "money/";
let ROOTP = METRO;
/** wording and columns that differ per municipality; the defaults are Cape Monitor's (City of Cape Town) */
export const L = {
  scope: "published City and eTender records", awards: "City award decisions", bids: "Bids at City tender openings", et: "eTender portal (Western Cape buyers)",
  rfq: "City quotation orders", land: "City land bought", tender: "City tender", notender: "No City record with this reference in this build.",
  factAwards: "award decisions", refCols: ["ref", "number"],
  supHeads: [[1, "Supplier"], [2, "Award decisions"], [3, "Fixed value of decisions"], [12, "Rates-based budgets"], [4, "Quotation orders"], [5, "Quotation value"], [6, "Bids"], [7, "eTenders"], [8, "Land bought"], [11, "Flags"]] as [number, string][], factRfq: "quotation orders", bidsRead: "bids read out",
  awardCols: ["date", "ref", "decision", "reason", "code", "desc", "value_text", "budget_text", "sup"], bidCols: ["closing", "ref", "desc", "price_text", "rank", "n_bids", "doc"],
  rfqCols: ["date", "tracking", "directorate", "group", "value", "bbbee", "dq"], tenderAwardCols: ["date", "decision", "reason", "code", "vendor", "value_text", "budget_text", "sup"],
  tenderBidCols: ["n", "bidder", "price_text", "rank", "hdi", "closing", "doc"],
  flagCols: { rfq: ["date", "tracking", "directorate", "group", "supplier", "value"], awards: ["date", "ref", "decision", "reason", "code", "vendor", "value_text", "budget_text"],
    bids: ["closing", "ref", "bidder", "price_text", "rank", "n_bids", "doc"], etenders: ["published", "number", "buyer", "desc", "awards", "official"] } as Record<string, string[]>,
  /** the municipality's own reference in an eTender record, to open its tender dossier; null when it has none */
  tenderRef: (e: any): string | null => { const m = String(e.tender_No || "").replace(/\s/g, "").toUpperCase().match(/\d{1,3}[A-Z]\/20\d\d\/\d\d/); return m && /cape town/i.test(e.organ_of_State || "") ? m[0] : null; },
  /** the dossier key of a reference, as build_money.py writes it */
  refKey: (ref: string) => ref.replace(/\s/g, "").toUpperCase().replace(/^0+/, ""),
};
/** point the money views at another municipality's data folder (e.g. "../data/muni/stellenbosch/") and wording */
export function configureMoney(root: string, labels: Partial<typeof L> = {}) { ROOTP = root; MP = root + "money/"; meta = null; view = null; Object.assign(L, labels); }
type TableMeta = { id: string; name: string; fields: [string, string][]; n: number; shards: number; source: string; url: string; retrieved: string; note?: string };
export interface MoneyMeta { built: string; tables: Record<string, TableMeta>; counts: Record<string, number>; buckets: number; shard: number; et_shard: number; registers: Record<string, string> }
export interface Flag { id: string; kind: string; title: string; text: string; records: [string, number][]; subjects: [string, string][]; value?: number; basis?: { text: string; url: string };
  verification_status?: string; review_reason?: string; scan?: string; scan_lowest?: string; method?: string }
let meta: MoneyMeta | null = null;
export const moneyMeta = async () => meta ??= await getJSON<MoneyMeta>(MP + "money.json");
const fi = (t: TableMeta, k: string) => t.fields.findIndex((f) => f[0] === k);

/** FNV-1a 32-bit, as in pipeline/metro/build_money.py */
export const bucket = (key: string, n: number) => { let h = 0x811c9dc5; for (const b of new TextEncoder().encode(key)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; } return h % n; };
export async function row(tid: string, i: number): Promise<any[] | null> {
  const m = await moneyMeta(); const rows = await getJSON<any[][]>(`${MP}t/${tid}-${Math.floor(i / m.shard)}.json`); return rows[i % m.shard] ?? null;
}
export async function allRows(tid: string): Promise<any[][]> {
  const m = await moneyMeta(); const t = m.tables[tid]; if (!t) return [];
  return (await Promise.all(Array.from({ length: t.shards }, (_, k) => getJSON<any[][]>(`${MP}t/${tid}-${k}.json`)))).flat();
}
type SupIndex = { fields: string[]; rows: any[][] };
export const suppliers = () => getJSON<SupIndex>(MP + "suppliers.json");
export const flagsData = () => getJSON<{ kinds: Record<string, string>; note: string; thresholds: any[]; flags: Flag[] }>(MP + "flags.json");
export const supName = async (id: string) => (await suppliers()).rows.find((r) => r[0] === id)?.[1] ?? id;
export const supNames = async () => { const S = await suppliers(); return new Map(S.rows.map((r) => [r[0] as string, r[1] as string])); };

/** Some published records name private individuals (land buyers, sole proprietors, contact people). They stay in, as published;
 * the owner decides on any redaction. Entries marked as possible private individuals can be hidden in this browser. */
export const PERSONAL_NOTE = "Some records name private individuals and their contact details (City land buyers, sole proprietors, contact people on awards), exactly as the state published them. Profiles that look like a private individual are marked; you can hide them.";
export const hidePersons = () => { try { return localStorage.getItem("cm-hide-persons") === "1"; } catch { return false; } };
export const IDENTITY_NOTE = "A supplier is identified only by its published name, normalised for case, punctuation and suffixes such as (Pty) Ltd or CC. No fuzzy matching: two spellings of one company appear as two profiles, and two companies with the same name would share one. Check the CIPC register before relying on identity.";

// ---------------------------------------------------------------- generic table renderer (filter, sort, group, export)
interface View { tid: string; rows: any[][]; q: string; sort: number; dir: number; group: number; year: string }
let view: View | null = null;
const hidden = new Set(["sup", "bidders", "oid", "portal_id"]);
const linkCols: Record<string, string> = { doc: "Register", url: "Document" };

function cell(t: TableMeta, k: number, v: any, names: Map<string, string>) {
  const key = t.fields[k][0];
  if (v == null || v === "") return "";
  if (key === "sup" || key === "bidders") return (Array.isArray(v) ? v : [v]).map((s: string) => `<a href="#s=${esc(s)}" data-sup="${esc(s)}">${esc(names.get(s) || s)}</a>`).join(", ");
  if (linkCols[key]) return `<a href="${esc(v)}" target="_blank" rel="noopener">${linkCols[key]} ↗</a>`;
  if (L.refCols.includes(key)) return `<a href="#t=${esc(String(v).replace(/\s/g, ""))}" data-tender="${esc(v)}">${esc(v)}</a>`;
  if (typeof v === "number" && /value|price|total|budget/.test(key)) return `<span class="mono">${rand(v)}</span>`;
  if (key === "dq") return `<span class="warn" title="${esc(v)}">⚠ suspect value</span>`;
  return esc(v);
}

export async function tableView(tid: string, host: HTMLElement, opts: { filter?: (r: any[]) => boolean; title?: string } = {}) {
  const m = await moneyMeta(); const t = m.tables[tid]; if (!t) { host.innerHTML = `<div class="empty">Not in this build.</div>`; return; }
  if (!view || view.tid !== tid) { host.innerHTML = `<div class="empty">Loading ${fmt(t.n)} records…</div>`; view = { tid, rows: await allRows(tid), q: "", sort: -1, dir: 1, group: -1, year: "" }; }
  const names = await supNames(); const v = view;
  const dateCol = t.fields.findIndex((f) => /^(date|closing|published|approved|month)$/.test(f[0]));
  let rows = opts.filter ? v.rows.filter(opts.filter) : v.rows;
  const years = dateCol >= 0 ? [...new Set(rows.map((r) => String(r[dateCol] ?? "").slice(0, 4)).filter((y) => /^\d{4}$/.test(y)))].sort() : [];
  if (v.year) rows = rows.filter((r) => String(r[dateCol] ?? "").startsWith(v.year));
  const q = v.q.toLowerCase().trim();
  if (q) rows = rows.filter((r) => r.some((x, k) => x != null && (t.fields[k][0] === "sup" ? (Array.isArray(x) ? x : [x]).some((s: string) => (names.get(s) || "").toLowerCase().includes(q)) : String(x).toLowerCase().includes(q))));
  if (v.sort >= 0) rows = [...rows].sort((a, b) => { const x = a[v.sort], y = b[v.sort]; return (typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""))) * v.dir; });
  const numCol = t.fields.findIndex((f) => /^(value|price|total|budget)$/.test(f[0]));
  let groupHtml = "";
  if (v.group >= 0) {
    const g = new Map<string, [number, number]>();
    for (const r of rows) { const keys = t.fields[v.group][0] === "sup" ? (r[v.group] || []).map((s: string) => names.get(s) || s) : [String(r[v.group] ?? "—")];
      for (const k of keys) { const e = g.get(k) || [0, 0]; e[0]++; if (numCol >= 0 && !r[fi(t, "dq")]) e[1] += Number(r[numCol]) || 0; g.set(k, e); } }
    const top = [...g].sort((a, b) => numCol >= 0 ? b[1][1] - a[1][1] : b[1][0] - a[1][0]).slice(0, 40);
    groupHtml = `<div class="tile"><div class="caps">By ${esc(t.fields[v.group][1])}${numCol >= 0 ? " · total " + esc(t.fields[numCol][1]) : " · records"}</div>${bars(top.map(([k, x]) => [k, numCol >= 0 ? x[1] : x[0]] as [string, number]), 40, numCol >= 0 ? short : fmt)}</div>`;
  }
  const cols = t.fields.map((f, k) => k).filter((k) => !hidden.has(t.fields[k][0]) || t.fields[k][0] === "sup");
  const show = rows.slice(0, 400);
  host.innerHTML = `<div class="toolbar">${opts.title ? `<b>${esc(opts.title)}</b>` : ""}<input class="tv-q" placeholder="Filter rows…" value="${esc(v.q)}" aria-label="Filter rows">
      ${years.length ? `<select class="tv-y" aria-label="Year"><option value="">All years</option>${years.map((y) => `<option ${y === v.year ? "selected" : ""}>${y}</option>`).join("")}</select>` : ""}
      <select class="tv-g" aria-label="Group by"><option value="-1">Group by…</option>${t.fields.map((f, k) => cols.includes(k) ? `<option value="${k}" ${k === v.group ? "selected" : ""}>${esc(f[1])}</option>` : "").join("")}</select>
      <button class="tb tv-x">Export CSV</button>
      <span class="note">${fmt(rows.length)} of ${fmt(t.n)} rows${rows.length > 400 ? " (first 400 shown; export has all)" : ""} · <a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.source)}</a> · fetched ${esc(t.retrieved.slice(0, 10))}</span></div>
    ${t.note ? `<div class="note">${esc(t.note)}</div>` : ""}${groupHtml}
    <div class="tscroll"><table class="t"><thead><tr>${cols.map((k) => `<th data-sort="${k}" title="${esc(t.fields[k][0])}">${esc(t.fields[k][1])}${v.sort === k ? (v.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
    <tbody>${show.map((r) => `<tr${r[fi(t, "dq")] ? ' class="dq"' : ""}>${cols.map((k) => `<td>${cell(t, k, r[k], names)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const rerender = () => tableView(tid, host, opts);
  let tm: any; (host.querySelector(".tv-q") as HTMLInputElement).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { v.q = (e.target as HTMLInputElement).value; rerender().then(() => { const el = host.querySelector(".tv-q") as HTMLInputElement; el.focus(); el.setSelectionRange(el.value.length, el.value.length); }); }, 250); };
  (host.querySelector(".tv-g") as HTMLSelectElement).onchange = (e) => { v.group = +(e.target as HTMLSelectElement).value; rerender(); };
  const ys = host.querySelector(".tv-y") as HTMLSelectElement | null; if (ys) ys.onchange = () => { v.year = ys.value; rerender(); };
  (host.querySelector(".tv-x") as HTMLElement).onclick = () => exportTable(`${t.id}${v.year ? "-" + v.year : ""}${v.q ? "-filtered" : ""}`, t.fields.map((f) => f[1]),
    rows.map((r) => r.map((x, k) => t.fields[k][0] === "sup" || t.fields[k][0] === "bidders" ? (Array.isArray(x) ? x : x ? [x] : []).map((s: string) => names.get(s) || s).join("; ") : x)),
    `${t.name}. Source: ${t.source} ${t.url}, fetched ${t.retrieved}. Exported from Cape Monitor ${new Date().toISOString().slice(0, 10)}.`);
  host.querySelectorAll("th[data-sort]").forEach((th) => (th as HTMLElement).onclick = () => { const k = +(th as HTMLElement).dataset.sort!; v.dir = v.sort === k ? -v.dir : -1; v.sort = k; rerender(); });
}

// ---------------------------------------------------------------- bottom-panel Money tab
let sub = "overview";
const SUBS: [string, string][] = [["overview", "Overview"], ["suppliers", "Suppliers"], ["flags", "Pattern flags"], ["awards", "Award decisions"], ["bids", "Bids received"],
  ["rfq", "Quotations"], ["etenders", "eTenders (WC)"], ["departments", "Departments"], ["land", "City land sales"], ["docs", "Documents"]];
export async function moneyTab(host: HTMLElement, k?: string) {
  if (k) sub = k;
  host.innerHTML = `<nav class="subnav">${SUBS.map(([id, l]) => `<button data-sub="${id}" class="${id === sub ? "on" : ""}">${l}</button>`).join("")}<label class="sm mu personal" style="margin-left:auto" title="${esc(PERSONAL_NOTE)}"><input type="checkbox" class="hidep" ${hidePersons() ? "checked" : ""}> Hide private individuals</label></nav><div id="msub"></div>`;
  host.querySelectorAll("[data-sub]").forEach((b) => (b as HTMLElement).onclick = () => moneyTab(host, (b as HTMLElement).dataset.sub));
  (host.querySelector(".hidep") as HTMLInputElement).onchange = (e) => { try { localStorage.setItem("cm-hide-persons", (e.target as HTMLInputElement).checked ? "1" : "0"); } catch { /* blocked */ } moneyTab(host); };
  const el = host.querySelector("#msub") as HTMLElement;
  try {
    if (sub === "overview") await overview(el);
    else if (sub === "suppliers") await supplierList(el);
    else if (sub === "flags") await flagList(el);
    else if (sub === "departments") await deptList(el);
    else await tableView(sub, el);
  } catch (e) { el.innerHTML = `<div class="empty">Money data is not in this build yet (${esc(e)}).</div>`; }
}

async function overview(el: HTMLElement) {
  const m = await moneyMeta(); const F = await flagsData();
  const [rfq, aw, et] = await Promise.all([allRows("rfq"), allRows("awards"), allRows("etenders").catch(() => [])]);
  const byYear = new Map<string, number>(); for (const r of rfq) if (!r[10]) byYear.set(String(r[0]).slice(0, 4), (byYear.get(String(r[0]).slice(0, 4)) || 0) + (Number(r[7]) || 0));
  const dec = new Map<string, number>(); for (const r of aw) dec.set(String(r[3] || "—"), (dec.get(String(r[3] || "—")) || 0) + 1);
  const kinds = new Map<string, number>(); for (const f of F.flags) kinds.set(f.kind, (kinds.get(f.kind) || 0) + 1);
  const T = m.tables.etenders; const open = T ? et.filter((r) => r[fi(T, "status")] === "Open").sort((a, b) => String(a[fi(T, "closing")]).localeCompare(String(b[fi(T, "closing")]))) : [];
  const kpi = (v: any, l: string) => `<div class="kpi"><b>${v}</b><span>${esc(l)}</span></div>`;
  el.innerHTML = `<div class="kpis">${kpi(fmt(m.counts.suppliers), "supplier profiles")}${kpi(fmt(m.counts.awards || 0), "City award decisions")}${kpi(fmt(m.counts.bids || 0), "bids read out at openings")}
      ${kpi(fmt(m.counts.rfq || 0), "City quotation orders")}${kpi(fmt(m.counts.etenders || 0), "Western Cape eTenders")}${kpi(fmt(m.counts.flags), "pattern flags")}</div>
    <div class="grid"><div class="tile"><div class="caps">City quotation orders: value per year</div>${columns([...byYear].filter(([y]) => /^\d{4}$/.test(y)).sort(), short)}</div>
      <div class="tile"><div class="caps">Award decisions by reason</div>${bars([...dec].sort((a, b) => b[1] - a[1]), 10)}</div>
      <div class="tile"><div class="caps">Pattern flags (click to list)</div>${bars([...kinds].map(([k, n]) => [F.kinds[k] || k, n] as [string, number]), 12, fmt, "flagkind")}
        <div class="note">${esc(F.note)}</div></div>
      <div class="tile"><div class="caps">Open Western Cape tenders closing soonest</div>${open.slice(0, 8).map((r) => `<div class="row" data-etd="${r[fi(T!, "portal_id")]}"><span class="t">${esc(r[fi(T!, "desc")])}</span><small>${esc(r[fi(T!, "buyer")])} · closes ${esc(r[fi(T!, "closing")])}</small></div>`).join("") || `<div class="empty">No open tenders in this build.</div>`}</div></div>`;
  el.querySelectorAll("[data-flagkind]").forEach((b) => (b as HTMLElement).onclick = () => { const k = Object.entries(F.kinds).find(([, v]) => v === (b as HTMLElement).dataset.flagkind)?.[0]; flagFilter = k || ""; sub = "flags"; moneyTab(el.parentElement!); });
}

let supQ = "", supSort = 3;
export async function supplierList(el: HTMLElement) {
  const S = await suppliers(); const q = supQ.toLowerCase();
  let rows = q ? S.rows.filter((r) => String(r[1]).toLowerCase().includes(q) || String(r[0]).includes(q.replace(/\s+/g, "-"))) : S.rows;
  if (hidePersons()) rows = rows.filter((r) => !r[13]);
  rows = [...rows].sort((a, b) => supSort === 3 ? (b[3] + b[5]) - (a[3] + a[5]) : (Number(b[supSort]) || 0) - (Number(a[supSort]) || 0));
  const H = L.supHeads;
  el.innerHTML = `<div class="toolbar"><input class="sq" placeholder="Find a supplier…" value="${esc(supQ)}" aria-label="Find a supplier"><button class="tb sx">Export CSV</button>
    <span class="note">${fmt(rows.length)} of ${fmt(S.rows.length)} suppliers named in ${esc(L.scope)}.</span></div><div class="note">${esc(IDENTITY_NOTE)}</div>
    <div class="tscroll"><table class="t"><thead><tr>${H.map(([k, l]) => `<th data-ss="${k}">${l}${supSort === k ? " ▼" : ""}</th>`).join("")}<th>Years</th></tr></thead><tbody>
    ${rows.slice(0, 300).map((r) => `<tr class="click" data-sup="${esc(r[0])}">${H.map(([k]) => k === 1 ? `<td>${esc(r[1])}${r[13] ? ' <span class="pill person" title="Possibly a private individual">person?</span>' : ""}</td>`
      : k === 3 || k === 5 ? `<td class="mono">${r[k] ? short(r[k]) : ""}</td>` : k === 12 ? `<td class="mono dim">${r[12] ? short(r[12]) : ""}</td>`
      : k === 11 ? `<td class="mono">${r[11] ? `<span class="flagc">${r[11]}</span>` : ""}</td>` : k === 8 ? `<td class="mono">${r[8] || ""}</td>`
      : k === 14 ? `<td>${r[14] ? "yes" : ""}</td>` : `<td class="mono">${fmt(r[k])}</td>`).join("")}<td class="mono dim">${esc(r[9] || "")}${r[10] && r[10] !== r[9] ? "–" + esc(r[10]) : ""}</td></tr>`).join("")}</tbody></table></div>`;
  let tm: any; (el.querySelector(".sq") as HTMLInputElement).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { supQ = (e.target as HTMLInputElement).value; supplierList(el).then(() => { const i = el.querySelector(".sq") as HTMLInputElement; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 200); };
  el.querySelectorAll("[data-ss]").forEach((th) => (th as HTMLElement).onclick = () => { supSort = +(th as HTMLElement).dataset.ss!; supplierList(el); });
  (el.querySelector(".sx") as HTMLElement).onclick = () => exportTable("suppliers", S.fields, rows, "Cape Monitor supplier index built from City of Cape Town Open Data Portal, City bid registers and the eTender portal");
}

let flagFilter = "";
export async function flagList(el: HTMLElement) {
  const F = await flagsData(); const names = await supNames();
  const list = F.flags.filter((f) => !flagFilter || f.kind === flagFilter);
  el.innerHTML = `<div class="toolbar"><select class="fk" aria-label="Kind of pattern"><option value="">All patterns (${fmt(F.flags.length)})</option>${Object.entries(F.kinds).map(([k, l]) => `<option value="${k}" ${k === flagFilter ? "selected" : ""}>${esc(l)} (${F.flags.filter((f) => f.kind === k).length})</option>`).join("")}</select>
    <button class="tb fx">Export CSV</button></div><div class="note warnbox">${esc(F.note)} Thresholds used: ${F.thresholds.map((t: any) => `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.text)}</a>`).join("; ")}.</div>
    ${list.slice(0, 300).map((f) => `<div class="feeditem click" data-flag="${esc(f.id)}"><b>${esc(f.title)}</b> ${flagBadges(f)}<div class="meta">${esc(F.kinds[f.kind])} · ${f.records.length} record${f.records.length === 1 ? "" : "s"}${f.value ? " · " + short(f.value) : ""} · ${f.subjects.filter((s) => s[0] === "supplier").map((s) => esc(names.get(s[1]) || s[1])).join(", ")}</div><div class="sm mu">${esc(f.text)}</div></div>`).join("")}
    ${list.length > 300 ? `<div class="note">First 300 of ${fmt(list.length)} shown; export has all.</div>` : ""}`;
  (el.querySelector(".fk") as HTMLSelectElement).onchange = (e) => { flagFilter = (e.target as HTMLSelectElement).value; flagList(el); };
  (el.querySelector(".fx") as HTMLElement).onclick = () => exportTable("pattern-flags", ["id", "kind", "title", "text", "value", "suppliers", "records"],
    list.map((f) => [f.id, F.kinds[f.kind], f.title, f.text, f.value ?? "", f.subjects.filter((s) => s[0] === "supplier").map((s) => names.get(s[1]) || s[1]), f.records.map((r) => r.join(":"))]), F.note);
}

export async function deptList(el: HTMLElement) {
  const D = await getJSON<any[]>(MP + "departments.json"); const names = await supNames();
  el.innerHTML = `<div class="note">City directorates (from quotation orders) and every Western Cape organ of state on the eTender portal. Click one for its profile.</div>
    <div class="tscroll"><table class="t"><thead><tr><th>Department or organ of state</th><th>Records</th><th>Quotation value</th><th>Largest supplier</th></tr></thead><tbody>
    ${D.map((d, k) => `<tr class="click" data-dept="${k}"><td>${esc(d.name)}</td><td class="mono">${fmt(d.n)}</td><td class="mono">${d.value ? short(d.value) : ""}</td><td>${esc(names.get(d.top[0]?.[0]) || "")}</td></tr>`).join("")}</tbody></table></div>`;
}

// ---------------------------------------------------------------- right-panel profiles
const R = () => $("#right");
function open(html: string, hash: string) { const r = R(); r.innerHTML = html; r.scrollTop = 0; document.body.classList.add("inspect"); history.replaceState(null, "", location.pathname + location.search + "#" + hash); }
const loading = (what: string) => { R().innerHTML = `<div class="card"><div class="empty">Loading ${esc(what)}…</div></div>`; document.body.classList.add("inspect"); };
const src = (t?: TableMeta) => t ? `<div class="note">Source: <a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.source)}</a>, fetched ${esc(t.retrieved.slice(0, 10))}.</div>` : "";

async function rowsTable(tid: string, idx: number[], cols: string[], limit = 60) {
  const m = await moneyMeta(); const t = m.tables[tid]; if (!t || !idx.length) return "";
  const names = await supNames(); const rows = await Promise.all(idx.map((i) => row(tid, i)));
  const ks = cols.map((c) => fi(t, c)).filter((k) => k >= 0);
  const sorted = rows.filter(Boolean).sort((a, b) => String(b![ks[0]] ?? "").localeCompare(String(a![ks[0]] ?? "")));
  return `<div class="tscroll"><table class="t"><thead><tr>${ks.map((k) => `<th>${esc(t.fields[k][1])}</th>`).join("")}</tr></thead><tbody>
    ${sorted.slice(0, limit).map((r) => `<tr${r![fi(t, "dq")] ? ' class="dq"' : ""}>${ks.map((k) => `<td>${cell(t, k, r![k], names)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    ${sorted.length > limit ? `<div class="note">${limit} most recent of ${fmt(sorted.length)} shown; export has all.</div>` : ""}
    <button class="mini" data-exp="${esc(JSON.stringify({ tid, idx }))}">Export these ${fmt(sorted.length)} rows (CSV)</button>${src(t)}`;
}
export async function exportRows(tid: string, idx: number[], name: string) {
  const m = await moneyMeta(); const t = m.tables[tid]; const names = await supNames(); const rows = (await Promise.all(idx.map((i) => row(tid, i)))).filter(Boolean) as any[][];
  exportCSV(name, t.fields.map((f) => f[1]), rows.map((r) => r.map((x, k) => t.fields[k][0] === "sup" || t.fields[k][0] === "bidders" ? (Array.isArray(x) ? x : x ? [x] : []).map((s: string) => names.get(s) || s).join("; ") : x)),
    `${t.name}. Source: ${t.source} ${t.url}, fetched ${t.retrieved}.`);
}

export async function openSupplier(id: string) {
  track("supplier", { id }); loading("supplier"); const m = await moneyMeta();
  const P = (await getJSON<Record<string, any>>(`${MP}sup/${bucket(id, m.buckets)}.json`))[id];
  const S = await suppliers(); const ix = S.rows.find((r) => r[0] === id);
  if (!P || !ix) { R().innerHTML = `<div class="card"><div class="empty">No supplier profile "${esc(id)}" in this build.</div></div>`; return; }
  const F = await flagsData(); const flags = F.flags.filter((f) => P.flags.includes(f.id));
  const J = await getJSON<any>(ROOTP + "justice.json").catch(() => null);
  const REG = await getJSON<any>(ROOTP + "registry.json").catch(() => null); const reg = REG?.records?.[id];
  const cases = (J?.items || []).filter((c: any) => c.suppliers?.includes(id));
  const name = ix[1]; const n = Object.values(P.refs as Record<string, number[]>).reduce((s, v) => s + v.length, 0);
  updateCount("supplier", id, n); markSeen("supplier", id, n);
  // co-named in the same award decisions (joint ventures, panels)
  const co = new Map<string, number>();
  for (const i of P.refs.awards || []) { const r = await row("awards", i); for (const s of (r?.[12] || []) as string[]) if (s !== id) co.set(s, (co.get(s) || 0) + 1); }
  const names = await supNames();
  const phones: string[] = P.phones || [];
  const sharePhone = phones.length ? S.rows.length && F.flags.filter((f) => f.kind === "phone" && f.subjects.some((s) => s[1] === id)).flatMap((f) => f.subjects.map((s) => s[1])).filter((s) => s !== id) : [];
  const q = encodeURIComponent(`"${name.replace(/\s*\((pty|ply)\)\s*ltd\.?/i, "").trim()}"`);
  const yearsRow = ix[9] ? `${ix[9]}${ix[10] !== ix[9] ? "–" + ix[10] : ""}` : "—";
  open(`<div class="card primary"><div class="kicker">Supplier profile${ix[13] ? " · possibly a private individual" : ""}</div><h2>${esc(name)}</h2>
      ${ix[13] ? `<div class="note warnbox">This profile looks like a private individual. The records are shown exactly as the state published them.</div>` : ""}
      ${P.names.length > 1 ? `<div class="sm mu">Published as: ${P.names.map(([n, c]: [string, number]) => `${esc(n)} <span class="dim">(${c})</span>`).join("; ")}</div>` : ""}
      <div class="facts"><div class="fact"><b>${fmt(ix[2])}</b><span>${esc(L.factAwards)}</span></div><div class="fact"><b>${ix[3] ? short(ix[3]) : "—"}</b><span>fixed values of decisions naming it</span></div><div class="fact"><b>${ix[12] ? short(ix[12]) : "—"}</b><span>rates-based budgets (estimates)</span></div><div class="fact"><b>${fmt(ix[4])}</b><span>${esc(L.factRfq)}</span></div>
        <div class="fact"><b>${ix[5] ? short(ix[5]) : "—"}</b><span>quotation value</span></div><div class="fact"><b>${fmt(ix[6])}</b><span>bids</span></div><div class="fact"><b>${esc(yearsRow)}</b><span>years active in records</span></div></div>
      ${phones.length || P.contacts?.length ? `<div class="sm">Contact details published on eTender awards: ${P.contacts.map(esc).join(", ")}${phones.length ? ` · numbers ending ${phones.map((p) => esc(p.slice(-4))).join(", ")}` : ""}</div>` : ""}
      <div class="links">${watchButton("supplier", id, name, n)}<button class="mini" data-share="s=${esc(id)}">Share link</button><button class="mini" data-expjson="1">Export profile (JSON)</button>${dossierButtons}</div>
      <div class="links sm"><span class="dim">Look up:</span><a href="https://www.saflii.org/cgi-bin/sinosrch-adw.cgi?query=${q}&method=boolean&meta=%2Fsaflii" target="_blank" rel="noopener">SAFLII judgments ↗</a>
        <a href="https://www.saflii.org/cgi-bin/sinosrch-adw.cgi?query=${q}&method=boolean&meta=%2Fsaflii&mask_path=za%2Fcases%2FZALCCT+za%2Fcases%2FZALAC+za%2Fcases%2FZALCJHB+za%2Fcases%2FZALCD+za%2Fcases%2FZALCPE" target="_blank" rel="noopener">SAFLII labour courts ↗</a>
        <a href="${esc(m.registers.cipc)}" target="_blank" rel="noopener">CIPC / BizPortal ↗</a><a href="${esc(m.registers.csd)}" target="_blank" rel="noopener">Central Supplier Database ↗</a>
        <a href="${esc(m.registers.restricted)}" target="_blank" rel="noopener">Treasury restricted suppliers ↗</a></div>
      <div class="note">${esc(IDENTITY_NOTE)}</div><div class="note">Totals add every published decision that names this supplier; a decision shared with others is counted in full for each, never divided. Fixed values and rates-based budgets (estimates of spend, not amounts paid) are kept apart; both are as published, including any capture errors in the source. Directors are not in these sources: CIPC records need a CIPC search.</div></div>
    <h3>Company register</h3>${reg ? `<table class="kv">${[["Registration number", reg.reg_no], ["Number printed in published records", (reg.printed_reg_no || []).join(", ")], ["Status", reg.status], ["Registration date", reg.reg_date],
        ["Registered address", reg.address], ["Directors", (reg.directors || []).map((d: any) => typeof d === "string" ? d : [d.name, d.role, d.appointed].filter(Boolean).join(", ")).join("; ")], ["Source", reg.source ? `${reg.source} (retrieved ${String(reg.retrieved || "").slice(0, 10)})` : ""]]
        .filter(([, v]) => v).map(([l, v]) => `<tr><td>${esc(l)}</td><td>${esc(v)}</td></tr>`).join("")}</table>${(reg.printed_in || []).map((h: any) => `<div class="sm dim">Printed in ${esc(h.table)} record: "${esc(h.text)}"</div>`).join("")}
        <div class="note">A CIPC number has the form YYYY/NNNNNN/NN; the first part is the year of registration.</div>`
      : `<div class="note">Not in Cape Monitor's register cache yet. Search the register yourself: <a href="https://www.bizportal.gov.za/" target="_blank" rel="noopener">CIPC BizPortal ↗</a> (login required, about 20 searches a day) or <a href="https://b2bhint.com/en/country/search-south-africa-company--16" target="_blank" rel="noopener">B2BHint ↗</a>.</div>`}
    ${flags.length ? `<h3>Pattern flags<span class="c">${flags.length}</span></h3>${flags.map((f) => `<div class="row" data-flag="${esc(f.id)}"><span class="t">${esc(f.title)}</span><small>${esc(F.kinds[f.kind])}</small></div>`).join("")}<div class="note">${esc(F.note)}</div>` : ""}
    ${elsewhere(P.elsewhere)}
    ${network(id, name, P.cobid || [], [...co], sharePhone as string[], names)}
    ${P.refs.awards ? `<h3>${esc(L.awards)}<span class="c">${P.refs.awards.length}</span></h3>${await rowsTable("awards", P.refs.awards, L.awardCols)}` : ""}
    ${P.refs.bids ? `<h3>${esc(L.bids)}<span class="c">${P.refs.bids.length}</span></h3>${await rowsTable("bids", P.refs.bids, L.bidCols)}` : ""}
    ${P.refs.et ? `<h3>${esc(L.et)}<span class="c">${P.refs.et.length}</span></h3>${await rowsTable("etenders", P.refs.et, ["published", "number", "buyer", "desc", "status", "awards", "official"])}` : ""}
    ${P.refs.rfq ? `<h3>${esc(L.rfq)}<span class="c">${P.refs.rfq.length}</span></h3>${await rowsTable("rfq", P.refs.rfq, L.rfqCols)}` : ""}
    ${P.refs.land ? `<h3>${esc(L.land)}<span class="c">${P.refs.land.length}</span></h3>${await rowsTable("land", P.refs.land, ["approved", "erf", "area", "extent", "price", "method"])}` : ""}
    ${cases.length ? `<h3>Competition Tribunal cases naming it<span class="c">${cases.length}</span></h3>${cases.slice(0, 20).map((c: any) => `<div class="row"><a class="t" href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.parties)}</a><small>${esc(c.case)} · ${esc(c.type)} · ${esc(c.date)}</small></div>`).join("")}` : ""}`, `s=${id}`);
  bindDossier(() => buildDossier(name, "Supplier profile", `Every published record naming ${name} (${n} records)` + (flags.length ? `; ${flags.length} pattern flag(s): ${flags.map((f) => f.title).join("; ")}` : "") + ".",
    Object.entries(P.refs as Record<string, number[]>).map(([k, v]) => [k === "et" ? "etenders" : k, v] as [string, number[]])));
  (R().querySelector("[data-expjson]") as HTMLElement).onclick = () => exportJSON(`supplier-${id}`, { supplier: name, id, profile: P, index: Object.fromEntries(S.fields.map((f, k) => [f, ix[k]])), flags, tribunal: cases, exported: new Date().toISOString() });
}

/** labels that keep a pattern from reading as more than it is */
export const NAME_MATCH_NOTE = "Matched by the same normalised name only (case, punctuation and suffixes such as (Pty) Ltd ignored), not by registration number. A match shows that two published records use the same name; it does not show that they are the same company.";
export function flagBadges(f: Flag) {
  let b = "";
  if (f.kind === "restricted") b += `<span class="badge nm" title="${esc(NAME_MATCH_NOTE)}">NAME MATCH ONLY</span>`;
  if (f.verification_status === "NEEDS_SCAN_REVIEW") b += `<span class="badge rv" title="The awarded price is more than 300% above the lowest price read from the scanned register: often a misread digit or a bid for part of the work. Check the scan.">NEEDS SCAN REVIEW</span>`;
  else if (f.verification_status === "OCR_DUAL_PASS_AGREED") b += `<span class="badge ok" title="Both prices were read twice from the scanned register (full page, then the price cell alone) and the two readings agree digit for digit.">DUAL-PASS OCR</span>`;
  return b;
}
function scanLinks(f: Flag) {
  if (!f.scan) return "";
  return `<div class="note${f.verification_status === "NEEDS_SCAN_REVIEW" ? " warnbox" : ""}">${f.verification_status === "NEEDS_SCAN_REVIEW" ? `Needs a look at the scan (${esc((f.review_reason || "").replace(/_/g, " ").toLowerCase())}). ` : ""}Scanned register: <a href="${esc(f.scan)}" target="_blank" rel="noopener">awarded bid ↗</a>${f.scan_lowest && f.scan_lowest !== f.scan ? ` · <a href="${esc(f.scan_lowest)}" target="_blank" rel="noopener">lowest bid ↗</a>` : ""}${f.method ? ` · read by ${esc(f.method)}` : ""}.</div>`;
}

// ---------------------------------------------------------------- evidence dossier: every record behind a profile or a flag, with its source
export interface Dossier { title: string; kind: string; generated: string; summary: string; note: string; sections: { table: string; source: string; source_url: string; retrieved: string; table_note?: string; records: Record<string, any>[] }[] }
export async function buildDossier(title: string, kind: string, summary: string, groups: [string, number[]][]): Promise<Dossier> {
  const m = await moneyMeta(); const names = await supNames(); const sections: Dossier["sections"] = [];
  for (const [tid, idx] of groups) {
    const t = m.tables[tid]; if (!t || !idx.length) continue;
    const rows = (await Promise.all(idx.map((i) => row(tid, i)))).filter(Boolean) as any[][];
    sections.push({ table: t.name, source: t.source, source_url: t.url, retrieved: t.retrieved, ...(t.note ? { table_note: t.note } : {}),
      records: rows.map((r) => Object.fromEntries(t.fields.map((f, k) => [f[1], f[0] === "sup" || f[0] === "bidders" ? (Array.isArray(r[k]) ? r[k] : r[k] ? [r[k]] : []).map((x: string) => names.get(x) || x) : r[k]]).filter(([, v]) => v !== null && v !== undefined && v !== ""))) });
  }
  return { title, kind, generated: new Date().toISOString(), summary, sections,
    note: "Every record as published by the source named in its section, with the document it was read from. Patterns are patterns in published data, not findings. " + IDENTITY_NOTE };
}
export function printDossier(d: Dossier) {
  const w = window.open("", "_blank"); if (!w) { exportJSON("evidence-dossier", d); return; }
  const cell = (v: any) => { const s = Array.isArray(v) ? v.join("; ") : String(v); return /^https?:\/\//.test(s) ? `<a href="${esc(s)}">${esc(s)}</a>` : esc(s); };
  w.document.write(`<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(d.title)}: evidence dossier</title><style>
    body{font:12px/1.45 system-ui,sans-serif;color:#111;margin:24px;max-width:1100px} h1{font-size:20px;margin:0 0 4px} h2{font-size:14px;margin:22px 0 4px;border-bottom:1px solid #999}
    .mu{color:#555} table{border-collapse:collapse;width:100%;margin:6px 0 14px;page-break-inside:auto} td{border:1px solid #ccc;padding:3px 5px;vertical-align:top} td:first-child{width:28%;color:#444}
    a{color:#0645ad;word-break:break-all} .rec{page-break-inside:avoid} @media print{button{display:none}}</style></head><body>
    <button onclick="print()">Print or save as PDF</button>
    <h1>${esc(d.title)}</h1><div class="mu">Evidence dossier · ${esc(d.kind)} · generated ${esc(d.generated.slice(0, 16).replace("T", " "))} UTC</div>
    <p>${esc(d.summary)}</p><p class="mu">${esc(d.note)}</p>
    ${d.sections.map((s) => `<h2>${esc(s.table)} (${s.records.length})</h2><div class="mu">Source: <a href="${esc(s.source_url)}">${esc(s.source)}</a>, retrieved ${esc(s.retrieved.slice(0, 10))}.${s.table_note ? " " + esc(s.table_note) : ""}</div>
      ${s.records.map((r) => `<table class="rec">${Object.entries(r).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${cell(v)}</td></tr>`).join("")}</table>`).join("")}`).join("")}
    </body></html>`);
  w.document.close();
}
const dossierButtons = `<button class="mini" data-dossier="print">Evidence dossier (print)</button><button class="mini" data-dossier="json">Evidence dossier (JSON)</button>`;
function bindDossier(make: () => Promise<Dossier>) {
  R().querySelectorAll("[data-dossier]").forEach((b) => (b as HTMLElement).onclick = async () => { const d = await make(); (b as HTMLElement).dataset.dossier === "json" ? exportJSON(`evidence-${d.title}`, d) : printDossier(d); });
}

/** the same normalised name in another municipality's records (ZopStopper: Cape Town) */
function elsewhere(E: Record<string, any> | undefined) {
  if (!E) return "";
  const lab: Record<string, string> = { "cape-town": "City of Cape Town (Cape Monitor)" };
  return `<h3>Also in other municipalities' records</h3>${Object.entries(E).map(([k, c]) => `<div class="card"><div class="kicker">${esc(lab[k] || k)} <span class="badge nm" title="${esc(NAME_MATCH_NOTE)}">NAME MATCH ONLY</span></div>
    <div class="facts"><div class="fact"><b>${fmt(c.awards)}</b><span>award decisions</span></div><div class="fact"><b>${c.award_value ? short(c.award_value) : "—"}</b><span>fixed value of decisions</span></div>
    <div class="fact"><b>${fmt(c.rfq)}</b><span>quotation orders</span></div><div class="fact"><b>${c.rfq_value ? short(c.rfq_value) : "—"}</b><span>quotation value</span></div>
    <div class="fact"><b>${fmt(c.bids)}</b><span>bids</span></div><div class="fact"><b>${esc(c.first || "—")}${c.last && c.last !== c.first ? "–" + esc(c.last) : ""}</b><span>years</span></div></div>
    <div class="links"><a href="${esc(c.url)}" target="_blank" rel="noopener">Open the ${esc(lab[k] || k)} profile ↗</a>${c.flags ? `<span class="flagc">${c.flags} flag${c.flags === 1 ? "" : "s"} there</span>` : ""}</div>
    <div class="note">Matched by the same normalised name (${esc(c.name)}), not by registration number. It may be a different company with the same name.</div></div>`).join("")}`;
}

/** a small network: co-bidders (shared bid registers), co-named in award decisions, shared contact numbers */
function network(id: string, name: string, cobid: [string, number][], co: [string, number][], phone: string[], names: Map<string, string>) {
  const nodes: { id: string; w: number; kind: string }[] = [];
  const add = (s: string, w: number, kind: string) => { if (!nodes.some((n) => n.id === s) && names.has(s)) nodes.push({ id: s, w, kind }); };
  cobid.slice(0, 10).forEach(([s, w]) => add(s, w, "bid")); co.sort((a, b) => b[1] - a[1]).slice(0, 6).forEach(([s, w]) => add(s, w, "co")); phone.slice(0, 6).forEach((s) => add(s, 1, "phone"));
  if (!nodes.length) return "";
  const W = 380, H = 300, cx = W / 2, cy = H / 2, rad = 112; const mx = Math.max(...nodes.map((n) => n.w));
  const col: Record<string, string> = { bid: "#2aa3ff", co: "#38d39f", phone: "#ff5d5d" };
  const pts = nodes.map((n, k) => { const a = -Math.PI / 2 + k * 2 * Math.PI / nodes.length; return { ...n, x: cx + rad * Math.cos(a), y: cy + rad * Math.sin(a) }; });
  const lab = (s: string) => { const t = names.get(s) || s; return t.length > 26 ? t.slice(0, 25) + "…" : t; };
  return `<h3>Network<span class="c">${nodes.length}</span></h3><svg class="net" viewBox="0 0 ${W} ${H}" role="img" aria-label="Companies linked to ${esc(name)}">
    ${pts.map((p) => `<line x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="${col[p.kind]}" stroke-width="${(1 + 4 * p.w / mx).toFixed(1)}" opacity=".6"/>`).join("")}
    <circle cx="${cx}" cy="${cy}" r="9" fill="#ffd54f"/>
    ${pts.map((p) => `<g class="nn" data-sup="${esc(p.id)}"><circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="6" fill="${col[p.kind]}"/><text x="${p.x.toFixed(1)}" y="${(p.y + (p.y > cy ? 17 : -10)).toFixed(1)}" text-anchor="middle">${esc(lab(p.id))}</text><title>${esc(names.get(p.id) || p.id)}: ${p.kind === "bid" ? p.w + " tenders bid on together" : p.kind === "co" ? "named together in " + p.w + " award decision(s)" : "same published contact number"}</title></g>`).join("")}</svg>
    <div class="sm"><span style="color:${col.bid}">━</span> bid on the same tenders · <span style="color:${col.co}">━</span> named in the same award decision · <span style="color:${col.phone}">━</span> same published contact number. Links are as published; they are not evidence of common ownership.</div>`;
}

export async function openTender(ref: string) {
  track("tender", { ref }); loading("tender"); const m = await moneyMeta(); const k = L.refKey(ref);
  const T = (await getJSON<Record<string, any>>(`${MP}tender/${bucket(k, m.buckets)}.json`))[k];
  if (!T) { R().innerHTML = `<div class="card"><div class="kicker">Tender ${esc(ref)}</div><div class="empty">${esc(L.notender)}</div></div>`; return; }
  const first = T.bids?.length ? await row("bids", T.bids[0]) : T.awards?.length ? await row("awards", T.awards[0]) : null;
  const fq = !first && T.rfq?.length ? await row("rfq", T.rfq[0]) : null;
  const desc = first ? (T.bids?.length ? first[2] : first[5]) : fq ? fq[4] : "";
  const docs = T.docs?.length ? await Promise.all(T.docs.map((i: number) => row("docs", i))) : [];
  const ets = T.et?.length ? await Promise.all(T.et.map((i: number) => row("etenders", i))) : [];
  const etd = ets.length ? await Promise.all(ets.map(async (r) => { const pid = r![fi(m.tables.etenders, "portal_id")]; const idx = (T.et as number[])[ets.indexOf(r)];
    return (await getJSON<Record<string, any>>(`${MP}etd/${Math.floor(idx / m.et_shard)}.json`))[String(idx)] || { id: pid }; })) : [];
  open(`<div class="card primary"><div class="kicker">${esc(L.tender)}</div><h2>${esc(ref)}</h2><div class="mu">${esc(desc)}</div>
      <div class="facts"><div class="fact"><b>${T.bids?.length || 0}</b><span>${esc(L.bidsRead)}</span></div><div class="fact"><b>${T.awards?.length || 0}</b><span>decisions</span></div><div class="fact"><b>${(T.docs?.length || 0) + etd.reduce((s: number, e: any) => s + (e.documents?.length || 0), 0)}</b><span>documents</span></div></div>
      <div class="links">${watchButton("tender", k, `Tender ${ref}`, (T.bids?.length || 0) + (T.awards?.length || 0))}<button class="mini" data-share="t=${esc(k)}">Share link</button></div></div>
    ${etd.map((e: any) => `<h3>Advertised on the eTender portal</h3><table class="kv">${[["Buyer", e.organ_of_State], ["Type", e.type], ["Category", e.category], ["Published", e.date_Published?.slice(0, 10)], ["Closing", e.closing_Date?.replace("T", " ").slice(0, 16)],
      ["Briefing session", e.briefingSession ? `${e.briefingCompulsory ? "Compulsory" : "Not compulsory"}: ${e.compulsory_briefing_session || ""} ${e.briefingVenue || ""}` : "None"], ["Responsible official", [e.contactPerson, e.email, e.telephone].filter(Boolean).join(" · ")],
      ["Delivery", e.delivery], ["Conditions", e.conditions], ["Status on portal", e.portal_status]].filter(([, v]) => v).map(([l, v]) => `<tr><td>${esc(l)}</td><td>${esc(v)}</td></tr>`).join("")}</table>
      ${e.documents?.length ? `<div class="links">${e.documents.map((d: any) => `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.name)} ↗</a>`).join("")}</div>` : ""}`).join("")}
    ${T.bids?.length ? `<h3>Bids read out at the opening<span class="c">${T.bids.length}</span></h3>${await rowsTable("bids", T.bids, L.tenderBidCols, 100)}` : ""}
    ${T.awards?.length ? `<h3>Award decisions<span class="c">${T.awards.length}</span></h3>${await rowsTable("awards", T.awards, L.tenderAwardCols, 100)}` : ""}
    ${T.rfq?.length ? `<h3>${esc(L.rfq)}<span class="c">${T.rfq.length}</span></h3>${await rowsTable("rfq", T.rfq, L.rfqCols, 100)}` : ""}
    ${docs.length ? `<h3>Documents naming it</h3>${docs.map((d) => `<div class="row"><a class="t" href="${esc(d![4])}" target="_blank" rel="noopener">${esc(d![2])}</a><small>${esc(d![1])} · ${esc(d![0] || "")}</small></div>`).join("")}` : ""}`, `t=${k}`);
}

export async function openDepartment(k: number) {
  loading("department"); const D = (await getJSON<any[]>(MP + "departments.json"))[k]; const names = await supNames(); const F = await flagsData();
  const flags = F.flags.filter((f) => f.subjects.some((s) => (s[0] === "directorate" || s[0] === "department") && D.name.toLowerCase().endsWith(String(s[1]).toLowerCase())));
  open(`<div class="card primary"><div class="kicker">Department / organ of state</div><h2>${esc(D.name)}</h2>
      <div class="facts"><div class="fact"><b>${fmt(D.n)}</b><span>records</span></div><div class="fact"><b>${D.value ? short(D.value) : "—"}</b><span>quotation value</span></div><div class="fact"><b>${flags.length}</b><span>pattern flags</span></div></div>
      <div class="links">${watchButton("department", String(k), D.name, D.n)}</div></div>
    ${D.years.length ? `<h3>Quotation value per year</h3>${columns(D.years.filter(([y]: [string]) => /^\d{4}$/.test(y)), short)}` : ""}
    <h3>Largest suppliers</h3>${D.top.map(([s, v]: [string, number]) => `<div class="row" data-sup="${esc(s)}"><span class="t">${esc(names.get(s) || s)}</span><small>${D.value ? short(v) : fmt(v) + " awards"}</small></div>`).join("")}
    ${flags.length ? `<h3>Pattern flags<span class="c">${flags.length}</span></h3>${flags.slice(0, 50).map((f) => `<div class="row" data-flag="${esc(f.id)}"><span class="t">${esc(f.title)}</span><small>${esc(F.kinds[f.kind])}</small></div>`).join("")}` : ""}`, `dep=${k}`);
}

export async function openFlag(id: string) {
  track("flag", { id }); loading("flag"); const F = await flagsData(); const f = F.flags.find((x) => x.id === id);
  if (!f) { R().innerHTML = `<div class="card"><div class="empty">Flag not in this build (flags are recomputed with every data refresh).</div></div>`; return; }
  const by = new Map<string, number[]>(); for (const [t, i] of f.records) by.set(t, [...(by.get(t) || []), i]);
  const COLS = L.flagCols;
  const names = await supNames();
  open(`<div class="card primary flagcard"><div class="kicker">Pattern in published data · ${esc(F.kinds[f.kind])}</div><h2>${esc(f.title)}</h2><div>${flagBadges(f)}</div><p>${esc(f.text)}</p>
      ${scanLinks(f)}${f.kind === "restricted" ? `<div class="note">${esc(NAME_MATCH_NOTE)}</div>` : ""}
      ${f.basis ? `<div class="sm">Rule: <a href="${esc(f.basis.url)}" target="_blank" rel="noopener">${esc(f.basis.text)}</a></div>` : ""}
      <div class="note warnbox">${esc(F.note)}</div>
      <div class="links">${f.subjects.filter((s) => s[0] === "supplier").map((s) => `<a href="#s=${esc(s[1])}" data-sup="${esc(s[1])}">${esc(names.get(s[1]) || s[1])}</a>`).join("")}${f.subjects.filter((s) => s[0] === "tender").map((s) => `<a href="#t=${esc(s[1])}" data-tender="${esc(s[1])}">Tender ${esc(s[1])}</a>`).join("")}
        ${watchButton("flag", f.id, f.title, f.records.length)}<button class="mini" data-share="f=${esc(f.id)}">Share link</button>${dossierButtons}</div></div>
    ${(await Promise.all([...by].map(async ([t, idx]) => `<h3>The records (${esc((await moneyMeta()).tables[t]?.name || t)})<span class="c">${idx.length}</span></h3>${await rowsTable(t, idx, COLS[t] || [], 200)}`))).join("")}`, `fl=${f.id}`);
  bindDossier(() => buildDossier(f.title, `Pattern flag: ${F.kinds[f.kind]}`, f.text + (f.basis ? ` Rule: ${f.basis.text} (${f.basis.url}).` : "") + (f.verification_status ? ` Verification: ${f.verification_status}${f.review_reason ? " (" + f.review_reason + ")" : ""}; scan ${f.scan}.` : ""), [...by]));
}

/** clicks inside the right panel and the dock that open money views */
export function bindMoney(...roots: HTMLElement[]) {
  for (const root of roots) root.addEventListener("click", async (e) => {
    const el = e.target as HTMLElement;
    const s = el.closest("[data-sup]") as HTMLElement | null; if (s) { e.preventDefault(); return openSupplier(s.dataset.sup!); }
    const t = el.closest("[data-tender]") as HTMLElement | null; if (t) { e.preventDefault(); return openTender(t.dataset.tender!); }
    const f = el.closest("[data-flag]") as HTMLElement | null; if (f) return openFlag(f.dataset.flag!);
    const d = el.closest("[data-dept]") as HTMLElement | null; if (d) return openDepartment(+d.dataset.dept!);
    const x = el.closest("[data-exp]") as HTMLElement | null; if (x) { const { tid, idx } = JSON.parse(x.dataset.exp!); return exportRows(tid, idx, `${tid}-selection`); }
    const et = el.closest("[data-etd]") as HTMLElement | null; if (et) return openEtender(+et.dataset.etd!);
  });
}
async function openEtender(portalId: number) {
  const m = await moneyMeta(); const rows = await allRows("etenders"); const T = m.tables.etenders; const i = rows.findIndex((r) => r[fi(T, "portal_id")] === portalId); if (i < 0) return;
  const e = (await getJSON<Record<string, any>>(`${MP}etd/${Math.floor(i / m.et_shard)}.json`))[String(i)];
  const own = L.tenderRef(e);
  if (own) return openTender(own);
  open(`<div class="card primary"><div class="kicker">eTender portal · ${esc(e.portal_status)}</div><h2>${esc(e.description)}</h2>
    <table class="kv">${[["Tender number", e.tender_No], ["Buyer", e.organ_of_State], ["Type", e.type], ["Category", e.category], ["Published", e.date_Published?.slice(0, 10)], ["Closing", e.closing_Date?.replace("T", " ").slice(0, 16)],
      ["Briefing session", e.briefingSession ? `${e.briefingCompulsory ? "Compulsory" : "Not compulsory"}: ${e.compulsory_briefing_session || ""} ${e.briefingVenue || ""}` : "None"], ["Responsible official", [e.contactPerson, e.email, e.telephone].filter(Boolean).join(" · ")],
      ["Delivery", e.delivery], ["Conditions", e.conditions]].filter(([, v]) => v).map(([l, v]) => `<tr><td>${esc(l)}</td><td>${esc(v)}</td></tr>`).join("")}</table>
    ${e.documents?.length ? `<div class="links">${e.documents.map((d: any) => `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.name)} ↗</a>`).join("")}</div>` : ""}
    <div class="note">Source: <a href="https://www.etenders.gov.za/Home/opportunities?id=1" target="_blank" rel="noopener">National Treasury eTender Portal</a>, record ${esc(e.id)}, seen ${esc(e.seen)}.</div></div>
    ${e.bidders?.length ? `<h3>Bidders listed<span class="c">${e.bidders.length}</span></h3>${e.bidders.map((b: any) => `<div class="row"><span class="t">${esc(b.name)}</span><small>${b.amount ? rand(b.amount) : ""}</small></div>`).join("")}` : ""}
    ${e.awards?.length ? `<h3>Awarded to</h3>${e.awards.map((a: any) => `<div class="row"><span class="t">${esc(a.company)}</span><small>${esc(a.amount || "")} · ${esc((a.date || "").slice(0, 10))}${a.contact ? " · contact " + esc(a.contact) : ""}</small></div>`).join("")}` : ""}`, `e=${portalId}`);
}
