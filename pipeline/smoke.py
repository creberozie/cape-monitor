"""After deploying: fetch the live site's key files and confirm tile files answer HTTP range requests. Usage: smoke.py <url>"""
import json, sys, time, urllib.request
base = sys.argv[1].rstrip("/") + "/"
def get(path, headers=None):
    for k in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path, headers={"User-Agent": "cape-monitor-smoke", **(headers or {})}), timeout=60) as r:
                return r.status, r.headers, r.read()
        except Exception as e:
            err = e; time.sleep(10)
    raise SystemExit(f"FAIL {path}: {err}")
ok = True
s, h, b = get(""); print("page", s, len(b))
s, h, b = get("data/index.json"); idx = json.loads(b); print("districts with data:", [d["slug"] for d in idx["districts"] if d["built"]])
for d in [d for d in idx["districts"] if d["built"]][:8]:
    s, h, b = get(f"data/d/{d['slug']}/manifest.json"); m = json.loads(b)
    t = m["tilesets"][0]
    s, h, b = get(f"data/d/{d['slug']}/tiles/{t}.pmtiles", {"Range": "bytes=0-126"})
    print(f"  {d['slug']}: manifest ok ({len(m['layers'])} layers); tiles {t} range request -> HTTP {s}, {len(b)} bytes")
    ok &= s == 206 and len(b) == 127
for p in ("data/metro/money/money.json", "live/news"):
    s, h, b = get(p); print(" ", p, s, len(b))
print("SMOKE OK" if ok else "SMOKE: range requests not honoured"); sys.exit(0 if ok else 1)
