// Data access: manifest, sharded attribute files, per-plot dossiers, area stats, feeds, tables. Everything is cached once loaded.
export type Field = [string, string | null];
export interface Layer { id: string; name: string; theme: string; geom: "Point" | "Polyline" | "Polygon" | "Multipoint" | null; n: number; server_count?: number;
  fields: Field[]; label: string | null; cat: string | null; cats: [string, number][]; url: string; retrieved: string; description?: string; custodian?: string;
  source: string; tileset?: string; tilesets?: string[]; minzoom?: number; sub?: string; }
export interface Table { id: string; name: string; n: number; n_city?: number; fields: Field[]; url: string; retrieved: string; shards?: number; scope?: string; note?: string; }
export interface Manifest { app: string; district: { slug: string; label: string; name: string; bounds: [number, number, number, number]; geometry: GeoJSON.Geometry }; built: string; suburbs?: string[];
  themes: { id: string; en: string; af: string }[]; layers: Layer[]; tables: Table[]; feeds: { id: string; name: string; n: number; url: string; retrieved: string }[];
  parcels: { layer: string; shard: number }; skipped: { name: string; service: string; url: string; n: number | null; why: string }[];
  heritage: { finds: number; registers: number; stories: number } | null; tilesets: string[]; }
export interface Dossier { zones?: [string, number][]; records?: [string, number][]; plans?: number[]; requests?: number[]; sales?: number[];
  near?: Record<string, [string, number, number]>; }

const cache = new Map<string, Promise<any>>();
export const BASE = new URL(".", location.href).href;
/** the planning district shown (?d=<slug>); empty = the metro overview */
export const DISTRICT = (new URLSearchParams(location.search).get("d") || "").toLowerCase().replace(/[^a-z-]/g, "");
/** folder of the district's data */
export const DP = DISTRICT ? `data/d/${DISTRICT}/` : "data/metro/none/";
export const METRO = "data/metro/";
export interface DataIndex { built: string; districts: { slug: string; label: string; built: string | null; bounds?: [number, number, number, number]; layers?: number; plots?: number }[]; metro: string | null }
export interface Districts { built: string; districts: { slug: string; label: string; bounds: [number, number, number, number]; outline: GeoJSON.Geometry }[]; suburbs: Record<string, { d: string; c: [number, number] }> }
export const districtUrl = (slug: string, hash = "") => `${location.pathname}${slug ? "?d=" + slug : ""}${hash ? "#" + hash : ""}`;
export const getJSON = <T = any>(url: string): Promise<T> => {
  if (!cache.has(url)) cache.set(url, (async () => {
    const r = await fetch(new URL(url, BASE)); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json();
  })());
  return cache.get(url)!;
};

export let M: Manifest;
export const layerById = new Map<string, Layer>();
export async function loadManifest() {
  if (!DISTRICT) {   // metro overview: no district layers; the outline is the whole city
    const D = await getJSON<Districts>(METRO + "districts.json");
    const b = D.districts.reduce((a, d) => [Math.min(a[0], d.bounds[0]), Math.min(a[1], d.bounds[1]), Math.max(a[2], d.bounds[2]), Math.max(a[3], d.bounds[3])], [180, 90, -180, -90]) as [number, number, number, number];
    M = { app: "Cape Monitor", district: { slug: "", label: "City of Cape Town", name: "CITY OF CAPE TOWN", bounds: b, geometry: { type: "GeometryCollection", geometries: D.districts.map((d) => d.outline) } as any },
      built: D.built, themes: [], layers: [], tables: [], feeds: [], parcels: { layer: "", shard: 2000 }, skipped: [], heritage: null, tilesets: [] };
    return M;
  }
  M = await getJSON<Manifest>(DP + "manifest.json");
  for (const l of M.layers) layerById.set(l.id, l);
  return M;
}

/** one record: all fields as recorded, as [field, alias, value] */
export async function record(layerId: string, i: number): Promise<{ fields: Field[]; values: any[] } | null> {
  const shard = M.parcels.shard;
  const L = layerById.get(layerId) || M.tables.find((t) => t.id === layerId);
  if (!L) return null;
  const rows = await getJSON<any[][]>(`${DP}attrs/${layerId}/${Math.floor(i / shard)}.json`);
  const values = rows[i % shard];
  return values ? { fields: L.fields, values } : null;
}
export const val = (rec: { fields: Field[]; values: any[] } | null, k: string) => rec ? rec.values[rec.fields.findIndex((f) => f[0] === k)] : undefined;

export async function dossier(i: number): Promise<Dossier> {
  const shards = await getJSON<Record<string, Dossier>>(`${DP}parcel/${Math.floor(i / M.parcels.shard)}.json`);
  return shards[String(i)] || {};
}

export const tableRows = async (t: Table): Promise<any[][]> => {
  if (t.shards) { const parts = await Promise.all(Array.from({ length: t.shards }, (_, k) => getJSON<any[][]>(`${DP}tables/${t.id}-${k}.json`))); return parts.flat(); }
  const n = Math.max(1, Math.ceil(t.n / M.parcels.shard));
  const parts = await Promise.all(Array.from({ length: n }, (_, k) => getJSON<any[][]>(`${DP}attrs/${t.id}/${k}.json`)));
  return parts.flat();
};

// plot lookup by parcel key and by erf number (built on first use from the parcel attribute shards)
let parcelIndex: Promise<{ byKey: Map<string, number>; rows: { i: number; erf: string; addr: string; sub: string }[] }> | null = null;
export function parcels() {
  if (!parcelIndex) parcelIndex = (async () => {
    const L = layerById.get(M.parcels.layer)!; const n = Math.ceil(L.n / M.parcels.shard);
    const parts = await Promise.all(Array.from({ length: n }, (_, k) => getJSON<any[][]>(`${DP}attrs/${L.id}/${k}.json`)));
    const f = (k: string) => L.fields.findIndex((x) => x[0] === k);
    const iKey = f("SL_LAND_PRCL_KEY"), iErf = f("PRTY_NMBR"), iSub = f("OFC_SBRB_NAME"), iNo = f("ADR_NO"), iStr = f("STR_NAME"), iTyp = f("LU_STR_NAME_TYPE"), iAlt = f("ALT_NAME");
    const byKey = new Map<string, number>(); const rows: { i: number; erf: string; addr: string; sub: string }[] = [];
    parts.flat().forEach((r, i) => {
      byKey.set(String(r[iKey]), i);
      rows.push({ i, erf: String(r[iErf] ?? ""), sub: String(r[iSub] ?? r[iAlt] ?? ""), addr: [r[iNo], r[iStr], r[iTyp]].filter((x) => x != null && x !== "").join(" ") });
    });
    return { byKey, rows };
  })();
  return parcelIndex;
}
