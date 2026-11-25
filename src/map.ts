import * as maplibregl from "maplibre-gl";
type MLMap = maplibregl.Map; type MapGeoJSONFeature = maplibregl.MapGeoJSONFeature;
import { Protocol, PMTiles } from "pmtiles";
import { BASE, DP, M, Layer, layerById, DISTRICT } from "./data";
import { clientTheme } from "./catalog";

export let map: MLMap;
export const visible = new Set<string>();
const PALETTE = ["#38d39f", "#2aa3ff", "#ffb020", "#ff5d5d", "#b98cff", "#ff7ac6", "#7be0ff", "#d4e157", "#ff9e57", "#4dd0e1", "#9ccc65", "#f06292",
  "#ba68c8", "#4fc3f7", "#ffd54f", "#a1887f", "#90a4ae", "#e57373", "#81c784", "#64b5f6", "#ffb74d", "#aed581", "#f48fb1", "#ce93d8"];
export const THEME_COLOUR: Record<string, string> = { money: "#ffd54f", justice: "#ff7ac6", notices: "#b98cff", property: "#c9a227", safety: "#ff7a2e",
  utilities: "#2aa3ff", infra: "#2aa3ff", transport: "#b0bec5", complaints: "#ff5d5d", boundaries: "#9fa8da", economy: "#e6c35c",
  community: "#38d39f", environment: "#7cd36b", heritage: "#e05cd0", live: "#ff5d5d" };
const themeColour = (L: Layer) => THEME_COLOUR[clientTheme(L)] || THEME_COLOUR[L.theme] || "#9fa8da";
export const catColour = (L: Layer, c: string) => { const k = L.cats.findIndex((x) => x[0] === c); return k < 0 ? themeColour(L) : PALETTE[k % PALETTE.length]; };
const colourExpr = (L: Layer): any => L.cats.length > 1 ? ["match", ["get", "c"], ...L.cats.flatMap(([c], k) => [c, PALETTE[k % PALETTE.length]]), themeColour(L)] : themeColour(L);
const TEXT = { "text-font": ["Noto Sans Regular"], "text-size": 10.5 } as const;
const HALO = { "text-color": "#d5dde2", "text-halo-color": "#0b0f12", "text-halo-width": 1.3 };
const isStreets = (L: Layer) => /^street-names?$/.test(L.id);
const isAddress = (L: Layer) => L.geom === "Point" && /^(ADR_NO|ADDR|FULL_ADR)$/i.test(L.label || "");

// draw order (bottom → top). Picking uses the same order reversed, so what you see on top is what you get.
const ORDER: Record<string, number> = { Polygon: 0, Polyline: 1, Multipoint: 2, Point: 2 };
const sets = (L: Layer) => L.tilesets || (L.tileset ? [L.tileset] : []);
/** style-layer ids of a record layer; a layer split over several tile files gets one set per file (id@k) */
export const ids = (L: Layer) => sets(L).flatMap((_, k) => { const b = k ? `${L.id}@${k}` : L.id;
  return L.geom === "Polygon" ? [`${b}~f`, `${b}~l`] : L.geom === "Polyline" ? [`${b}~l`] : [`${b}~p`]; });
export const baseId = (styleId: string) => styleId.split("~")[0].split("@")[0];

maplibregl.setWorkerUrl(new URL("vendor/maplibre-gl-worker.mjs", BASE).href);

/** Tile files are read with HTTP range requests. If a host ignores ranges and sends the whole file, it is kept and sliced. */
class RangeOrWhole {
  private whole: Promise<ArrayBuffer> | null = null;
  constructor(private url: string) {}
  getKey() { return this.url; }
  async getBytes(offset: number, length: number, signal?: AbortSignal) {
    if (!this.whole) {
      const r = await fetch(this.url, { headers: { Range: `bytes=${offset}-${offset + length - 1}` }, signal });
      if (r.status === 206) return { data: await r.arrayBuffer() };
      if (!r.ok) throw new Error(`${this.url}: ${r.status}`);
      this.whole = r.arrayBuffer();
    }
    const all = await this.whole; return { data: all.slice(offset, offset + length) };
  }
}
const protocol = new Protocol();
/** in production every tile file is under /t/ (answered with range requests by functions/t); in development it stays in public/ */
const tilePath = (path: string) => import.meta.env.DEV ? path : path.replace(/^data\/d\/([^/]+)\/tiles\//, "t/$1/").replace(/^basemap\//, "t/basemap/") + `?v=${encodeURIComponent(M.built || "")}`;
const tiles = (path: string) => { const url = new URL(tilePath(path), BASE).href; protocol.add(new PMTiles(new RangeOrWhole(url) as any)); return "pmtiles://" + url; };

export async function initMap(container: string, outlines: { slug: string; label: string; outline: GeoJSON.Geometry }[] = []) {
  maplibregl.addProtocol("pmtiles", protocol.tile);
  const style = await (await fetch(new URL("basemap/style.json", BASE))).json();
  style.glyphs = BASE + "basemap/fonts/{fontstack}/{range}.pbf"; style.sprite = BASE + "basemap/sprite/dark";
  style.sources.protomaps.url = tiles("basemap/capetown.pmtiles");
  const [w, s, e, n] = M.district.bounds;
  map = new maplibregl.Map({ container, style, bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: 20 }, maxBounds: [[17.6, -34.6], [19.4, -33.0]], hash: false,
    attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false });
  map.touchZoomRotate.disableRotation();
  new ResizeObserver(() => map.resize()).observe(document.getElementById(container)!);
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
  await new Promise<void>((r) => map.once("load", () => r()));
  const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  map.addSource("sat", { type: "raster", tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 19, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" });
  map.addLayer({ id: "sat", type: "raster", source: "sat", layout: { visibility: "none" } }, firstLabel);
  // planning districts: all eight, the current one highlighted
  map.addSource("districts", { type: "geojson", generateId: true, data: { type: "FeatureCollection", features: outlines.map((d) => ({ type: "Feature", properties: { slug: d.slug, label: d.label, cur: d.slug === DISTRICT ? 1 : 0 }, geometry: d.outline })) } as any });
  map.addLayer({ id: "districts-fill", type: "fill", source: "districts", paint: { "fill-color": "#38d39f", "fill-opacity": DISTRICT ? 0 : ["case", ["boolean", ["feature-state", "hover"], false], .14, .05] } });
  map.addLayer({ id: "districts-line", type: "line", source: "districts", paint: { "line-color": ["case", ["==", ["get", "cur"], 1], "#38d39f", "#5d6b74"], "line-width": ["case", ["==", ["get", "cur"], 1], 1.8, 1], "line-dasharray": [3, 2] } });
  if (!DISTRICT) map.addLayer({ id: "districts-label", type: "symbol", source: "districts", layout: { "text-field": ["get", "label"], "text-font": ["Noto Sans Medium"], "text-size": 13 }, paint: { "text-color": "#dfe6ea", "text-halo-color": "#0b0f12", "text-halo-width": 1.5 } });
  // tile sources are registered when a layer that uses one is first switched on, so a first visit reads no tile file it does not draw
  // draw-order anchors: record layers are added only when first switched on, and slot in below the right anchor
  map.addSource("anchor", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  for (const a of ["anchor-line", "anchor-point", "anchor-top", "anchor-labels"]) map.addLayer({ id: a, type: "circle", source: "anchor" });
  // live and metro point overlays (news, court records, fires, ships): GeoJSON filled in by live.ts
  for (const [id, colour] of [["live-news", "#ffb020"], ["live-courts", "#ff7ac6"], ["live-notices", "#b98cff"], ["live-fires", "#ff3d00"], ["live-ships", "#7be0ff"]] as const) {
    map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({ id: id + "~p", type: "circle", source: id, layout: { visibility: "none" }, paint: { "circle-color": colour, "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 4, 15, 8], "circle-stroke-color": "#0b0f12", "circle-stroke-width": 1.2, "circle-opacity": .9 } });
  }
  map.addSource("sel", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({ id: "sel-f", type: "fill", source: "sel", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#ffffff", "fill-opacity": .12 } });
  map.addLayer({ id: "sel-l", type: "line", source: "sel", paint: { "line-color": "#ffffff", "line-width": 2.5 } });
  map.addLayer({ id: "sel-p", type: "circle", source: "sel", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 10, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#fff", "circle-stroke-width": 2.5 } });
  return map;
}

function addHeat() {
  if (!layerById.has("service-requests") || map.getLayer("service-requests-density~h")) return;
    ensureSource(layerById.get("service-requests")!.tileset!);
    map.addLayer({ id: "service-requests-density~h", type: "heatmap", source: "ts-" + layerById.get("service-requests")!.tileset, "source-layer": "service-requests-density", maxzoom: 13.5, layout: { visibility: "none" },
      paint: { "heatmap-weight": ["interpolate", ["linear"], ["get", "v"], 0, 0, 400, 1], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 10, 13, 30], "heatmap-opacity": .75,
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", .2, "#3b1f5c", .45, "#a1245b", .7, "#ff5d5d", 1, "#ffe08a"] } });
  }
const added = new Set<string>();
function ensureSource(t: string) { if (!map.getSource("ts-" + t)) map.addSource("ts-" + t, { type: "vector", url: tiles(`${DP}tiles/${t}.pmtiles`) }); }
const ANCHOR: Record<string, string> = { Polygon: "anchor-line", Polyline: "anchor-point", Point: "anchor-top", Multipoint: "anchor-top" };
function addLayer(L: Layer) {
  if (added.has(L.id)) return; added.add(L.id);
  for (const t of sets(L)) ensureSource(t);
  const before = ANCHOR[L.geom || "Point"];
  const _add = map.addLayer.bind(map) as any; const add = (spec: any, under = before) => _add(spec, under);
  const col = colourExpr(L), vis = { visibility: "none" as const }, minzoom = L.minzoom ?? 9;
  const boundary = clientTheme(L) === "boundaries" && L.geom === "Polygon" && L.n <= 400 && !!L.label;
  sets(L).forEach((ts, k) => {
    const src = "ts-" + ts, sl = L.id, b = k ? `${L.id}@${k}` : L.id;
    if (L.geom === "Polygon") {
      const parcels = L.id === M.parcels.layer;
      add({ id: `${b}~f`, type: "fill", source: src, "source-layer": sl, minzoom, layout: vis, paint: { "fill-color": col, "fill-opacity": parcels ? 0 : boundary ? .04 : L.n > 5000 ? .16 : .2 } });
      add({ id: `${b}~l`, type: "line", source: src, "source-layer": sl, minzoom, layout: vis, paint: { "line-color": parcels ? "#aab4bb" : col, "line-width": ["interpolate", ["linear"], ["zoom"], 11, .4, 16, parcels ? 1 : 1.6], "line-opacity": parcels ? .55 : .9 } });
      // parcel house numbers from z16; boundary names ("Ward 23") from the layer's own zoom to street scale, so the first screen is not empty
      if (parcels) add({ id: `${b}~t`, type: "symbol", source: src, "source-layer": sl, minzoom: 16, layout: { ...vis, ...TEXT, "text-field": ["get", "n"], "text-size": 10 }, paint: { ...HALO, "text-color": "#c3ccd2" } }, "anchor-labels");
      else if (boundary) add({ id: `${b}~t`, type: "symbol", source: src, "source-layer": sl, minzoom, maxzoom: 15, layout: { ...vis, ...TEXT, "text-size": 12,
        "text-field": /^wards?$/.test(L.id) ? ["concat", "Ward ", ["get", "n"]] : ["get", "n"] }, paint: { ...HALO, "text-color": "#aeb8f0" } }, "anchor-labels");
    } else if (L.geom === "Polyline") {
      const streets = isStreets(L);
      add({ id: `${b}~l`, type: "line", source: src, "source-layer": sl, minzoom, layout: { ...vis, "line-cap": "round" }, paint: { "line-color": streets ? "#8a99a3" : col,
        "line-width": streets ? ["interpolate", ["linear"], ["zoom"], 11, .4, 16, 1.2] : ["interpolate", ["linear"], ["zoom"], 11, .8, 16, 2.4], "line-opacity": streets ? .35 : 1 } });
      if (streets) add({ id: `${b}~t`, type: "symbol", source: src, "source-layer": sl, minzoom: Math.max(14, minzoom), layout: { ...vis, ...TEXT, "symbol-placement": "line", "text-field": ["get", "n"], "text-size": 11 }, paint: HALO }, "anchor-labels");
    } else {
      // address points are the base layer: small grey dots, so the facilities a view is about stay readable
      if (isAddress(L)) add({ id: `${b}~p`, type: "circle", source: src, "source-layer": sl, minzoom, layout: vis, paint: {
        "circle-color": "#8a99a3", "circle-opacity": ["interpolate", ["linear"], ["zoom"], 14, .35, 17, .8], "circle-radius": ["interpolate", ["linear"], ["zoom"], 14, 1, 17, 2.6] } });
      else add({ id: `${b}~p`, type: "circle", source: src, "source-layer": sl, minzoom, layout: vis, paint: {
        "circle-color": col, "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, L.n > 2000 ? 1.6 : 3, 16, L.n > 2000 ? 4.5 : 7],
        "circle-stroke-color": "#0b0f12", "circle-stroke-width": L.n > 2000 ? .4 : 1 } });
      // house numbers on address points from z16; names on smaller named point layers from z14
      if (isAddress(L)) add({ id: `${b}~t`, type: "symbol", source: src, "source-layer": sl, minzoom: 16, layout: { ...vis, ...TEXT, "text-field": ["get", "n"], "text-size": 10, "text-offset": [0, -.9] }, paint: HALO }, "anchor-labels");
      else if (L.label && L.n <= 3000) add({ id: `${b}~t`, type: "symbol", source: src, "source-layer": sl, minzoom: Math.max(14, minzoom), layout: { ...vis, ...TEXT, "text-field": ["get", "n"], "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true }, paint: HALO }, "anchor-labels");
    }
  });
}

export function setVisible(id: string, on: boolean) {
  const L = layerById.get(id);
  on ? visible.add(id) : visible.delete(id);
  if (on && L && sets(L).length) addLayer(L);
  if (on && id === "service-requests") addHeat();
  const all = L ? [...ids(L), ...sets(L).map((_, k) => `${k ? `${id}@${k}` : id}~t`), ...(id === "service-requests" ? ["service-requests-density~h"] : [])] : [id + "~p"];
  for (const lid of all) if (map.getLayer(lid)) map.setLayoutProperty(lid, "visibility", on ? "visible" : "none");
  // house numbers never twice: parcel numbers hide while an address layer is on
  const P = layerById.get(M.parcels.layer); if (!P) return;
  const addressOn = [...visible].some((v) => { const A = layerById.get(v); return !!A && isAddress(A); });
  sets(P).forEach((_, k) => { const t = `${k ? `${P.id}@${k}` : P.id}~t`; if (map.getLayer(t)) map.setLayoutProperty(t, "visibility", visible.has(P.id) && !addressOn ? "visible" : "none"); });
}

/** time filter for layers whose tiles carry a month ("d": YYYY-MM): service requests */
export function setMonthRange(from: string, to: string) {
  const f: any = ["all", [">=", ["get", "d"], from], ["<=", ["get", "d"], to]];
  for (const lid of ["service-requests~p"]) if (map.getLayer(lid)) map.setFilter(lid, f);
}

/** what is under the pointer, top-most first; one entry per record */
export function pick(pt: maplibregl.PointLike): { layer: string; i: number; f: MapGeoJSONFeature }[] {
  const p = map.project(map.unproject(pt as any)); const box: [maplibregl.PointLike, maplibregl.PointLike] = [[p.x - 4, p.y - 4], [p.x + 4, p.y + 4]];
  const layers = map.getStyle().layers.map((l) => l.id).filter((id) => id.includes("~") && !id.endsWith("~t") && !id.endsWith("~h") && map.getLayoutProperty(id, "visibility") === "visible");
  if (!layers.length) return [];
  const fs = map.queryRenderedFeatures(box, { layers });
  // points and lines need the small box; polygons must contain the exact point
  const exact = new Set(map.queryRenderedFeatures(p as any, { layers }).filter((f) => f.layer.type === "fill").map((f) => `${baseId(f.layer.id)}|${f.properties.i}`));
  const seen = new Set<string>(); const out: { layer: string; i: number; f: MapGeoJSONFeature }[] = [];
  for (const f of fs) {
    const lid = baseId(f.layer.id), k = `${lid}|${f.properties.i}`;
    if (lid.startsWith("live-")) { if (!seen.has(k)) { seen.add(k); out.push({ layer: lid, i: Number(f.properties.i), f }); } continue; }
    if (f.layer.type === "fill" && !exact.has(k)) continue;
    if (f.layer.type === "line" && layerById.get(lid)?.geom === "Polygon" && !exact.has(k)) continue;
    if (seen.has(k)) continue; seen.add(k); out.push({ layer: lid, i: Number(f.properties.i), f });
  }
  return out;
}

/** the record's tile sets (for reading its shape back from the map) */
export const tileSources = (L: Layer) => sets(L).map((t) => "ts-" + t);
export function highlight(features: GeoJSON.Feature[]) { (map.getSource("sel") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features }); }
export function setBase(b: "map" | "sat") { map.setLayoutProperty("sat", "visibility", b === "sat" ? "visible" : "none"); }
