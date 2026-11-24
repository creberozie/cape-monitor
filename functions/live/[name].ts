// Live layers, served by Cloudflare (Pages Functions run on Workers) and cached at the edge for a few minutes.
//   /live/fires  NASA FIRMS VIIRS (Suomi NPP) detections, last 24 h, around the Cape (no key needed)
//   /live/ships  AIS positions around the Cape from aisstream.io (needs the AISSTREAM_KEY secret on the Pages project)
//   /live/news   latest Western Cape headlines (IOL Western Cape, News24) for a quick live check
interface Env { AISSTREAM_KEY?: string }
const BOX = { w: 17.6, s: -34.9, e: 19.6, n: -32.9 };   // the Cape Peninsula, False Bay, Saldanha approaches
const json = (body: unknown, maxAge = 300) => new Response(JSON.stringify(body), { headers: { "content-type": "application/json; charset=utf-8", "cache-control": `public, max-age=${maxAge}` } });
const now = () => new Date().toISOString();

async function fires() {
  const src = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Southern_Africa_24h.csv";
  const r = await fetch(src, { cf: { cacheTtl: 600 } } as RequestInit);
  if (!r.ok) return { items: [], error: `FIRMS answered ${r.status}`, source: src, at: now() };
  const [head, ...lines] = (await r.text()).trim().split(/\r?\n/); const h = head.split(",");
  const items = lines.map((l) => Object.fromEntries(l.split(",").map((v, k) => [h[k], v]))).map((o: any) => ({ lat: +o.latitude, lon: +o.longitude, date: o.acq_date, time_utc: o.acq_time,
    confidence: o.confidence, frp_mw: o.frp, satellite: o.satellite, day_night: o.daynight, name: `Fire detection ${o.acq_date} ${o.acq_time} UTC` }))
    .filter((o) => o.lon >= BOX.w && o.lon <= BOX.e && o.lat >= BOX.s && o.lat <= BOX.n);
  return { items, source: src, at: now() };
}

async function ships(env: Env) {
  if (!env.AISSTREAM_KEY) return { items: [], error: "AIS needs a free aisstream.io API key saved as the AISSTREAM_KEY secret of this site", source: "https://aisstream.io", at: now() };
  const r = await fetch("https://stream.aisstream.io/v0/stream", { headers: { Upgrade: "websocket" } });
  const ws = (r as any).webSocket as WebSocket | null;
  if (!ws) return { items: [], error: `aisstream answered ${r.status}`, source: "https://aisstream.io", at: now() };
  (ws as any).accept();
  const seen = new Map<number, any>();
  ws.addEventListener("message", (ev: MessageEvent) => {
    try {
      const m = JSON.parse(typeof ev.data === "string" ? ev.data : new TextDecoder().decode(ev.data as ArrayBuffer)); const md = m.MetaData || {};
      const p = m.Message?.PositionReport || m.Message?.StandardClassBPositionReport || {};
      if (md.MMSI && md.latitude != null) seen.set(md.MMSI, { mmsi: md.MMSI, name: (md.ShipName || "").trim() || `MMSI ${md.MMSI}`, lat: md.latitude, lon: md.longitude,
        speed_knots: p.Sog, course: p.Cog, heading: p.TrueHeading, nav_status: p.NavigationalStatus, time_utc: md.time_utc });
    } catch { /* ignore malformed messages */ }
  });
  ws.send(JSON.stringify({ APIKey: env.AISSTREAM_KEY, BoundingBoxes: [[[BOX.s, BOX.w], [BOX.n, BOX.e]]], FilterMessageTypes: ["PositionReport", "StandardClassBPositionReport"] }));
  await new Promise((res) => setTimeout(res, 8000));
  try { ws.close(); } catch { /* already closed */ }
  return { items: [...seen.values()], source: "https://aisstream.io", at: now(), note: "Positions received in an 8-second listening window; ships that did not report in that window are not shown." };
}

async function news() {
  const feeds = ["https://iol.co.za/rss/iol/news/south-africa/western-cape", "https://feeds.capi24.com/v1/Search/articles/news24/SouthAfrica/rss"];
  const items: any[] = [];
  for (const u of feeds) {
    try {
      const x = await (await fetch(u, { cf: { cacheTtl: 300 } } as RequestInit)).text();
      for (const m of x.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
        const g = (t: string) => (m[1].match(new RegExp(`<${t}>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${t}>`)) || [])[1]?.trim() || "";
        items.push({ title: g("title"), link: g("link"), date: g("pubDate"), source: u });
      }
    } catch { /* one feed down does not stop the other */ }
  }
  return { items: items.slice(0, 60), at: now() };
}

export const onRequestGet: PagesFunction<Env> = async (ctx) => {
  const name = String(ctx.params.name);
  const cache = (caches as any).default as Cache; const key = new Request(new URL(`/live/${name}`, ctx.request.url).toString());
  const hit = await cache.match(key); if (hit) return hit;
  let res: Response;
  try {
    if (name === "fires") res = json(await fires(), 600);
    else if (name === "ships") res = json(await ships(ctx.env), 60);
    else if (name === "news") res = json(await news(), 300);
    else return json({ error: "unknown live layer" }, 60);
  } catch (e) { return json({ items: [], error: String(e), at: now() }, 30); }
  ctx.waitUntil(cache.put(key, res.clone()));
  return res;
};
