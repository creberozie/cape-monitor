// Cape Monitor offline support: app files and data are served from storage at once and refreshed in the background.
const C = "cm-v1";
self.addEventListener("install", (e) => { e.waitUntil(caches.open(C).then((c) => c.addAll(["/", "/manifest.webmanifest", "/data/manifest.json"])).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== C).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || e.request.headers.has("range")) return;   // map tiles use range requests: browser cache
  e.respondWith(caches.open(C).then(async (c) => { const hit = await c.match(e.request); const net = fetch(e.request).then((r) => { if (r.ok) c.put(e.request, r.clone()); return r; });
    if (hit) { e.waitUntil(net.catch(() => {})); return hit; } return net; }));
});
