// Stellenbosch Watch offline support. App files and data: served from storage at once and refreshed in the background
// (stale-while-revalidate). Live layers and the data index: always from the network first. Map tiles use range requests
// and are left to the browser cache.
const C = "sw-v1";
self.addEventListener("install", (e) => { e.waitUntil(caches.open(C).then((c) => c.addAll(["./", "manifest.webmanifest"])).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== C && k.startsWith("sw-")).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || e.request.headers.has("range")) return;
  const fresh = u.pathname.includes("/live/") || u.pathname.endsWith("/data/index.json") || u.pathname.endsWith("/feed.json");
  e.respondWith(caches.open(C).then(async (c) => {
    const net = fetch(e.request).then((r) => { if (r.ok && !u.pathname.includes("/live/")) c.put(e.request, r.clone()); return r; });
    if (fresh) return net.catch(() => c.match(e.request));
    const hit = await c.match(e.request); if (hit) { e.waitUntil(net.catch(() => {})); return hit; } return net;
  }));
});
