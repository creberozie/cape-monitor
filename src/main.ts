import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import { loadManifest, M, layerById, parcels, getJSON } from "./data";
import { initMap, map, setVisible, visible, setBase, THEME_COLOUR, catColour, ids } from "./map";
import { inspectPoint, bindInspector, openRecord, openPlot, showStart } from "./inspector";
import { bindDock, renderTabs, openTab } from "./dock";
import { t, esc, fmt, setLang, LANG } from "./i18n";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
const DEFAULT_ON = ["land-parcels", "zoning", "heritage-inventory", "police-stations", "fire-stations", "service-requests", "wards"];
const PRESETS: [string, string[]][] = [
  ["Property check", ["land-parcels", "zoning", "servitudes", "heritage-inventory", "split-zoning", "home-owners-associations-gv-2021"]],
  ["Safety", ["police-stations", "fire-stations", "koeberg-radii-planning", "south-evacuation-direction-koeberg", "east-evacuation-direction-koeberg", "health-care-facilities"]],
  ["Complaints", ["service-requests", "wards", "official-suburb"]],
  ["Utilities", ["electricity-substations", "bulk-water-reservoir", "sewer-pump-station", "sewer-treatment-plant", "electricity-overhead-lines"]],
  ["Heritage", ["heritage-inventory", "heritage-audit-areas", "formal-national-heritage-resources-act-nhra-protection", "land-parcels"]],
  ["Nature", ["wetlands", "dunes", "terrestrial-biodiversity-network", "indigenous-vegetation-current-extent", "open-watercourses"]],
];

function renderLeft(filter = "") {
  const f = filter.toLowerCase();
  const sw = (id: string) => { const L = layerById.get(id)!; const c = THEME_COLOUR[L.theme]; return `<span class="sw ${L.geom === "Point" ? "pt" : L.geom === "Polyline" ? "ln" : ""}" style="background:${c}"></span>`; };
  $("#left").innerHTML = `<div class="phoneonly toolbar"><div class="seg" id="base2"><button data-base="map">Map</button><button data-base="sat">Satellite</button></div><button class="tb" data-lang2="1">${LANG === "en" ? "Afrikaans" : "English"}</button></div>
    <input class="lsearch" id="lfind" placeholder="${esc(t("findlayer"))}" value="${esc(filter)}">
    <div class="caps" style="margin:2px 0 6px">${t("presets")}</div><div class="presets">${PRESETS.map(([n], k) => `<button data-preset="${k}">${esc(n)}</button>`).join("")}<button data-preset="none">Clear</button></div>
    ${M.themes.map((th) => { const ls = M.layers.filter((l) => l.theme === th.id && l.tileset && (!f || l.name.toLowerCase().includes(f))); if (!ls.length) return "";
      const on = ls.filter((l) => visible.has(l.id)).length;
      return `<details class="theme" ${f || on ? "open" : ""}><summary><span class="sw" style="background:${THEME_COLOUR[th.id]}"></span>${esc(LANG === "af" ? th.af : th.en)}<span class="c">${on ? on + "/" : ""}${ls.length}</span></summary>
        ${ls.sort((a, b) => a.name.localeCompare(b.name)).map((l) => `<label class="lr" title="${esc(l.description || l.name)}"><input type="checkbox" data-l="${l.id}" ${visible.has(l.id) ? "checked" : ""}>${sw(l.id)}<span class="nm">${esc(l.name)}</span><span class="n">${fmt(l.n)}</span></label>`).join("")}</details>`; }).join("")}
    <p class="note">${fmt(M.layers.length)} map layers and ${fmt(M.tables.length)} record tables for the ${esc(M.district.name)} district. Records and lists are in the bottom panel; sources and what was left out are under Sources.</p>`;
  const inp = $("#lfind") as HTMLInputElement; inp.oninput = () => { renderLeft(inp.value); const n = $("#lfind") as HTMLInputElement; n.focus(); n.setSelectionRange(n.value.length, n.value.length); };
  legend();
}
function legend() {
  const shown = [...visible].map((id) => layerById.get(id)!).filter((L) => L && L.cats.length > 1 && L.id !== M.parcels.layer).slice(-3);
  $("#legend").innerHTML = shown.map((L) => `<div class="caps" style="margin:4px 0 3px">${esc(L.name)}</div>${L.cats.slice(0, 12).map(([c, n]) => `<div class="sm"><span class="sw ${L.geom === "Point" ? "pt" : ""}" style="display:inline-block;background:${catColour(L, c)}"></span> ${esc(c)} <span class="dim">${fmt(n)}</span></div>`).join("")}`).join("");
}
function toggle(id: string, on: boolean) { setVisible(id, on); saveView(); }
function saveView() { localStorage.setItem("cm-layers", JSON.stringify([...visible])); }

// search: plots by erf number or address, layers, suburbs, tables, heritage finds, news
async function search(q: string) {
  const out: { l: string; s: string; go: () => void }[] = []; const ql = q.toLowerCase().trim(); if (ql.length < 2) return out;
  const erf = ql.match(/^(?:erf\s*)?(\d{1,6})\b\s*(.*)$/);
  if (/\d/.test(ql)) {
    const P = await parcels(); const rest = erf ? erf[2] : ql;
    for (const r of P.rows) {
      const hay = `${r.addr} ${r.sub}`.toLowerCase();
      if ((erf && r.erf === erf[1] && (!rest || hay.includes(rest))) || (!erf && hay.includes(ql)) || (erf && rest && `${r.addr}`.toLowerCase().startsWith(ql))) {
        out.push({ l: `Erf ${r.erf}${r.addr ? " · " + r.addr : ""}`, s: r.sub, go: () => openPlot(r.i) }); if (out.length > 12) break; }
    }
  }
  for (const L of M.layers) if (L.name.toLowerCase().includes(ql)) out.push({ l: L.name, s: `layer · ${fmt(L.n)}`, go: () => { toggle(L.id, true); renderLeft(); } });
  for (const T of M.tables) if (T.name.toLowerCase().includes(ql)) out.push({ l: T.name, s: `records · ${fmt(T.n)}`, go: () => openTab("records") });
  const H = await getJSON<any>("data/heritage.json").catch(() => null);
  if (H) for (const f of H.finds) if (`${f.name} ${f.facts}`.toLowerCase().includes(ql)) out.push({ l: f.name, s: f.cat, go: () => map.flyTo({ center: [f.lon, f.lat], zoom: 15 }) });
  // named records in small layers (stations, schools, facilities…)
  for (const L of M.layers) {
    if (!L.label || L.n > 3000 || L.theme === "infra") continue;
    const shards = Math.ceil(L.n / 2000), li = L.fields.findIndex((x) => x[0] === L.label);
    for (let s = 0; s < shards && out.length < 40; s++) {
      const rows = await getJSON<any[][]>(`data/attrs/${L.id}/${s}.json`);
      const words = ql.split(/\s+/).filter((w) => w.length > 1);
      rows.forEach((r, k) => { const hay = `${r[li] ?? ""} ${L.name}`.toLowerCase(); if (words.every((w) => hay.includes(w.replace(/s$/, ""))) && out.length < 40) out.push({ l: String(r[li]), s: L.name, go: () => { toggle(L.id, true); renderLeft(); openRecord(L.id, s * 2000 + k); } }); });
    }
  }
  return out.slice(0, 40);
}
function bindSearch() {
  const q = $("#q") as HTMLInputElement, box = $("#results"); let res: Awaited<ReturnType<typeof search>> = [], tm: any, k = -1;
  q.placeholder = t("search");
  q.oninput = () => { clearTimeout(tm); tm = setTimeout(async () => { const v = q.value; res = await search(v); if (q.value !== v) return; k = -1;
    box.innerHTML = res.length ? res.map((r, n) => `<div class="res" data-n="${n}"><span>${esc(r.l)}</span><small>${esc(r.s)}</small></div>`).join("") : `<div class="res dim">Nothing found.</div>`; box.hidden = !v.trim(); }, 200); };
  q.onkeydown = (e) => { if (e.key === "Enter") { (res[Math.max(0, k)])?.go(); box.hidden = true; q.blur(); } else if (e.key === "Escape") box.hidden = true;
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") { k = Math.max(0, Math.min(res.length - 1, k + (e.key === "ArrowDown" ? 1 : -1))); box.querySelectorAll(".res").forEach((el, n) => el.classList.toggle("on", n === k)); e.preventDefault(); } };
  box.onmousedown = (e) => { const el = (e.target as HTMLElement).closest("[data-n]") as HTMLElement | null; if (el) { e.preventDefault(); res[+el.dataset.n!].go(); box.hidden = true; q.blur(); } };
  q.onblur = () => setTimeout(() => (box.hidden = true), 150);
}

// share links: #p=<parcel key>  #f=<layer>:<OBJECTID>  #@lng,lat,zoom
async function openHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (h.startsWith("p=")) { const P = await parcels(); const i = P.byKey.get(h.slice(2)); if (i != null) openPlot(i); return; }
  if (h.startsWith("f=")) { const [lid, oid] = h.slice(2).split(":"); const L = layerById.get(lid); if (!L) return; toggle(lid, true); renderLeft();
    for (let s = 0; s < Math.ceil(L.n / 2000); s++) { const rows = await getJSON<any[][]>(`data/attrs/${lid}/${s}.json`); const k = rows.findIndex((r) => String(r[r.length - 1]) === oid); if (k >= 0) return openRecord(lid, s * 2000 + k); } }
}

function clock() { const el = $("#clock"); const tick = () => { el.textContent = new Date().toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg", weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " SAST"; }; tick(); setInterval(tick, 1000); }

async function boot() {
  try { await loadManifest(); } catch (e) { $("#bootmsg").textContent = "Could not load the data. " + e; return; }
  $("#district").textContent = M.district.name + " PILOT";
  $("#fresh").innerHTML = `${t("fresh")} <b>${esc(M.built.slice(0, 10))}</b>`;
  clock();
  await initMap("map");
  const saved = JSON.parse(localStorage.getItem("cm-layers") || "null") as string[] | null;
  for (const id of (saved || DEFAULT_ON)) if (layerById.has(id)) setVisible(id, true);
  renderLeft(); bindInspector(); bindDock(); bindSearch();
  $("#left").addEventListener("change", (e) => { const c = e.target as HTMLInputElement; if (c.dataset.l) { toggle(c.dataset.l, c.checked); legend(); } });
  $("#left").addEventListener("click", (e) => { const b = (e.target as HTMLElement).closest("[data-preset]") as HTMLElement | null; if (!b) return;
    for (const id of [...visible]) setVisible(id, false);
    if (b.dataset.preset !== "none") for (const id of PRESETS[+b.dataset.preset!][1]) if (layerById.has(id)) setVisible(id, true);
    saveView(); renderLeft(); });
  map.on("click", (e) => { document.body.classList.remove("leftopen"); inspectPoint(e.lngLat); });
  map.on("mousemove", (e) => { $("#hud").textContent = `${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)} · z${map.getZoom().toFixed(1)}`;
    map.getCanvas().style.cursor = map.queryRenderedFeatures([[e.point.x - 3, e.point.y - 3], [e.point.x + 3, e.point.y + 3]]).some((f) => f.layer.id.includes("~") && !f.layer.id.endsWith("~t")) ? "pointer" : ""; });
  $("#left").addEventListener("click", (e) => { const el = e.target as HTMLElement; const b = el.closest("#base2 button") as HTMLElement | null; if (b) setBase(b.dataset.base as any); if (el.closest("[data-lang2]")) $("#lang").click(); });
  $("#base").onclick = (e) => { const b = (e.target as HTMLElement).closest("button"); if (!b) return; setBase(b.dataset.base as any); $("#base").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); };
  $("#menu").onclick = () => document.body.classList.toggle("leftopen");
  $("#closeinspect").onclick = () => document.body.classList.remove("inspect");
  $("#lang").textContent = LANG === "en" ? "AF" : "EN";
  $("#lang").onclick = () => { setLang(LANG === "en" ? "af" : "en"); $("#lang").textContent = LANG === "en" ? "AF" : "EN"; ($("#q") as HTMLInputElement).placeholder = t("search"); renderLeft(); renderTabs(); };
  addEventListener("hashchange", openHash);
  (window as any).__cm = map;   // for automated tests
  $("#boot").remove();
  for (const ms of [100, 600, 1500]) setTimeout(() => map.resize(), ms);   // phones settle their height after load
  addEventListener("resize", () => map.resize());
  if (location.hash.length > 2) openHash(); else showStart();
  // install as an app
  let deferred: any = null;
  addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; $("#install").hidden = false; });
  $("#install").onclick = async () => { if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; $("#install").hidden = true; } };
  if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
  void ids;
}
boot();
