"""Step 2: download every selected City GIS layer for the district into pipeline/cache/city/<layer>.json
(GeoJSON features with readable values). Already-downloaded layers are skipped unless --refresh is given."""
import json, os, sys, re, datetime, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
from arcgis import fetch_features, domains, spatial, query_polygon, in_district
from themes import theme_for, excluded, slug
from common import paths

P = paths(); OUT = P["out"]; CACHE = P["city"]
REFRESH = "--refresh" in sys.argv
MAX = 400_000

cat = json.load(open(os.path.join(OUT, "catalogue.json")))
area = json.load(open(os.path.join(OUT, "district.geojson")))["features"][0]["geometry"]
FILT = spatial(polygon=query_polygon(area)); INSIDE = in_district(area)

# choose layers: records in the district, not excluded, one copy per (name, geometry) preferring the named theme services
chosen, skipped, seen = [], [], {}
for l in sorted(cat["layers"], key=lambda l: (l["service"].startswith("ODP_SPLIT"), l["service"], l["id"])):
    n = l.get("n_district")
    why = excluded(l["name"]) or ("no records in this district" if not n else None) or (f"{n} records; over the {MAX} limit" if n and n > MAX else None)
    key = (l["name"].lower(), l["geom"])
    if not why and key in seen:
        why = f"duplicate of {seen[key]}"
    if why:
        skipped.append({"name": l["name"], "service": l["service"], "url": l["url"], "n": n, "why": why}); continue
    if not re.search(r"[A-Za-z]", l["name"]):   # a few City layers have no proper name
        l["name"] = "City of Cape Town boundary" if any(f[0] == "CITY_NAME" for f in l["fields"]) else f"{l['service'].replace('_', ' ')} layer {l['id']}"
    lid = slug(l["name"])
    while lid in {c["id"] for c in chosen}:
        lid = slug(f"{l['name']}-{l['service']}")
    seen[key] = lid
    chosen.append({"id": lid, "name": l["name"], "service": l["service"], "url": l["url"], "geom": l["geom"], "n": n,
                   "theme": theme_for(l["service"], l["name"]), "description": l["description"], "copyright": l["copyright"],
                   "fields": l["fields"]})
json.dump({"chosen": chosen, "skipped": skipped}, open(os.path.join(OUT, "selection.json"), "w"), indent=1)
print(len(chosen), "layers chosen,", len(skipped), "left out")

def ms_to_iso(v):
    try:
        return datetime.datetime.fromtimestamp(v / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return v

def clean(v):
    if isinstance(v, str):
        v = re.sub(r"\s+", " ", v).strip()
        return v or None
    return v

def run(c):
    path = os.path.join(CACHE, c["id"] + ".json")
    if os.path.exists(path) and not REFRESH:
        return c["id"], "cached"
    try:
        feats, info, oid = fetch_features(c["url"], filt=FILT if c["geom"] else None, geometry=bool(c["geom"]), log=lambda m: print(c["id"], m))
    except Exception as e:
        return c["id"], f"FAILED {e}"
    dom, sub, tf = domains(info)
    dates = {f["name"] for f in info.get("fields", []) if f.get("type") == "esriFieldTypeDate"}
    drop = {k for k in (f["name"] for f in info.get("fields", [])) if re.match(r"^(SHAPE|Shape)(\.|_|$)|^GlobalID$|^created_|^last_edited_", k)}
    out = []
    feats = [f for f in feats if INSIDE(f.get("geometry"))] if c["geom"] else feats
    for f in feats:
        p = {}
        for k, v in (f.get("properties") or {}).items():
            if k in ("SHAPE.STArea()", "Shape.STArea()", "Shape__Area") and isinstance(v, (int, float)):
                p["_area"] = round(v); continue
            if k in drop:
                continue
            if v is not None and k == tf and str(v) in sub:
                v = sub[str(v)]
            elif v is not None and str(v) in dom.get(k, {}):
                v = dom[k][str(v)]
            elif k in dates and isinstance(v, (int, float)):
                v = ms_to_iso(v)
            p[k] = clean(v)
        out.append({"g": f.get("geometry"), "p": p, "oid": (f.get("properties") or {}).get(oid)})
    json.dump({"layer": c["id"], "retrieved": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "server_count": c["n"],
               "fields": [[f["name"], f.get("alias"), f.get("type")] for f in info.get("fields", []) if f["name"] not in drop] + ([["_area", "Mapped area (m²)", "double"]] if any("_area" in o["p"] for o in out[:50]) else []),
               "features": out}, open(path, "w"))
    return c["id"], f"{len(out)} features"

with cf.ThreadPoolExecutor(int(os.environ.get("CM_WORKERS", "10"))) as ex:
    futs = [ex.submit(run, c) for c in sorted(chosen, key=lambda c: c["n"] or 0)]
    for fu in cf.as_completed(futs):
        lid, msg = fu.result(); print(lid, msg, flush=True)
