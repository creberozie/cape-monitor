"""Writes public/data/search/: one city-wide search index across every built district.
  e/<nn>.json   erven by the last two digits of the erf number: [erf, address, suburb, district, row]
  s/<xx>.json   addresses by the first two letters of the street name: [street, number, type, suburb, erf, district, row]
  places.json   named points (police stations, schools, clinics, ...): [name, layer name, district, layer id, row]
Kept in shards so a phone loads only the part a query needs."""
import json, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, DISTRICTS

D = os.path.join(ROOT, "public", "data")
OUT = os.path.join(D, "search")
SKIP_THEMES = {"utilities", "infra"}


def rows_of(base, lid, n, shard):
    out = []
    for k in range((n + shard - 1) // shard):
        p = os.path.join(base, "attrs", lid, f"{k}.json")
        if os.path.exists(p): out += json.load(open(p))
    return out


def key2(s):
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return (s[:2] or "_").ljust(2, "_")


def main():
    erven, streets, places = defaultdict(list), defaultdict(list), []
    for d in DISTRICTS:
        base = os.path.join(D, "d", d); mp = os.path.join(base, "manifest.json")
        if not os.path.exists(mp): continue
        M = json.load(open(mp)); shard = M["parcels"]["shard"]
        P = next((l for l in M["layers"] if l["id"] == M["parcels"]["layer"]), None)
        if P:
            f = {x[0]: k for k, x in enumerate(P["fields"])}
            g = lambda r, k: r[f[k]] if k in f and r[f[k]] not in (None, "") else ""
            for i, r in enumerate(rows_of(base, P["id"], P["n"], shard)):
                erf = str(g(r, "PRTY_NMBR")).lstrip("0"); no = str(g(r, "ADR_NO")); st = str(g(r, "STR_NAME")); ty = str(g(r, "LU_STR_NAME_TYPE"))
                sub = str(g(r, "OFC_SBRB_NAME") or g(r, "ALT_NAME"))
                if erf: erven[(erf[-2:] if len(erf) >= 2 else erf).rjust(2, "0").replace("/", "_")].append([erf, " ".join(x for x in (no, st, ty) if x), sub, d, i])
                if st: streets[key2(st)].append([st, no, ty, sub, erf, d, i])
        for L in M["layers"]:
            if L.get("geom") not in ("Point", "Multipoint") or not L.get("label") or L["n"] > 3000 or L["theme"] in SKIP_THEMES or L["id"] == "service-requests" or re.search(r"smart-facilit|free-call|survey-mark|depot|grid|sampling|monitoring|meter", L["id"]): continue
            li = next((k for k, x in enumerate(L["fields"]) if x[0] == L["label"]), None)
            if li is None: continue
            for i, r in enumerate(rows_of(base, L["id"], L["n"], shard)):
                if r[li] not in (None, ""): places.append([str(r[li]), L["name"], d, L["id"], i])
    os.makedirs(os.path.join(OUT, "e"), exist_ok=True); os.makedirs(os.path.join(OUT, "s"), exist_ok=True)
    for k, v in erven.items(): json.dump(v, open(os.path.join(OUT, "e", f"{k}.json"), "w"), separators=(",", ":"))
    for k, v in streets.items(): json.dump(v, open(os.path.join(OUT, "s", f"{k}.json"), "w"), separators=(",", ":"))
    json.dump(places, open(os.path.join(OUT, "places.json"), "w"), separators=(",", ":"))
    print(f"search index: {sum(map(len, erven.values()))} erven in {len(erven)} files, {sum(map(len, streets.values()))} addresses in {len(streets)} files, {len(places)} places")


if __name__ == "__main__":
    main()
