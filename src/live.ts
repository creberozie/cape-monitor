// Point overlays that are not City GIS layers: news and court/tribunal records placed at the suburb they name (from the metro
// build), and live layers read through the site's own /live endpoints (Cloudflare Functions): NASA FIRMS fires and AIS ships.
import * as maplibregl from "maplibre-gl";
import { getJSON, METRO, DISTRICT, BASE } from "./data";
import { map } from "./map";
import { esc } from "./i18n";

export interface Overlay { id: string; theme: "live" | "justice"; name: string; note: string; load: () => Promise<{ items: any[]; error?: string; source?: string; at?: string }> }
const cache = new Map<string, any[]>();
const status = new Map<string, string>();
const inDistrict = (places: [string, string, [number, number]][]) => !DISTRICT || places.some((p) => p[1] === DISTRICT);

export const OVERLAYS: Overlay[] = [
  { id: "live-news", theme: "live", name: "News naming a suburb", note: "Items from news and NGO feeds, placed at the centre of the official suburb they name (not an exact address).",
    load: async () => { const F = await getJSON<any>(METRO + "feed.json"); return { items: F.items.filter((i: any) => i.places?.length && inDistrict(i.places)), at: F.built }; } },
  { id: "live-courts", theme: "justice", name: "Tribunal cases naming a suburb", note: "Competition Tribunal cases whose title names a Cape Town suburb or erf, placed at the suburb centre.",
    load: async () => { const J = await getJSON<any>(METRO + "justice.json"); return { items: J.items.filter((i: any) => i.places?.length && inDistrict(i.places)), at: J.built }; } },
  { id: "live-fires", theme: "live", name: "Active fires (NASA FIRMS, last 24 h)", note: "Satellite fire detections (VIIRS), refreshed through this site's live endpoint.",
    load: async () => { const r = await fetch(new URL("live/fires", BASE)); const j = await r.json(); return { items: j.items || [], error: j.error, source: j.source, at: j.at }; } },
  { id: "live-ships", theme: "live", name: "Ships around the Cape (AIS)", note: "Live AIS positions, refreshed through this site's live endpoint.",
    load: async () => { const r = await fetch(new URL("live/ships", BASE)); const j = await r.json(); return { items: j.items || [], error: j.error, source: j.source, at: j.at }; } },
];

const point = (it: any): [number, number] | null => it.lon != null ? [it.lon, it.lat] : it.places?.[0]?.[2] ?? null;
export async function showOverlay(id: string, on: boolean) {
  const O = OVERLAYS.find((o) => o.id === id)!;
  if (map.getLayer(id + "~p")) map.setLayoutProperty(id + "~p", "visibility", on ? "visible" : "none");
  if (!on) return;
  try {
    const r = await O.load(); cache.set(id, r.items); status.set(id, r.error ? `Not available: ${r.error}` : `${r.items.length} items${r.at ? " · " + String(r.at).slice(0, 16).replace("T", " ") : ""}`);
    (map.getSource(id) as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features: r.items.map((it, i) => ({ it, i, c: point(it) })).filter((x) => x.c)
      .map(({ i, c }) => ({ type: "Feature", properties: { i }, geometry: { type: "Point", coordinates: c! } })) } as any);
  } catch (e) { status.set(id, "Not available: " + e); }
  document.dispatchEvent(new CustomEvent("overlay-status"));
}
export const overlayStatus = (id: string) => status.get(id) || "";

/** the card for a clicked overlay item */
export function overlayCard(id: string, i: number) {
  const it = cache.get(id)?.[i]; const O = OVERLAYS.find((o) => o.id === id); if (!it || !O) return "";
  const where = (it.places || []).map((p: any) => `<span class="pill">${esc(p[0])}</span>`).join("");
  if (id === "live-news") return `<div class="card primary"><div class="kicker">${esc(O.name)}</div><h2><a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.title)} ↗</a></h2><div class="sm mu">${esc(it.feed)} · ${esc(it.date)}</div><p class="sm">${esc(it.summary)}</p>${where}<div class="note">${esc(O.note)}</div></div>`;
  if (id === "live-courts") return `<div class="card primary"><div class="kicker">${esc(O.name)}</div><h2><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.parties)} ↗</a></h2><div class="sm mu">${esc(it.case)} · ${esc(it.type)} · ${esc(it.status)} · ${esc(it.date)}</div>${where}${it.erfs?.length ? `<div class="sm">Erven named: ${it.erfs.map(esc).join(", ")}</div>` : ""}
    <div class="links">${(it.docs || []).map((d: any) => `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)} ↗</a>`).join("")}${(it.suppliers || []).map((s: string) => `<a href="#s=${esc(s)}" data-sup="${esc(s)}">Supplier profile: ${esc(s)}</a>`).join("")}</div><div class="note">${esc(O.note)}</div></div>`;
  return `<div class="card primary"><div class="kicker">${esc(O.name)}</div><h2>${esc(it.name || it.label || "Detection")}</h2><table class="kv">${Object.entries(it).filter(([k]) => !["lon", "lat"].includes(k)).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}<tr><td>Position</td><td class="mono">${esc(it.lat)}, ${esc(it.lon)}</td></tr></table><div class="note">${esc(O.note)}</div></div>`;
}
