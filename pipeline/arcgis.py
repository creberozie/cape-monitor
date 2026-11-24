"""Minimal, robust ArcGIS REST client (stdlib only).

Every request is retried with backoff because the City's server and our network path both drop connections.
Paging uses OBJECTID ranges, which is reliable where resultOffset is not supported, and every layer download is
checked against the server's own count before it is accepted."""
import json, time, urllib.request, urllib.parse, urllib.error

UA = {"User-Agent": "cape-monitor-pipeline/1.0"}


def get(url, params=None, tries=6, timeout=120):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    err = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                j = json.load(r)
            if isinstance(j, dict) and j.get("error"):
                raise RuntimeError(f"server error: {j['error']}")
            return j
        except Exception as e:  # network resets, 5xx, server errors
            err = e
            time.sleep(min(60, 2 * (k + 1) ** 2))
    raise RuntimeError(f"{url[:160]} failed after {tries} tries: {err}")


def post(url, params, tries=6, timeout=180):
    data = urllib.parse.urlencode(params).encode()
    err = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.load(r)
            if isinstance(j, dict) and j.get("error"):
                raise RuntimeError(f"server error: {j['error']}")
            return j
        except Exception as e:
            err = e
            time.sleep(min(60, 2 * (k + 1) ** 2))
    raise RuntimeError(f"{url[:160]} POST failed after {tries} tries: {err}")


def layer_info(layer_url):
    return get(layer_url, {"f": "json"})


def query_polygon(geometry, tolerance=0.0015):
    """A simplified, slightly enlarged copy of the district outline for server queries (the full outline is ~80 KB per
    request). Results are then clipped exactly against the real outline with in_district()."""
    from shapely.geometry import shape, mapping
    g = shape(geometry).buffer(tolerance).simplify(tolerance, preserve_topology=True)
    m = mapping(g)
    return [list(map(list, r)) for r in (m["coordinates"] if m["type"] == "Polygon" else [r for p in m["coordinates"] for r in p])]


def in_district(geometry):
    from shapely.geometry import shape
    from shapely.prepared import prep
    P = prep(shape(geometry))
    def test(g):
        if not g: return True
        try: return P.intersects(shape(g))
        except Exception: return True
    return test


def spatial(envelope=None, polygon=None):
    """Spatial filter: an esri polygon (rings, WGS84) is exact; an envelope is a quick pre-filter."""
    if polygon:
        return {"geometry": json.dumps({"rings": polygon, "spatialReference": {"wkid": 4326}}), "geometryType": "esriGeometryPolygon",
                "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
    if envelope:
        return {"geometry": ",".join(map(str, envelope)), "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
    return {}


def fetch_features(layer_url, where="1=1", filt=None, out_fields="*", geometry=True, page=None, precision=6, log=print):
    """Download every matching feature as GeoJSON features. Returns (features, info)."""
    info = layer_info(layer_url)
    oid = info.get("objectIdField") or next((f["name"] for f in info.get("fields", []) if f.get("type") == "esriFieldTypeOID"), "OBJECTID")
    base = {"where": where, "f": "json", **(filt or {})}
    ids = post(layer_url + "/query", {**base, "returnIdsOnly": "true"}).get("objectIds") or []
    ids.sort()
    n = page or min(int(info.get("maxRecordCount") or 1000), 2000)
    feats = []
    for i in range(0, len(ids), n):
        chunk = ids[i:i + n]
        q = {"objectIds": ",".join(map(str, chunk)), "outFields": out_fields, "returnGeometry": "true" if geometry else "false",
             "outSR": 4326, "f": "geojson" if geometry else "json"}
        if geometry:
            q["geometryPrecision"] = precision
        j = post(layer_url + "/query", q)
        got = j.get("features", [])
        if not geometry:  # esri json → geojson-like
            got = [{"type": "Feature", "geometry": None, "properties": g["attributes"]} for g in got]
        feats += got
        if len(ids) > 5 * n and (i // n) % 10 == 0:
            log(f"    {len(feats)}/{len(ids)}")
    if len(feats) != len(ids):
        raise RuntimeError(f"{layer_url}: expected {len(ids)} features, got {len(feats)}")
    return feats, info, oid


def domains(info):
    """Coded-value domains and subtypes, so values are stored as their readable labels."""
    dom = {f["name"]: {str(c["code"]): c["name"] for c in (f.get("domain") or {}).get("codedValues", [])} for f in info.get("fields", [])}
    sub = {str(t["id"]): t["name"] for t in info.get("types", [])}
    return dom, sub, info.get("typeIdField")
