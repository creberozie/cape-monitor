// Data access: manifest, sharded attribute files, per-plot dossiers, area stats, feeds, tables. Everything is cached once loaded.
export type Field = [string, string | null];
export interface Layer { id: string; name: string; theme: string; geom: "Point" | "Polyline" | "Polygon" | "Multipoint" | null; n: number; server_count?: number;
  fields: Field[]; label: string | null; cat: string | null; cats: [string, number][]; url: string; retrieved: string; description?: string; custodian?: string;
  source: string; tileset?: string; minzoom?: number; }
export interface Table { id: string; name: string; n: number; n_city?: number; fields: Field[]; url: string; retrieved: string; shards?: number; scope?: string; note?: string; }
export interface Manifest { app: string; district: { name: string; bounds: [number, number, number, number]; geometry: GeoJSON.Geometry }; built: string;
  themes: { id: string; en: string; af: string }[]; layers: Layer[]; tables: Table[]; feeds: { id: string; name: string; n: number; url: string; retrieved: string }[];
  parcels: { layer: string; shard: number }; skipped: { name: string; service: string; url: string; n: number | null; why: string }[];
  heritage: { finds: number; registers: number; stories: number } | null; tilesets: string[]; }
export interface Dossier { zones?: [string, number][]; records?: [string, number][]; plans?: number[]; requests?: number[]; sales?: number[];
  near?: Record<string, [string, number, number]>; }

const cache = new Map<string, Promise<any>>();
export const BASE = new URL(".", location.href).href;
// PACKED: hosts that serve only text formats get every data file as base64 of its gzip (name + ".gz.b64.txt")
export const PACKED = import.meta.env.VITE_PACK === "1";
export const unb64 = (s: string) => { const b = atob(s.trim()); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u.buffer; };
// data files are grouped into bundles (data/bundle-N.txt: one JSON object of path -> base64), listed in data/bundles.txt
let bundleIndex: Promise<Record<string, number>> | null = null;
const bundles = new Map<number, Promise<Record<string, string>>>();
const fetchText = async (u: string) => { const r = await fetch(new URL(u, BASE)); if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.text(); };
export const packedBytes = async (url: string) => {
  bundleIndex ??= fetchText("data/bundles.txt").then(JSON.parse);
  const b = (await bundleIndex)[url];
  if (b == null) return unb64(await fetchText(url + ".b64.txt"));
  if (!bundles.has(b)) bundles.set(b, fetchText(`data/bundle-${b}.txt`).then(JSON.parse));
  const s = (await bundles.get(b)!)[url]; if (s == null) throw new Error(url + " missing"); return unb64(s);
};
export const getJSON = <T = any>(url: string): Promise<T> => {
  if (!cache.has(url)) cache.set(url, (async () => {
    if (PACKED && url.startsWith("data/")) {
      const gz = await packedBytes(url + ".gz");
      return JSON.parse(await new Response(new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"))).text());
    }
    const r = await fetch(new URL(url, BASE)); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json();
  })());
  return cache.get(url)!;
};

export let M: Manifest;
export const layerById = new Map<string, Layer>();
export async function loadManifest() {
  M = await getJSON<Manifest>("data/manifest.json");
  for (const l of M.layers) layerById.set(l.id, l);
  return M;
}

/** one record: all fields as recorded, as [field, alias, value] */
export async function record(layerId: string, i: number): Promise<{ fields: Field[]; values: any[] } | null> {
  const shard = M.parcels.shard;
  const L = layerById.get(layerId) || M.tables.find((t) => t.id === layerId);
  if (!L) return null;
  const rows = await getJSON<any[][]>(`data/attrs/${layerId}/${Math.floor(i / shard)}.json`);
  const values = rows[i % shard];
  return values ? { fields: L.fields, values } : null;
}
export const val = (rec: { fields: Field[]; values: any[] } | null, k: string) => rec ? rec.values[rec.fields.findIndex((f) => f[0] === k)] : undefined;

export async function dossier(i: number): Promise<Dossier> {
  const shards = await getJSON<Record<string, Dossier>>(`data/parcel/${Math.floor(i / M.parcels.shard)}.json`);
  return shards[String(i)] || {};
}

export const tableRows = async (t: Table): Promise<any[][]> => {
  if (t.shards) { const parts = await Promise.all(Array.from({ length: t.shards }, (_, k) => getJSON<any[][]>(`data/tables/${t.id}-${k}.json`))); return parts.flat(); }
  const n = Math.max(1, Math.ceil(t.n / M.parcels.shard));
  const parts = await Promise.all(Array.from({ length: n }, (_, k) => getJSON<any[][]>(`data/attrs/${t.id}/${k}.json`)));
  return parts.flat();
};

// plot lookup by parcel key and by erf number (built on first use from the parcel attribute shards)
let parcelIndex: Promise<{ byKey: Map<string, number>; rows: { i: number; erf: string; addr: string; sub: string }[] }> | null = null;
export function parcels() {
  if (!parcelIndex) parcelIndex = (async () => {
    const L = layerById.get(M.parcels.layer)!; const n = Math.ceil(L.n / M.parcels.shard);
    const parts = await Promise.all(Array.from({ length: n }, (_, k) => getJSON<any[][]>(`data/attrs/${L.id}/${k}.json`)));
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
