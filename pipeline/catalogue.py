"""Step 1: discover every City of Cape Town GIS layer and count its records inside the chosen planning district.
Writes pipeline/out/<district>/catalogue.json. Run: CM_DISTRICT=blaauwberg python3 pipeline/catalogue.py"""
import json, os, sys, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
from arcgis import get, post, spatial, query_polygon
from common import paths, CITY_GIS as ROOT, DMD_LAYER as dmd

P = paths(); OUT = P["out"]; DISTRICT = P["name"]

# the district boundary (official Development Management District)
area = get(dmd + "/query", {"where": f"PBDM_RGN_NAME='{DISTRICT}'", "outFields": "*", "outSR": 4326, "f": "geojson", "geometryPrecision": 5})
assert area["features"], DISTRICT
json.dump(area, open(os.path.join(OUT, "district.geojson"), "w"))
geom = area["features"][0]["geometry"]
FILT = spatial(polygon=query_polygon(geom))

skip = ("Base_Data", "Test", "Overview", "Facility_Booking", "ECAMP", "Water_Dashboard_Background", "BU_")
folder = get(ROOT + "Theme_Based", {"f": "json"})
services = sorted({s["name"] for s in folder["services"] if s["type"] == "MapServer" and not any(k in s["name"] for k in skip)})

def layers(svc):
    try:
        j = get(f"{ROOT}{svc}/MapServer/layers", {"f": "json"})
        return [(svc, l) for l in j.get("layers", []) + j.get("tables", []) if l.get("type") != "Group Layer"]
    except Exception as e:
        print("FAILED", svc, e); return []

with cf.ThreadPoolExecutor(6) as ex:
    all_layers = [x for xs in ex.map(layers, services) for x in xs]

def count(item):
    svc, l = item
    url = f"{ROOT}{svc}/MapServer/{l['id']}"
    rec = {"url": url, "service": svc.split("/")[-1], "id": l["id"], "name": l["name"].strip(), "geom": (l.get("geometryType") or "").replace("esriGeometry", "") or None,
           "fields": [[f["name"], f.get("alias"), f.get("type")] for f in l.get("fields") or []], "description": (l.get("description") or "").strip()[:500],
           "copyright": (l.get("copyrightText") or "").strip()[:200], "maxRecordCount": l.get("maxRecordCount")}
    try:
        rec["n_district"] = post(url + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json", **(FILT if rec["geom"] else {})}).get("count")
    except Exception as e:
        rec["n_district"] = None; rec["error"] = str(e)[:200]
    return rec

cat = []
with cf.ThreadPoolExecutor(10) as ex:
    for k, rec in enumerate(ex.map(count, all_layers)):
        cat.append(rec)
        if k % 25 == 0: print(f"  counted {k + 1}/{len(all_layers)}", flush=True)
json.dump({"district": DISTRICT, "layers": cat}, open(os.path.join(OUT, "catalogue.json"), "w"), indent=1)
print(len(cat), "layers;", sum(1 for c in cat if c.get("n_district")), "with records in", DISTRICT, ";", sum(1 for c in cat if c.get("error")), "errors")
