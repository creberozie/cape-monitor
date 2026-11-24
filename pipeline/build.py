"""Step 4: turn the downloads into what the app reads (public/data):
  manifest.json          every layer, table, feed and source, with counts, fields, retrieval time and why anything is left out
  attrs/<layer>/<n>.json every record, all fields as recorded (sharded, loaded on click)
  tiles/<theme>.pmtiles  vector tiles per theme (z/x/y in one file)
  parcel/<n>.json        the per-property dossier: zoning, heritage, building plans, City sales, service requests, nearest services
  areas.json             per suburb and ward: service requests by type and month, building plans by year, population, licences
  feed.json              news and GI-TOC items, tagged with the places they mention
  tables/<id>-<n>.json   city-wide tables (quotation and tender awards)"""
import json, os, re, sys, math, shutil, subprocess, collections, datetime
from shapely.geometry import shape as _shape, Point
from shapely.validation import make_valid
def shape(g):
    s = _shape(g)
    return s if s.is_valid else make_valid(s)
from shapely.strtree import STRtree
from shapely.prepared import prep

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out"); CITY = os.path.join(HERE, "cache", "city"); EXTRA = os.path.join(HERE, "cache", "extra")
PUB = os.path.join(ROOT, "public", "data"); TMP = os.path.join(HERE, "tmp")
sys.path.insert(0, HERE)
from themes import THEMES

SHARD = 2000
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
for d in ("attrs", "tiles", "parcel", "tables", "pos"):
    if d == "tiles" and os.environ.get("CM_SKIP_TILES") == "1": continue
    shutil.rmtree(os.path.join(PUB, d), ignore_errors=True); os.makedirs(os.path.join(PUB, d), exist_ok=True)
if os.environ.get("CM_SKIP_TILES") != "1": shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)

sel = json.load(open(os.path.join(OUT, "selection.json")))
district = json.load(open(os.path.join(OUT, "district.geojson")))["features"][0]
DGEOM = shape(district["geometry"]); DPREP = prep(DGEOM)

def dump(obj, *p):
    path = os.path.join(PUB, *p); os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w"), ensure_ascii=False, separators=(",", ":"))

LABEL = re.compile(r"(^|_)(NAME|NM|TITLE|DESC|DSCR|STN|SITE_NAME|ADR|ADDRESS|LABEL)(_|$)", re.I)
CAT = re.compile(r"(TYPE|TYP|CAT|CTGR|CLASS|CLS|ZONE|ZONING|STATUS|STS|GRD|GRADE|USE|KIND|SYST|DSCR)", re.I)

def pick_fields(fields, rows):
    """Label field (name-like, mostly filled) and category field (2-24 distinct values) for colouring."""
    names = [f[0] for f in fields]
    filled = {k: sum(1 for r in rows if r.get(k) not in (None, "")) for k in names}
    n = max(1, len(rows))
    label = next((k for k in names if LABEL.search(k) and filled[k] > 0.5 * n), None)
    cat, best = None, 0
    for k in names:
        if filled[k] < 0.5 * n or k.upper().endswith(("KEY", "_ID", "ID", "OBJECTID", "CODE", "NMBR")):
            continue
        vals = collections.Counter(str(r.get(k)) for r in rows if r.get(k) not in (None, ""))
        if 2 <= len(vals) <= 24:
            score = (2 if CAT.search(k) else 1) * filled[k]
            if score > best:
                cat, best = k, score
    return label, cat

def write_pos(lid, gs):
    """position of every record (point, or bounding box), so a record can be found on the map from lists and links"""
    def bb(g):
        if not g: return None
        if g["type"] == "Point": return [round(c, 6) for c in g["coordinates"]]
        xs, ys = [], []
        def w(c):
            if isinstance(c[0], (int, float)): xs.append(c[0]); ys.append(c[1])
            else: [w(x) for x in c]
        w(g["coordinates"]); return [round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)]
    out = {}
    for i, g in enumerate(gs): out.setdefault(str(i // SHARD), []).append(bb(g))
    dump(out, "pos", lid + ".json")

# ---------------------------------------------------------------- City GIS layers
layers, tilejobs, geoms = [], collections.defaultdict(list), {}
tables, feeds = [], []
for c in sel["chosen"]:
    if not c["id"]:
        c = {**c, "id": "city-of-cape-town-boundary", "name": "City of Cape Town boundary", "_file": ".json"}
    path = os.path.join(CITY, c.get("_file") or c["id"] + ".json")
    if not os.path.exists(path):
        sel["skipped"].append({"name": c["name"], "service": c["service"], "url": c["url"], "n": c["n"], "why": "download failed this run"}); continue
    raw = json.load(open(path))
    feats = raw["features"]
    if c["geom"] and not any(f["g"] for f in feats):   # the City publishes some layers without positions
        c = {**c, "geom": None, "no_geometry": True}
    fields = [f for f in raw["fields"] if f[0] not in ("OBJECTID", "OBJECTID_1", "FID")]
    rows = [f["p"] for f in feats]
    label, cat = pick_fields(fields, rows)
    lid = c["id"]
    # attributes, as recorded, in field order
    keys = [f[0] for f in fields]
    for s in range(0, len(rows), SHARD):
        dump([[r.get(k) for k in keys] + [f["oid"]] for r, f in zip(rows[s:s + SHARD], feats[s:s + SHARD])], "attrs", lid, f"{s // SHARD}.json")
    cats = collections.Counter(str(r.get(cat)) for r in rows if cat and r.get(cat) not in (None, "")).most_common(24) if cat else []
    meta = {"id": lid, "name": c["name"], "theme": c["theme"], "geom": c["geom"], "n": len(rows), "server_count": raw.get("server_count"),
            "fields": [[f[0], f[1]] for f in fields] + [["_oid", "City record number (OBJECTID)"]], "label": label, "cat": cat, "cats": cats,
            "url": c["url"], "retrieved": raw["retrieved"], "description": c["description"], "custodian": c["copyright"], "source": "City of Cape Town GIS"}
    if c["geom"]:
        g = c["geom"]
        n = len(rows)
        heavy = n > 20000
        minz = 13 if (heavy and g != "Polygon") else 12 if heavy else 9 if n < 3000 else 11
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": f["g"], "properties": {"i": i, **({"n": str(f["p"].get(label))[:60]} if label and f["p"].get(label) else {}),
                                                                   **({"c": str(f["p"].get(cat))} if cat and f["p"].get(cat) is not None else {})}}
            for i, f in enumerate(feats) if f["g"]]}
        fp = os.path.join(TMP, lid + ".geojson"); json.dump(fc, open(fp, "w"))
        ts = c["theme"] if n < 25000 else f"{c['theme']}-{lid}"   # big layers get their own file (Cloudflare limit: 25 MB per file)
        meta.update({"tileset": ts, "minzoom": minz})
        tilejobs[ts].append({"id": lid, "file": fp, "minzoom": minz, "maxzoom": 15 if heavy else 14})
        geoms[lid] = feats
        write_pos(lid, [f["g"] for f in feats])
    if not c["geom"]:   # attribute-only: a record table, not a map layer
        tables.append({"id": lid, "name": c["name"], "n": len(rows), "fields": meta["fields"], "url": c["url"], "retrieved": raw["retrieved"], "theme": c["theme"],
                       "note": "The City publishes this layer without map positions, so it is listed as a table." if c.get("no_geometry") else None})
    else:
        layers.append(meta)
    print(f"{lid}: {len(rows)} ({c['theme']}) label={label} cat={cat}", flush=True)

# ---------------------------------------------------------------- extra: service requests as a tiled point layer + area stats
def extra(sid):
    p = os.path.join(EXTRA, sid + ".json")
    return json.load(open(p)) if os.path.exists(p) else None

sr = extra("service-requests")
if sr:
    rows = [r for r in sr["rows"] if r.get("g")]
    fields = [[f[0], f[1]] for f in sr["fields"] if f[0] not in ("ObjectId",)]
    keys = [f[0] for f in fields]
    rows.sort(key=lambda r: r["p"].get("Created_On_Date") or "")
    for s in range(0, len(rows), SHARD):
        dump([[r["p"].get(k) for k in keys] for r in rows[s:s + SHARD]], "attrs", "service-requests", f"{s // SHARD}.json")
    types = collections.Counter(r["p"].get("C3_Complaint_Type") or r["p"].get("Notification_type") for r in rows)
    top = [t for t, _ in types.most_common(23)]
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": r["g"], "properties": {
        "i": i, "c": (r["p"].get("C3_Complaint_Type") or "") if (r["p"].get("C3_Complaint_Type") in top) else "Other",
        "d": (r["p"].get("Created_On_Date") or "")[:7]}} for i, r in enumerate(rows)]}
    fp = os.path.join(TMP, "service-requests.geojson"); json.dump(fc, open(fp, "w"))
    tilejobs["complaints"].append({"id": "service-requests", "file": fp, "minzoom": 13, "maxzoom": 15})
    layers.append({"id": "service-requests", "name": "Service requests (C3 notifications) since January 2023", "theme": "complaints", "geom": "Point",
                   "n": len(rows), "fields": fields, "label": "C3_Complaint_Type", "cat": "C3_Complaint_Type", "cats": types.most_common(24),
                   "url": sr["url"], "retrieved": sr["retrieved"], "source": "City of Cape Town Open Data Portal", "tileset": "complaints", "minzoom": 13,
                   "description": "Every fault and complaint logged with the City (water, electricity, roads, refuse, sewer and more), with the date it was logged, changed and completed. Point positions are as published by the City."})
    # a coarse density grid for low zoom (about 500 m cells): count by cell
    cells = collections.Counter()
    for r in rows:
        x, y = r["g"]["coordinates"]; cells[(round(x / 0.005), round(y / 0.0045))] += 1
    grid = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [k[0] * 0.005, k[1] * 0.0045]}, "properties": {"v": v}} for k, v in cells.items()]}
    fp = os.path.join(TMP, "service-requests-density.geojson"); json.dump(grid, open(fp, "w"))
    tilejobs["complaints"].append({"id": "service-requests-density", "file": fp, "minzoom": 8, "maxzoom": 12})
    geoms["service-requests"] = [{"g": r["g"], "p": r["p"]} for r in rows]
    write_pos("service-requests", [r["g"] for r in rows])

# ---------------------------------------------------------------- heritage research register as map layers
her = os.path.join(HERE, "heritage", "timeflyer.json")
if os.path.exists(her):
    H = json.load(open(her))
    def add_points(lid, name, items, fields, row, desc):
        feats = [{"g": {"type": "Point", "coordinates": [x, y]}, "p": dict(zip([f[0] for f in fields], row(it))), "oid": k} for k, (it, x, y) in enumerate(items)]
        for s in range(0, len(feats), SHARD):
            dump([[f["p"].get(k) for k in [x[0] for x in fields]] + [f["oid"]] for f in feats[s:s + SHARD]], "attrs", lid, f"{s // SHARD}.json")
        cats = collections.Counter(f["p"]["Category"] for f in feats).most_common(24)
        fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": f["g"], "properties": {"i": i, "n": str(f["p"]["Name"])[:60], "c": f["p"]["Category"]}} for i, f in enumerate(feats)]}
        fp = os.path.join(TMP, lid + ".geojson"); json.dump(fc, open(fp, "w"))
        tilejobs["heritage"].append({"id": lid, "file": fp, "minzoom": 9, "maxzoom": 14}); geoms[lid] = feats; write_pos(lid, [f["g"] for f in feats])
        layers.append({"id": lid, "name": name, "theme": "heritage", "geom": "Point", "n": len(feats), "fields": [[f[0], f[1]] for f in fields] + [["_oid", "Record number"]],
                       "label": "Name", "cat": "Category", "cats": cats, "url": "docs/Research register.csv", "retrieved": NOW, "source": "Cape Monitor heritage research register",
                       "tileset": "heritage", "minzoom": 9, "description": desc})
    F = [["Name", "Name"], ["Category", "Kind"], ["Placement", "How it is placed"], ["Uncertainty_m", "Uncertainty (m)"], ["Position_basis", "Position basis"],
         ["What_the_source_says", "What the source says"], ["Sources", "Sources"]]
    add_points("research-finds", "Research finds (middens, burials, wrecks, Stone Age, battle)", [(f, f["lon"], f["lat"]) for f in H["finds"]], F,
               lambda f: [f["name"], f["cat"], {"gps": "GPS in source", "erf": "Matched to erf", "farm": "Matched to farm", "feature": "Approximate (named place)", "cited": "Cited coordinates"}.get(f["place"], f["place"]),
                          f.get("radius"), f["basis"], f["facts"], " | ".join(f"{s['title']} <{s['url']}>" for s in f["sources"])],
               "Sourced finds from heritage reports, journals, theses and archives. Positions only where a source gives one; approximate ones carry an uncertainty radius.")
    R = [["Name", "Name"], ["Category", "Register"], ["Group", "Status"], ["References", "References"], ["Description", "Description"]]
    add_points("other-heritage-records", "Other heritage records (SAHRIS, Wikidata, OpenStreetMap)", [(r, r["x"], r["y"]) for r in H["registers"]], R,
               lambda r: [r["n"], r["reg"][0]["source"], "Heritage" if r["grp"] == "keep" else "Local context (no heritage status)", " | ".join(f"{e['source']} {e['ref']} <{e.get('url', '')}>" for e in r["reg"]), r.get("d")],
               "Heritage records from the national SAHRIS inventory, Wikidata and OpenStreetMap, audited: businesses removed, landmarks marked as local context.")

# ---------------------------------------------------------------- tiles
jobs = [{"tileset": t, "out": os.path.join(TMP, "tiles-" + t), "layers": ls} for t, ls in tilejobs.items()]
SKIP_TILES = os.environ.get("CM_SKIP_TILES") == "1"   # development: reuse the tiles from the last run
json.dump(jobs, open(os.path.join(TMP, "jobs.json"), "w"))
if not SKIP_TILES: subprocess.run(["node", "--max-old-space-size=8000", os.path.join(HERE, "tile.mjs"), os.path.join(TMP, "jobs.json")], check=True)
bounds = list(DGEOM.bounds)
for j in jobs:
    json.dump({"bounds": bounds, "vector_layers": [{"id": L["id"], "minzoom": L["minzoom"], "maxzoom": L["maxzoom"], "fields": {}} for L in j["layers"]]}, open(os.path.join(j["out"], "meta.json"), "w"))
    if not SKIP_TILES: subprocess.run([sys.executable, "-I", os.path.join(HERE, "pack_pmtiles.py"), j["out"], os.path.join(PUB, "tiles", j["tileset"] + ".pmtiles"), j["tileset"]], check=True)

# ---------------------------------------------------------------- joins
by_name = {l["name"].lower(): l["id"] for l in layers}
def lid_for(*names):
    for n in names:
        if n.lower() in by_name: return by_name[n.lower()]
    return None
PARCELS = lid_for("Land Parcels", "Land Parcel", "Erven")
assert PARCELS, "no land parcel layer"
parcels = geoms[PARCELS]
pf = {str(f["p"].get("SL_LAND_PRCL_KEY")): i for i, f in enumerate(parcels)}
pshapes = [shape(f["g"]) if f["g"] else None for f in parcels]
pidx = [i for i, s in enumerate(pshapes) if s is not None]
ptree = STRtree([pshapes[i] for i in pidx])

def parcel_at(pt):
    for k in ptree.query(pt, predicate="intersects"):
        return pidx[k]
    return None

D = collections.defaultdict(lambda: collections.defaultdict(list))   # parcel index -> section -> items

def link_polys(layer_id, section):
    if layer_id not in geoms: return
    feats = geoms[layer_id]
    for i, f in enumerate(feats):
        if not f["g"]: continue
        s = shape(f["g"]); ps = prep(s); small = s.area < 1e-7
        for k in ptree.query(s.representative_point() if small else s, predicate="intersects"):
            pi = pidx[k]
            try: hit = small or ps.contains(pshapes[pi]) or s.intersection(pshapes[pi]).area > 0.3 * pshapes[pi].area
            except Exception: hit = s.contains(pshapes[pi].representative_point())
            if hit:
                D[pi][section].append([layer_id, i])

# zoning, heritage and planning overlays that cover the plot
for l in layers:
    if l["geom"] == "Polygon" and l["id"] != PARCELS and l["n"] < 120000 and l["theme"] in ("property", "heritage", "safety", "environment", "boundaries", "economy"):
        link_polys(l["id"], "zones")
        print("joined", l["id"], flush=True)
# heritage inventory by parcel key
for l in layers:
    if "SL_LAND_PRCL_KEY" in [f[0] for f in l["fields"]] and l["id"] != PARCELS and l["id"] in geoms:
        for i, f in enumerate(geoms[l["id"]]):
            pi = pf.get(str(f["p"].get("SL_LAND_PRCL_KEY")))
            if pi is not None and [l["id"], i] not in D[pi]["zones"]:
                D[pi]["records"].append([l["id"], i])

# research finds tied to plots by parcel key; every other point record that sits on a plot
if her_finds := [f for f in json.load(open(her))["finds"]] if os.path.exists(her) else []:
    for k, f in enumerate(her_finds):
        for key in f.get("pk", []):
            pi = pf.get(str(key))
            if pi is not None: D[pi]["records"].append(["research-finds", k])
for l in layers:
    if l["geom"] == "Point" and l["id"] in geoms and l["id"] != "service-requests" and l["n"] < 20000 and l["theme"] != "infra":
        for i, f in enumerate(geoms[l["id"]]):
            if f["g"] and f["g"]["type"] == "Point":
                pi = parcel_at(Point(f["g"]["coordinates"]))
                if pi is not None and [l["id"], i] not in D[pi]["records"]: D[pi]["records"].append([l["id"], i])

# building plans: ERF number + suburb (the plan's case title names the allotment)
bp = extra("building-plans")
bp_rows, bp_matched = [], 0
if bp:
    norm = lambda s: re.sub(r"[^A-Z0-9]", "", str(s or "").upper())
    key = collections.defaultdict(list)
    for i, f in enumerate(parcels):
        p = f["p"]
        for sub in {p.get("OFC_SBRB_NAME"), p.get("ALT_NAME"), p.get("LU_ADR_DSCR")}:
            if sub: key[(str(p.get("PRTY_NMBR")).lstrip("0"), norm(sub))].append(i)
    fields = [[f[0], f[1]] for f in bp["fields"] if f[0] != "ObjectId"]; keys = [f[0] for f in fields]
    for r in bp["rows"]:
        p = r["p"]
        m = re.match(r"ERF\s+0*(\d+)\s+(.*)", p.get("Case_Title") or "")
        hits = key.get((m.group(1), norm(re.sub(r"\(.*?\)", "", m.group(2)))), []) if m else []
        if not hits and m: hits = key.get((m.group(1), norm(m.group(2))), [])
        if hits:
            bp_matched += 1
            ri = len(bp_rows); bp_rows.append([p.get(k) for k in keys])
            for pi in set(hits): D[pi]["plans"].append(ri)
    for s in range(0, len(bp_rows), SHARD):
        dump(bp_rows[s:s + SHARD], "attrs", "building-plans", f"{s // SHARD}.json")
    tables.append({"id": "building-plans", "name": bp["title"], "n": len(bp_rows), "n_city": len(bp["rows"]), "fields": fields, "url": bp["url"], "retrieved": bp["retrieved"],
                   "note": f"{len(bp_rows):,} of {len(bp['rows']):,} City building-plan cases matched to a plot in this district by erf number and allotment name."})
    print("building plans matched:", bp_matched, flush=True)

# service requests: which plot each falls on, plus counts per type
if "service-requests" in geoms:
    for i, f in enumerate(geoms["service-requests"]):
        pi = parcel_at(Point(f["g"]["coordinates"]))
        if pi is not None: D[pi]["requests"].append(i)

# City property sales: erf + area name
pdisp = extra("property-disposals")
if pdisp:
    fields = [[f[0], f[1]] for f in pdisp["fields"] if f[0] != "ObjectId"]; keys = [f[0] for f in fields]
    rows = [[r["p"].get(k) for k in keys] for r in pdisp["rows"]]
    dump(rows, "attrs", "property-disposals", "0.json")
    tables.append({"id": "property-disposals", "name": pdisp["title"], "n": len(rows), "fields": fields, "url": pdisp["url"], "retrieved": pdisp["retrieved"]})
    erfs = collections.defaultdict(list)
    for i, f in enumerate(parcels): erfs[str(f["p"].get("PRTY_NMBR")).lstrip("0")].append(i)
    for ri, r in enumerate(pdisp["rows"]):
        e = str(r["p"].get("ERF_ERVEN_NO") or "").lstrip("0"); a = str(r["p"].get("AREA") or "").upper()
        for pi in erfs.get(e, []):
            if a and a in " ".join(str(parcels[pi]["p"].get(k) or "") for k in ("OFC_SBRB_NAME", "ALT_NAME", "LU_ADR_DSCR")).upper():
                D[pi]["sales"].append(ri)

# nearest services for every plot
NEAR = [("police", "Police Stations"), ("fire", "Fire Stations"), ("health", "Health Care Facilities"), ("school", "Schools"), ("library", "Libraries")]
near_pts = {}
for key, name in NEAR:
    lid = lid_for(name)
    if lid and lid in geoms:
        pts = [(i, shape(f["g"])) for i, f in enumerate(geoms[lid]) if f["g"]]
        near_pts[key] = (lid, pts)

def metres(a, b):
    r = math.pi / 180; x = (b[0] - a[0]) * r * math.cos((a[1] + b[1]) / 2 * r); y = (b[1] - a[1]) * r
    return round(math.hypot(x, y) * 6371000)

# dossier shards
shards = collections.defaultdict(dict)
for pi, sec in D.items():
    c = pshapes[pi].representative_point() if pshapes[pi] else None
    item = {k: v for k, v in sec.items()}
    if c is not None:
        item["near"] = {}
        for key, (lid, pts) in near_pts.items():
            best = min(pts, key=lambda t: (t[1].x - c.x) ** 2 + (t[1].y - c.y) ** 2) if pts else None
            if best: item["near"][key] = [lid, best[0], metres((c.x, c.y), (best[1].x, best[1].y))]
    shards[pi // SHARD][pi] = item
for pi, s in enumerate(pshapes):   # plots with nothing linked still get their nearest services
    if pi not in D and s is not None:
        c = s.representative_point(); item = {"near": {}}
        for key, (lid, pts) in near_pts.items():
            best = min(pts, key=lambda t: (t[1].x - c.x) ** 2 + (t[1].y - c.y) ** 2) if pts else None
            if best: item["near"][key] = [lid, best[0], metres((c.x, c.y), (best[1].x, best[1].y))]
        shards[pi // SHARD][pi] = item
for k, v in shards.items(): dump(v, "parcel", f"{k}.json")

# ---------------------------------------------------------------- area statistics (suburb and ward)
areas = {"suburb": collections.defaultdict(lambda: {"sr_type": collections.Counter(), "sr_month": collections.Counter(), "plans_year": collections.Counter(), "plans_value": collections.Counter()}),
         "ward": collections.defaultdict(lambda: {"sr_type": collections.Counter(), "sr_month": collections.Counter(), "plans_year": collections.Counter(), "plans_value": collections.Counter()})}
if "service-requests" in geoms:
    for f in geoms["service-requests"]:
        p = f["p"]; t = p.get("C3_Complaint_Type") or p.get("Notification_type"); m = (p.get("Created_On_Date") or "")[:7]
        for kind, k in (("suburb", (p.get("Suburb_Clean") or p.get("Suburb") or "").upper()), ("ward", str(p.get("Ward") or "").lstrip("0"))):
            if k and re.fullmatch(r"[ -~]+", k): areas[kind][k]["sr_type"][t] += 1; areas[kind][k]["sr_month"][m] += 1
if bp:
    keys = next(([f[0] for f in x["fields"]] for x in tables if x["id"] == "building-plans"), [])
    for row in bp_rows:
        p = dict(zip(keys, row)); yr = (p.get("Approval_Date") or p.get("Submission_Date") or "")[:4]
        for kind, k in (("suburb", str(p.get("Suburb") or "").upper()), ("ward", str(p.get("Ward_No") or "").lstrip("0"))):
            if k and yr: areas[kind][k]["plans_year"][yr] += 1; areas[kind][k]["plans_value"][yr] += int(p.get("Building_Work_Value") or 0)
pop = extra("population-2025")
popmap = {}
if pop:
    for r in pop["rows"]:
        p = r["p"]; name = str(next((v for k, v in p.items() if "suburb" in k.lower() and isinstance(v, str)), "")).upper()
        if name: popmap[name] = {k: v for k, v in p.items() if k not in ("ObjectId", "FID")}
lic = extra("business-licences")
licmap = collections.defaultdict(collections.Counter)
if lic:
    for r in lic["rows"]: licmap[str(r["p"].get("Suburb") or "").upper()][r["p"].get("Licence_Type")] += 1
out_areas = {"suburb": {}, "ward": {}}
for kind in ("suburb", "ward"):
    for k, v in areas[kind].items():
        out_areas[kind][k] = {"sr_total": sum(v["sr_type"].values()), "sr_type": v["sr_type"].most_common(40), "sr_month": sorted(v["sr_month"].items()),
                              "plans_year": sorted(v["plans_year"].items()), "plans_value": sorted(v["plans_value"].items())}
        if kind == "suburb":
            if k in popmap: out_areas[kind][k]["population"] = popmap[k]
            if k in licmap: out_areas[kind][k]["licences"] = licmap[k].most_common()
dump(out_areas, "areas.json")

# ---------------------------------------------------------------- city-wide tables and incident tables
for sid in ("rfq-awards", "tender-awards", "crashes", "fire-incidents", "business-licences", "certificates-acceptability", "homeless-shelters"):
    t = extra(sid)
    if not t: continue
    fields = [[f[0], f[1]] for f in t["fields"] if f[0] not in ("ObjectId", "FID")]; keys = [f[0] for f in fields]
    rows = [[r["p"].get(k) for k in keys] for r in t["rows"]]
    for s in range(0, len(rows), 10000): dump(rows[s:s + 10000], "tables", f"{sid}-{s // 10000}.json")
    tables.append({"id": sid, "name": t["title"], "n": len(rows), "fields": fields, "url": t["url"], "retrieved": t["retrieved"], "shards": math.ceil(len(rows) / 10000), "scope": "city-wide"})

# ---------------------------------------------------------------- feeds, tagged with places in the district
sub_lid = lid_for("Official Suburb", "Official Planning Suburbs")
places = sorted({str(f["p"].get("OFC_SBRB_NAME")).title() for f in geoms.get(sub_lid, []) if f["p"].get("OFC_SBRB_NAME")}, key=len, reverse=True)
extra_places = ["Blaauwberg", "Blouberg", "Bloubergstrand", "Melkbos", "Melkbosstrand", "Atlantis", "Mamre", "Table View", "Parklands", "Big Bay", "Sunningdale",
                "Koeberg", "Duynefontein", "Philadelphia", "Klein Dassenberg", "Witsand", "Robben Island", "West Coast", "Cape Town", "Western Cape", "Dunoon", "Du Noon"]
gaz = sorted(set(places + extra_places), key=len, reverse=True)
items = []
for sid in ("news24", "iol-wc", "dailymaverick", "gitoc", "gitoc-assassination"):
    f = extra(sid)
    if not f: continue
    feeds.append({"id": sid, "name": f["title"], "n": len(f["items"]), "url": f["url"], "retrieved": f["retrieved"]})
    for it in f["items"]:
        txt = f"{it['title']} {it['summary']}"
        tags = [p for p in gaz if re.search(r"\b" + re.escape(p) + r"\b", txt, re.I)]
        items.append({**it, "feed": sid, "places": tags})
dump({"built": NOW, "items": items}, "feed.json")

# ---------------------------------------------------------------- heritage module (research register from TimeFlyer)
her = os.path.join(HERE, "heritage", "timeflyer.json")
heritage = None
if os.path.exists(her):
    H = json.load(open(her))
    dump({k: H[k] for k in ("finds", "registers", "stories", "glossary", "pending", "highlights") if k in H}, "heritage.json")
    heritage = {"finds": len(H.get("finds", [])), "registers": len(H.get("registers", [])), "stories": len(H.get("stories", []))}

# ---------------------------------------------------------------- manifest
manifest = {"app": "Cape Monitor", "district": {"name": district["properties"].get("PBDM_RGN_NAME"), "bounds": bounds, "geometry": district["geometry"]},
            "built": NOW, "themes": [{"id": t, "en": en, "af": af} for t, en, af in THEMES], "layers": layers, "tables": tables, "feeds": feeds,
            "parcels": {"layer": PARCELS, "shard": SHARD}, "skipped": sel["skipped"], "heritage": heritage,
            "tilesets": sorted({l["tileset"] for l in layers if l.get("tileset")})}
dump(manifest, "manifest.json")
shutil.copy(os.path.join(OUT, "district.geojson"), os.path.join(PUB, "district.geojson"))
print("layers", len(layers), "tables", len(tables), "feeds", len(feeds), "dossiers", sum(len(v) for v in shards.values()))
for f in sorted(os.listdir(os.path.join(PUB, "tiles"))): print(" ", f, round(os.path.getsize(os.path.join(PUB, "tiles", f)) / 1e6, 1), "MB")
