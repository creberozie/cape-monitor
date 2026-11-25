"""Shared settings: which planning district a run is for, and where its files go.

Every district script reads the district from the CM_DISTRICT environment variable (a slug below), so the same code
runs for all eight districts in parallel. Metro-wide data (money, courts, gazettes, feeds) is built by pipeline/metro/."""
import os, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# slug -> official name in the City's Development Management District layer (PBDM_RGN_NAME)
DISTRICTS = {
    "blaauwberg": "BLAAUWBERG",
    "table-bay": "TABLE BAY",
    "tygerberg": "TYGERBERG",
    "northern": "NORTHERN",
    "southern": "SOUTHERN",
    "cape-flats": "CAPE FLATS",
    "mitchells-plain-khayelitsha": "MITCHELLS PLAIN/KHAYELITSHA",
    "helderberg": "HELDERBERG",
}
LABEL = {"blaauwberg": "Blaauwberg", "table-bay": "Table Bay", "tygerberg": "Tygerberg", "northern": "Northern", "southern": "Southern",
         "cape-flats": "Cape Flats", "mitchells-plain-khayelitsha": "Mitchells Plain / Khayelitsha", "helderberg": "Helderberg"}

CITY_GIS = "https://citymaps.capetown.gov.za/agsext/rest/services/"
DMD_LAYER = CITY_GIS + "Theme_Based/Political_Administrative_Boundaries/MapServer/3"


def slug():
    s = os.environ.get("CM_DISTRICT") or (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "blaauwberg")
    s = s.lower().replace(" ", "-").replace("/", "-")
    if s not in DISTRICTS:
        raise SystemExit(f"unknown district {s!r}; one of {', '.join(DISTRICTS)}")
    return s


def paths(s=None):
    s = s or slug()
    p = {"slug": s, "name": DISTRICTS[s], "label": LABEL[s],
         "out": os.path.join(HERE, "out", s), "city": os.path.join(HERE, "cache", s, "city"), "extra": os.path.join(HERE, "cache", s, "extra"),
         "tmp": os.path.join(HERE, "tmp", s), "pub": os.path.join(ROOT, "public", "data", "d", s)}
    for k in ("out", "city", "extra"):
        os.makedirs(p[k], exist_ok=True)
    return p


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
