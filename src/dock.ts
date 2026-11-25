// The bottom dock: Brief (district and suburb statistics), Activity (latest City records), Feed (news and GI-TOC),
// Records (every table, searchable), Sources (what is in, when it was fetched, what was left out and why), Heritage.
import { M, getJSON, tableRows, layerById, Table, DP, DISTRICT, METRO, districtUrl, DataIndex } from "./data";
import { t, esc, fmt, money } from "./i18n";
import { openRecord, openWatched } from "./inspector";
import { map } from "./map";
import { moneyTab, moneyMeta, suppliers, PERSONAL_NOTE, IDENTITY_NOTE } from "./money";
import { watches, toggleWatch, updateCount, exportCSV, exportTable, exportJSON } from "./util";
import { can, proNote } from "./auth/entitlements";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
type Area = { sr_total: number; sr_type: [string, number][]; sr_month: [string, number][]; plans_year: [string, number][]; plans_value: [string, number][];
  population?: Record<string, any>; licences?: [string, number][] };
let areas: { suburb: Record<string, Area>; ward: Record<string, Area> } | null = null;
let tab = "brief";

const bars = (rows: [string, number][], max = 12, f = fmt) => { const top = rows.slice(0, max); const m = Math.max(1, ...top.map((r) => r[1]));
  return top.map(([l, v]) => `<div class="bar"><span class="lab" title="${esc(l)}">${esc(l)}</span><span class="track"><span class="fill" style="width:${(v / m * 100).toFixed(1)}%"></span></span><span class="v">${f(v)}</span></div>`).join(""); };
const spark = (rows: [string, number][]) => { if (rows.length < 2) return ""; const m = Math.max(1, ...rows.map((r) => r[1])); const W = 300, H = 60;
  const pts = rows.map(([, v], k) => `${(k / (rows.length - 1) * W).toFixed(1)},${(H - v / m * (H - 4)).toFixed(1)}`).join(" ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><polygon class="a" points="0,${H} ${pts} ${W},${H}"/></svg><div class="sm dim" style="display:flex;justify-content:space-between"><span>${esc(rows[0][0])}</span><span>${esc(rows[rows.length - 1][0])}</span></div>`; };
const sum = (list: Area[], key: "sr_type" | "sr_month" | "plans_year" | "plans_value") => { const m = new Map<string, number>(); for (const a of list) for (const [k, v] of a[key]) m.set(k, (m.get(k) || 0) + v); return [...m]; };

let cmp = "";
const briefSlot = () => can("weeklyBrief") ? `<div class="tile pro">Weekly brief: the next human-written brief will appear here once briefs are published.</div>` : "";
async function brief() {
  if (!DISTRICT) return metroBrief();
  areas ??= await getJSON(DP + "areas.json");
  const kind = ((document.getElementById("area-kind") as HTMLSelectElement | null)?.value || "suburb") as "suburb" | "ward";
  const keys = Object.keys(areas![kind]).filter((k) => /^[ -~]+$/.test(k)).sort((a, b) => kind === "ward" ? +a - +b : a.localeCompare(b));
  const sel = (document.getElementById("area-sel") as HTMLSelectElement | null)?.value || "";
  cmp = (document.getElementById("area-cmp") as HTMLSelectElement | null)?.value ?? cmp;
  const col = (key: string) => {
    const list = key ? [areas![kind][key]].filter(Boolean) : keys.map((k) => areas![kind][k]);
    const months = sum(list, "sr_month").sort((x, y) => x[0].localeCompare(y[0])).filter(([m]) => m);
    const types = sum(list, "sr_type").sort((x, y) => y[1] - x[1]);
    const py = sum(list, "plans_year").sort((x, y) => x[0].localeCompare(y[0])), pv = sum(list, "plans_value");
    const a = key ? areas![kind][key] : null;
    const pop = a?.population ? Object.entries(a.population).filter(([k, v]) => typeof v === "number" && !/id/i.test(k)) : [];
    const kpi = (v: any, l: string) => `<div class="kpi"><b>${v}</b><span>${esc(l)}</span></div>`;
    return `<div class="cmpcol"><h3>${key ? esc((kind === "ward" ? "Ward " : "") + key) : "Whole district"}</h3>
      <div class="kpis">${kpi(fmt(list.reduce((s, x) => s + x.sr_total, 0)), "service requests")}${kpi(fmt(py.reduce((s, x) => s + x[1], 0)), "building plans")}
        ${kpi(money(pv.reduce((s, x) => s + x[1], 0) / 1e6) + "m", "declared building value")}${pop.slice(0, 3).map(([k, v]) => kpi(fmt(v as number), k.replace(/_/g, " "))).join("")}</div>
      <div class="grid"><div class="tile"><div class="caps">Service requests per month</div>${spark(months)}</div>
        <div class="tile"><div class="caps">Top service-request types</div>${bars(types, 8)}</div>
        <div class="tile"><div class="caps">Building plans per year</div>${bars(py.map(([y, n]) => [y, n] as [string, number]).reverse(), 13)}</div>
        ${a?.licences ? `<div class="tile"><div class="caps">Business licences</div>${bars(a.licences, 8)}</div>` : ""}</div></div>`;
  };
  const opts = (v: string, none: string) => `<option value="">${none}</option>${keys.map((k) => `<option ${k === v ? "selected" : ""}>${esc(k)}</option>`).join("")}`;
  $("#dockbody").innerHTML = `<div class="toolbar"><b>${esc(M.district.label || M.district.name)}</b><select id="area-kind" aria-label="Compare by"><option value="suburb" ${kind === "suburb" ? "selected" : ""}>Suburbs</option><option value="ward" ${kind === "ward" ? "selected" : ""}>Wards</option></select>
      <select id="area-sel" aria-label="Area">${opts(sel, "Whole district")}</select><span class="sm">compare with</span><select id="area-cmp" aria-label="Compare with">${opts(cmp, "— nothing —")}</select>
      <span class="note">Service requests since Jan 2023; building plans matched to plots in this district.</span></div>
    <div class="${cmp ? "cmp" : ""}">${col(sel)}${cmp ? col(cmp) : ""}</div>
    ${!sel && !cmp ? `<div class="tile"><div class="caps">Busiest ${kind === "ward" ? "wards" : "suburbs"} (service requests)</div>${bars(keys.map((k) => [k, areas![kind][k].sr_total] as [string, number]).sort((x, y) => y[1] - x[1]), 12)}</div>` : ""}`;
  for (const id of ["area-kind", "area-sel", "area-cmp"]) (document.getElementById(id) as HTMLSelectElement).onchange = (e) => { if (id === "area-kind") { (document.getElementById("area-sel") as HTMLSelectElement).value = ""; cmp = ""; (document.getElementById("area-cmp") as HTMLSelectElement).value = ""; } brief(); };
}

async function metroBrief() {
  const I = await getJSON<DataIndex>("data/index.json").catch(() => null);
  const ms = await Promise.all((I?.districts || []).filter((d) => d.built).map(async (d) => ({ d, a: await getJSON<any>(`data/d/${d.slug}/areas.json`).catch(() => null) })));
  const tot = (a: any) => a ? Object.values(a.suburb as Record<string, any>).reduce((s: number, x: any) => s + x.sr_total, 0) : 0;
  const plans = (a: any) => a ? Object.values(a.suburb as Record<string, any>).reduce((s: number, x: any) => s + x.plans_year.reduce((t: number, y: any) => t + y[1], 0), 0) : 0;
  const m = await moneyMeta().catch(() => null);
  $("#dockbody").innerHTML = `${briefSlot()}<div class="toolbar"><b>City of Cape Town</b><span class="note">District figures come from each district's own build; money is city-wide.</span></div>
    ${m ? `<div class="kpis">${[["suppliers", "supplier profiles"], ["awards", "award decisions"], ["bids", "bids read out"], ["rfq", "quotation orders"], ["etenders", "WC eTenders"], ["flags", "pattern flags"]].map(([k, l]) => `<div class="kpi"><b>${fmt(m.counts[k] || 0)}</b><span>${l}</span></div>`).join("")}</div>` : ""}
    <div class="tscroll"><table class="t"><thead><tr><th>District</th><th>Plots</th><th>Map layers</th><th>Service requests</th><th>Building plans matched</th><th>Data built</th></tr></thead><tbody>
    ${(I?.districts || []).map((d) => { const a = ms.find((x) => x.d.slug === d.slug)?.a; return `<tr><td><a href="${districtUrl(d.slug)}">${esc(d.label)}</a></td><td class="mono">${d.plots ? fmt(d.plots) : ""}</td><td class="mono">${d.layers ?? ""}</td><td class="mono">${a ? fmt(tot(a)) : ""}</td><td class="mono">${a ? fmt(plans(a)) : ""}</td><td class="mono">${d.built ? esc(d.built.slice(0, 10)) : "not built yet"}</td></tr>`; }).join("")}</tbody></table></div>`;
}

async function activity() {
  const L = layerById.get("service-requests"); if (!L) { $("#dockbody").innerHTML = `<div class="empty">No service-request data.</div>`; return; }
  const last = Math.floor((L.n - 1) / M.parcels.shard);
  const [a, b] = await Promise.all([getJSON<any[][]>(`${DP}attrs/service-requests/${last}.json`), last > 0 ? getJSON<any[][]>(`${DP}attrs/service-requests/${last - 1}.json`) : Promise.resolve([])]);
  const f = (k: string) => L.fields.findIndex((x) => x[0] === k);
  const rows = [...b.map((r, k) => [r, (last - 1) * M.parcels.shard + k] as const), ...a.map((r, k) => [r, last * M.parcels.shard + k] as const)].reverse().slice(0, 300);
  $("#dockbody").innerHTML = `<div class="note">Latest ${rows.length} service requests logged in ${esc(M.district.name)} (of ${fmt(L.n)} since January 2023). Click one to see it on the map.</div>
    <table class="t"><thead><tr><th>Logged</th><th>Type</th><th>Suburb</th><th>Ward</th><th>Completed</th><th>Work centre</th></tr></thead><tbody>
    ${rows.map(([r, i]) => `<tr class="click" data-rec="service-requests:${i}"><td class="mono">${esc(r[f("Created_On_Date")])}</td><td>${esc(r[f("C3_Complaint_Type")] || r[f("Notification_type")])}</td><td>${esc(r[f("Suburb")])}</td><td>${esc(r[f("Ward")])}</td><td class="mono">${esc(r[f("Completed_Date")] || "open")}</td><td class="dim">${esc(r[f("Work_Center")])}</td></tr>`).join("")}</tbody></table>`;
}

async function feed() {
  const F = await getJSON<{ items: any[]; feeds: any[] }>(METRO + "feed.json");
  const only = (document.getElementById("feed-local") as HTMLInputElement | null)?.checked ?? !!DISTRICT;
  const items = F.items.filter((i) => !only || i.places.some((p: any) => !DISTRICT || p[1] === DISTRICT));
  items.sort((a, b) => Date.parse(b.date || 0) - Date.parse(a.date || 0));
  $("#dockbody").innerHTML = `<div class="toolbar"><label><input type="checkbox" id="feed-local" ${only ? "checked" : ""}> Only items naming a suburb ${DISTRICT ? "in " + esc(M.district.label) : "in Cape Town"}</label>
      ${F.feeds.map((f) => `<a class="pill" href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.error || "fetched " + f.retrieved)}">${esc(f.name)} · ${f.error ? "unavailable" : f.n}</a>`).join("")}</div>
    ${items.slice(0, 300).map((i) => `<div class="feeditem"><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.title)}</a><div class="meta">${esc(F.feeds.find((f) => f.id === i.feed)?.name)} · ${esc(String(i.date).slice(0, 16).replace("T", " "))}${i.places.length ? " · " + i.places.map((p: any) => `<span class="pill">${esc(p[0])}</span>`).join("") : ""}</div><div class="sm mu">${esc(i.summary)}</div></div>`).join("") || `<div class="empty">No items.</div>`}`;
  (document.getElementById("feed-local") as HTMLInputElement).onchange = () => feed();
}

// generic table viewer: search, sort, aggregate by one column
let tv: { id: string; rows: any[][]; q: string; sort: number; dir: number; group: number } | null = null;
async function records(id?: string) {
  const tables = M.tables.filter((x) => x.n > 0);
  const T = tables.find((x) => x.id === (id || tv?.id)) || tables.find((x) => x.id === "rfq-awards") || tables[0];
  if (!T) return;
  if (!tv || tv.id !== T.id) { $("#dockbody").innerHTML = `<div class="empty">${t("loading")}</div>`; tv = { id: T.id, rows: await tableRows(T), q: "", sort: -1, dir: 1, group: -1 }; }
  const q = tv.q.toLowerCase();
  let rows = q ? tv.rows.filter((r) => r.some((v) => v != null && String(v).toLowerCase().includes(q))) : tv.rows;
  if (tv.sort >= 0) rows = [...rows].sort((a, b) => { const x = a[tv!.sort], y = b[tv!.sort]; return (typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""))) * tv!.dir; });
  const numCol = T.fields.findIndex((f) => /value|amount|price|total/i.test(f[0]) && typeof tv!.rows[0]?.[T.fields.indexOf(f)] === "number");
  let groupHtml = "";
  if (tv.group >= 0) {
    const m = new Map<string, [number, number]>(); for (const r of rows) { const k = String(r[tv.group] ?? "—"); const e = m.get(k) || [0, 0]; e[0]++; if (numCol >= 0) e[1] += Number(r[numCol]) || 0; m.set(k, e); }
    const g = [...m].sort((a, b) => (numCol >= 0 ? b[1][1] - a[1][1] : b[1][0] - a[1][0])).slice(0, 40);
    groupHtml = `<div class="tile" style="margin-bottom:8px"><div class="caps">By ${esc(T.fields[tv.group][1] || T.fields[tv.group][0])}${numCol >= 0 ? " (total " + esc(T.fields[numCol][1] || T.fields[numCol][0]) + ")" : ""}</div>${bars(g.map(([k, v]) => [k, numCol >= 0 ? v[1] : v[0]] as [string, number]), 40, numCol >= 0 ? money : fmt)}</div>`;
  }
  const show = rows.slice(0, 500);
  $("#dockbody").innerHTML = `<div class="toolbar"><select id="tv-t">${tables.map((x) => `<option value="${x.id}" ${x.id === T.id ? "selected" : ""}>${esc(x.name)} (${fmt(x.n)})</option>`).join("")}</select>
      <input id="tv-q" placeholder="Filter rows…" value="${esc(tv.q)}"><select id="tv-g"><option value="-1">Group by…</option>${T.fields.map((f, k) => `<option value="${k}" ${k === tv!.group ? "selected" : ""}>${esc(f[1] || f[0])}</option>`).join("")}</select>
      <button class="tb" id="tv-x">Export CSV</button><span class="note">${fmt(rows.length)} rows${rows.length > 500 ? " (first 500 shown; export has all)" : ""} · ${T.scope === "city-wide" ? "whole city" : esc(M.district.name)} · <a href="${esc(T.url)}" target="_blank" rel="noopener">source</a> · fetched ${esc((T.retrieved || "").slice(0, 10))}</span></div>
    ${T.note ? `<div class="note">${esc(T.note)}</div>` : ""}${groupHtml}
    <div class="tscroll"><table class="t"><thead><tr>${T.fields.map((f, k) => `<th data-sort="${k}" title="${esc(f[0])}">${esc(f[1] || f[0])}${tv!.sort === k ? (tv!.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
    <tbody>${show.map((r) => `<tr>${r.map((v, k) => `<td${k === numCol ? ' class="mono"' : ""}>${v == null ? "" : k === numCol ? money(v) : esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  ($("#tv-t") as HTMLSelectElement).onchange = (e) => records((e.target as HTMLSelectElement).value);
  let tm: any; ($("#tv-q") as HTMLInputElement).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { tv!.q = (e.target as HTMLInputElement).value; records(); setTimeout(() => { const el = $("#tv-q") as HTMLInputElement; el.focus(); el.setSelectionRange(el.value.length, el.value.length); }); }, 250); };
  ($("#tv-g") as HTMLSelectElement).onchange = (e) => { tv!.group = +(e.target as HTMLSelectElement).value; records(); };
  ($("#tv-x") as HTMLElement).onclick = () => exportTable(`${T.id}-${DISTRICT}${tv!.q ? "-filtered" : ""}`, T.fields.map((f) => f[1] || f[0]), rows, `${T.name}. Source: ${T.url}, fetched ${T.retrieved}.`);
  $("#dockbody").querySelectorAll("th[data-sort]").forEach((th) => (th as HTMLElement).onclick = () => { const k = +(th as HTMLElement).dataset.sort!; tv!.dir = tv!.sort === k ? -tv!.dir : -1; tv!.sort = k; records(); });
}

async function justice() {
  const J = await getJSON<any>(METRO + "justice.json").catch(() => null);
  if (!J) { $("#dockbody").innerHTML = `<div class="empty">Court records are not in this build yet.</div>`; return; }
  const q = ((document.getElementById("j-q") as HTMLInputElement | null)?.value || "").toLowerCase();
  const only = (document.getElementById("j-sup") as HTMLInputElement | null)?.checked ?? false;
  const items = J.items.filter((c: any) => (!q || `${c.parties} ${c.case} ${c.type}`.toLowerCase().includes(q)) && (!only || c.suppliers.length));
  $("#dockbody").innerHTML = `<div class="toolbar"><input id="j-q" placeholder="Filter by party, case number, type…" value="${esc(q)}"><label><input type="checkbox" id="j-sup" ${only ? "checked" : ""}> Only cases naming a City supplier</label>
      <button class="tb" id="j-x">Export CSV</button>${J.sources.map((s: any) => `<a class="pill" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)} · ${fmt(s.n)} · fetched ${esc(s.retrieved.slice(0, 10))}</a>`).join("")}</div>
    <div class="note">Not added: ${J.not_added.map((n: any) => `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.name)}</a>: ${esc(n.why)}`).join(" ")}</div>
    <div class="tscroll"><table class="t"><thead><tr><th>Order date</th><th>Case</th><th>Type</th><th>Parties</th><th>Status</th><th>City suppliers named</th><th>Places</th><th>Documents</th></tr></thead><tbody>
    ${items.slice(0, 400).map((c: any) => `<tr><td class="mono">${esc(c.date)}</td><td><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.case)}</a></td><td>${esc(c.type)}</td><td>${esc(c.parties)}</td><td>${esc(c.status)}</td>
      <td>${c.suppliers.map((s: string) => `<a href="#s=${esc(s)}" data-sup="${esc(s)}">${esc(s)}</a>`).join(", ")}</td><td>${c.places.map((p: any) => esc(p[0])).join(", ")}${c.erfs.length ? " · erf " + c.erfs.map(esc).join(", ") : ""}</td>
      <td>${c.docs.map((d: any) => `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a>`).join("<br>")}</td></tr>`).join("")}</tbody></table></div>
    ${items.length > 400 ? `<div class="note">First 400 of ${fmt(items.length)}; export has all.</div>` : ""}`;
  let tm: any; (document.getElementById("j-q") as HTMLInputElement).oninput = () => { clearTimeout(tm); tm = setTimeout(() => justice().then(() => { const i = document.getElementById("j-q") as HTMLInputElement; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }), 250); };
  (document.getElementById("j-sup") as HTMLInputElement).onchange = () => justice();
  (document.getElementById("j-x") as HTMLElement).onclick = () => exportTable("tribunal-cases", ["date", "case", "type", "parties", "status", "suppliers", "places", "erfs", "url", "documents"],
    items.map((c: any) => [c.date, c.case, c.type, c.parties, c.status, c.suppliers, c.places.map((p: any) => p[0]), c.erfs, c.url, c.docs.map((d: any) => d.url)]), "Competition Tribunal decided cases, " + J.sources[0].url);
}

async function notices() {
  const N = await getJSON<any>(METRO + "notices.json").catch(() => null);
  if (!N) { $("#dockbody").innerHTML = `<div class="empty">Gazette notices are not in this build yet.</div>`; return; }
  const q = ((document.getElementById("n-q") as HTMLInputElement | null)?.value || "").toLowerCase();
  const kind = (document.getElementById("n-k") as HTMLSelectElement | null)?.value || "";
  const mine = (document.getElementById("n-d") as HTMLInputElement | null)?.checked ?? !!DISTRICT;
  const kinds = [...new Set(N.notices.map((n: any) => n.kind))].sort() as string[];
  const list = N.notices.filter((n: any) => (!kind || n.kind === kind) && (!q || `${n.title} ${n.text} ${n.gazette}`.toLowerCase().includes(q)) && (!mine || !DISTRICT || n.places.some((p: any) => p[1] === DISTRICT)));
  $("#dockbody").innerHTML = `<div class="toolbar"><input id="n-q" placeholder="Filter: erf, suburb, applicant, word…" value="${esc(q)}"><select id="n-k" aria-label="Kind"><option value="">All kinds (${N.notices.length})</option>${kinds.map((k) => `<option ${k === kind ? "selected" : ""}>${esc(k)}</option>`).join("")}</select>
      ${DISTRICT ? `<label><input type="checkbox" id="n-d" ${mine ? "checked" : ""}> Only naming a suburb in ${esc(M.district.label)}</label>` : ""}<button class="tb" id="n-x">Export CSV</button>
      <span class="note"><a href="${esc(N.source.url)}" target="_blank" rel="noopener">${esc(N.source.name)}</a> · ${N.source.gazettes} gazettes (${esc(N.source.years.join(", "))}) · built ${esc(N.built.slice(0, 10))}</span></div>
    ${list.slice(0, 200).map((n: any) => `<div class="feeditem"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.kind)}: ${esc(n.title)}</a><div class="meta">${esc(n.gazette)} · ${esc(n.issuer)}${n.ref ? " · " + esc(n.ref) : ""}${n.places.length ? " · " + n.places.map((p: any) => `<span class="pill">${esc(p[0])}</span>`).join("") : ""}${n.erf_suburbs.length ? " · " + n.erf_suburbs.map((e: any) => esc(`Erf ${e[0]} ${e[1]}`)).join("; ") : ""}</div>
      <details class="raw"><summary>Notice text</summary><div class="sm" style="white-space:pre-wrap">${esc(n.text)}</div></details></div>`).join("") || `<div class="empty">No notices match.</div>`}
    ${list.length > 200 ? `<div class="note">First 200 of ${list.length}; export has all.</div>` : ""}`;
  let tm: any; (document.getElementById("n-q") as HTMLInputElement).oninput = () => { clearTimeout(tm); tm = setTimeout(() => notices().then(() => { const i = document.getElementById("n-q") as HTMLInputElement; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }), 250); };
  (document.getElementById("n-k") as HTMLSelectElement).onchange = () => notices();
  const nd = document.getElementById("n-d"); if (nd) nd.onchange = () => notices();
  (document.getElementById("n-x") as HTMLElement).onclick = () => exportTable("gazette-notices", ["date", "gazette", "issuer", "kind", "title", "reference", "erven", "suburbs", "url", "text"],
    list.map((n: any) => [n.date_iso, n.gazette, n.issuer, n.kind, n.title, n.ref, n.erf_suburbs.map((e: any) => `Erf ${e[0]} ${e[1]}`), n.places.map((p: any) => p[0]), n.url, n.text]), N.source.name + " " + N.source.url);
}

// labour and employment: statutory minimums, bargaining-council documents, Labour Research Service publications.
// Filter state lives in the address as #l=<council>:<kind>:<year>:<search> so a filtered view can be shared.
let lab = { council: "", kind: "", year: "", q: "" };
export function setLabourFilter(h: string) { const [council = "", kind = "", year = "", q = ""] = h.split(":").map(decodeURIComponent); lab = { council, kind, year, q }; }
async function labour() {
  const L = await getJSON<any>(METRO + "labour.json").catch(() => null);
  if (!L) { $("#dockbody").innerHTML = `<div class="empty">Labour records are not in this build yet.</div>`; return; }
  const councils = L.sources.filter((x: any) => x.id !== "lrs");
  const kinds = [...new Set(L.documents.map((d: any) => d.kind))].sort() as string[];
  const years = [...new Set(L.documents.map((d: any) => d.year).filter(Boolean))].sort().reverse() as string[];
  const q = lab.q.toLowerCase();
  const docs = L.documents.filter((d: any) => (!lab.council || d.council === lab.council) && (!lab.kind || d.kind === lab.kind) && (!lab.year || d.year === lab.year) && (!q || `${d.title} ${d.sector}`.toLowerCase().includes(q)));
  const name = (id: string) => councils.find((c: any) => c.id === id)?.name || id;
  const opt = (v: string, cur: string, label = v) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(label)}</option>`;
  history.replaceState(null, "", location.pathname + location.search + "#l=" + [lab.council, lab.kind, lab.year, lab.q].map(encodeURIComponent).join(":"));
  $("#dockbody").innerHTML = `<h3>Statutory minimums (from the Government Gazette)</h3>
    <div class="tscroll"><table class="t"><thead><tr><th>Item</th><th>Rate</th><th>Applies to</th><th>Binding from</th><th>Source</th></tr></thead><tbody>
    ${L.statutory.map((r: any) => `<tr><td>${esc(r.item)}</td><td class="mono">${esc(r.rate)}</td><td>${esc(r.scope)}</td><td class="mono">${esc(r.binding_from)}</td><td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.source)}</a></td></tr>`).join("")}</tbody></table></div>
    <h3>Bargaining-council agreements, wage schedules, circulars and exemptions<span class="c">${fmt(docs.length)} of ${fmt(L.documents.length)}</span></h3>
    <div class="toolbar"><select id="lb-c" aria-label="Council">${opt("", lab.council, "All councils")}${councils.map((c: any) => opt(c.id, lab.council, `${c.name} (${c.n})`)).join("")}</select>
      <select id="lb-k" aria-label="Kind">${opt("", lab.kind, "All kinds")}${kinds.map((k) => opt(k, lab.kind)).join("")}</select>
      <select id="lb-y" aria-label="Year">${opt("", lab.year, "All years")}${years.map((y) => opt(y, lab.year)).join("")}</select>
      <input id="lb-q" placeholder="Filter by title…" value="${esc(lab.q)}" aria-label="Filter by title"><button class="tb" id="lb-x">Export CSV</button><button class="tb" id="lb-j">Export JSON</button>
      <span class="note">Documents are linked as each council publishes them; the year is the first year named (the start of an agreement period).</span></div>
    <div class="tscroll"><table class="t"><thead><tr><th>Year</th><th>Council</th><th>Kind</th><th>Document</th><th>Employers named</th><th>Found on</th></tr></thead><tbody>
    ${docs.slice(0, 300).map((d: any) => `<tr><td class="mono">${esc(d.year || "")}</td><td>${esc(d.council.toUpperCase())}</td><td>${esc(d.kind)}</td><td><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a>${d.kept_from ? ` <span class="dim">(kept from ${esc(String(d.kept_from).slice(0, 10))})</span>` : ""}</td>
      <td>${(d.employers || []).map((e: string) => `<a href="#s=${esc(e)}" data-sup="${esc(e)}">${esc(L.employers[e]?.name || e)}</a> <a class="sm" href="${esc(L.employers[e]?.saflii || "")}" target="_blank" rel="noopener">labour courts ↗</a>`).join("<br>")}</td>
      <td class="sm"><a href="${esc(d.found_on)}" target="_blank" rel="noopener">${esc(new URL(d.found_on).pathname)}</a></td></tr>`).join("")}</tbody></table></div>
    ${docs.length > 300 ? `<div class="note">First 300 of ${fmt(docs.length)}; export has them all${can("bulkExport") ? "" : " (up to the free-tier limit)"}.</div>` : ""}
    <h3>Labour Research Service publications<span class="c">${L.lrs.length}</span></h3>
    ${L.lrs.slice(0, 40).map((p: any) => `<div class="feeditem"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a><div class="meta">${esc(p.date)}</div><div class="sm mu">${esc(p.summary)}</div></div>`).join("")}
    <h3>Sources</h3><table class="t"><tbody>${L.sources.map((x: any) => `<tr><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a></td><td class="mono">${fmt(x.n)}</td><td class="mono">${esc(String(x.retrieved).slice(0, 10))}</td></tr>`).join("")}</tbody></table>
    <h3>Not added, and why</h3><table class="t"><tbody>${L.not_added.map((n: any) => `<tr><td><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.name)}</a></td><td>${esc(n.why)}</td></tr>`).join("")}</tbody></table>`;
  const set = (k: keyof typeof lab) => (e: Event) => { lab[k] = (e.target as HTMLInputElement).value; labour(); };
  (document.getElementById("lb-c") as HTMLSelectElement).onchange = set("council");
  (document.getElementById("lb-k") as HTMLSelectElement).onchange = set("kind");
  (document.getElementById("lb-y") as HTMLSelectElement).onchange = set("year");
  let tm: any; (document.getElementById("lb-q") as HTMLInputElement).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { lab.q = (e.target as HTMLInputElement).value; labour().then(() => { const i = document.getElementById("lb-q") as HTMLInputElement; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 250); };
  (document.getElementById("lb-x") as HTMLElement).onclick = () => exportTable("labour-documents", ["year", "council", "sector", "kind", "title", "url", "found_on", "employers"],
    docs.map((d: any) => [d.year, name(d.council), d.sector, d.kind, d.title, d.url, d.found_on, (d.employers || []).map((e: string) => L.employers[e]?.name || e)]), `Bargaining-council documents as published on each council's site; built ${L.built}.`);
  (document.getElementById("lb-j") as HTMLElement).onclick = () => exportJSON("labour", { built: L.built, filter: lab, statutory: L.statutory, documents: docs.slice(0, can("bulkExport") ? docs.length : 500), lrs: L.lrs, sources: L.sources, not_added: L.not_added });
}

async function watchlist() {
  const W = watches();
  // suppliers can be re-counted from the index without opening each profile
  if (W.some((w) => w.kind === "supplier")) { const S = await suppliers().catch(() => null); if (S) for (const w of W.filter((w) => w.kind === "supplier")) { const r = S.rows.find((x) => x[0] === w.id); if (r) updateCount("supplier", w.id, r[2] + r[4] + r[6] + r[7] + r[8]); } }
  const L = watches();
  $("#dockbody").innerHTML = `<div class="note">Your watchlist is kept in this browser only (nothing is sent anywhere). Items show how many records were added since you last opened them. Use ☆ Watch on any supplier, tender, plot, record, department or flag.</div>
    ${L.length ? `<div class="tscroll"><table class="t"><thead><tr><th>Item</th><th>Kind</th><th>District</th><th>Records</th><th>Change</th><th>Added</th><th></th></tr></thead><tbody>
    ${L.map((w, k) => `<tr class="click" data-wopen="${k}"><td>${esc(w.label)}</td><td>${esc(w.kind)}</td><td>${esc(w.district || "city-wide")}</td><td class="mono">${fmt(w.n)}</td><td class="mono">${w.n !== w.seen ? `<b class="new">${w.n - w.seen > 0 ? "+" : ""}${w.n - w.seen}</b>` : ""}</td><td class="mono">${esc(w.added)}</td><td><button class="mini" data-wdel="${k}">Remove</button></td></tr>`).join("")}</tbody></table></div>
    <button class="tb" id="w-x">Export watchlist (CSV)</button>` : `<div class="empty">Nothing watched yet.</div>`}
    <h3>Alert rules</h3>${can("alertRules") ? `<div class="note">Alert rules (for example "any new award to a watched supplier") will be delivered once accounts are switched on. Your watchlist changes above already show here and on the start page.</div>` : `<div class="note">${esc(proNote("alertRules"))}</div>`}`;
  $("#dockbody").querySelectorAll("[data-wdel]").forEach((b) => (b as HTMLElement).onclick = (e) => { e.stopPropagation(); const w = L[+(b as HTMLElement).dataset.wdel!]; toggleWatch(w); watchlist(); });
  $("#dockbody").querySelectorAll("[data-wopen]").forEach((r) => (r as HTMLElement).onclick = () => openWatched(L[+(r as HTMLElement).dataset.wopen!]));
  const x = document.getElementById("w-x"); if (x) x.onclick = () => exportCSV("watchlist", ["label", "kind", "id", "district", "records", "seen", "added"], L.map((w) => [w.label, w.kind, w.id, w.district, w.n, w.seen, w.added]));
}

async function sources() {
  const LB = await getJSON<any>(METRO + "labour.json").catch(() => null); const RG = await getJSON<any>(METRO + "registry.json").catch(() => null);
  const mm = await moneyMeta().catch(() => null); const NN = await getJSON<any>(METRO + "notices.json").catch(() => null); const J = await getJSON<any>(METRO + "justice.json").catch(() => null); const F = await getJSON<any>(METRO + "feed.json").catch(() => null);
  const metro = `<h3>Personal information and identity</h3><div class="note warnbox">${esc(PERSONAL_NOTE)} Officials named on tenders appear in their public capacity.</div><div class="note">${esc(IDENTITY_NOTE)}</div>
    <div class="note">Place tags (news, tribunal cases, gazette notices) are matched by suburb name and placed at the suburb centre, not an address. Erven are matched by erf number and suburb name as published. Pattern flags are patterns in published data, each with its rule, its records and, where one applies, the regulation it cites.</div>
    <div class="note">Money, Justice and Notices panels are in English only in this version; the map, layers and plot dossiers are in English and Afrikaans.</div>
    ${(mm as any)?.warnings?.length || NN?.warnings?.length ? `<h3>Parser and source warnings</h3>${[...((mm as any)?.warnings || []), ...(NN?.warnings || [])].map((w: string) => `<div class="note warnbox">${esc(w)}</div>`).join("")}` : ""}
    <h3>City-wide sources</h3><table class="t"><thead><tr><th>Group</th><th>Source</th><th>Records</th><th>Fetched</th></tr></thead><tbody>
    ${mm ? Object.values(mm.tables).map((x: any) => `<tr><td class="dim">Money</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a> · ${esc(x.source)}${x.note ? `<div class="sm dim">${esc(x.note)}</div>` : ""}</td><td class="mono">${fmt(x.n)}</td><td class="mono">${esc(x.retrieved.slice(0, 10))}</td></tr>`).join("") : ""}
    ${J ? J.sources.map((x: any) => `<tr><td class="dim">Justice</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a></td><td class="mono">${fmt(x.n)}</td><td class="mono">${esc(x.retrieved.slice(0, 10))}</td></tr>`).join("") : ""}
    ${LB ? LB.sources.map((x: any) => `<tr><td class="dim">Labour</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a></td><td class="mono">${fmt(x.n)}</td><td class="mono">${esc(String(x.retrieved).slice(0, 10))}</td></tr>`).join("") + LB.statutory.slice(0, 1).map((x: any) => `<tr><td class="dim">Labour</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.source)}</a> (statutory minimum rates)</td><td class="mono">${LB.statutory.length}</td><td class="mono">${esc(x.binding_from)}</td></tr>`).join("") : ""}
    ${RG ? `<tr><td class="dim">Companies</td><td>Company-register cache: ${esc(RG.status.provider === "configured" ? "licensed provider configured" : "no licensed provider configured; registration numbers printed in published records only")}. Up to ${RG.batch} suppliers a day, flagged first; ${fmt(RG.queue_left)} not yet looked up.</td><td class="mono">${fmt(Object.keys(RG.records).length)}</td><td class="mono">${esc(RG.built.slice(0, 10))}</td></tr>` : ""}
    ${F ? F.feeds.map((x: any) => `<tr><td class="dim">Feed</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a>${x.error ? ` <span class="warn">unavailable: ${esc(x.error)}</span>` : ""}</td><td class="mono">${fmt(x.n)}</td><td class="mono">${esc(x.retrieved.slice(0, 10))}</td></tr>`).join("") : ""}
    </tbody></table>
    <h3>Not added, and why</h3><table class="t"><tbody>${(LB?.not_added || []).map((n: any) => `<tr><td><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.name)}</a></td><td>${esc(n.why)}</td></tr>`).join("")}${NOT_ADDED.map(([n, u, w]) => `<tr><td><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a></td><td>${esc(w)}</td></tr>`).join("")}${(J?.not_added || []).map((n: any) => `<tr><td><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.name)}</a></td><td>${esc(n.why)}</td></tr>`).join("")}</tbody></table>`;
  if (!DISTRICT) { $("#dockbody").innerHTML = `<div class="note">Everything city-wide in Cape Monitor, where it comes from and when it was fetched. Each district's GIS layers are listed under Sources inside that district.</div>${metro}`; return; }
  const byTheme = M.themes.map((th) => ({ th, ls: M.layers.filter((l) => l.theme === th.id) })).filter((x) => x.ls.length);
  $("#dockbody").innerHTML = `<div class="note">Everything in Cape Monitor, where it comes from and when it was fetched. Data built ${esc(M.built.slice(0, 16).replace("T", " "))} UTC. Counts are records inside the ${esc(M.district.name)} planning district unless marked city-wide.</div>
    <table class="t"><thead><tr><th>Theme</th><th>Layer or table</th><th>Records</th><th>Source</th><th>Fetched</th></tr></thead><tbody>
    ${byTheme.map(({ th, ls }) => ls.map((l) => `<tr><td class="dim">${esc(th.en)}</td><td>${esc(l.name)}</td><td class="mono">${fmt(l.n)}${l.server_count && l.server_count !== l.n ? ` <span class="dim">(server ${fmt(l.server_count)})</span>` : ""}</td><td><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.source)}</a></td><td class="mono">${esc((l.retrieved || "").slice(0, 10))}</td></tr>`).join("")).join("")}
    ${M.tables.map((x) => `<tr><td class="dim">Records</td><td>${esc(x.name)}</td><td class="mono">${fmt(x.n)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">City of Cape Town Open Data Portal</a> ${x.scope === "city-wide" ? "· city-wide" : ""}</td><td class="mono">${esc((x.retrieved || "").slice(0, 10))}</td></tr>`).join("")}
    ${M.feeds.map((x) => `<tr><td class="dim">Feed</td><td>${esc(x.name)}</td><td class="mono">${fmt(x.n)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">RSS</a></td><td class="mono">${esc((x.retrieved || "").slice(0, 10))}</td></tr>`).join("")}
    </tbody></table>
    ${metro}
    <h3>Left out (${M.skipped.filter((s) => s.why !== "no records in this district").length}) and empty here (${M.skipped.filter((s) => s.why === "no records in this district").length})</h3>
    <table class="t"><thead><tr><th>Layer</th><th>Service</th><th>Why</th></tr></thead><tbody>${M.skipped.sort((a, b) => a.why.localeCompare(b.why)).map((s) => `<tr><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a></td><td class="dim">${esc(s.service)}</td><td>${esc(s.why)}</td></tr>`).join("")}</tbody></table>`;
}

async function heritage() {
  const H = await getJSON<any>(DP + "heritage.json").catch(() => null);
  if (!H) { $("#dockbody").innerHTML = `<div class="empty">No heritage module.</div>`; return; }
  $("#dockbody").innerHTML = `<div class="note">The Blaauwberg heritage research register: ${H.finds.length} sourced finds (middens, burials, shipwrecks, Stone Age sites, battle), ${H.registers.length} records from SAHRIS, Wikidata and OpenStreetMap, and ${H.stories.length} stories. The City's heritage inventory is in the Heritage layers on the left.</div>
    <div class="grid">${H.finds.map((f: any, k: number) => `<div class="tile"><div class="caps">${esc(f.cat)} · ${esc(f.place)}${f.radius ? " ±" + fmt(f.radius) + " m" : ""}</div><b>${esc(f.name)}</b><div class="sm" style="margin:4px 0">${esc(f.facts)}</div>
      <div class="links"><button class="mini" data-fly="${f.lon},${f.lat}">Show on map</button>${f.sources.slice(0, 3).map((s: any) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title.slice(0, 60))}…</a>`).join("")}</div></div>`).join("")}</div>
    <h3>Stories</h3><div class="grid">${H.stories.map((s: any) => `<div class="tile"><div class="caps">${esc(s.date)}</div><b>${esc(s.title)}</b><div class="sm" style="white-space:pre-wrap;margin-top:4px">${esc(s.text)}</div><div class="links">${s.sources.map((x: any) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title.slice(0, 50))}</a>`).join("")}</div></div>`).join("")}</div>`;
}

const TABS: [string, () => any][] = [["brief", brief], ["money", () => moneyTab($("#dockbody"))], ["justice", justice], ["labour", labour], ["notices", notices], ["feed", feed],
  ...(DISTRICT ? [["activity", activity], ["records", () => records()]] as [string, () => any][] : []), ["watchlist", watchlist],
  ...(DISTRICT === "blaauwberg" ? [["heritage", heritage]] as [string, () => any][] : []), ["sources", sources]];
const NOT_ADDED: [string, string, string][] = [
  ["Government Gazette (national) and gazettes.africa", "https://gazettes.africa/", "gazettes.africa now asks for a login (HTTP 401) for every page; the national gazette archive on gov.za did not answer from the build machine. The Western Cape Provincial Gazette is read directly from the Province (Notices panel)."],
  ["City land-use applications and public participation notices", "https://www.capetown.gov.za/", "Published through the City's e-services and notice pages, not as data; not yet read."],
  ["Council and committee agendas and minutes", "https://www.capetown.gov.za/", "Published as PDFs per meeting; not yet read."],
  ["CIPC company register: directors, registration dates, addresses", "https://www.bizportal.gov.za/", "CIPC BizPortal requires a personal login under POPIA and allows about 20 searches a day; it is not read automatically. B2BHint answers automated requests with a block page and is linked for manual searches only. Registration numbers printed in published records are used; a licensed provider can be added (up to 200 suppliers a day, flagged suppliers first, results kept between runs). Until then director networks and the 'award within 12 months of registration' flag stay empty."],
  ["SAPS station crime statistics", "https://www.saps.gov.za/services/crimestats.php", "saps.gov.za did not answer from the build machine. The City's police station layer is in each district under Justice."],
  ["ISS Crime Hub", "https://crimehub.org/", "Interactive pages only; no published data file found."],
  ["Community newspapers (Tygerburger, Netwerk24 locals)", "https://www.netwerk24.com/", "Feeds refuse automated requests (HTTP 403)."],
  ["Live AIS ships", "https://aisstream.io/", "Not active. Needs a persistent listener (a Cloudflare Durable Object, paid Workers plan) and a free aisstream.io key; a connection per page view is too slow and incomplete."],
  ["City web procurement portal (open RFQs)", "https://web1.capetown.gov.za/web1/procurementportal/", "Did not answer from the build machine. Open City tenders are taken from the national eTender portal instead."],
];
export function renderTabs() {
  $("#tabs").innerHTML = TABS.map(([k]) => `<button data-tab="${k}" class="${k === tab ? "on" : ""}">${t(k as any)}</button>`).join("") + `<span class="sp"></span><button data-size="1" title="Bigger or smaller">⇕</button>`;
}
export function openTab(k: string) { tab = k; renderTabs(); if (document.body.classList.contains("dockmin")) document.body.classList.remove("dockmin"); TABS.find((x) => x[0] === k)![1](); }
export function bindDock() {
  renderTabs();
  $("#tabs").onclick = (e) => { const b = (e.target as HTMLElement).closest("button"); if (!b) return;
    if (b.dataset.size) { const c = document.body.classList; c.contains("dockbig") ? (c.remove("dockbig"), c.add("dockmin")) : c.contains("dockmin") ? c.remove("dockmin") : c.add("dockbig"); setTimeout(() => map.resize(), 60); return; }
    openTab(b.dataset.tab!); };
  $("#dockbody").onclick = (e) => { const el = e.target as HTMLElement; const r = el.closest("[data-rec]") as HTMLElement | null; if (r) { const [l, i] = r.dataset.rec!.split(":"); openRecord(l, +i); }
    const f = el.closest("[data-fly]") as HTMLElement | null; if (f) { const [x, y] = f.dataset.fly!.split(",").map(Number); map.flyTo({ center: [x, y], zoom: 15 }); } };
  renderTabs(); $("#dockbody").innerHTML = `<div class="empty">${t("loading")}</div>`;
  // the first panel waits until the map has drawn, so it does not compete with the first paint
  let done = false; const go = () => { if (!done) { done = true; openTab(tab); } };
  map.once("idle", go); setTimeout(go, 4000);
}
export type { Table };
