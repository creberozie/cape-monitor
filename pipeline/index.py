"""Writes public/data/index.json: which districts have data in this build (and when each was built), for the district switcher."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, DISTRICTS, LABEL, now
out = {"built": now(), "districts": [], "metro": None}
for s in DISTRICTS:
    p = os.path.join(ROOT, "public", "data", "d", s, "manifest.json")
    if os.path.exists(p):
        m = json.load(open(p))
        out["districts"].append({"slug": s, "label": LABEL[s], "built": m["built"], "bounds": m["district"]["bounds"], "layers": len(m["layers"]),
                                 "plots": next((l["n"] for l in m["layers"] if l["id"] == m["parcels"]["layer"]), None)})
    else:
        out["districts"].append({"slug": s, "label": LABEL[s], "built": None})
p = os.path.join(ROOT, "public", "data", "metro", "districts.json")
if os.path.exists(p): out["metro"] = json.load(open(p)).get("built")
os.makedirs(os.path.join(ROOT, "public", "data"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "public", "data", "index.json"), "w"), indent=1)
print("data index:", [(d["slug"], (d["built"] or "MISSING")[:10]) for d in out["districts"]], "metro", out["metro"])
import search_index; search_index.main()
