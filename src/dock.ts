// The bottom dock: Brief (district and suburb statistics), Activity (latest City records), Feed (news and GI-TOC),
// Records (every table, searchable), Sources (what is in, when it was fetched, what was left out and why), Heritage.
import { M, getJSON, tableRows, layerById, Table } from "./data";
import { t, esc, fmt, money } from "./i18n";
import { openRecord } from "./inspector";
import { map } from "./map";

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

async function brief() {
  areas ??= await getJSON("data/areas.json");
  const subs = Object.keys(areas!.suburb).filter((k) => /^[ -~]+$/.test(k)).sort();
  const sel = (document.getElementById("area-sel") as HTMLSelectElement | null)?.value || "";
  const list = sel ? [areas!.suburb[sel]] : subs.map((k) => areas!.suburb[k]);
  const a = sel ? areas!.suburb[sel] : null;
  const months = sum(list, "sr_month").sort((x, y) => x[0].localeCompare(y[0])).filter(([m]) => m);
  const types = sum(list, "sr_type").sort((x, y) => y[1] - x[1]);
  const py = sum(list, "plans_year").sort((x, y) => x[0].localeCompare(y[0])), pv = sum(list, "plans_value").sort((x, y) => x[0].localeCompare(y[0]));
  const L = (id: string) => layerById.get(id);
  const kpi = (v: any, l: string) => `<div class="kpi"><b>${v}</b><span>${esc(l)}</span></div>`;
  const parcels = L(M.parcels.layer);
  const pop = a?.population ? Object.entries(a.population).filter(([k, v]) => typeof v === "number" && !/id/i.test(k)) : [];
  $("#dockbody").innerHTML = `<div class="toolbar"><b>${sel ? esc(sel) : esc(M.district.name)}</b><select id="area-sel"><option value="">Whole district</option>${subs.map((s) => `<option ${s === sel ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <span class="note">Service requests since Jan 2023; building plans matched to plots in this district.</span></div>
    <div class="kpis">${!sel ? kpi(fmt(parcels?.n || 0), "plots (erven)") : ""}${kpi(fmt(list.reduce((s, x) => s + x.sr_total, 0)), "service requests")}${kpi(fmt(py.reduce((s, x) => s + x[1], 0)), "building plans")}
      ${kpi(money(pv.reduce((s, x) => s + x[1], 0) / 1e6) + "m", "declared building value")}${pop.slice(0, 3).map(([k, v]) => kpi(fmt(v as number), k.replace(/_/g, " "))).join("")}
      ${!sel ? M.layers.filter((l) => ["police-stations", "fire-stations", "schools", "health-care-facilities"].includes(l.id)).map((l) => kpi(fmt(l.n), l.name)).join("") : ""}</div>
    <div class="grid"><div class="tile"><div class="caps">Service requests per month</div>${spark(months)}</div>
      <div class="tile"><div class="caps">Top service-request types</div>${bars(types, 10)}</div>
      <div class="tile"><div class="caps">Building plans per year</div>${bars(py.map(([y, n]) => [y, n] as [string, number]).reverse(), 13)}</div>
      ${!sel ? `<div class="tile"><div class="caps">Busiest suburbs (service requests)</div>${bars(Object.entries(areas!.suburb).filter(([k]) => /^[ -~]+$/.test(k)).map(([k, v]) => [k, v.sr_total] as [string, number]).sort((x, y) => y[1] - x[1]), 12)}</div>` : ""}
      ${a?.licences ? `<div class="tile"><div class="caps">Business licences</div>${bars(a.licences, 8)}</div>` : ""}</div>`;
  (document.getElementById("area-sel") as HTMLSelectElement).onchange = () => brief();
}

async function activity() {
  const L = layerById.get("service-requests"); if (!L) { $("#dockbody").innerHTML = `<div class="empty">No service-request data.</div>`; return; }
  const last = Math.floor((L.n - 1) / M.parcels.shard);
  const [a, b] = await Promise.all([getJSON<any[][]>(`data/attrs/service-requests/${last}.json`), last > 0 ? getJSON<any[][]>(`data/attrs/service-requests/${last - 1}.json`) : Promise.resolve([])]);
  const f = (k: string) => L.fields.findIndex((x) => x[0] === k);
  const rows = [...b.map((r, k) => [r, (last - 1) * M.parcels.shard + k] as const), ...a.map((r, k) => [r, last * M.parcels.shard + k] as const)].reverse().slice(0, 300);
  $("#dockbody").innerHTML = `<div class="note">Latest ${rows.length} service requests logged in ${esc(M.district.name)} (of ${fmt(L.n)} since January 2023). Click one to see it on the map.</div>
    <table class="t"><thead><tr><th>Logged</th><th>Type</th><th>Suburb</th><th>Ward</th><th>Completed</th><th>Work centre</th></tr></thead><tbody>
    ${rows.map(([r, i]) => `<tr class="click" data-rec="service-requests:${i}"><td class="mono">${esc(r[f("Created_On_Date")])}</td><td>${esc(r[f("C3_Complaint_Type")] || r[f("Notification_type")])}</td><td>${esc(r[f("Suburb")])}</td><td>${esc(r[f("Ward")])}</td><td class="mono">${esc(r[f("Completed_Date")] || "open")}</td><td class="dim">${esc(r[f("Work_Center")])}</td></tr>`).join("")}</tbody></table>`;
}

async function feed() {
  const F = await getJSON<{ items: any[] }>("data/feed.json");
  const only = (document.getElementById("feed-local") as HTMLInputElement | null)?.checked ?? false;
  const items = F.items.filter((i) => !only || i.places.some((p: string) => !["Cape Town", "Western Cape", "West Coast"].includes(p)));
  items.sort((a, b) => Date.parse(b.date || 0) - Date.parse(a.date || 0));
  $("#dockbody").innerHTML = `<div class="toolbar"><label><input type="checkbox" id="feed-local" ${only ? "checked" : ""}> Only items naming a place in ${esc(M.district.name)}</label>
      ${M.feeds.map((f) => `<span class="pill">${esc(f.name)} · ${f.n}</span>`).join("")}</div>
    ${items.map((i) => `<div class="feeditem"><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.title)}</a><div class="meta">${esc(M.feeds.find((f) => f.id === i.feed)?.name)} · ${esc(i.date)}${i.places.length ? " · " + i.places.map((p: string) => `<span class="pill">${esc(p)}</span>`).join("") : ""}</div><div class="sm mu">${esc(i.summary)}</div></div>`).join("") || `<div class="empty">No items.</div>`}`;
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
      <span class="note">${fmt(rows.length)} rows${rows.length > 500 ? " (first 500 shown)" : ""} · ${T.scope === "city-wide" ? "whole city" : esc(M.district.name)} · <a href="${esc(T.url)}" target="_blank" rel="noopener">source</a> · fetched ${esc((T.retrieved || "").slice(0, 10))}</span></div>
    ${T.note ? `<div class="note">${esc(T.note)}</div>` : ""}${groupHtml}
    <table class="t"><thead><tr>${T.fields.map((f, k) => `<th data-sort="${k}" title="${esc(f[0])}">${esc(f[1] || f[0])}${tv!.sort === k ? (tv!.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
    <tbody>${show.map((r) => `<tr>${r.map((v, k) => `<td${k === numCol ? ' class="mono"' : ""}>${v == null ? "" : k === numCol ? money(v) : esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  ($("#tv-t") as HTMLSelectElement).onchange = (e) => records((e.target as HTMLSelectElement).value);
  let tm: any; ($("#tv-q") as HTMLInputElement).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { tv!.q = (e.target as HTMLInputElement).value; records(); setTimeout(() => { const el = $("#tv-q") as HTMLInputElement; el.focus(); el.setSelectionRange(el.value.length, el.value.length); }); }, 250); };
  ($("#tv-g") as HTMLSelectElement).onchange = (e) => { tv!.group = +(e.target as HTMLSelectElement).value; records(); };
  $("#dockbody").querySelectorAll("th[data-sort]").forEach((th) => (th as HTMLElement).onclick = () => { const k = +(th as HTMLElement).dataset.sort!; tv!.dir = tv!.sort === k ? -tv!.dir : -1; tv!.sort = k; records(); });
}

function sources() {
  const byTheme = M.themes.map((th) => ({ th, ls: M.layers.filter((l) => l.theme === th.id) })).filter((x) => x.ls.length);
  $("#dockbody").innerHTML = `<div class="note">Everything in Cape Monitor, where it comes from and when it was fetched. Data built ${esc(M.built.slice(0, 16).replace("T", " "))} UTC. Counts are records inside the ${esc(M.district.name)} planning district unless marked city-wide.</div>
    <table class="t"><thead><tr><th>Theme</th><th>Layer or table</th><th>Records</th><th>Source</th><th>Fetched</th></tr></thead><tbody>
    ${byTheme.map(({ th, ls }) => ls.map((l) => `<tr><td class="dim">${esc(th.en)}</td><td>${esc(l.name)}</td><td class="mono">${fmt(l.n)}${l.server_count && l.server_count !== l.n ? ` <span class="dim">(server ${fmt(l.server_count)})</span>` : ""}</td><td><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.source)}</a></td><td class="mono">${esc((l.retrieved || "").slice(0, 10))}</td></tr>`).join("")).join("")}
    ${M.tables.map((x) => `<tr><td class="dim">Records</td><td>${esc(x.name)}</td><td class="mono">${fmt(x.n)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">City of Cape Town Open Data Portal</a> ${x.scope === "city-wide" ? "· city-wide" : ""}</td><td class="mono">${esc((x.retrieved || "").slice(0, 10))}</td></tr>`).join("")}
    ${M.feeds.map((x) => `<tr><td class="dim">Feed</td><td>${esc(x.name)}</td><td class="mono">${fmt(x.n)}</td><td><a href="${esc(x.url)}" target="_blank" rel="noopener">RSS</a></td><td class="mono">${esc((x.retrieved || "").slice(0, 10))}</td></tr>`).join("")}
    </tbody></table>
    <h3>Left out (${M.skipped.filter((s) => s.why !== "no records in this district").length}) and empty here (${M.skipped.filter((s) => s.why === "no records in this district").length})</h3>
    <table class="t"><thead><tr><th>Layer</th><th>Service</th><th>Why</th></tr></thead><tbody>${M.skipped.sort((a, b) => a.why.localeCompare(b.why)).map((s) => `<tr><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a></td><td class="dim">${esc(s.service)}</td><td>${esc(s.why)}</td></tr>`).join("")}</tbody></table>`;
}

async function heritage() {
  const H = await getJSON<any>("data/heritage.json").catch(() => null);
  if (!H) { $("#dockbody").innerHTML = `<div class="empty">No heritage module.</div>`; return; }
  $("#dockbody").innerHTML = `<div class="note">The Blaauwberg heritage research register: ${H.finds.length} sourced finds (middens, burials, shipwrecks, Stone Age sites, battle), ${H.registers.length} records from SAHRIS, Wikidata and OpenStreetMap, and ${H.stories.length} stories. The City's heritage inventory is in the Heritage layers on the left.</div>
    <div class="grid">${H.finds.map((f: any, k: number) => `<div class="tile"><div class="caps">${esc(f.cat)} · ${esc(f.place)}${f.radius ? " ±" + fmt(f.radius) + " m" : ""}</div><b>${esc(f.name)}</b><div class="sm" style="margin:4px 0">${esc(f.facts)}</div>
      <div class="links"><button class="mini" data-fly="${f.lon},${f.lat}">Show on map</button>${f.sources.slice(0, 3).map((s: any) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title.slice(0, 60))}…</a>`).join("")}</div></div>`).join("")}</div>
    <h3>Stories</h3><div class="grid">${H.stories.map((s: any) => `<div class="tile"><div class="caps">${esc(s.date)}</div><b>${esc(s.title)}</b><div class="sm" style="white-space:pre-wrap;margin-top:4px">${esc(s.text)}</div><div class="links">${s.sources.map((x: any) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title.slice(0, 50))}</a>`).join("")}</div></div>`).join("")}</div>`;
}

const TABS: [string, () => any][] = [["brief", brief], ["activity", activity], ["feed", feed], ["records", () => records()], ["heritage", heritage], ["sources", sources]];
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
  openTab("brief");
}
export type { Table };
