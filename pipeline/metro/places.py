"""Place tagging shared by feeds, court records and notices: finds official suburb names (and a few common local names)
in text and returns each with its planning district and position. Only exact, whole-word name matches are used."""
import json, os, re
from functools import lru_cache
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Everyday and historical names -> the official suburb (or nearest official part) they are placed at.
# Names are compared without apostrophes, so "Mitchell's Plain", "Mitchells Plain" and "Mitchell’s Plain" all match.
ALIASES = {
    "MITCHELLS PLAIN": "MITCHELLS PLAIN CBD", "TAFELSIG": "TAFELSIG", "SOMERSET WEST": "WESTRIDGE - SOMERSET WEST", "KUILS RIVER": "EIKENBOSCH KUILS RIVER",
    "KUILSRIVIER": "EIKENBOSCH KUILS RIVER", "BLUE DOWNS": "BLUE DOWNS CBD", "GOODWOOD": "GOODWOOD ESTATE", "STRAND": "ONVERWACHT - THE STRAND",
    "THE STRAND": "ONVERWACHT - THE STRAND", "BELLVILLE": "BELLVILLE CBD", "BLOUBERGSTRAND": "BLOUBERG RISE", "BLOUBERG": "BLOUBERG RISE",
    "MELKBOSSTRAND": "MELKBOSCH STRAND", "MELKBOS": "MELKBOSCH STRAND", "SCHOTSCHE KLOOF": "BO-KAAP", "SCHOTSCHEKLOOF": "BO-KAAP",
    "V AND A WATERFRONT": "CAPE TOWN CITY CENTRE", "VA WATERFRONT": "CAPE TOWN CITY CENTRE", "CAPE TOWN CBD": "CAPE TOWN CITY CENTRE",
    "CBD": "CAPE TOWN CITY CENTRE", "CITY BOWL": "CAPE TOWN CITY CENTRE", "DU NOON": "DUNOON", "TABLEVIEW": "TABLE VIEW", "SIMONSTOWN": "SIMONS TOWN",
    "SIMONSTAD": "SIMONS TOWN", "KAAPSTAD": "CAPE TOWN CITY CENTRE", "GUGULETHU": "GUGULETU", "NYANGA EAST": "NYANGA", "CROSSROADS": "CROSSROADS",
    "KHAYELITSHA SITE C": "KHAYELITSHA", "SITE C": "KHAYELITSHA", "DELFT": "DELFT 1 & 2", "SIR LOWRYS PASS": "SIR LOWRYS PASS VILLAGE CENTRE",
    "GORDONS BAY": "GORDONS BAY", "FISH HOEK": "FISH HOEK", "OCEAN VIEW": "OCEAN VIEW", 
    "PAROW": "PAROW", "ELSIES RIVER": "ELSIES RIVER", "BONTEHEUWEL": "BONTEHEUWEL", "LAVENDER HILL": "LAVENDER HILL", "STEENBERG": "STEENBERG",
    "ATLANTIS": "WESFLEUR", "MAMRE": "MAMRE", "PHILADELPHIA": "PHILADELPHIA", "BRACKENFELL": "BRACKENFELL CENTRAL", "KRAAIFONTEIN": "KRAAIFONTEIN",
    "DURBANVILLE": "DURBANVILLE", "MILNERTON": "MILNERTON", "MAITLAND": "MAITLAND", "SALT RIVER": "SALT RIVER", "MOWBRAY": "MOWBRAY",
}
# Known limits: places are matched only by name, at the centre of the official suburb (not an address); a suburb name that is
# also a common word or a personal name is used only when the text also names Cape Town; names not in the City's suburb layer
# or the list above (informal settlements, new developments, farm names) are not placed; an alias whose official target is
# missing from the City's layer is skipped rather than guessed.
# suburb names that are also everyday words or national names: matched only with a capital letter and never alone
AMBIG = {"CENTRAL", "PARK", "CITY", "VILLAGE", "HEIGHTS", "INDUSTRIA", "SUNSET", "GARDENS", "OAKDALE", "WOODSTOCK", "RONDEBOSCH", "SALT RIVER", "OBSERVATORY",
         "DISTRICT SIX", "EASTRIDGE", "PHILIPPI"} - {"WOODSTOCK", "RONDEBOSCH", "SALT RIVER", "OBSERVATORY", "DISTRICT SIX", "EASTRIDGE", "PHILIPPI"}


@lru_cache(1)
def gazetteer():
    j = json.load(open(os.path.join(ROOT, "public", "data", "metro", "districts.json")))
    s = {key(n): {**v, "name": n} for n, v in j["suburbs"].items()}
    for a, b in ALIASES.items():
        if key(b) in s and key(a) not in s: s[key(a)] = s[key(b)]
    names = sorted((n for n in s if len(n) >= 4 and n not in AMBIG), key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)
    return s, rx


def key(n):
    """compare names without apostrophes, case or doubled spaces"""
    return re.sub(r"\s+", " ", re.sub(r"[’'`]", "", str(n).upper())).strip()


def tag(text):
    s, rx = gazetteer()
    found = []
    text = re.sub(r"[’'`]", "", text or "")
    ctx = re.search(r"Cape Town|Western Cape|Kaapstad|Wes-Kaap|\bCPT\b", text, re.I)
    for m in rx.finditer(text):
        if not m.group(0)[0].isupper(): continue
        n = re.sub(r"\s+", " ", m.group(1).upper())
        if " " not in n and len(n) < 9 and not ctx: continue   # short one-word names are often ordinary words or personal names
        if n in s and s[n]["name"] not in [f[0] for f in found]: found.append([s[n]["name"], s[n]["d"], s[n]["c"]])
    erfs = sorted(set(re.findall(r"\b(?:erf|erven)\s+(?:no\.?\s*)?(\d{1,6})\b", text or "", re.I)))
    return found, erfs
