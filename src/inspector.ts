import type * as maplibregl from "maplibre-gl";
// The right-hand panel: what you clicked, first; then everything else at that point; for a plot, the full dossier.
import { M, layerById, record, val, dossier, getJSON, tableRows, Field, DP, DISTRICT, METRO, districtUrl, DataIndex } from "./data";
import { map, pick, highlight, catColour, THEME_COLOUR, tileSources } from "./map";
import { overlayCard } from "./live";
import { watchButton, exportJSON, markSeen, watches } from "./util";
import { flagsData } from "./money";
import { t, esc, fmt, money } from "./i18n";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
let seq = 0, showEmpty = false;
export let current: { kind: "feature" | "plot"; layer: string; i: number } | null = null;

const kv = (fields: Field[], values: any[]) => `<table class="kv">${fields.map((f, k) => [f, values[k]] as const)
  .filter(([, v]) => showEmpty || (v != null && v !== "")).map(([f, v]) => `<tr><td title="${esc(f[0])}">${esc(f[1] || f[0])}</td><td class="${v == null || v === "" ? "e" : ""}">${v == null || v === "" ? "—" : esc(v)}</td></tr>`).join("")}</table>`;
const restLink = (layerId: string, oid: any) => { const L = layerById.get(layerId); return L && oid != null ? `${L.url}/query?where=OBJECTID%3D${oid}&outFields=*&returnGeometry=false&f=html` : null; };
const swatch = (layerId: string, c?: string) => { const L = layerById.get(layerId); if (!L) return ""; const col = c ? catColour(L, c) : THEME_COLOUR[L.theme];
  return `<span class="sw ${L.geom === "Point" ? "pt" : L.geom === "Polyline" ? "ln" : ""}" style="background:${col}"></span>`; };
const labelOf = (layerId: string, rec: any) => { const L = layerById.get(layerId)!; const v = L.label ? val(rec, L.label) : null; return v ? String(v) : L.name; };

export function setHash(h: string) { history.replaceState(null, "", "#" + h); }

export async function inspectPoint(lngLat: maplibregl.LngLat, focus?: { layer: string; i: number }) {
  const s = ++seq;
  const pt = map.project(lngLat);
  let hits = pick(pt);
  // what you meant: a point or line under the pointer first; otherwise the plot; otherwise the smallest area that contains the point
  const parcelHit = hits.find((h) => h.layer === M.parcels.layer);
  const isArea = (h: { layer: string }) => layerById.get(h.layer)?.geom === "Polygon";
  const bboxArea = (f: any) => { if (!f?.geometry) return Infinity; let a = [180, 90, -180, -90]; const w = (c: any) => typeof c[0] === "number" ? (a = [Math.min(a[0], c[0]), Math.min(a[1], c[1]), Math.max(a[2], c[0]), Math.max(a[3], c[1])]) : c.forEach(w); w(f.geometry.coordinates); return (a[2] - a[0]) * (a[3] - a[1]); };
  hits = [...hits.filter((h) => !isArea(h)), ...(parcelHit ? [parcelHit] : []), ...hits.filter((h) => isArea(h) && h !== parcelHit).sort((x, y) => bboxArea(x.f) - bboxArea(y.f))];
  if (focus) hits = [{ layer: focus.layer, i: focus.i, f: null as any }, ...hits.filter((h) => !(h.layer === focus.layer && h.i === focus.i))];
  const primary = hits[0];
  document.body.classList.add("inspect");
  if (primary?.layer.startsWith("live-")) { highlight([{ type: "Feature", properties: {}, geometry: primary.f.geometry }]); $("#right").innerHTML = overlayCard(primary.layer, primary.i) + (hits.length > 1 ? `<h3>${t("alsohere")}<span class="c">${hits.length - 1}</span></h3><div class="note">Click again closer to the other markers.</div>` : ""); return; }
  if (!primary) { $("#right").innerHTML = `<div class="card"><div class="kicker">${lngLat.lat.toFixed(6)}, ${lngLat.lng.toFixed(6)}</div><p class="empty">${map.getZoom() < 14 ? t("zoomplot") : t("nothing")}</p></div>`; highlight([]); return; }
  if (primary.layer === M.parcels.layer) return showPlot(primary.i, primary.f, s, hits);
  return showFeature(primary.layer, primary.i, primary.f, s, hits, parcelHit?.i);
}

async function showFeature(layerId: string, i: number, f: any, s: number, hits: { layer: string; i: number; f: any }[], plotI?: number) {
  const L = layerById.get(layerId)!; const rec = await record(layerId, i); if (s !== seq) return;
  current = { kind: "feature", layer: layerId, i }; document.body.classList.add("inspect");
  if (f) highlight([{ type: "Feature", properties: {}, geometry: f.geometry }]);
  const oid = rec ? rec.values[rec.values.length - 1] : null;
  const cat = L.cat && rec ? val(rec, L.cat) : null;
  const others = hits.filter((h) => !(h.layer === layerId && h.i === i));
  const lines = await Promise.all(others.slice(0, 14).map(async (h) => { const r = await record(h.layer, h.i); const HL = layerById.get(h.layer)!;
    return `<div class="row" data-go="${h.layer}:${h.i}">${swatch(h.layer, HL.cat && r ? String(val(r, HL.cat)) : undefined)}<span class="t">${esc(labelOf(h.layer, r))}</span><small>${esc(HL.name)}</small></div>`; }));
  if (s !== seq) return;
  $("#right").innerHTML = `<div class="card primary"><div class="kicker">${esc(L.name)}</div><h2>${esc(labelOf(layerId, rec))}</h2>
    ${cat ? `<span class="pill">${swatch(layerId, String(cat))} ${esc(cat)}</span>` : ""}
    ${rec ? kv(rec.fields.slice(0, -1), rec.values) : ""}
    <div class="links">${restLink(layerId, oid) ? `<a href="${restLink(layerId, oid)}" target="_blank" rel="noopener">${t("cityrec")} ↗</a>` : ""}<button class="mini" data-share="f=${layerId}:${oid ?? i}">${t("share")}</button>
    ${watchButton("record", `${DISTRICT}|${layerId}|${oid ?? i}`, labelOf(layerId, rec), 1, DISTRICT)}<button class="mini" data-dl="1">Export (JSON)</button>
    <label class="mini"><input type="checkbox" id="empty" ${showEmpty ? "checked" : ""}> ${t("showempty")}</label></div>
    <div class="note">${esc(L.source)} · ${esc((L.retrieved || "").slice(0, 10))}</div></div>
    ${plotI != null ? `<div class="row" data-plot="${plotI}"><span class="t">▭ ${t("plot")}: open the full plot dossier</span></div>` : ""}
    ${lines.length ? `<h3>${t("alsohere")}<span class="c">${others.length}</span></h3>${lines.join("")}` : ""}`;
  $("#right").scrollTop = 0; setHash(`f=${layerId}:${oid ?? i}`);
  const dl = $("#right").querySelector("[data-dl]") as HTMLElement | null;
  if (dl && rec) dl.onclick = () => exportJSON(`${layerId}-${oid ?? i}`, { layer: L.name, source: L.source, url: L.url, retrieved: L.retrieved, record: Object.fromEntries(rec.fields.map((f, k) => [f[1] || f[0], rec.values[k]])) });
}

async function showPlot(i: number, f: any, s: number, hits: { layer: string; i: number; f: any }[] = []) {
  const P = layerById.get(M.parcels.layer)!;
  const [rec, D] = await Promise.all([record(P.id, i), dossier(i)]); if (s !== seq) return;
  current = { kind: "plot", layer: P.id, i }; document.body.classList.add("inspect");
  if (f) highlight([{ type: "Feature", properties: {}, geometry: f.geometry }]);
  const v = (k: string) => val(rec, k);
  const addr = [v("ADR_NO_PRF"), v("ADR_NO"), v("ADR_NO_SFX")].filter(Boolean).join("") + " " + [v("STR_NAME"), v("LU_STR_NAME_TYPE")].filter(Boolean).join(" ");
  const key = v("SL_LAND_PRCL_KEY");
  // sections, each loaded in parallel
  const zoneRows = async (items: [string, number][] = []) => (await Promise.all(items.map(async ([lid, k]) => { const r = await record(lid, k); const L = layerById.get(lid); if (!L) return "";
    return `<div class="row" data-go="${lid}:${k}">${swatch(lid, L.cat && r ? String(val(r, L.cat)) : undefined)}<span class="t">${esc(labelOf(lid, r))}${L.cat && r && val(r, L.cat) ? ` <span class="dim">· ${esc(val(r, L.cat))}</span>` : ""}</span><small>${esc(L.name)}</small></div>`; }))).join("");
  const plansT = M.tables.find((x) => x.id === "building-plans");
  const plans = async () => { if (!D.plans?.length || !plansT) return ""; const rows = await Promise.all([...new Set(D.plans)].map((k) => record("building-plans", k)));
    return rows.filter(Boolean).sort((a, b) => String(val(b, "Submission_Date")).localeCompare(String(val(a, "Submission_Date"))))
      .map((r) => `<details class="raw"><summary>${esc(val(r, "Submission_Date") || "")} · ${esc(val(r, "Building_Work_Descri") || val(r, "Primary_Category__") || "Building plan")} · ${val(r, "Building_Work_Value") ? money(val(r, "Building_Work_Value")) : ""} ${val(r, "Approval_Date") ? "· approved " + esc(val(r, "Approval_Date")) : ""}</summary>${kv(r!.fields, r!.values)}</details>`).join(""); };
  const reqs = async () => { if (!D.requests?.length) return ""; const rows = await Promise.all(D.requests.slice(-40).map((k) => record("service-requests", k)));
    const by = new Map<string, number>(); for (const r of rows) { const ty = String(val(r, "C3_Complaint_Type") || val(r, "Notification_type") || "?"); by.set(ty, (by.get(ty) || 0) + 1); }
    return `${[...by].sort((a, b) => b[1] - a[1]).map(([ty, n]) => `<span class="pill">${esc(ty)} · ${n}</span>`).join("")}
      ${rows.reverse().map((r) => `<details class="raw"><summary>${esc(val(r, "Created_On_Date"))} · ${esc(val(r, "C3_Complaint_Type") || val(r, "Notification_type"))}${val(r, "Completed_Date") ? " · done " + esc(val(r, "Completed_Date")) : " · open"}</summary>${kv(r!.fields, r!.values)}</details>`).join("")}
      ${D.requests.length > 40 ? `<div class="note">Latest 40 of ${fmt(D.requests.length)} shown.</div>` : ""}`; };
  const sales = async () => { if (!D.sales?.length) return ""; const rows = await Promise.all(D.sales.map((k) => record("property-disposals", k))); return rows.map((r) => kv(r!.fields, r!.values)).join(""); };
  const near = async () => { if (!D.near) return ""; return (await Promise.all(Object.entries(D.near).map(async ([kind, [lid, k, m]]) => { const r = await record(lid, k);
    return `<div class="row" data-go="${lid}:${k}"><span class="t">${esc(labelOf(lid, r))}</span><small>${esc(layerById.get(lid)?.name)} · ${m >= 1000 ? (m / 1000).toFixed(1) + " km" : m + " m"}</small></div>`; }))).join(""); };
  const wardZ = D.zones?.find(([l]) => l === "wards"); const wardRec = wardZ ? await record(wardZ[0], wardZ[1]) : null;
  const ward = v("WARD_NAME") || (wardRec ? val(wardRec, "WARD_NAME") : null);
  const named = async () => {   // court/tribunal records and news that name this erf number in this plot's suburb
    const erf = String(v("PRTY_NMBR") || "").replace(/^0+/, ""); const sub = String(v("OFC_SBRB_NAME") || v("ALT_NAME") || "").toUpperCase(); if (!erf) return "";
    const [J, F] = await Promise.all([getJSON<any>(METRO + "justice.json").catch(() => null), getJSON<any>(METRO + "feed.json").catch(() => null)]);
    const hit = (it: any) => it.erfs?.includes(erf) && it.places?.some((p: any) => p[0] === sub);
    const items = [...(J?.items || []).filter(hit).map((c: any) => `<div class="row"><a class="t" href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.parties)}</a><small>Competition Tribunal ${esc(c.case)} · ${esc(c.date)}</small></div>`),
      ...(F?.items || []).filter(hit).map((n: any) => `<div class="row"><a class="t" href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a><small>${esc(n.feed)} · ${esc(String(n.date).slice(0, 10))}</small></div>`)];
    return items.join("");
  };
  const [z, r2, pl, rq, sa, ne, nm] = await Promise.all([zoneRows(D.zones), zoneRows(D.records), plans(), reqs(), sales(), near(), named()]);
  if (s !== seq) return;
  const others = hits.filter((h) => h.layer !== P.id);
  $("#right").innerHTML = `<div class="card primary"><div class="kicker">${t("plot")} · ${esc(v("OFC_SBRB_NAME") || v("ALT_NAME") || "")}</div>
    <h2>Erf ${esc(v("PRTY_NMBR"))}${v("ALT_NAME") && v("ALT_NAME") !== v("OFC_SBRB_NAME") ? `, ${esc(v("ALT_NAME"))}` : ""}</h2>
    <div class="mu">${esc(addr.trim())}</div>
    <div class="facts"><div class="fact"><b>${fmt(Number(v("_area") || 0)) || "—"}</b><span>m² (mapped)</span></div><div class="fact"><b>${esc(ward || "—")}</b><span>${t("ward")}</span></div><div class="fact"><b>${esc(v("SUB_CNCL_NMBR") || "—")}</b><span>Subcouncil</span></div></div>
    ${v("ZONING") ? `<span class="pill">${esc(v("ZONING"))}</span>` : ""}${v("LU_LGL_STS_DSCR") ? `<span class="pill">${esc(v("LU_LGL_STS_DSCR"))}</span>` : ""}
    <div class="links"><a href="${P.url}/query?where=SL_LAND_PRCL_KEY%3D${encodeURIComponent(key)}&outFields=*&returnGeometry=false&f=html" target="_blank" rel="noopener">${t("cityrec")} ↗</a><button class="mini" data-share="p=${esc(key)}">${t("share")}</button>
      ${watchButton("plot", `${DISTRICT}|${key}`, `Erf ${v("PRTY_NMBR")} ${v("OFC_SBRB_NAME") || ""}`, (D.plans?.length || 0) + (D.requests?.length || 0) + (D.sales?.length || 0), DISTRICT)}<button class="mini" data-dl="1">Export dossier (JSON)</button></div></div>
    ${nm ? `<h3>Court records and news naming this erf</h3>${nm}<div class="note">Matched by erf number and suburb name in the published title or summary.</div>` : ""}
    ${pl ? `<h3>${t("plans")}<span class="c">${new Set(D.plans).size}</span></h3>${pl}` : `<h3>${t("plans")}<span class="c">0</span></h3><div class="empty">${t("none")} (2014 onward)</div>`}
    ${rq ? `<h3>${t("requests")}<span class="c">${fmt(D.requests!.length)}</span></h3>${rq}` : ""}
    ${sa ? `<h3>${t("sales")}</h3>${sa}` : ""}
    ${r2 ? `<h3>${t("recs")}<span class="c">${D.records!.length}</span></h3>${r2}` : ""}
    ${z ? `<h3>${t("zones")}<span class="c">${D.zones!.length}</span></h3>${z}` : ""}
    ${ne ? `<h3>${t("near")}</h3>${ne}` : ""}
    ${others.length ? `<h3>${t("alsohere")}<span class="c">${others.length}</span></h3>${(await Promise.all(others.slice(0, 12).map(async (h) => `<div class="row" data-go="${h.layer}:${h.i}">${swatch(h.layer)}<span class="t">${esc(labelOf(h.layer, await record(h.layer, h.i)))}</span><small>${esc(layerById.get(h.layer)?.name)}</small></div>`))).join("")}` : ""}
    <details class="raw"><summary>${t("allfields")}</summary>${rec ? kv(rec.fields.slice(0, -1), rec.values) : ""}</details>`;
  $("#right").scrollTop = 0; setHash(`p=${key}`);
  markSeen("plot", `${DISTRICT}|${key}`, (D.plans?.length || 0) + (D.requests?.length || 0) + (D.sales?.length || 0));
  const dl = $("#right").querySelector("[data-dl]") as HTMLElement | null;
  if (dl) dl.onclick = async () => {
    const sec = async (items: [string, number][] = []) => Promise.all(items.map(async ([lid, k]) => { const r = await record(lid, k); const L = layerById.get(lid); return { layer: L?.name, source: L?.url, retrieved: L?.retrieved, record: r ? Object.fromEntries(r.fields.map((f, j) => [f[1] || f[0], r.values[j]])) : null }; }));
    const tab = async (tid: string, idx: number[] = []) => Promise.all([...new Set(idx)].map(async (k) => { const r = await record(tid, k); return r ? Object.fromEntries(r.fields.map((f, j) => [f[1] || f[0], r.values[j]])) : null; }));
    exportJSON(`erf-${v("PRTY_NMBR")}-${v("OFC_SBRB_NAME") || ""}`, { plot: rec ? Object.fromEntries(rec.fields.map((f, j) => [f[1] || f[0], rec.values[j]])) : null, source: P.url, retrieved: P.retrieved,
      zones: await sec(D.zones), records: await sec(D.records), building_plans: await tab("building-plans", D.plans), service_requests: await tab("service-requests", D.requests), city_sales: await tab("property-disposals", D.sales), exported: new Date().toISOString() });
  };
}

/** open a record by layer and row (from lists, search, links) */
export async function openRecord(layerId: string, i: number) {
  if (layerId === M.parcels.layer) return openPlot(i);
  const s = ++seq; const L = layerById.get(layerId); if (!L) return;
  const geo = await locate(layerId, i);
  if (geo) { flyTo(geo); await idle(); }
  if (s !== seq) return;
  const f = outline(layerId, i) || (geo ? { geometry: geo } : null);
  const c = geo ? centre(geo) : null;
  const hits = c ? pick(map.project(c as any)) : [];
  return showFeature(layerId, i, f, s, hits, hits.find((h) => h.layer === M.parcels.layer)?.i);
}
export async function openPlot(i: number) {
  const s = ++seq; const geo = await locate(M.parcels.layer, i);
  if (geo) { flyTo(geo, 17.5); await idle(); }
  if (s !== seq) return;
  const c = geo ? centre(geo) : null; const hits = c ? pick(map.project(c as any)) : [];
  return showPlot(i, outline(M.parcels.layer, i) || (geo ? { geometry: geo } : null), s, hits);
}
/** the record's real shape, from the loaded map tiles (pieces from neighbouring tiles are merged into one multi-shape) */
function outline(layerId: string, i: number): { geometry: GeoJSON.Geometry } | null {
  const L = layerById.get(layerId); if (!L?.tileset) return null;
  const fs = tileSources(L).flatMap((s) => map.querySourceFeatures(s, { sourceLayer: layerId, filter: ["==", ["get", "i"], i] }));
  if (!fs.length) return null;
  if (fs.length === 1) return { geometry: fs[0].geometry };
  const polys = fs.flatMap((f) => f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : []);
  return polys.length ? { geometry: { type: "MultiPolygon", coordinates: polys } as GeoJSON.Geometry } : { geometry: fs[0].geometry };
}
// geometry of a record: read from rendered tiles after flying there (tiles hold the geometry; attrs hold the fields)
async function locate(layerId: string, i: number): Promise<GeoJSON.Geometry | null> {
  const L = layerById.get(layerId); if (!L?.tileset) return null;
  const pos = await getJSON<Record<string, number[][]>>(`${DP}pos/${layerId}.json`).catch(() => null);
  const p = pos?.[String(Math.floor(i / 2000))]?.[i % 2000];
  if (!p) return null;
  return p.length === 2 ? { type: "Point", coordinates: p } : { type: "Polygon", coordinates: [[[p[0], p[1]], [p[2], p[1]], [p[2], p[3]], [p[0], p[3]], [p[0], p[1]]]] };
}
const centre = (g: GeoJSON.Geometry): [number, number] => { if (g.type === "Point") return g.coordinates as [number, number]; const r = (g as GeoJSON.Polygon).coordinates[0]; return [(r[0][0] + r[2][0]) / 2, (r[0][1] + r[2][1]) / 2]; };
// on a phone the dossier covers the lower part of the screen, so the record is framed in the strip above it
const pad = () => { map.resize(); return innerWidth > 900 ? 80 : 30; };
function flyTo(g: GeoJSON.Geometry, z = 17) { if (g.type === "Point") map.flyTo({ center: g.coordinates as [number, number], zoom: Math.max(map.getZoom(), z), duration: 700, padding: innerWidth <= 900 ? pad() as any : undefined });
  else { const r = (g as GeoJSON.Polygon).coordinates[0]; map.fitBounds([r[0] as [number, number], r[2] as [number, number]], { maxZoom: z + .5, padding: pad(), duration: 700 }); } }
const idle = () => new Promise<void>((r) => map.once("idle", () => r()));

export async function showStart() {
  current = null; highlight([]);
  const W = watches(); const changed = W.filter((w) => w.n !== w.seen);
  const watchHtml = W.length ? `<h3>Your watchlist<span class="c">${W.length}</span></h3>${W.slice(0, 12).map((w) => `<div class="row" data-w="${esc(JSON.stringify(w))}"><span class="t">${esc(w.label)}</span><small>${w.kind}${w.n !== w.seen ? ` · <b class="new">${w.n - w.seen > 0 ? "+" : ""}${w.n - w.seen} new</b>` : ""}</small></div>`).join("")}<div class="note">Kept in this browser only.${changed.length ? ` ${changed.length} item(s) changed since you last opened them.` : ""}</div>` : "";
  if (!DISTRICT) {
    const [I, F] = await Promise.all([getJSON<DataIndex>("data/index.json").catch(() => null), flagsData().catch(() => null)]);
    $("#right").innerHTML = `<div class="card primary"><div class="kicker">City of Cape Town · metro overview</div><h2>Public records, joined and sourced</h2>
      <p class="mu">Cape Monitor brings together what the City, the courts and the state have already published, often in obscure places: tender decisions, bids read out at openings, quotations, eTenders, City land sales, tribunal cases and every City GIS layer, plot by plot. Every record links to its source.</p>
      <div class="facts"><div class="fact"><b>${I ? I.districts.filter((d) => d.built).length : "—"}/8</b><span>districts built</span></div><div class="fact"><b>${F ? fmt(F.flags.length) : "—"}</b><span>pattern flags</span></div><div class="fact"><b>${I ? fmt(I.districts.reduce((s, d) => s + (d.plots || 0), 0)) : "—"}</b><span>plots</span></div></div>
      <p class="note">Choose a planning district on the map for its plots and layers. Money, flags, courts and news are in the panel below for the whole city.</p></div>
      <h3>Planning districts</h3>${(I?.districts || []).map((d) => d.built ? `<a class="row" href="${districtUrl(d.slug)}"><span class="t">${esc(d.label)}</span><small>${fmt(d.plots || 0)} plots · ${d.layers} layers · data ${esc(String(d.built).slice(0, 10))}</small></a>` : `<div class="row"><span class="t dim">${esc(d.label)}</span><small>not built yet</small></div>`).join("")}
      ${watchHtml}`;
    return;
  }
  const H = await getJSON<any>(DP + "heritage.json").catch(() => null);
  const sr = layerById.get("service-requests");
  $("#right").innerHTML = `<div class="card primary"><div class="kicker">${esc(M.district.label || M.district.name)} planning district</div><h2>Click any plot or place on the map</h2>
    <p class="mu">The panel shows what you clicked first, then everything else at that point. A plot opens its full dossier: building plans, service requests, City sales, court records naming it, the records on it, every zone and overlay, and the nearest police, fire, clinic, school and library.</p>
    <div class="facts"><div class="fact"><b>${fmt(M.layers.length)}</b><span>map layers</span></div><div class="fact"><b>${fmt(layerById.get(M.parcels.layer)?.n || 0)}</b><span>plots</span></div><div class="fact"><b>${fmt(sr?.n || 0)}</b><span>service requests</span></div></div>
    <p class="note">Search above for an erf number, address, suburb, supplier, tender number, police station, school or layer. Turn layers on at the left. Money, statistics, courts, news and sources are in the panel below.</p></div>
    ${watchHtml}
    ${H ? `<h3>Start with</h3>${(H.highlights || []).filter((h: any) => h.t === "find").map((h: any) => { const k = H.finds.findIndex((f: any) => f.id === h.k); return k < 0 ? "" : `<div class="row" data-go="research-finds:${k}"><span class="t">${esc(H.finds[k].name)}</span><small>${esc(h.why)}</small></div>`; }).join("")}` : ""}`;
}

export function bindInspector() {
  $("#right").addEventListener("click", async (e) => {
    const el = e.target as HTMLElement;
    const go = el.closest("[data-go]") as HTMLElement | null; if (go) { const [l, k] = go.dataset.go!.split(":"); return openRecord(l, +k); }
    const pl = el.closest("[data-plot]") as HTMLElement | null; if (pl) return openPlot(+pl.dataset.plot!);
    const w = el.closest("[data-w]") as HTMLElement | null; if (w) { const x = JSON.parse(w.dataset.w!); return openWatched(x); }
    const sh = el.closest("[data-share]") as HTMLElement | null; if (sh) { const u = location.href.split("#")[0] + "#" + sh.dataset.share; try { await navigator.clipboard.writeText(u); sh.textContent = t("copied"); } catch { sh.textContent = u; } }
  });
  $("#right").addEventListener("change", (e) => { if ((e.target as HTMLElement).id === "empty") { showEmpty = (e.target as HTMLInputElement).checked; if (current) current.kind === "plot" ? openPlot(current.i) : openRecord(current.layer, current.i); } });
}
export { tableRows };

/** open a watchlist entry: suppliers, tenders, flags and departments anywhere; plots and records in their own district */
export async function openWatched(w: { kind: string; id: string; district?: string }) {
  if (w.kind === "supplier") return location.hash = "s=" + w.id;
  if (w.kind === "tender") return location.hash = "t=" + w.id;
  if (w.kind === "flag") return location.hash = "fl=" + w.id;
  if (w.kind === "department") return location.hash = "dep=" + w.id;
  const [d, ...rest] = w.id.split("|");
  const hash = w.kind === "plot" ? "p=" + rest[0] : "f=" + rest.join(":");
  if (d !== DISTRICT) location.href = districtUrl(d, hash); else location.hash = hash;
}
