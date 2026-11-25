"""Which municipality a money run is for: MUNI=<slug> (default cape-town).

cape-town     the metro build Cape Monitor has always made: caches in pipeline/cache/metro/money, output in public/data/metro/money.
stellenbosch  ZopStopper: caches in pipeline/cache/metro/muni/stellenbosch (inside the metro cache, so the data workflow keeps
              them between runs), output in public/data/muni/stellenbosch.

Each entry lists, in the code, every spelling the national eTender portal uses for the buyer, the places used to tag gazette notices
and tribunal cases, and the competitive-bidding threshold of the municipality's category (MFMA SCM Regulations reg. 12 and 19)."""
import os, re
from common import HERE, ROOT

GN4198 = "https://www.gov.za/sites/default/files/gcis_document/202312/49863gon4198.pdf"
GN868 = "https://www.gov.za/documents/notices/local-government-municipal-finance-management-act-regulations-supply-chain-1"

MUNIS = {
    "cape-town": {
        "label": "City of Cape Town", "code": "CPT", "category": "metropolitan municipality",
        "thresholds": [("2023-12-14", 750000, "R750 000 (VAT incl.) for metros since 14 Dec 2023: MFMA SCM Regulations reg. 12, as amended by GN 4198, GG 49863", GN4198),
                       ("0000-00-00", 200000, "R200 000 (VAT incl.) before 14 Dec 2023: MFMA SCM Regulations reg. 12 (GN 868 of 2005)", GN868)],
    },
    "stellenbosch": {
        "label": "Stellenbosch Municipality", "code": "WC024", "category": "local municipality",
        "site": "https://stellenbosch.gov.za/",
        # Buyer names the eTender portal uses for this municipality (organ_of_State, department). Checked against the portal's records;
        # matching is on the whole name, case-insensitive. "Stellenbosch University" and provincial departments based in Stellenbosch are
        # other organs of state and are left out on purpose.
        "buyers": [r"^stellenbosch( local)? municipality$", r"^stellenbosch municipality\b", r"^municipality of stellenbosch$", r"^stellenbosch lm$",
                   r"^wc024\b", r"^stellenbosch( local)? municipality \(wc024\)$"],
        # gazette notices and tribunal cases naming one of these places are tagged to Stellenbosch (whole words, case-insensitive)
        "places": ["Stellenbosch", "Kayamandi", "Cloetesville", "Idas Valley", "Idasvallei", "Franschhoek", "Pniel", "Kylemore", "Klapmuts",
                   "Jamestown", "Raithby", "Lynedoch", "Groendal", "Wemmershoek", "La Motte", "Johannesdal", "Lanquedoc", "Koelenhof",
                   "Vlottenburg", "Dwarsrivier", "Banhoek", "Jonkershoek", "Mooiwater", "Die Boord", "Paradyskloof", "Onder-Papegaaiberg",
                   "Welgevonden", "Techno Park", "Technopark", "Enkanini", "Langrug", "Meerlust", "Elsenburg", "WC024"],
        "thresholds": [("2023-12-14", 300000, "R300 000 (VAT incl.) for local municipalities since 14 Dec 2023: MFMA SCM Regulations reg. 12, as amended by GN 4198, GG 49863", GN4198),
                       ("0000-00-00", 200000, "R200 000 (VAT incl.) before 14 Dec 2023: MFMA SCM Regulations reg. 12 (GN 868 of 2005)", GN868)],
    },
}


def muni():
    s = (os.environ.get("MUNI") or "cape-town").strip().lower()
    if s not in MUNIS: raise SystemExit(f"unknown MUNI {s!r}; one of {', '.join(MUNIS)}")
    return s


def cfg(s=None):
    s = s or muni()
    m = dict(MUNIS[s]); m["slug"] = s
    if s == "cape-town":
        m["cache"] = os.path.join(HERE, "cache", "metro", "money"); m["pub"] = os.path.join(ROOT, "public", "data", "metro", "money")
        m["pub_root"] = os.path.join(ROOT, "public", "data", "metro")
    else:
        m["cache"] = os.path.join(HERE, "cache", "metro", "muni", s); m["pub_root"] = os.path.join(ROOT, "public", "data", "muni", s)
        m["pub"] = os.path.join(m["pub_root"], "money")
    os.makedirs(m["cache"], exist_ok=True)
    return m


def is_buyer(name, s=None):
    pats = MUNIS[s or muni()].get("buyers")
    n = re.sub(r"\s+", " ", str(name or "")).strip().lower()
    return bool(pats) and any(re.search(p, n) for p in pats)


def ref_key(ref):
    """one key per tender or quotation number, whatever the spelling: 'B/SM 06/27', 'BSM 6/27' -> 'BSM6/27'; 'FQ/SM 84/27', 'FQ 84/27' -> 'FQ84/27';
    City of Cape Town references ('46Q/2023/24') keep their form, without leading zeros."""
    r = re.sub(r"\s", "", str(ref or "")).upper()
    m = re.match(r"^(B/?SM|FQ(?:/?SM)?|RFQ)[-:/]?0*(\d+)/(\d\d)\b", r)
    if m: return ("BSM" if "B" in m.group(1)[:1] else "FQ" if m.group(1).startswith("FQ") else "RFQ") + f"{int(m.group(2))}/{m.group(3)}"
    return re.sub(r"^0+", "", r)
