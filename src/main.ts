import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { loadManifest, M, layerById, parcels, getJSON, DP, DISTRICT, METRO, districtUrl, DataIndex, Districts, Layer } from "./data";
import { initMap, map, setVisible, visible, setBase, THEME_COLOUR, catColour, setMonthRange } from "./map";
import { inspectPoint, bindInspector, openRecord, openPlot, showStart } from "./inspector";
import { bindDock, renderTabs, openTab } from "./dock";
import { OVERLAYS, showOverlay, overlayStatus } from "./live";
import { openSupplier, openTender, openFlag, openDepartment, suppliers, bindMoney } from "./money";
import { bindWatch } from "./util";
import { t, esc, fmt, setLang, LANG } from "./i18n";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
const DEFAULT_ON = ["land-parcels", "zoning", "heritage-inventory", "police-stations", "fire-stations", "wards"];
const PRESETS: [string, string[]][] = [
  ["Property check", ["land-parcels", "zoning", "servitudes", "heritage-inventory", "split-zoning", "home-owners-associations-gv-2021"]],
  ["Safety and justice", ["police-stations", "fire-stations", "health-care-facilities", "live-courts"]],
  ["Complaints", ["service-requests", "wards", "official-suburb"]],
  ["Heritage", ["heritage-inventory", "heritage-audit-areas", "formal-national-heritage-resources-act-nhra-protection", "land-parcels"]],
  ["Nature", ["wetlands", "dunes", "terrestrial-biodiversity-network", "indigenous-vegetation-current-extent", "open-watercourses"]],
  ["Live", ["live-news", "live-fires", "live-ships"]],
];
let IDX: DataIndex | null = null, DIS: Districts | null = null;
let monthFrom = "", monthTo = "";
const overlayOn = new Set<string>();

function swatch(L: Layer) { return `<span class="sw ${L.geom === "Point" ? "pt" : L.geom === "Polyline" ? "ln" : ""}" style="background:${THEME_COLOUR[L.theme] || "#9fa8da"}"></span>`; }
const layerRow = (l: Layer) => `<label class="lr" title="${esc(l.description || l.name)}"><input type="checkbox" data-l="${l.id}" ${visible.has(l.id) ? "checked" : ""}>${swatch(l)}<span class="nm">${esc(l.name)}</span><span class="n">${fmt(l.n)}</span></label>`;
const overlayRow = (id: string) => { const O = OVERLAYS.find((o) => o.id === id)!; const st = overlayStatus(id);
  return `<label class="lr" title="${esc(O.note)}"><input type="checkbox" data-o="${O.id}" ${overlayOn.has(O.id) ? "checked" : ""}><span class="sw pt" style="background:${THEME_COLOUR[O.theme]}"></span><span class="nm">${esc(O.name)}${st ? `<br><small class="dim">${esc(st)}</small>` : ""}</span></label>`; };
const GROUPS: [string, string, string][] = [["money", "Money and tenders", "Geld en tenders"], ["justice", "Justice", "Justisie"], ["notices", "Notices and gazettes", "Kennisgewings en koerante"],
  ["property", "Property and planning", "Eiendom en beplanning"], ["safety", "Safety", "Veiligheid"], ["utilities", "Utilities and infrastructure", "Nutsdienste en infrastruktuur"],
  ["community", "Community and City services", "Gemeenskap en Stadsdienste"], ["environment", "Environment", "Omgewing"], ["heritage", "Heritage", "Erfenis"], ["live", "Live", "Regstreeks"]];

function renderLeft(filter = "") {
  const f = filter.toLowerCase();
  const groups = (M.themes.length ? M.themes.map((x) => [x.id, x.en, x.af] as [string, string, string]) : GROUPS);
  const body = groups.map(([id, en, af]) => {
    const ls = M.layers.filter((l) => l.theme === id && (l.tilesets?.length || l.tileset) && (!f || l.name.toLowerCase().includes(f))).sort((a, b) => a.name.localeCompare(b.name));
    const ovs = OVERLAYS.filter((o) => o.theme === id && (!f || o.name.toLowerCase().includes(f))).map((o) => o.id);
    const extra = id === "money" ? `<div class="note" style="padding-left:14px">City awards, bids, quotations, eTenders, land sales, supplier profiles and pattern flags are city-wide: <button class="mini" data-tab="money">open Money</button></div>`
      : id === "notices" ? `<div class="note" style="padding-left:14px">Gazette and planning notices are not in this build yet; see Sources for why.</div>` : "";
    if (!ls.length && !ovs.length && !extra) return "";
    const on = ls.filter((l) => visible.has(l.id)).length + ovs.filter((o) => overlayOn.has(o)).length;
    let inner = ovs.map(overlayRow).join("");
    if (id === "utilities") {   // hundreds of networks: nested by service
      const subs = [...new Set(ls.map((l) => l.sub || "Other"))].sort();
      inner += subs.map((s) => { const sl = ls.filter((l) => (l.sub || "Other") === s); const so = sl.filter((l) => visible.has(l.id)).length;
        return `<details class="theme sub" ${f || so ? "open" : ""}><summary>${esc(s)}<span class="c">${so ? so + "/" : ""}${sl.length}</span></summary>${sl.map(layerRow).join("")}</details>`; }).join("");
    } else inner += ls.map(layerRow).join("");
    if (id === "community" && layerById.has("service-requests")) inner += timeSlider();
    return `<details class="theme" ${f || on ? "open" : ""}><summary><span class="sw" style="background:${THEME_COLOUR[id] || "#9fa8da"}"></span>${esc(LANG === "af" ? af : en)}<span class="c">${on ? on + "/" : ""}${ls.length + ovs.length}</span></summary>${extra}${inner}</details>`;
  }).join("");
  $("#left").innerHTML = `<div class="phoneonly toolbar"><select id="district2" aria-label="Planning district">${districtOptions()}</select><div class="seg" id="base2"><button data-base="map">Map</button><button data-base="sat">Satellite</button></div><button class="tb" data-lang2="1">${LANG === "en" ? "Afrikaans" : "English"}</button></div>
    <input class="lsearch" id="lfind" placeholder="${esc(t("findlayer"))}" value="${esc(filter)}" aria-label="${esc(t("findlayer"))}">
    ${DISTRICT ? `<div class="caps" style="margin:2px 0 6px">${t("presets")}</div><div class="presets">${PRESETS.map(([n], k) => `<button data-preset="${k}">${esc(n)}</button>`).join("")}<button data-preset="none">Clear</button></div>` : ""}
    ${body}
    <p class="note">${DISTRICT ? `${fmt(M.layers.length)} map layers and ${fmt(M.tables.length)} record tables for ${esc(M.district.label || M.district.name)}.` : "Metro overview. Choose a planning district on the map or in the list above for its plots and map layers."} Sources and what was left out are under Sources.</p>`;
  const inp = $("#lfind") as HTMLInputElement; inp.oninput = () => { renderLeft(inp.value); const n = $("#lfind") as HTMLInputElement; n.focus(); n.setSelectionRange(n.value.length, n.value.length); };
  ($("#district2") as HTMLSelectElement).onchange = (e) => goDistrict((e.target as HTMLSelectElement).value);
  legend();
}
function timeSlider() {
  const L = layerById.get("service-requests")!; const months = (L as any).months as string[] | undefined;
  const ms = months || Array.from({ length: 48 }, (_, k) => { const d = new Date(2023, k, 1); return d.toISOString().slice(0, 7); }).filter((m) => m <= new Date().toISOString().slice(0, 7));
  monthFrom ||= ms[0]; monthTo ||= ms[ms.length - 1];
  return `<div class="slider" style="padding-left:14px"><div class="caps">Service requests: time</div>
    <label class="sm">From <input type="month" id="m-from" min="${ms[0]}" max="${ms[ms.length - 1]}" value="${monthFrom}"></label>
    <label class="sm">to <input type="month" id="m-to" min="${ms[0]}" max="${ms[ms.length - 1]}" value="${monthTo}"></label></div>`;
}
function legend() {
  const shown = [...visible].map((id) => layerById.get(id)!).filter((L) => L && L.cats.length > 1 && L.id !== M.parcels.layer).slice(-3);
  $("#legend").innerHTML = shown.map((L) => `<div class="caps" style="margin:4px 0 3px">${esc(L.name)}</div>${L.cats.slice(0, 12).map(([c, n]) => `<div class="sm"><span class="sw ${L.geom === "Point" ? "pt" : ""}" style="display:inline-block;background:${catColour(L, c)}"></span> ${esc(c)} <span class="dim">${fmt(n)}</span></div>`).join("")}`).join("");
}
function toggle(id: string, on: boolean) {
  if (id.startsWith("live-")) { on ? overlayOn.add(id) : overlayOn.delete(id); showOverlay(id, on); }
  else setVisible(id, on);
  saveView();
}
function saveView() { localStorage.setItem(`cm-layers-${DISTRICT || "metro"}`, JSON.stringify([...visible, ...overlayOn])); }

const districtOptions = () => `<option value="">Metro overview</option>${(IDX?.districts || []).map((d) => `<option value="${d.slug}" ${d.slug === DISTRICT ? "selected" : ""} ${d.built ? "" : "disabled"}>${esc(d.label)}${d.built ? "" : " (not built yet)"}</option>`).join("")}`;
function goDistrict(slug: string, hash = "") { if (slug === DISTRICT && !hash) return; location.href = districtUrl(slug, hash); }

// search: plots by erf or address, layers, records in small layers, suppliers, tenders, districts and suburbs
async function search(q: string) {
  const out: { l: string; s: string; go: () => void }[] = []; const ql = q.toLowerCase().trim(); if (ql.length < 2) return out;
  const ref = q.toUpperCase().replace(/\s/g, "").match(/^0*(\d{1,3}[A-Z]\/20\d\d\/\d\d)$/);
  if (ref) out.push({ l: `Tender ${ref[1]}`, s: "City tender dossier", go: () => openTender(ref[1]) });
  for (const d of DIS?.districts || []) if (d.label.toLowerCase().includes(ql)) out.push({ l: d.label, s: "planning district", go: () => goDistrict(d.slug) });
  for (const [n, s] of Object.entries(DIS?.suburbs || {})) if (n.toLowerCase().startsWith(ql) && out.length < 12) out.push({ l: n.replace(/\b\w+/g, (w) => w[0] + w.slice(1).toLowerCase()), s: `suburb · ${DIS!.districts.find((d) => d.slug === s.d)?.label}`,
    go: () => s.d === DISTRICT ? map.flyTo({ center: s.c, zoom: 15 }) : goDistrict(s.d, `@${s.c[0]},${s.c[1]},15`) });
  if (DISTRICT && /\d/.test(ql)) {
    const erf = ql.match(/^(?:erf\s*)?(\d{1,6})\b\s*(.*)$/);
    const P = await parcels(); const rest = erf ? erf[2] : ql;
    for (const r of P.rows) {
      const hay = `${r.addr} ${r.sub}`.toLowerCase();
      if ((erf && r.erf === erf[1] && (!rest || hay.includes(rest))) || (!erf && hay.includes(ql))) { out.push({ l: `Erf ${r.erf}${r.addr ? " · " + r.addr : ""}`, s: r.sub, go: () => openPlot(r.i) }); if (out.length > 20) break; }
    }
  }
  if (ql.length >= 3) {
    const S = await suppliers().catch(() => null);
    if (S) { let n = 0; for (const r of S.rows) if (String(r[1]).toLowerCase().includes(ql)) { out.push({ l: String(r[1]), s: `supplier · ${fmt(r[2] + r[4] + r[6] + r[7])} records`, go: () => openSupplier(r[0]) }); if (++n >= 8) break; } }
  }
  for (const L of M.layers) if (L.name.toLowerCase().includes(ql)) out.push({ l: L.name, s: `layer · ${fmt(L.n)}`, go: () => { toggle(L.id, true); renderLeft(); } });
  for (const L of M.layers) {
    if (!L.label || L.n > 3000 || L.theme === "utilities" || out.length >= 40) continue;
    const li = L.fields.findIndex((x) => x[0] === L.label); const words = ql.split(/\s+/).filter((w) => w.length > 1);
    for (let s = 0; s < Math.ceil(L.n / 2000) && out.length < 40; s++) {
      const rows = await getJSON<any[][]>(`${DP}attrs/${L.id}/${s}.json`);
      rows.forEach((r, k) => { const hay = `${r[li] ?? ""} ${L.name}`.toLowerCase(); if (words.every((w) => hay.includes(w.replace(/s$/, ""))) && out.length < 40) out.push({ l: String(r[li]), s: L.name, go: () => { toggle(L.id, true); renderLeft(); openRecord(L.id, s * 2000 + k); } }); });
    }
  }
  return out.slice(0, 40);
}
function bindSearch() {
  const q = $("#q") as HTMLInputElement, box = $("#results"); let res: Awaited<ReturnType<typeof search>> = [], tm: any, k = -1;
  q.placeholder = t("search");
  q.oninput = () => { clearTimeout(tm); tm = setTimeout(async () => { const v = q.value; res = await search(v); if (q.value !== v) return; k = -1;
    box.innerHTML = res.length ? res.map((r, n) => `<div class="res" role="option" data-n="${n}"><span>${esc(r.l)}</span><small>${esc(r.s)}</small></div>`).join("") : `<div class="res dim">Nothing found.</div>`; box.hidden = !v.trim(); }, 220); };
  q.onkeydown = (e) => { if (e.key === "Enter") { (res[Math.max(0, k)])?.go(); box.hidden = true; q.blur(); } else if (e.key === "Escape") box.hidden = true;
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") { k = Math.max(0, Math.min(res.length - 1, k + (e.key === "ArrowDown" ? 1 : -1))); box.querySelectorAll(".res").forEach((el, n) => el.classList.toggle("on", n === k)); e.preventDefault(); } };
  box.onmousedown = (e) => { const el = (e.target as HTMLElement).closest("[data-n]") as HTMLElement | null; if (el) { e.preventDefault(); res[+el.dataset.n!].go(); box.hidden = true; q.blur(); } };
  q.onblur = () => setTimeout(() => (box.hidden = true), 150);
}

// share links: #p=<parcel key>  #f=<layer>:<OBJECTID>  #s=<supplier>  #t=<tender>  #fl=<flag>  #dep=<n>  #@lng,lat,zoom
async function openHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (h.startsWith("s=")) return openSupplier(h.slice(2));
  if (h.startsWith("t=")) return openTender(h.slice(2));
  if (h.startsWith("fl=")) return openFlag(h.slice(3));
  if (h.startsWith("dep=")) return openDepartment(+h.slice(4));
  if (h.startsWith("@")) { const [x, y, z] = h.slice(1).split(",").map(Number); if (isFinite(x) && isFinite(y)) map.jumpTo({ center: [x, y], zoom: z || 15 }); return; }
  if (!DISTRICT) return;
  if (h.startsWith("p=")) { const P = await parcels(); const i = P.byKey.get(h.slice(2)); if (i != null) openPlot(i); return; }
  if (h.startsWith("f=")) { const [lid, oid] = h.slice(2).split(":"); const L = layerById.get(lid); if (!L) return; toggle(lid, true); renderLeft();
    for (let s = 0; s < Math.ceil(L.n / 2000); s++) { const rows = await getJSON<any[][]>(`${DP}attrs/${lid}/${s}.json`); const k = rows.findIndex((r) => String(r[r.length - 1]) === oid); if (k >= 0) return openRecord(lid, s * 2000 + k); } }
}

function clock() { const el = $("#clock"); const tick = () => { el.textContent = new Date().toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg", weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " SAST"; }; tick(); setInterval(tick, 30000); }

async function boot() {
  try { [IDX, DIS] = await Promise.all([getJSON<DataIndex>("data/index.json").catch(() => null), getJSON<Districts>(METRO + "districts.json").catch(() => null)]); await loadManifest(); }
  catch (e) { $("#bootmsg").textContent = DISTRICT ? `The ${DISTRICT} district is not in this build yet. ` : "Could not load the data. "; $("#bootmsg").insertAdjacentHTML("beforeend", `<a href="${districtUrl("")}">Open the metro overview</a>`); return; }
  document.title = `Cape Monitor · ${DISTRICT ? M.district.label : "City of Cape Town"}`;
  ($("#district") as HTMLSelectElement).innerHTML = districtOptions();
  ($("#district") as HTMLSelectElement).onchange = (e) => goDistrict((e.target as HTMLSelectElement).value);
  $("#fresh").innerHTML = `${t("fresh")} <b>${esc((M.built || "").slice(0, 10))}</b>`;
  clock();
  await initMap("map", DIS?.districts || []);
  const saved = JSON.parse(localStorage.getItem(`cm-layers-${DISTRICT || "metro"}`) || "null") as string[] | null;
  for (const id of (saved || (DISTRICT ? DEFAULT_ON : ["live-news"]))) { if (layerById.has(id)) setVisible(id, true); else if (OVERLAYS.some((o) => o.id === id)) { overlayOn.add(id); showOverlay(id, true); } }
  renderLeft(); bindInspector(); bindDock(); bindSearch(); bindMoney($("#right"), $("#dockbody")); bindWatch($("#right")); bindWatch($("#dockbody"));
  document.addEventListener("overlay-status", () => renderLeft(($("#lfind") as HTMLInputElement)?.value || ""));
  $("#left").addEventListener("change", (e) => { const c = e.target as HTMLInputElement;
    if (c.dataset.l || c.dataset.o) { toggle((c.dataset.l || c.dataset.o)!, c.checked); legend(); }
    if (c.id === "m-from" || c.id === "m-to") { monthFrom = ($("#m-from") as HTMLInputElement).value; monthTo = ($("#m-to") as HTMLInputElement).value; setMonthRange(monthFrom, monthTo); } });
  $("#left").addEventListener("click", (e) => { const el = e.target as HTMLElement;
    const b = el.closest("[data-preset]") as HTMLElement | null;
    if (b) { for (const id of [...visible]) setVisible(id, false); for (const id of [...overlayOn]) toggle(id, false);
      if (b.dataset.preset !== "none") for (const id of PRESETS[+b.dataset.preset!][1]) if (layerById.has(id) || id.startsWith("live-")) toggle(id, true);
      saveView(); renderLeft(); }
    const tb = el.closest("[data-tab]") as HTMLElement | null; if (tb) { openTab(tb.dataset.tab!); document.body.classList.remove("leftopen"); }
    const bb = el.closest("#base2 button") as HTMLElement | null; if (bb) setBase(bb.dataset.base as any); if (el.closest("[data-lang2]")) $("#lang").click(); });
  map.on("click", (e) => {
    document.body.classList.remove("leftopen");
    if (!DISTRICT) { const f = map.queryRenderedFeatures(e.point, { layers: ["districts-fill"] })[0]; const hits = map.queryRenderedFeatures(e.point).filter((x) => x.layer.id.endsWith("~p"));
      if (f && !hits.length) return goDistrict(f.properties.slug, `@${e.lngLat.lng.toFixed(5)},${e.lngLat.lat.toFixed(5)},${Math.max(14, map.getZoom() + 2).toFixed(1)}`); }
    inspectPoint(e.lngLat);
  });
  let hover: string | number | undefined;
  map.on("mousemove", (e) => { $("#hud").textContent = `${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)} · z${map.getZoom().toFixed(1)}`;
    const fs = map.queryRenderedFeatures([[e.point.x - 3, e.point.y - 3], [e.point.x + 3, e.point.y + 3]]);
    map.getCanvas().style.cursor = fs.some((f) => f.layer.id.includes("~") && !f.layer.id.endsWith("~t")) || (!DISTRICT && fs.some((f) => f.layer.id === "districts-fill")) ? "pointer" : "";
    if (!DISTRICT) { const d = fs.find((f) => f.layer.id === "districts-fill"); if (hover != null) map.setFeatureState({ source: "districts", id: hover }, { hover: false }); hover = d?.id; if (hover != null) map.setFeatureState({ source: "districts", id: hover }, { hover: true }); } });
  $("#base").onclick = (e) => { const b = (e.target as HTMLElement).closest("button"); if (!b) return; setBase(b.dataset.base as any); $("#base").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); };
  $("#menu").onclick = () => document.body.classList.toggle("leftopen");
  $("#closeinspect").onclick = () => document.body.classList.remove("inspect");
  $("#lang").textContent = LANG === "en" ? "AF" : "EN";
  $("#lang").onclick = () => { setLang(LANG === "en" ? "af" : "en"); $("#lang").textContent = LANG === "en" ? "AF" : "EN"; ($("#q") as HTMLInputElement).placeholder = t("search"); renderLeft(); renderTabs(); };
  addEventListener("hashchange", openHash);
  (window as any).__cm = map;   // for automated tests
  $("#boot").remove();
  for (const ms of [100, 600, 1500]) setTimeout(() => map.resize(), ms);
  addEventListener("resize", () => map.resize());
  if (location.hash.length > 2) openHash(); else showStart();
  let deferred: any = null;
  addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; $("#install").hidden = false; });
  $("#install").onclick = async () => { if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; $("#install").hidden = true; } };
  if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
}
boot();
