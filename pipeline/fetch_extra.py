"""Step 3: City Open Data Portal records (service requests, building plans, spending, sales, incidents, licences),
news and NGO feeds. Everything lands in pipeline/cache/extra/<id>.json with retrieval time and source URL."""
import json, os, sys, csv, io, re, datetime, html, urllib.request, concurrent.futures as cf
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
from arcgis import fetch_features, spatial, UA, query_polygon, in_district

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out"); CACHE = os.path.join(HERE, "cache", "extra"); os.makedirs(CACHE, exist_ok=True)
REFRESH = "--refresh" in sys.argv
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
area = json.load(open(os.path.join(OUT, "district.geojson")))["features"][0]["geometry"]
RINGS = query_polygon(area); INSIDE = in_district(area)
HUB = "https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/"
ITEM = "https://www.arcgis.com/sharing/rest/content/items/{}/data"

# id, title, kind, url, options. kind: fs-geo (feature service, district polygon), fs (whole table), csv (ArcGIS item CSV), rss
SOURCES = [
    ("service-requests", "Service requests (C3 notifications) Jan 2023 to present", "fs-geo", HUB + "service_requests_2023_01_02_spatial/FeatureServer/0", {}),
    ("building-plans", "Building plan approvals 2014 to 2026", "fs", HUB + "Building_Plan_Approvals_2014_to_2025/FeatureServer/0", {}),
    ("rfq-awards", "Requests for quotations awarded 2020 to 2026", "fs", HUB + "Requests_for_Quotations_Awarded_2020_to_April_2026/FeatureServer/0", {}),
    ("tender-awards", "Tender awards 2021 to 2026", "fs", HUB + "Tender_Awards_2021_to_2026/FeatureServer/0", {}),
    ("property-disposals", "City property disposals Jan 2025 to 2026", "fs", HUB + "Property_Disposals_Jan_2025_to_June_2026/FeatureServer/0", {}),
    ("population-2025", "Population estimates 2025 by suburb", "fs", HUB + "Population_Estimates_2026_(Suburb_Level)/FeatureServer/0", {}),
    ("crashes", "Traffic accidents (crash data)", "csv", ITEM.format("f97a738e16ee4789a4557975858075b4"), {}),
    ("fire-incidents", "Fire and rescue incidents", "csv", ITEM.format("31cfc14f770241bea45ce539eb07c2a5"), {}),
    ("business-licences", "Business licences", "csv", ITEM.format("6a8b3147a6964afa81df67a61f272de4"), {}),
    ("certificates-acceptability", "Food premises certificates of acceptability", "csv", ITEM.format("0e7ccc1a135f42bda046bba238105aa0"), {}),
    ("homeless-shelters", "Homeless shelters", "csv", ITEM.format("410b11538a0a4d7a9f06cdd505614670"), {}),
    ("news24", "News24 South Africa", "rss", "https://feeds.capi24.com/v1/Search/articles/news24/SouthAfrica/rss", {}),
    ("iol-wc", "IOL Western Cape", "rss", "https://iol.co.za/rss/iol/news/south-africa/western-cape", {}),
    ("dailymaverick", "Daily Maverick", "rss", "https://www.dailymaverick.co.za/dmrss/", {}),
    ("gitoc", "Global Initiative Against Transnational Organized Crime: analysis", "rss", "https://globalinitiative.net/feed/", {}),
    ("gitoc-assassination", "GI-TOC Assassination Witness", "rss", "https://globalinitiative.net/initiatives/assassination-witness/feed/", {}),
]

def fetch_url(url, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()

def parse_rss(raw):
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):
        g = lambda tag: (it.findtext(tag) or "").strip()
        desc = html.unescape(re.sub(r"<[^>]+>", " ", g("description")))
        items.append({"title": html.unescape(g("title")), "link": g("link"), "date": g("pubDate"), "summary": re.sub(r"\s+", " ", desc).strip()[:600],
                      "categories": [c.text for c in it.findall("category") if c.text]})
    return items

def run(s):
    sid, title, kind, url, opt = s
    path = os.path.join(CACHE, sid + ".json")
    if os.path.exists(path) and not REFRESH and kind != "rss":
        return sid, "cached"
    try:
        if kind in ("fs-geo", "fs"):
            feats, info, oid = fetch_features(url, filt=spatial(polygon=RINGS) if kind == "fs-geo" else None, geometry=(kind == "fs-geo"), log=lambda m: print(sid, m, flush=True))
            dates = {f["name"] for f in info.get("fields", []) if f.get("type") == "esriFieldTypeDate"}
            rows = []
            if kind == "fs-geo": feats = [f for f in feats if INSIDE(f.get("geometry"))]
            for f in feats:
                p = {k: (datetime.datetime.fromtimestamp(v / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if k in dates and isinstance(v, (int, float)) else v)
                     for k, v in (f.get("properties") or {}).items()}
                rows.append({"g": f.get("geometry"), "p": p})
            data = {"fields": [[f["name"], f.get("alias"), f.get("type")] for f in info.get("fields", [])], "rows": rows}
        elif kind == "csv":
            txt = fetch_url(url).decode("utf-8-sig", errors="replace")
            rdr = list(csv.reader(io.StringIO(txt)))
            hi = next(i for i, r in enumerate(rdr) if sum(1 for c in r if c.strip()) >= 3)   # skip blank lead rows
            head = [h.strip() for h in rdr[hi]]
            keep = [i for i, h in enumerate(head) if h]
            rows = [{"p": {head[i]: (r[i].strip() if i < len(r) else None) or None for i in keep}} for r in rdr[hi + 1:] if any(c.strip() for c in r)]
            data = {"fields": [[head[i], head[i], "string"] for i in keep], "rows": rows}
        else:
            data = {"items": parse_rss(fetch_url(url))}
    except Exception as e:
        return sid, f"FAILED {str(e)[:200]}"
    json.dump({"id": sid, "title": title, "kind": kind, "url": url, "retrieved": NOW, **data}, open(path, "w"))
    return sid, f"{len(data.get('rows', data.get('items', [])))} records"

with cf.ThreadPoolExecutor(4) as ex:
    for sid, msg in ex.map(run, SOURCES):
        print(sid, msg, flush=True)
