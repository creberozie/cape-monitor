"""Second step for a municipality other than Cape Town (MUNI=stellenbosch), after build_money.py: writes, in public/data/muni/<slug>/,
  finance.json  budget against audited actual, and unauthorised, irregular, fruitless and wasteful expenditure (National Treasury)
  audit.json    Auditor-General audit opinions per year, with the audit report links Treasury publishes
  justice.json  Competition Tribunal decided cases naming one of the municipality's places or one of its suppliers
  sources.json  every source: link, publication and retrieval dates, record counts, warnings, and what was not added and why
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

notices_path = os.path.join(OUT, "notices.json")
notices = json.load(open(notices_path)) if os.path.exists(notices_path) else None

T = money.get("tables", {})
def src(id, name, url, retrieved, n, published=None, note=None, warnings=None):
    return {"id": id, "name": name, "url": url, "retrieved": (retrieved or "")[:10], "published": published, "n": n, **({"note": note} if note else {}), **({"warnings": warnings} if warnings else {})}
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
    {"name": "Quotation registers of 2019 and early 2020 (list every offer received)", "url": M["site"] + "formal-quotations-awarded/",
     "why": "A different layout (offers received, then the award). Not read yet; listed under Documents."},
    {"name": "Auditor-General findings (text of the audit reports)", "url": "https://www.agsa.co.za/Reporting/MFMAReports.aspx",
     "why": "Opinions are in as data; the findings are in PDF audit reports, linked per year, not yet read into records."},
    {"name": "Contracts register and long-term contracts (s33)", "url": M["site"] + "downloads/long-term-contracts/", "why": "Not read in this first version."},
    {"name": "Directors and registration dates (CIPC)", "url": "https://www.bizportal.gov.za/", "why": "Not in any free public source used here; each profile links to CIPC BizPortal and the CSD."},
]
dump({"built": now(), "muni": {k: M[k] for k in ("slug", "label", "code", "category")}, "thresholds": [{"from": t[0], "value": t[1], "text": t[2], "url": t[3]} for t in M["thresholds"]],
      "sources": sources, "not_added": not_added, "money_counts": money.get("counts", {})}, os.path.join(OUT, "sources.json"))
print("muni:", M["slug"], {s["id"]: s["n"] for s in sources})
