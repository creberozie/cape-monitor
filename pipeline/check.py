"""Checks run before anything is saved or deployed. Exit code 1 stops the workflow, so a broken build never replaces good data.
  check.py district <slug>   the district build is complete and sane
  check.py metro             the metro build is complete
  check.py dist              the built site fits Cloudflare Pages (files <= 25 MiB, <= 20 000 files)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
MiB = 1024 * 1024
errors = []
def need(cond, msg):
    if not cond: errors.append(msg)

kind = sys.argv[1]
if kind == "district":
    d = os.path.join(ROOT, "public", "data", "d", sys.argv[2])
    m = json.load(open(os.path.join(d, "manifest.json")))
    need(len(m["layers"]) >= 50, f"only {len(m['layers'])} map layers")
    need(m["parcels"]["layer"], "no land parcel layer")
    for t in m["tilesets"]:
        p = os.path.join(d, "tiles", t + ".pmtiles"); need(os.path.exists(p), f"missing tiles {t}")
    print(f"{sys.argv[2]}: {len(m['layers'])} layers, {len(m['tables'])} tables, {len(m['tilesets'])} tile files, {len(m['skipped'])} left out")
elif kind == "metro":
    d = os.path.join(ROOT, "public", "data", "metro")
    for f in ("money/money.json", "money/suppliers.json", "money/flags.json", "districts.json"):
        need(os.path.exists(os.path.join(d, f)), f"missing {f}")
    if os.path.exists(os.path.join(d, "money/money.json")):
        c = json.load(open(os.path.join(d, "money/money.json")))["counts"]; print("metro money:", c)
        need(c.get("awards", 0) > 1000 and c.get("rfq", 0) > 10000, "money tables too small")
elif kind == "muni":   # check.py muni <slug>: another municipality's build (ZopStopper)
    d = os.path.join(ROOT, "public", "data", "muni", sys.argv[2])
    for f in ("money/money.json", "money/suppliers.json", "money/flags.json", "sources.json"):
        need(os.path.exists(os.path.join(d, f)), f"missing {f}")
    if os.path.exists(os.path.join(d, "money/money.json")):
        c = json.load(open(os.path.join(d, "money/money.json")))["counts"]; print(sys.argv[2], "money:", c)
        need(c.get("etenders", 0) > 0, "no eTender records"); need(c.get("awards", 0) + c.get("rfq", 0) > 100, "award registers gave too few rows")
elif kind == "dist":
    d = os.path.join(ROOT, "dist"); n = 0
    for base, _, files in os.walk(d):
        for f in files:
            n += 1; s = os.path.getsize(os.path.join(base, f))
            need(s <= 25 * MiB, f"{os.path.relpath(os.path.join(base, f), d)} is {s / MiB:.1f} MiB (limit 25)")
    need(n <= 20000, f"{n} files (limit 20 000)")
    print(f"dist: {n} files")
if errors:
    print("CHECK FAILED:\n  " + "\n  ".join(errors)); sys.exit(1)
print("check ok")
