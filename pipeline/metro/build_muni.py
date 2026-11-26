"""Second step for a municipality other than Cape Town (MUNI=stellenbosch), after build_money.py: writes, in public/data/muni/<slug>/,
  finance.json  budget against audited actual, and unauthorised, irregular, fruitless and wasteful expenditure (National Treasury)
  audit.json    Auditor-General audit opinions per year, with the audit report links Treasury publishes
  justice.json  Competition Tribunal decided cases naming one of the municipality's places or one of its suppliers
  sources_manifest.json  every source: link, publication and retrieval dates, record counts, extraction method, warnings; every document read
                with its page counts (readable and unreadable); rows the readers rejected (parse_warnings); and what was not added and why
Gazette notices are written by gazettes.py (it reads each gazette once for every municipality)."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, ROOT, now, dump
from muni import cfg
from names import norm

M = cfg()
if M["slug"] == "cape-town": raise SystemExit("build_muni.py is for municipalities other than Cape Town; set MUNI")
OUT = M["pub_root"]; C = M["cache"]
load = lambda n: json.load(open(os.path.join(C, n))) if os.path.exists(os.path.join(C, n)) else None
PLACES = re.compile(r"\b(" + "|".join(re.escape(p) for p in M["places"]) + r")\b", re.I)

fin = load("finance.json"); aud = load("audit.json"); rs = load("restricted.json"); docs = load("docs.json")
bids = load("muni-bids.json"); aw = load("muni-awards.json"); fq = load("muni-fq.json"); et = load("etenders.json")
money = json.load(open(os.path.join(M["pub"], "money.json"))) if os.path.exists(os.path.join(M["pub"], "money.json")) else {"tables": {}, "counts": {}}
if fin: dump(fin, os.path.join(OUT, "finance.json"))
if aud: dump(aud, os.path.join(OUT, "audit.json"))

# Competition Tribunal: cases naming a place in the municipality or a supplier in its records
cases_path = os.path.join(HERE, "cache", "metro", "comptrib.json")
justice = None
if os.path.exists(cases_path):
    J = json.load(open(cases_path)); sup_path = os.path.join(M["pub"], "suppliers.json")
    sup = {r[0] for r in json.load(open(sup_path))["rows"]} if os.path.exists(sup_path) else set()
    items = []
    for c in sorted(J["cases"].values(), key=lambda c: c.get("date") or "", reverse=True):
        names = [p.strip() for p in re.split(r"\s+(?:and|And|AND|v|vs|V)\s+|;\s*", c.get("parties") or "") if len(p.strip()) > 2]
        ids = [k for k in dict.fromkeys(re.sub(r"[^a-z0-9]+", "-", norm(p).lower()).strip("-")[:60] for p in names) if k in sup]
        places = sorted({m.group(1).title() for m in PLACES.finditer(f"{c.get('parties')} {c.get('subject')}")})
        if ids or places: items.append({**c, "companies": names, "suppliers": ids, "places": places})
    justice = {"built": now(), "source": {"name": "Competition Tribunal: decided cases", "url": "https://www.comptrib.co.za/decided-cases", "retrieved": J.get("retrieved")}, "items": items}
    dump(justice, os.path.join(OUT, "justice.json"))

notices_src = os.path.join(ROOT, "public", "data", "metro", f"notices-{M['slug']}.json")   # written by gazettes.py in the metro step
kept = os.path.join(OUT, "notices.json")   # last good copy, when the metro step has not written this municipality's notices yet
notices = json.load(open(notices_src)) if os.path.exists(notices_src) else json.load(open(kept)) if os.path.exists(kept) else None
if notices and os.path.exists(notices_src): dump(notices, kept)

T = money.get("tables", {})
METHOD = {"etenders": "eTender API", "awards": "PDF Text (OCR for scanned registers)", "fq": "PDF Text (OCR for scanned registers)", "bids": "Dual-Pass OCR",
          "deviations": "PDF Text (page by page)", "docs": "Municipal document API", "finance": "Treasury API", "uifw": "Treasury API", "audit": "Treasury API",
          "restricted": "PDF Text", "tribunal": "Tribunal website", "gazette": "PDF Text"}
def src(id, name, url, retrieved, n, published=None, note=None, warnings=None):
    return {"id": id, "name": name, "url": url, "retrieved": (retrieved or "")[:10], "published": published, "n": n, "method": METHOD.get(id, ""),
            **({"note": note} if note else {}), **({"warnings": warnings} if warnings else {})}
sources = []
if et: sources.append(src("etenders", "National Treasury eTender Portal: this municipality's tenders", "https://www.etenders.gov.za/Home/opportunities?id=1", et.get("retrieved"), len(et["tenders"]),
                          note="Filtered from Cape Monitor's Western Cape eTender archive by buyer name: " + "; ".join(et.get("buyer_names", [])) + ". Other buyers with a similar name, left out: "
                          + ("; ".join(et.get("other_names_seen", [])) or "none") + "."))
if aw: sources.append(src("awards", aw["title"], aw["url"], aw.get("retrieved"), len(aw["rows"]), note=f"{len(aw.get('documents', []))} monthly registers read ({sum(1 for d in aw.get('documents', []) if d['how'] == 'ocr')} by OCR).", warnings=aw.get("warnings")))
if fq: sources.append(src("fq", fq["title"], fq["url"], fq.get("retrieved"), len(fq["rows"]), note=f"{len(fq.get('documents', []))} monthly registers read ({sum(1 for d in fq.get('documents', []) if d['how'] == 'ocr')} by OCR).", warnings=fq.get("warnings")))
if bids: sources.append(src("bids", bids["title"], bids["url"], bids.get("retrieved"), sum(len(t["bids"]) for t in bids["tenders"]),
                            note=f"{len(bids['tenders'])} tenders. " + bids.get("method", "") + f" Registers: {sum(1 for r in bids['registers'] if r['bids'])} read, "
                            f"{sum(1 for r in bids['registers'] if r['how'] == 'ocr' and not r['bids'])} unreadable (mostly handwritten), {sum(1 for r in bids['registers'] if r['how'] == 'waiting for OCR')} waiting for the next run.",
                            warnings=bids.get("warnings")))
dv = load("muni-deviations.json")
if dv: sources.append(src("deviations", dv["title"], dv["url"], dv.get("retrieved"), len(dv["rows"]), note=f"Read from {sum(1 for x in dv['agendas'] if x.get('how') == 'read')} Council agendas since 2023 "
                          f"(monthly item 'Monthly financial statutory reporting: deviations'); each deviation links to its agenda page.", warnings=dv.get("warnings")))
if docs: sources.append(src("docs", docs["title"], docs["url"], docs.get("retrieved"), len(docs["docs"]), note="Read through the site's public document API (" + docs.get("api", "") + "), procurement categories only."))
if fin: sources.append(src("finance", fin["title"], fin["url"], fin.get("retrieved"), len(fin["rows"]), published=fin.get("data_updated"), note="Data API: " + fin["api"]))
if fin: sources.append(src("uifw", fin["uifw"]["title"], fin["url"], fin["uifw"].get("retrieved"), len(fin["uifw"]["rows"]), note="Data API: " + fin["uifw"]["api"] + ". Figures as published, including repeated or unusual values."))
if aud: sources.append(src("audit", aud["title"], aud["url"], aud.get("retrieved"), len(aud["rows"]), note="Data API: " + aud["api"] + ". The Auditor-General's own MFMA reports: " + aud["agsa"]))
if rs: sources.append(src("restricted", rs["title"], rs["url"], rs.get("retrieved"), len(rs["rows"]), published=rs.get("generated"),
                          note="Matched to suppliers by normalised name only; a match is labelled as a name match. Register for Tender Defaulters: " + rs["defaulters"]["url"] + " (" + ("none listed" if rs["defaulters"]["none"] else "entries present") + ")."))
if justice: sources.append(src("tribunal", "Competition Tribunal decided cases naming a Stellenbosch place or supplier", justice["source"]["url"], justice["source"].get("retrieved"), len(justice["items"])))
if notices: sources.append(src("gazette", "Western Cape Provincial Gazette notices naming a Stellenbosch place", notices.get("url", ""), notices.get("built"), len(notices.get("notices", []))))

not_added = [
    {"name": "Deviations in Council agendas that print only the minutes, or whose table is a scanned annexure", "url": M["site"] + "council/",
     "why": "Deviations are read from the monthly deviations table in each Council agenda. Where an agenda carries only the minutes (which note the deviations without the table), or a damaged PDF, they are not in; listed under Sources with the agenda."},
    {"name": "Handwritten bid-opening registers (mostly 2019 to 2021)", "url": M["site"] + "tender-opening/",
     "why": "Scanned handwriting cannot be read reliably by OCR. They are listed under Documents with a link to each scan; no bids are taken from them."},
    {"name": "Award registers whose table is split across two pages side by side (some 2024 quotation registers)", "url": M["site"] + "formal-quotations-awarded/",
     "why": "The left and right halves of each row are on separate pages; the reader does not join them yet. Listed under Documents."},
    {"name": "Auditor-General findings (text of the audit reports)", "url": "https://www.agsa.co.za/Reporting/MFMAReports.aspx",
     "why": "Opinions are in as data; the findings are in PDF audit reports, linked per year, not yet read into records."},
    {"name": "Contracts register and long-term contracts (s33)", "url": M["site"] + "downloads/long-term-contracts/", "why": "Not read in this first version."},
    {"name": "Directors and registration dates (CIPC)", "url": "https://www.bizportal.gov.za/", "why": "Not in any free public source used here; each profile links to CIPC BizPortal and the CSD."},
]
# the start page: one small file (counts, ranked flags, largest suppliers, deviations, latest awards, departments, expenditure and audit),
# so the first screen needs about 20 KB of data; the full tables load only when a section is opened
SEV = {"restricted": 1, "split": 1, "notlowest": 1, "portal": 2, "deviation": 2, "growth": 2, "near": 2, "official": 2, "phone": 2, "retender": 2, "young": 2,
       "single": 3, "repeat": 3, "cobid": 3}
MP = M["pub"]
if os.path.exists(os.path.join(MP, "flags.json")):
    import glob
    F = json.load(open(os.path.join(MP, "flags.json"))); S = json.load(open(os.path.join(MP, "suppliers.json")))
    rows = lambda t: sum((json.load(open(f)) for f in sorted(glob.glob(os.path.join(MP, "t", f"{t}-*.json")), key=lambda f: int(f.rsplit("-", 1)[1][:-5]))), [])
    AW, FQ, BI = rows("awards"), rows("rfq"), rows("bids")
    fidx = lambda t, k: [f[0] for f in money["tables"][t]["fields"]].index(k) if k in [f[0] for f in money["tables"][t]["fields"]] else None
    dA, dF, dB = fidx("awards", "dq"), fidx("rfq", "dq"), fidx("bids", "dq")
    marked = lambda r, i: i is not None and i < len(r) and r[i]
    clean_aw = [r for r in AW if not marked(r, dA)]; clean_fq = [r for r in FQ if not marked(r, dF)]
    # spend by year: published amounts of awards, quotations and deviations without a notice (rates-based awards have no amount)
    by_year = {}
    for r, k in [(r, 2 if str(r[3]).startswith("Deviation") else 0) for r in clean_aw] + [(r, 1) for r in clean_fq]:
        y = str(r[0] or "")[:4]
        if not y.isdigit() or y < "2019": continue
        e = by_year.setdefault(y, [0, 0, 0, 0, 0, 0]); v = r[8] if k != 1 else r[7]
        e[k] += v or 0; e[k + 3] += 1
    names = {r[0]: r[1] for r in S["rows"]}
    flags = sorted(F["flags"], key=lambda f: (SEV.get(f["kind"], 3), -(f.get("value") or 0), -len(f["records"])))
    keep = ("id", "kind", "title", "value", "verification_status", "review_reason", "scan")
    devs = sorted([r for r in AW if str(r[3]).startswith("Deviation")], key=lambda r: str(r[0]), reverse=True)
    by_dev = {}
    for r in devs: k = names.get((r[12] or [None])[0], r[6]); by_dev[k] = by_dev.get(k, 0) + (r[8] or 0)
    latest = sorted([{"d": r[0], "ref": r[1], "desc": str(r[5] or "")[:140], "sup": (r[12] or [None])[0], "name": r[6], "v": r[7], "kind": "Tender"} for r in clean_aw if not str(r[3]).startswith("Deviation")]
                    + [{"d": r[0], "ref": r[1], "desc": str(r[4] or "")[:140], "sup": r[8], "name": r[5], "v": r[11], "kind": "Quotation"} for r in clean_fq], key=lambda x: str(x["d"]), reverse=True)[:14]
    ct = S["fields"].index("cape_town") if "cape_town" in S["fields"] else -1
    D = json.load(open(os.path.join(MP, "departments.json")))
    dump({"built": now(), "counts": money.get("counts", {}),
          "clean": {"awards": sum(1 for r in clean_aw if not str(r[3]).startswith("Deviation")), "deviations": sum(1 for r in AW if str(r[3]).startswith("Deviation")),
                    "rfq": len(clean_fq), "bids": sum(1 for r in BI if not marked(r, dB))},
          "marked": {"awards": sum(1 for r in AW if marked(r, dA)), "rfq": sum(1 for r in FQ if marked(r, dF)), "bids": sum(1 for r in BI if marked(r, dB))},
          "first": min((str(r[0]) for r in clean_aw + clean_fq if r[0]), default=None),
          "by_year": sorted([[y] + [round(x) for x in e] for y, e in by_year.items()]), "kinds": F["kinds"], "note": F["note"], "n_flags": len(F["flags"]),
          "restricted": sum(1 for f in F["flags"] if f["kind"] == "restricted"), "cape_town": sum(1 for r in S["rows"] if ct >= 0 and r[ct]),
          "flags": [{k: f[k] for k in keep if k in f} for f in flags[:12]],
          "top": [[r[0], r[1], r[3] + r[5]] for r in sorted(S["rows"], key=lambda r: -(r[3] + r[5])) if r[3] + r[5] > 0][:12],
          "devs": {"n": len(devs), "total": round(sum(r[8] or 0 for r in devs)), "latest": [[r[1], names.get((r[12] or [None])[0], r[6]), r[0], r[8]] for r in devs[:8]],
                   "top": sorted(([k, round(v)] for k, v in by_dev.items()), key=lambda x: -x[1])[:6]},
          "latest": [{**x, "sup_name": names.get(x["sup"])} for x in latest],
          "departments": [{"i": i, "name": d["name"], "n": d["n"], "value": d["value"]} for i, d in enumerate(D[:10])],
          "uifw": (fin or {}).get("uifw", {}).get("rows", []), "audit": (aud or {}).get("rows", [])}, os.path.join(OUT, "overview.json"))

# every document read, with its page counts; agendas are read page by page, so a damaged file still gives its readable pages
documents = []
for x in (aw or {}).get("documents", []) + (fq or {}).get("documents", []):
    documents.append({"title": x["title"], "url": x.get("file"), "published": x.get("published"), "kind": x["kind"], "method": "Dual-Pass OCR" if x["how"].startswith("ocr") else "PDF Text",
                      "rows": x.get("rows"), **({"rotated_chars_left_out": x["rotated_chars"]} if x.get("rotated_chars") else {})})
for x in (bids or {}).get("registers", []):
    documents.append({"title": x["title"], "url": x.get("file"), "published": x.get("published"), "kind": "bids", "method": "Dual-Pass OCR", "rows": x.get("bids"),
                      "unreadable_rows": x.get("unreadable", 0)})
for x in (dv or {}).get("agendas", []):
    documents.append({"title": x["title"], "url": x.get("file"), "published": x.get("published"), "kind": "agenda", "method": "PDF Text (page by page)", "rows": x.get("deviations"),
                      "pages": x.get("pages"), "readable_pages": x.get("readable_pages", (x.get("pages") or 0) - (x.get("unreadable_pages") or 0)),
                      "unreadable_pages": x.get("unreadable_pages", 0), **({"note": x["note"]} if x.get("note") else {})})
parse_warnings = [{**w, "register": "tenders awarded"} for w in (aw or {}).get("parse_warnings", [])] + [{**w, "register": "quotations awarded"} for w in (fq or {}).get("parse_warnings", [])]
damaged = [d for d in documents if d.get("unreadable_pages")]
dump({"built": now(), "muni": {k: M[k] for k in ("slug", "label", "code", "category")}, "thresholds": [{"from": t[0], "value": t[1], "text": t[2], "url": t[3]} for t in M["thresholds"]],
      "sources": sources, "not_added": not_added, "money_counts": money.get("counts", {}), "documents": documents, "damaged_documents": damaged,
      "parse_warnings": parse_warnings}, os.path.join(OUT, "sources_manifest.json"))
old = os.path.join(OUT, "sources.json")
if os.path.exists(old): os.remove(old)
print("muni:", M["slug"], {s["id"]: s["n"] for s in sources})
