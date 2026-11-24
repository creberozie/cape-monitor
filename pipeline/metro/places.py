"""Place tagging shared by feeds, court records and notices: finds official suburb names (and a few common local names)
in text and returns each with its planning district and position. Only exact, whole-word name matches are used."""
import json, os, re
from functools import lru_cache
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALIASES = {"BLOUBERG": "BLOUBERGSTRAND", "MELKBOS": "MELKBOSSTRAND", "DU NOON": "DUNOON", "TABLEVIEW": "TABLE VIEW", "MITCHELLS PLAIN": "MITCHELLS PLAIN",
           "STRAND": "STRAND", "SOMERSET WEST": "SOMERSET WEST", "KHAYELITSHA": "KHAYELITSHA", "CBD": "CAPE TOWN CITY CENTRE", "CITY BOWL": "CAPE TOWN CITY CENTRE"}
# suburb names that are also everyday words or national names: matched only with a capital letter and never alone
AMBIG = {"CENTRAL", "PARK", "CITY", "VILLAGE", "HEIGHTS", "INDUSTRIA", "SUNSET", "GARDENS", "OAKDALE", "WOODSTOCK", "RONDEBOSCH", "SALT RIVER", "OBSERVATORY",
         "DISTRICT SIX", "EASTRIDGE", "PHILIPPI"} - {"WOODSTOCK", "RONDEBOSCH", "SALT RIVER", "OBSERVATORY", "DISTRICT SIX", "EASTRIDGE", "PHILIPPI"}


@lru_cache(1)
def gazetteer():
    j = json.load(open(os.path.join(ROOT, "public", "data", "metro", "districts.json")))
    s = dict(j["suburbs"])
    for a, b in ALIASES.items():
        if b in s and a not in s: s[a] = s[b]
    names = sorted((n for n in s if len(n) >= 4 and n not in AMBIG), key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)
    return s, rx


def tag(text):
    s, rx = gazetteer()
    found = []
    ctx = re.search(r"Cape Town|Western Cape|Kaapstad|Wes-Kaap|\bCPT\b", text or "", re.I)
    for m in rx.finditer(text or ""):
        if not m.group(0)[0].isupper(): continue
        n = m.group(1).upper()
        if " " not in n and len(n) < 9 and not ctx: continue   # short one-word names are often ordinary words or personal names
        if n not in [f[0] for f in found]: found.append([n, s[n]["d"], s[n]["c"]])
    erfs = sorted(set(re.findall(r"\b(?:erf|erven)\s+(?:no\.?\s*)?(\d{1,6})\b", text or "", re.I)))
    return found, erfs
