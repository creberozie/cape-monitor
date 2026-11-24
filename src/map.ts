import * as maplibregl from "maplibre-gl";
type MLMap = maplibregl.Map; type MapGeoJSONFeature = maplibregl.MapGeoJSONFeature;
import { Protocol, PMTiles } from "pmtiles";
import { BASE, PACKED, packedBytes } from "./data";
import { M, Layer, layerById } from "./data";

export let map: MLMap;
export const visible = new Set<string>();
const PALETTE = ["#38d39f", "#2aa3ff", "#ffb020", "#ff5d5d", "#b98cff", "#ff7ac6", "#7be0ff", "#d4e157", "#ff9e57", "#4dd0e1", "#9ccc65", "#f06292",
  "#ba68c8", "#4fc3f7", "#ffd54f", "#a1887f", "#90a4ae", "#e57373", "#81c784", "#64b5f6", "#ffb74d", "#aed581", "#f48fb1", "#ce93d8"];
export const THEME_COLOUR: Record<string, string> = { property: "#c9a227", complaints: "#ff5d5d", safety: "#ff7a2e", infra: "#2aa3ff", transport: "#b0bec5",
  community: "#38d39f", economy: "#ffd54f", environment: "#7cd36b", heritage: "#e05cd0", boundaries: "#9fa8da" };
export const catColour = (L: Layer, c: string) => { const k = L.cats.findIndex((x) => x[0] === c); return k < 0 ? THEME_COLOUR[L.theme] : PALETTE[k % PALETTE.length]; };
const colourExpr = (L: Layer): any => L.cats.length > 1 ? ["match", ["get", "c"], ...L.cats.flatMap(([c], k) => [c, PALETTE[k % PALETTE.length]]), THEME_COLOUR[L.theme]] : THEME_COLOUR[L.theme];

// draw order (bottom → top). Picking uses the same order reversed, so what you see on top is what you get.
const ORDER: Record<string, number> = { Polygon: 0, Polyline: 1, Multipoint: 2, Point: 2 };
export const ids = (L: Layer) => L.geom === "Polygon" ? [`${L.id}~f`, `${L.id}~l`] : L.geom === "Polyline" ? [`${L.id}~l`] : [`${L.id}~p`];

// the map's background worker ships as separate ES modules (copied to /vendor by `npm run vendor`)
maplibregl.setWorkerUrl(new URL("vendor/maplibre-gl-worker.mjs", BASE).href);

/** Tile files are read with HTTP range requests; where a host ignores ranges and sends the whole file, it is kept and sliced. */
class RangeOrWhole {
  private whole: Promise<ArrayBuffer> | null = null;
  constructor(private url: string) {}
  getKey() { return this.url; }
  async getBytes(offset: number, length: number, signal?: AbortSignal) {
    if (!this.whole && PACKED) this.whole = packedBytes(this.url.slice(BASE.length));
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
const tiles = (path: string) => { const url = new URL(path, BASE).href; protocol.add(new PMTiles(new RangeOrWhole(url) as any)); return "pmtiles://" + url; };

export async function initMap(container: string) {
  maplibregl.addProtocol("pmtiles", protocol.tile);
  // packed fonts: basemap/fonts/<Noto-Sans-Regular>/<range>.pbf.b64.txt
  maplibregl.addProtocol("b64", async (p) => ({ data: await packedBytes(decodeURIComponent(p.url.replace("b64://", "")).replace(/ /g, "-")) }));
  const style = await (await fetch(new URL("basemap/style.json", BASE))).json();
  style.glyphs = PACKED ? "b64://basemap/fonts/{fontstack}/{range}.pbf" : BASE + "basemap/fonts/{fontstack}/{range}.pbf"; style.sprite = BASE + "basemap/sprite/dark";
  style.sources.protomaps.url = tiles("basemap/capetown.pmtiles");
  const [w, s, e, n] = M.district.bounds;
  map = new maplibregl.Map({ container, style, bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: 20 }, maxBounds: [[17.6, -34.6], [19.4, -33.0]], hash: false,
    attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false });
  map.touchZoomRotate.disableRotation();
  new ResizeObserver(() => map.resize()).observe(document.getElementById(container)!);   // panels open and close around the map
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
  await new Promise<void>((r) => map.once("load", () => r()));
  const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  map.addSource("sat", { type: "raster", tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 19, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" });
  map.addLayer({ id: "sat", type: "raster", source: "sat", layout: { visibility: "none" } }, firstLabel);
  // district outline
  map.addSource("district", { type: "geojson", data: { type: "Feature", properties: {}, geometry: M.district.geometry } as any });
  map.addLayer({ id: "district-line", type: "line", source: "district", paint: { "line-color": "#38d39f", "line-width": 1.6, "line-dasharray": [3, 2] } });
  for (const t of M.tilesets) map.addSource("ts-" + t, { type: "vector", url: tiles(`data/tiles/${t}.pmtiles`) });
  const sorted = [...M.layers].filter((l) => l.tileset).sort((a, b) => (ORDER[a.geom || "Point"] - ORDER[b.geom || "Point"]) || (b.n - a.n));
  for (const L of sorted) addLayer(L);
  // service requests: density at low zoom
  if (layerById.has("service-requests")) {
    map.addLayer({ id: "service-requests-density~h", type: "heatmap", source: "ts-complaints", "source-layer": "service-requests-density", maxzoom: 13.5, layout: { visibility: "none" },
      paint: { "heatmap-weight": ["interpolate", ["linear"], ["get", "v"], 0, 0, 400, 1], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 10, 13, 30], "heatmap-opacity": .75,
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", .2, "#3b1f5c", .45, "#a1245b", .7, "#ff5d5d", 1, "#ffe08a"] } });
  }
  map.addSource("sel", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({ id: "sel-f", type: "fill", source: "sel", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#ffffff", "fill-opacity": .12 } });
  map.addLayer({ id: "sel-l", type: "line", source: "sel", paint: { "line-color": "#ffffff", "line-width": 2.5 } });
  map.addLayer({ id: "sel-p", type: "circle", source: "sel", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 10, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#fff", "circle-stroke-width": 2.5 } });
  return map;
}

function addLayer(L: Layer) {
  const src = "ts-" + L.tileset, sl = L.id, col = colourExpr(L), vis = { visibility: "none" as const }, minzoom = L.minzoom ?? 9;
  if (L.geom === "Polygon") {
    const parcels = L.id === M.parcels.layer;
    map.addLayer({ id: `${L.id}~f`, type: "fill", source: src, "source-layer": sl, minzoom, layout: vis, paint: { "fill-color": col, "fill-opacity": parcels ? 0 : L.theme === "boundaries" ? .04 : L.n > 5000 ? .16 : .2 } });
    map.addLayer({ id: `${L.id}~l`, type: "line", source: src, "source-layer": sl, minzoom, layout: vis, paint: { "line-color": parcels ? "#aab4bb" : col, "line-width": ["interpolate", ["linear"], ["zoom"], 11, .4, 16, parcels ? 1 : 1.6], "line-opacity": parcels ? .55 : .9 } });
    if (parcels) map.addLayer({ id: `${L.id}~t`, type: "symbol", source: src, "source-layer": sl, minzoom: 16, layout: { ...vis, "text-field": ["get", "n"], "text-font": ["Noto Sans Regular"], "text-size": 10 }, paint: { "text-color": "#c3ccd2", "text-halo-color": "#0b0f12", "text-halo-width": 1.3 } });
  } else if (L.geom === "Polyline") {
    map.addLayer({ id: `${L.id}~l`, type: "line", source: src, "source-layer": sl, minzoom, layout: { ...vis, "line-cap": "round" }, paint: { "line-color": col, "line-width": ["interpolate", ["linear"], ["zoom"], 11, .8, 16, 2.4] } });
  } else {
    map.addLayer({ id: `${L.id}~p`, type: "circle", source: src, "source-layer": sl, minzoom, layout: vis, paint: {
      "circle-color": col, "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, L.n > 2000 ? 1.6 : 3, 16, L.n > 2000 ? 4.5 : 7],
      "circle-stroke-color": "#0b0f12", "circle-stroke-width": L.n > 2000 ? .4 : 1 } });
  }
}

export function setVisible(id: string, on: boolean) {
  const L = layerById.get(id); if (!L) return;
  on ? visible.add(id) : visible.delete(id);
  const all = [...ids(L), ...(id === M.parcels.layer ? [`${id}~t`] : []), ...(id === "service-requests" ? ["service-requests-density~h"] : [])];
  for (const lid of all) if (map.getLayer(lid)) map.setLayoutProperty(lid, "visibility", on ? "visible" : "none");
}

/** what is under the pointer, top-most first; one entry per record */
export function pick(pt: maplibregl.PointLike): { layer: string; i: number; f: MapGeoJSONFeature }[] {
  const p = map.project(map.unproject(pt as any)); const box: [maplibregl.PointLike, maplibregl.PointLike] = [[p.x - 4, p.y - 4], [p.x + 4, p.y + 4]];
  const layers = map.getStyle().layers.map((l) => l.id).filter((id) => id.includes("~") && !id.endsWith("~t") && !id.endsWith("~h") && map.getLayoutProperty(id, "visibility") === "visible");
  const fs = map.queryRenderedFeatures(box, { layers });
  // points and lines need the small box; polygons must contain the exact point
  const exact = new Set(map.queryRenderedFeatures(p as any, { layers }).map((f) => `${f.layer.id}|${f.properties.i}`));
  const seen = new Set<string>(); const out: { layer: string; i: number; f: MapGeoJSONFeature }[] = [];
  for (const f of fs) {
    const lid = f.layer.id.split("~")[0], k = `${lid}|${f.properties.i}`;
    if (f.layer.type === "fill" && !exact.has(`${f.layer.id}|${f.properties.i}`)) continue;
    if (f.layer.type === "line" && f.layer.id.endsWith("~l") && layerById.get(lid)?.geom === "Polygon" && !exact.has(`${lid}~f|${f.properties.i}`)) continue;
    if (seen.has(k)) continue; seen.add(k); out.push({ layer: lid, i: Number(f.properties.i), f });
  }
  return out;
}

export function highlight(features: GeoJSON.Feature[]) { (map.getSource("sel") as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features }); }
export function setBase(b: "map" | "sat") { map.setLayoutProperty("sat", "visibility", b === "sat" ? "visible" : "none"); }
