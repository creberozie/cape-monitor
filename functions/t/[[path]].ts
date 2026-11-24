// Tile files (PMTiles) with HTTP range requests. Cloudflare Pages serves static files whole, ignoring Range, so every tile
// file lives under /t/ and is answered here: the whole file is fetched once from the site's own assets into the edge cache,
// and each range is answered from it (206 Partial Content). The ?v= query (the data build time) keys the cache, so a new
// data build is never answered from an old cached file.
interface Env { ASSETS: Fetcher }
const HDR = { "content-type": "application/octet-stream", "accept-ranges": "bytes", "access-control-allow-origin": "*" };

function partial(buf: ArrayBuffer, range: string | null) {
  const size = buf.byteLength;
  const m = range && /^bytes=(\d*)-(\d*)$/.exec(range.trim());
  if (!m) return new Response(buf, { headers: { ...HDR, "content-length": String(size), "cache-control": "public, max-age=3600" } });
  let start = m[1] === "" ? size - Number(m[2]) : Number(m[1]);
  let end = m[1] === "" || m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  if (start < 0) start = 0;
  if (start >= size || start > end) return new Response(null, { status: 416, headers: { ...HDR, "content-range": `bytes */${size}` } });
  return new Response(buf.slice(start, end + 1), { status: 206, headers: { ...HDR, "content-range": `bytes ${start}-${end}/${size}`, "content-length": String(end - start + 1), "cache-control": "public, max-age=3600" } });
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env, waitUntil }) => {
  const url = new URL(request.url);
  const range = request.headers.get("range");
  const cache = (caches as any).default as Cache;
  const key = new Request(url.toString());
  let whole = await cache.match(key);
  if (!whole) {
    const asset = await env.ASSETS.fetch(new Request(new URL(url.pathname, url).toString()));
    if (!asset.ok || (asset.headers.get("content-type") || "").includes("text/html")) return new Response("not found", { status: 404 });   // no SPA fallback for tiles
    const buf = await asset.arrayBuffer();
    waitUntil(cache.put(key, new Response(buf, { headers: { ...HDR, "content-length": String(buf.byteLength), "cache-control": "public, max-age=604800" } })));
    return partial(buf, range);
  }
  if (range) {
    const hit = await cache.match(new Request(url.toString(), { headers: { range } }));
    if (hit && hit.status === 206) { const r = new Response(hit.body, hit); r.headers.set("access-control-allow-origin", "*"); return r; }
  }
  return partial(await whole.arrayBuffer(), range);
};
