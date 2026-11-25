import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { loadManifest, M, layerById, parcels, getJSON, DP, DISTRICT, METRO, districtUrl, DataIndex, Districts, Layer, record, val } from "./data";
import { initMap, map, setVisible, visible, setBase, THEME_COLOUR, catColour, setMonthRange, notDrawnHere } from "./map";
import { inspectPoint, bindInspector, openRecord, openPlot, showStart } from "./inspector";
import { bindDock, renderTabs, openTab, setLabourFilter, addOwnerTab } from "./dock";
import { entitlements } from "./auth/entitlements";
import { accessGate } from "./access/gate";
import { joinPresence, onCount } from "./access/presence";
import { track } from "./access/activity";
import { user, signOut, isOwner } from "./access/auth";
import { ACCESS } from "./access/config";
import { OVERLAYS, showOverlay, overlayStatus } from "./live";
import { openSupplier, openTender, openFlag, openDepartment, suppliers, bindMoney, hidePersons } from "./money";
import { bindWatch } from "./util";
import { t, esc, fmt, setLang, LANG } from "./i18n";
import { THEME_ORDER, THEME_HINT, themeName, themeLayers, quickViews, basics, buildCatalog, nameOf, alsoFrom, clientTheme, isBase, fieldLabel, legendValue } from "./catalog";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
let IDX: DataIndex | null = null, DIS: Districts | null = null;
let monthFrom = "", monthTo = "";
const overlayOn = new Set<string>();

function swatch(L: Layer) { return `<span class="sw ${L.geom === "Point" ? "pt" : L.geom === "Polyline" ? "ln" : ""}" style="background:${THEME_COLOUR[clientTheme(L)] || "#9fa8da"}"></span>`; }
const far = (L: Layer) => visible.has(L.id) && notDrawnHere(L);
function layerRow(L: Layer) {
  const copies = alsoFrom.get(L.id) || [], r = far(L);
  return `<label class="lr${r ? " far" : ""}" title="${esc((L.description || L.name) + (copies.length ? `\n\nAlso published by the City as: ${copies.map((c) => c.name).join(", ")}` : ""))}"><input type="checkbox" data-l="${L.id}" ${visible.has(L.id) ? "checked" : ""}>${swatch(L)}<span class="nm">${esc(nameOf(L))}${r ? `<small class="zh">${t("farscale")}</small>` : ""}</span><span class="n">${fmt(L.n)}</span></label>`;
}
const overlayRow = (id: string) => { const O = OVERLAYS.find((o) => o.id === id)!; const st = overlayStatus(id);
  return `<label class="lr" title="${esc(O.note)}"><input type="checkbox" data-o="${O.id}" ${overlayOn.has(O.id) ? "checked" : ""}><span class="sw pt" style="background:${THEME_COLOUR[O.theme]}"></span><span class="nm">${esc(O.name)}${st ? `<small class="zh" style="color:var(--dim)">${esc(st)}</small>` : ""}</span></label>`; };
const moreOpen = new Set<string>(); let openThemes: Set<string> | null = null;

// the layer panel, laid out as in the Blaauwberg pilot; the city-wide groups (courts, money, notices, live) follow
function renderLeft(filter = "") {
  const f = filter.trim();
  const activeL = [...visible].map((id) => layerById.get(id)).filter(Boolean) as Layer[];
  openThemes ??= new Set([...activeL.map((L) => clientTheme(L)), ...[...overlayOn].map((id) => OVERLAYS.find((o) => o.id === id)?.theme || "")]);
  const body = THEME_ORDER.map((id) => {
    const { main, more, all } = themeLayers(id, f);
    const ovs = OVERLAYS.filter((o) => o.theme === id && (!f || o.name.toLowerCase().includes(f.toLowerCase()))).map((o) => o.id);
    const extra = id === "money" ? `<div class="note" style="margin-left:14px">Awards, bids, quotations, eTenders, land sales, supplier profiles and pattern flags, city-wide. <button class="lnk" data-tab="money">Open Money</button></div>`
      : id === "notices" ? `<div class="note" style="margin-left:14px">Western Cape Provincial Gazette notices naming Cape Town. <button class="lnk" data-tab="notices">Open Notices</button></div>` : "";
    if (!all.length && !ovs.length && !extra) return "";
    const on = all.filter((l) => visible.has(l.id)).length + ovs.filter((o) => overlayOn.has(o)).length;
    const expanded = !!f || moreOpen.has(id);
    const moreHtml = !f && more.length ? (expanded ? `<div class="morehd">${t("specialist")}</div>${more.map(layerRow).join("")}<button class="lnk more" data-more="${id}">${t("fewer")}</button>`
      : `<button class="lnk more" data-more="${id}">+ ${more.length} ${t("specialist").toLowerCase()}</button>`) : "";
    const slider = id === "complaints" && layerById.has("service-requests") ? timeSlider() : "";
    return `<details class="theme" data-theme="${id}" ${f || openThemes!.has(id) ? "open" : ""}><summary><span class="sw" style="background:${THEME_COLOUR[id] || "#9fa8da"}"></span><span class="tn">${esc(themeName(id, LANG))}<small>${esc(THEME_HINT[id] || "")}</small></span><span class="c">${on ? `<b>${on}</b>/` : ""}${all.length + ovs.length}</span></summary>
      ${extra}${ovs.map(overlayRow).join("")}${(f ? all : main).map(layerRow).join("")}${moreHtml}${slider}</details>`;
  }).join("");
  const chips = [...activeL.map((L) => [L.id, nameOf(L), THEME_COLOUR[clientTheme(L)] || "#9fa8da"]), ...[...overlayOn].map((id) => { const O = OVERLAYS.find((o) => o.id === id); return [id, O?.name || id, THEME_COLOUR[O?.theme || "live"]]; })];
  const qv = DISTRICT ? quickViews() : [];
  $("#left").innerHTML = `<div class="phoneonly toolbar"><select id="district2" aria-label="Planning district">${districtOptions()}</select><div class="seg" id="base2"><button data-base="map">Map</button><button data-base="sat">Satellite</button></div><button class="tb" data-lang2="1">${LANG === "en" ? "Afrikaans" : "English"}</button></div>
    ${qv.length ? `<div class="caps lh">${t("presets")}</div><div class="views">${qv.map(([n, h], k) => `<button data-qv="${k}" title="${esc(h)}"><b>${esc(n)}</b><small>${esc(h)}</small></button>`).join("")}</div>` : ""}
    <div class="onmap"><div class="caps lh">${t("active")} <span class="c">${chips.length}</span><span class="sp"></span>${DISTRICT ? `<button class="lnk" data-basics="1">${t("reset")}</button>` : ""}<button class="lnk" data-clear="1">${t("clear")}</button></div>
      ${chips.length ? `<div class="chips">${chips.map(([id, n, c]) => `<span class="chipx" style="--c:${c}">${esc(n)}<button data-off="${esc(id)}" aria-label="Remove ${esc(n)}">×</button></span>`).join("")}</div>` : `<div class="note">${t("noactive")}</div>`}</div>
    <input class="lsearch" id="lfind" placeholder="${esc(t("findlayer"))}" value="${esc(filter)}" aria-label="${esc(t("findlayer"))}">
    ${body}
    <p class="note">${DISTRICT ? `${fmt(M.layers.length)} layers, duplicates consolidated; ${fmt(M.tables.length)} record tables. Sector: ${esc(M.district.name)}. Layer descriptions on hover; records, statistics and sources in the lower panel.` : "Metro overview. Select a sector on the map or above for its erven and layers. Records, statistics and sources in the lower panel."}</p>`;
  const inp = $("#lfind") as HTMLInputElement; inp.oninput = () => { renderLeft(inp.value); const n = $("#lfind") as HTMLInputElement; n.focus(); n.setSelectionRange(n.value.length, n.value.length); };
  ($("#district2") as HTMLSelectElement).onchange = (e) => goDistrict((e.target as HTMLSelectElement).value);
  $("#left").querySelectorAll("details.theme").forEach((d) => d.addEventListener("toggle", () => { const id = (d as HTMLElement).dataset.theme!; (d as HTMLDetailsElement).open ? openThemes!.add(id) : openThemes!.delete(id); }));
  legend(); scaleNotice();
}
function timeSlider() {
  const L = layerById.get("service-requests")!; const months = (L as any).months as string[] | undefined;
  const ms = months || Array.from({ length: 48 }, (_, k) => { const d = new Date(2023, k, 1); return d.toISOString().slice(0, 7); }).filter((m) => m <= new Date().toISOString().slice(0, 7));
  monthFrom ||= ms[0]; monthTo ||= ms[ms.length - 1];
  return `<div class="slider" style="margin-left:14px"><div class="caps">Incidents: period</div>
    <label class="sm">From <input type="month" id="m-from" min="${ms[0]}" max="${ms[ms.length - 1]}" value="${monthFrom}"></label>
    <label class="sm">to <input type="month" id="m-to" min="${ms[0]}" max="${ms[ms.length - 1]}" value="${monthTo}"></label></div>`;
}
/** legend only where colour carries meaning: not the base layers, not jurisdictions, not yes/no flags, not layers off at this scale */
function legend() {
  const base = new Set(basics());
  const shown = [...visible].map((id) => layerById.get(id)!).filter((L) => L && L.cats.length > 1 && !base.has(L.id) && clientTheme(L) !== "boundaries" && !notDrawnHere(L)
    && !L.cats.every(([c]) => /^(yes|no|y|n|true|false|0|1)$/i.test(c))).slice(-3);
  $("#legend").innerHTML = shown.map((L) => { const f = L.fields.find((x) => x[0] === L.cat); const by = f ? fieldLabel(f) : "";
    return `<div class="caps" style="margin:4px 0 1px">${esc(nameOf(L))}</div>${by ? `<div class="lgby">by ${esc(by.toLowerCase())}</div>` : ""}${L.cats.slice(0, 12).map(([c, n]) => `<div class="sm"><span class="sw ${L.geom === "Point" ? "pt" : ""}" style="display:inline-block;background:${catColour(L, c)}"></span> ${esc(legendValue(L, c, by))} <span class="dim">${fmt(n)}</span></div>`).join("")}`; }).join("");
}
/** a notice on the map when an active layer is too detailed to draw at this zoom; clicking it goes to street scale */
function scaleNotice() {
  let el = document.getElementById("scalehint") as HTMLButtonElement | null;
  if (!el) { el = document.createElement("button"); el.id = "scalehint"; $("#mapwrap").appendChild(el); el.onclick = () => map.easeTo({ zoom: 15.5, duration: 900 }); }
  const hidden = [...visible].map((id) => layerById.get(id)!).filter((L) => L && notDrawnHere(L));
  el.hidden = !hidden.length;
  if (hidden.length) el.innerHTML = `${esc(hidden.map((L) => nameOf(L)).slice(0, 3).join(", "))}${hidden.length > 3 ? ` and ${hidden.length - 3} more` : ""}: drawn from street scale. <b>Go to street scale</b> or query an erf or address.`;
}
function toggle(id: string, on: boolean) {
  if (id.startsWith("live-")) { on ? overlayOn.add(id) : overlayOn.delete(id); showOverlay(id, on); }
  else setVisible(id, on);
  saveView();
}
const VIEW_KEY = `cm-layers-v2-${DISTRICT || "metro"}`;
function saveView() { try { localStorage.setItem(VIEW_KEY, JSON.stringify([...visible, ...overlayOn])); } catch { /* storage blocked */ } }
function savedView(): string[] | null { try { return JSON.parse(localStorage.getItem(VIEW_KEY) || "null"); } catch { return null; } }
const zoomNow = () => { try { return map.getZoom(); } catch { return 99; } };
function clearAll() { for (const id of [...visible]) setVisible(id, false); for (const id of [...overlayOn]) toggle(id, false); }
function applyQuickView(k: number) {
  const [, , ids] = quickViews()[k];
  clearAll();
  const on = [...new Set([...ids, ...basics().filter((b) => !/^wards?$/.test(b))])];   // erven, streets and addresses stay on underneath
  for (const id of on) toggle(id, true);
  openThemes = new Set(on.map((id) => clientTheme(layerById.get(id)!)));
  const z = zoomNow();
  if (k !== 0 && z > 15) map.easeTo({ zoom: 14 });
  else if (on.some((id) => notDrawnHere(layerById.get(id)!) && !basics().includes(id))) map.easeTo({ zoom: Math.max(z, 13.2) });
  saveView(); renderLeft();
}

const districtOptions = () => `<option value="">Sector: Metro overview</option>${(IDX?.districts || []).map((d) => `<option value="${d.slug}" ${d.slug === DISTRICT ? "selected" : ""} ${d.built ? "" : "disabled"}>Sector: ${esc(d.label)}${d.built ? "" : " (not built yet)"}</option>`).join("")}`;
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
    const hide = hidePersons();
    if (S) { let n = 0; for (const r of S.rows) if (String(r[1]).toLowerCase().includes(ql) && !(hide && r[13])) { out.push({ l: String(r[1]), s: `supplier · ${fmt(r[2] + r[4] + r[6] + r[7])} records`, go: () => openSupplier(r[0]) }); if (++n >= 8) break; } }
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

// share links: #p=<parcel key>  #f=<layer>:<OBJECTID>  #s=<supplier>  #t=<tender>  #fl=<flag>  #dep=<n>  #l=<council>:<kind>:<year>:<q>  #@lng,lat,zoom
async function openHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (h.startsWith("s=")) return openSupplier(h.slice(2));
  if (h.startsWith("t=")) return openTender(h.slice(2));
  if (h.startsWith("fl=")) return openFlag(h.slice(3));
  if (h.startsWith("dep=")) return openDepartment(+h.slice(4));
  if (h.startsWith("l=")) { setLabourFilter(h.slice(2)); return openTab("labour"); }
  if (h.startsWith("@")) { const [x, y, z] = h.slice(1).split(",").map(Number); if (isFinite(x) && isFinite(y)) map.jumpTo({ center: [x, y], zoom: z || 15 }); return; }
  if (!DISTRICT) return;
  if (h.startsWith("p=")) { const P = await parcels(); const i = P.byKey.get(h.slice(2)); if (i != null) openPlot(i); return; }
  if (h.startsWith("f=")) { const [lid, oid] = h.slice(2).split(":"); const L = layerById.get(lid); if (!L) return; toggle(lid, true); renderLeft();
    for (let s = 0; s < Math.ceil(L.n / 2000); s++) { const rows = await getJSON<any[][]>(`${DP}attrs/${lid}/${s}.json`); const k = rows.findIndex((r) => String(r[r.length - 1]) === oid); if (k >= 0) return openRecord(lid, s * 2000 + k); } }
}

function clock() { const el = $("#clock"); const tick = () => { el.textContent = new Date().toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg", weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " SAST"; }; tick(); setInterval(tick, 30000); }

async function boot() {
  await accessGate();   // returns at once when the wall is off or Supabase is not configured
  try { [IDX, DIS] = await Promise.all([getJSON<DataIndex>("data/index.json").catch(() => null), getJSON<Districts>(METRO + "districts.json").catch(() => null)]); await loadManifest(); }
  catch (e) { $("#bootmsg").textContent = DISTRICT ? `The ${DISTRICT} district is not in this build yet. ` : "Could not load the data. "; $("#bootmsg").insertAdjacentHTML("beforeend", `<a href="${districtUrl("")}">Open the metro overview</a>`); return; }
  document.title = `Cape Monitor · ${DISTRICT ? M.district.label : "City of Cape Town"}`;
  ($("#district") as HTMLSelectElement).innerHTML = districtOptions();
  ($("#district") as HTMLSelectElement).onchange = (e) => goDistrict((e.target as HTMLSelectElement).value);
  if (entitlements().source === "preview") $("#fresh").insertAdjacentHTML("afterend", `<span class="chip" title="Pro preview (testing only)">PRO preview</span>`);
  void joinPresence().then((on) => { if (!on) return; onCount((n) => { const el = $("#online"); el.hidden = n < 1; el.textContent = `● ${n} online`; }); });
  if (user()) { $("#signout").hidden = false; $("#signout").onclick = async () => { await signOut(); if (ACCESS.requireAccount) location.reload(); else $("#signout").hidden = true; };
    void isOwner().then((o) => { if (o) addOwnerTab(); }); }
  track("open", { district: DISTRICT || "metro" });
  $("#fresh").innerHTML = `${t("fresh")} <b>${esc((M.built || "").slice(0, 10))}</b>`;
  clock();
  await initMap("map", DIS?.districts || []);
  buildCatalog();
  const saved = savedView();   // key bumped to v2: earlier saved states do not override the new defaults
  for (const id of (saved || (DISTRICT ? basics() : ["live-news"]))) { if (layerById.has(id)) setVisible(id, true); else if (OVERLAYS.some((o) => o.id === id)) { overlayOn.add(id); showOverlay(id, true); } }
  renderLeft(); bindInspector(); bindDock(); bindSearch(); bindMoney($("#right"), $("#dockbody")); bindWatch($("#right")); bindWatch($("#dockbody"));
  document.addEventListener("overlay-status", () => renderLeft(($("#lfind") as HTMLInputElement)?.value || ""));
  $("#left").addEventListener("change", (e) => { const c = e.target as HTMLInputElement;
    if (c.dataset.l || c.dataset.o) { toggle((c.dataset.l || c.dataset.o)!, c.checked); renderLeft(($("#lfind") as HTMLInputElement)?.value || ""); }
    if (c.id === "m-from" || c.id === "m-to") { monthFrom = ($("#m-from") as HTMLInputElement).value; monthTo = ($("#m-to") as HTMLInputElement).value; setMonthRange(monthFrom, monthTo); } });
  $("#left").addEventListener("click", (e) => { const el = e.target as HTMLElement;
    const q = el.closest("[data-qv]") as HTMLElement | null; if (q) applyQuickView(+q.dataset.qv!);
    const off = el.closest("[data-off]") as HTMLElement | null; if (off) { e.preventDefault(); toggle(off.dataset.off!, false); renderLeft(($("#lfind") as HTMLInputElement)?.value || ""); }
    const mo = el.closest("[data-more]") as HTMLElement | null; if (mo) { const id = mo.dataset.more!; moreOpen.has(id) ? moreOpen.delete(id) : moreOpen.add(id); renderLeft(); return; }
    if (el.closest("[data-basics]")) { clearAll(); for (const id of basics()) toggle(id, true); openThemes = new Set(basics().map((id) => clientTheme(layerById.get(id)!))); saveView(); renderLeft(); }
    if (el.closest("[data-clear]")) { clearAll(); saveView(); renderLeft(); }
    const tb = el.closest("[data-tab]") as HTMLElement | null; if (tb) { openTab(tb.dataset.tab!); document.body.classList.remove("leftopen"); }
    const bb = el.closest("#base2 button") as HTMLElement | null; if (bb) setBase(bb.dataset.base as any); if (el.closest("[data-lang2]")) $("#lang").click(); });
  map.on("click", (e) => {
    document.body.classList.remove("leftopen");
    if (!DISTRICT) { const f = map.queryRenderedFeatures(e.point, { layers: ["districts-fill"] })[0]; const hits = map.queryRenderedFeatures(e.point).filter((x) => x.layer.id.endsWith("~p"));
      if (f && !hits.length) return goDistrict(f.properties.slug, `@${e.lngLat.lng.toFixed(5)},${e.lngLat.lat.toFixed(5)},${Math.max(14, map.getZoom() + 2).toFixed(1)}`); }
    inspectPoint(e.lngLat);
  });
  let hover: string | number | undefined;
  // coordinates under the pointer; at street scale over an erf: erf number, address, suburb and zoning (as in the pilot)
  let hovN = 0; const P = DISTRICT ? layerById.get(M.parcels.layer) : undefined;
  map.on("mousemove", async (e) => {
    const fs = map.queryRenderedFeatures([[e.point.x - 3, e.point.y - 3], [e.point.x + 3, e.point.y + 3]]);
    map.getCanvas().style.cursor = fs.some((f) => f.layer.id.includes("~") && !f.layer.id.endsWith("~t")) || (!DISTRICT && fs.some((f) => f.layer.id === "districts-fill")) ? "pointer" : "";
    if (!DISTRICT) { const d = fs.find((f) => f.layer.id === "districts-fill"); if (hover != null) map.setFeatureState({ source: "districts", id: hover }, { hover: false }); hover = d?.id; if (hover != null) map.setFeatureState({ source: "districts", id: hover }, { hover: true }); }
    $("#hud").textContent = `${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)}`;
    if (!P || !visible.has(P.id) || map.getZoom() < 14) return;
    const n = ++hovN; const pf = map.queryRenderedFeatures(e.point).find((f) => f.layer.type === "fill" && f.layer.id.split("~")[0].split("@")[0] === P.id); if (!pf) return;
    const r = await record(P.id, Number(pf.properties.i)); if (n !== hovN || !r) return;
    const v = (k: string) => val(r, k); const addr = [[v("ADR_NO_PRF"), v("ADR_NO"), v("ADR_NO_SFX")].filter(Boolean).join(""), v("STR_NAME"), v("LU_STR_NAME_TYPE")].filter(Boolean).join(" ");
    $("#hud").innerHTML = `<b>Erf ${esc(v("PRTY_NMBR") ?? "?")}</b>${addr ? " · " + esc(addr) : ""}${v("OFC_SBRB_NAME") ? " · " + esc(v("OFC_SBRB_NAME")) : ""}${v("ZONING") ? ` · <span class="dim">${esc(v("ZONING"))}</span>` : ""}`;
  });
  // what is drawn depends on zoom: refresh the "not drawn at this scale" marks and the map notice when the zoom settles
  let zt: any; map.on("zoomend", () => { clearTimeout(zt); zt = setTimeout(() => { const lf = $("#lfind") as HTMLInputElement | null; if (document.activeElement !== lf) renderLeft(lf?.value || ""); else scaleNotice(); }, 150); });
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
