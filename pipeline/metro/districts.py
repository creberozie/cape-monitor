"""Metro: the eight planning district outlines and a gazetteer of official suburbs (each with its district), used to
switch districts and to place news, court and notice items. Writes public/data/metro/districts.json."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from arcgis import get, fetch_features
from common import ROOT, DISTRICTS, LABEL, DMD_LAYER, CITY_GIS, now, dump
from shapely.geometry import shape, mapping
from shapely.strtree import STRtree

j = get(DMD_LAYER + "/query", {"where": "1=1", "outFields": "PBDM_RGN_NAME", "outSR": 4326, "f": "geojson", "geometryPrecision": 5})
by_name = {v: k for k, v in DISTRICTS.items()}
polys, out = [], []
for f in j["features"]:
    slug = by_name[f["properties"]["PBDM_RGN_NAME"]]
    g = shape(f["geometry"]); polys.append((slug, g))
    out.append({"slug": slug, "label": LABEL[slug], "bounds": [round(x, 5) for x in g.bounds],
                "outline": mapping(g.simplify(0.0008, preserve_topology=True))})
# official suburbs layer (Theme_Based / Land_Administration or Political boundaries): find it by name
svc = get(CITY_GIS + "Theme_Based/Political_Administrative_Boundaries/MapServer/layers", {"f": "json"})
sub = next(l for l in svc["layers"] if "suburb" in l["name"].lower())
feats, info, oid = fetch_features(f"{CITY_GIS}Theme_Based/Political_Administrative_Boundaries/MapServer/{sub['id']}", precision=5)
name_f = next(f["name"] for f in info["fields"] if "SBRB" in f["name"].upper() or "SUBURB" in f["name"].upper())
tree = STRtree([g for _, g in polys])
gaz = {}
for f in feats:
    if not f.get("geometry"): continue
    g = shape(f["geometry"]); c = g.representative_point()
    hit = [polys[k][0] for k in tree.query(c, predicate="intersects")]
    n = str(f["properties"].get(name_f) or "").strip().upper()
    if n and hit: gaz[n] = {"d": hit[0], "c": [round(c.x, 5), round(c.y, 5)]}
dump({"built": now(), "source": DMD_LAYER, "suburb_source": f"{CITY_GIS}Theme_Based/Political_Administrative_Boundaries/MapServer/{sub['id']}",
      "districts": out, "suburbs": gaz}, os.path.join(ROOT, "public", "data", "metro", "districts.json"))
print(len(out), "districts,", len(gaz), "suburbs")
