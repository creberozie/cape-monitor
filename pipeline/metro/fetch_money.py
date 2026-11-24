"""Metro step 1: every published record of City and Western Cape public spending we can reach, as published.

Lands in pipeline/cache/metro/money/<id>.json, each with its source URL and retrieval time:
  odp-tender-awards, odp-rfq-awards, odp-property-disposals   City Open Data Portal tables (whole city)
  city-docs                                                   index of every PDF on the City's tender pages
  city-bids                                                   bids received at public tender openings (parsed from the City's monthly registers)
  city-sum-increases                                          tender-sum increases (contract variations) as published
  etenders                                                    national eTender portal: open, awarded, closed and cancelled tenders
                                                              placed by Western Cape buyers, with bidders and awards
Run: python3 -I pipeline/metro/fetch_money.py [--refresh]"""
import json, os, re, sys, time, datetime, subprocess, tempfile, urllib.parse, urllib.request, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from arcgis import fetch_features, UA
from common import HERE, now, dump

CACHE = os.path.join(HERE, "cache", "metro", "money"); os.makedirs(CACHE, exist_ok=True)
PDFS = os.path.join(HERE, "cache", "metro", "pdf"); os.makedirs(PDFS, exist_ok=True)
REFRESH = "--refresh" in sys.argv
HUB = "https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/"
CITY = "https://www.capetown.gov.za"
SCM = CITY + "/work-and-business/doing-business-with-the-city/tenders-rfqs-and-supply/"
BROWSER = {"User-Agent": "Mozilla/5.0 (compatible; cape-monitor/2.0; public-records index)"}
log = lambda *a: print(*a, flush=True)


def http(url, tries=5, timeout=180, headers=BROWSER):
    err = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            err = e; time.sleep(3 * (k + 1) ** 2)
    raise RuntimeError(f"{url[:160]}: {err}")


def fresh(path, days=6):
    return os.path.exists(path) and not REFRESH and time.time() - os.path.getmtime(path) < days * 86400


# ------------------------------------------------------------------ City Open Data Portal tables
ODP = [("odp-tender-awards", "City tender awards and decisions 2021 to 2026", "Tender_Awards_2021_to_2026"),
       ("odp-rfq-awards", "City quotations (RFQs) awarded 2020 to 2026", "Requests_for_Quotations_Awarded_2020_to_April_2026"),
       ("odp-property-disposals", "City property disposals (land sales) Jan 2025 to 2026", "Property_Disposals_Jan_2025_to_June_2026")]


def odp(item):
    sid, title, svc = item
    path = os.path.join(CACHE, sid + ".json")
    if fresh(path): return sid, "cached"
    url = HUB + svc + "/FeatureServer/0"
    feats, info, oid = fetch_features(url, geometry=False, log=lambda m: log(sid, m))
    dates = {f["name"] for f in info.get("fields", []) if f.get("type") == "esriFieldTypeDate"}
    rows = []
    for f in feats:
        p = {k: (datetime.datetime.fromtimestamp(v / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if k in dates and isinstance(v, (int, float)) else v)
             for k, v in (f.get("properties") or {}).items()}
        rows.append(p)
    dump({"id": sid, "title": title, "url": url, "page": "https://odp-cctegis.opendata.arcgis.com/", "retrieved": now(),
          "fields": [[f["name"], f.get("alias")] for f in info.get("fields", [])], "oid": oid, "rows": rows}, path)
    return sid, f"{len(rows)} rows"


# ------------------------------------------------------------------ City tender-page PDFs
PAGES = {"tenders-received": "Bids received at tender openings", "tenders-awarded": "Tenders awarded (monthly registers)",
         "tender-sum-increases": "Tender-sum increases", "tenders-awarded-to-organs-of-state": "Tenders awarded to organs of state",
         "tender-contracts-s33": "Long-term contracts (MFMA section 33)"}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def doc_month(name):
    n = name.lower()
    y = re.search(r"(20\d\d)", n)
    m = next((v for k, v in MONTHS.items() if re.search(r"(^|[^a-z])" + k, n)), None)
    return f"{y.group(1)}-{m:02d}" if y and m else (y.group(1) if y else None)


def city_docs():
    docs = []
    for page, title in PAGES.items():
        url = SCM + page + "/"
        html = http(url).decode("utf-8", "replace")
        for m in re.finditer(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.I | re.S):
            href, text = m.group(1), re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
            if "[[DynamicPath]]" in href: continue
            full = urllib.parse.urljoin(url, href.replace(" ", "%20"))
            name = urllib.parse.unquote(full.rsplit("/", 1)[-1])
            refs = sorted(set(re.findall(r"(\d{1,3}[A-Z])[-_ /](20\d\d)[-_ /](\d\d)", name, re.I)))
            docs.append({"page": page, "page_title": title, "page_url": url, "url": full, "title": text or name, "file": name,
                         "month": doc_month(name + " " + text), "tenders": [f"{a.upper()}/{b}/{c}" for a, b, c in refs]})
    seen, out = set(), []
    for d in docs:
        if d["url"] not in seen: seen.add(d["url"]); out.append(d)
    dump({"id": "city-docs", "title": "City of Cape Town tender-page documents", "url": SCM, "retrieved": now(), "docs": out}, os.path.join(CACHE, "city-docs.json"))
    return out


def pdf_text(url):
    """download once (PDFs do not change once published) and return the layout text"""
    key = re.sub(r"[^A-Za-z0-9.]+", "_", urllib.parse.unquote(url.split("://", 1)[1]))[-150:]
    pdf = os.path.join(PDFS, key); txt = pdf + ".txt"
    if not os.path.exists(txt):
        if not os.path.exists(pdf):
            open(pdf, "wb").write(http(url))
        subprocess.run(["pdftotext", "-layout", pdf, txt], check=True, timeout=300)
    return open(txt, encoding="utf-8", errors="replace").read()


NUM = r"(?:\d{1,3}(?:[  ]\d{3})+|\d+)(?:[,.]\d{1,2})?"
BID = re.compile(r"^\s{0,6}(\d{1,3})\s{2,}(.+?)\s{2,}(Various Rates|Rates|Blank|Not ?stated|R?\s?" + NUM + r")(?:\s{2,}(.*))?$")


REF = r"([0-9]{1,3}\s?[A-Z]\s?/\s?20\d\d\s?/\s?\d\d)"


def parse_bids(text, doc):
    """'CCT Receiving / Opening of Tenders' registers. Two layouts are in use:
    2025 onward: 'TENDER NUMBER: 038Q/2025/26 ... CLOSING DATE: 01/10/2025', then 'DESCRIPTION: ...';
    up to 2024: the description first, then 'Tender No 35S/2023/24: Date 02/09/2024'.
    Then a numbered list of bidders with price and HDI points; bidder names may wrap over several lines."""
    out, cur, pending = [], None, []
    lines = text.splitlines()
    last_table = 0
    for i, line in enumerate(lines):
        m = re.search(r"TENDER NUMBER:\s*" + REF, line) or re.search(r"Tender\s+No\.?\s*:?\s*" + REF, line, re.I)
        if m:
            ref = re.sub(r"\s", "", m.group(1)).upper()
            cd = None
            for j in range(i, min(i + 3, len(lines))):
                c = re.search(r"(?:CLOSING DATE:|Date)\s*:?\s*(\d\d)/(\d\d)/(20\d\d)", lines[j], re.I)
                if c: cd = f"{c.group(3)}-{c.group(2)}-{c.group(1)}"; break
            desc = []
            if "TENDER NUMBER" in line:
                for j in range(i + 1, min(i + 12, len(lines))):
                    d = re.search(r"DESCRIPTION:\s*(.*)", lines[j])
                    if d:
                        desc.append(d.group(1).strip())
                        for k in range(j + 1, min(j + 6, len(lines))):
                            t = lines[k].strip()
                            if not t or re.search(r"Price|Serial|Service Provider|HDI", t): break
                            desc.append(t)
                        break
            else:   # older layout: description is the block of text just above
                k = i - 1
                while k > last_table and k >= i - 6:
                    t = lines[k].strip()
                    if t and not re.search(r"^(January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d$|TOTAL|Page \d", t, re.I):
                        desc.insert(0, t)
                    elif desc: break
                    k -= 1
            prev = next((t for t in out if t["ref"] == ref and t["doc"] == doc["url"]), None)
            if prev:   # the same tender continued on the next page
                cur = prev
            else:
                cur = {"ref": ref, "closing": cd, "description": " ".join(desc).strip(), "doc": doc["url"], "month": doc.get("month"), "bids": [], "total": None}
                out.append(cur)
            pending = []; continue
        if not cur: continue
        t = re.search(r"TOTAL:\s*(\d+|Zero)", line, re.I)
        if t: cur["total"] = 0 if t.group(1).lower() == "zero" else int(t.group(1)); last_table = i; pending = []; continue
        b = BID.match(line)
        if b and not re.search(r"Serial|Name of Service|Folio", line):
            name = re.sub(r"\s{2,}", " ", b.group(2)).strip(" -")
            if pending: name = " ".join(pending + [name]); pending = []
            price = b.group(3).strip()
            val = None
            if re.match(r"R?\s?" + NUM + "$", price):
                try: val = float(price.replace("R", "").replace(" ", "").replace(" ", "").replace(",", "."))
                except ValueError: val = None
            pts = re.findall(r"(\d+(?:[.,]\d+)?|Blank|-)", b.group(4) or "")
            cur["bids"].append({"n": int(b.group(1)), "bidder": name, "price_text": price, "price": val, "hdi": pts[:2]})
            last_table = i; continue
        w = re.match(r"^\s{5,}(\S.{2,70}?)\s*$", line)
        if w and cur["bids"] and not re.search(r"\b(Price|Points|System|Including|Excluding|VAT|Provider|Tender|Box No|Closing)\b", line, re.I):
            txt = w.group(1).strip()
            if txt.startswith("(") or (i + 1 < len(lines) and not lines[i + 1].strip()):
                cur["bids"][-1]["bidder"] += " " + txt   # trailing part of the name above
            else:
                pending.append(txt)                       # leading part of the next name
            continue
        if not line.strip(): pending = pending if pending else []
    for t in out:
        t["parse_complete"] = t["total"] is None or t["total"] == len(t["bids"])
    return out


def city_registers(docs):
    bids, increases, failed = [], [], []
    todo = [d for d in docs if d["page"] in ("tenders-received", "tender-sum-increases")]
    def one(d):
        try: return d, pdf_text(d["url"]), None
        except Exception as e: return d, None, str(e)[:200]
    with cf.ThreadPoolExecutor(4) as ex:
        for d, text, err in ex.map(one, todo):
            if err: failed.append({"url": d["url"], "error": err}); continue
            if d["page"] == "tenders-received":
                bids += parse_bids(text, d)
            else:
                increases.append({"doc": d["url"], "title": d["title"], "month": d["month"], "text": text[:60000]})
    dump({"id": "city-bids", "title": "Bids received at City tender openings (parsed from the City's monthly registers)", "url": SCM + "tenders-received/",
          "retrieved": now(), "tenders": bids, "failed": failed}, os.path.join(CACHE, "city-bids.json"))
    dump({"id": "city-sum-increases", "title": "City tender-sum increases (as published)", "url": SCM + "tender-sum-increases/", "retrieved": now(),
          "docs": increases}, os.path.join(CACHE, "city-sum-increases.json"))
    return f"{len(bids)} tenders, {sum(len(b['bids']) for b in bids)} bids; {len(increases)} increase registers; {len(failed)} PDFs failed"


# ------------------------------------------------------------------ national eTender portal (all spheres), Western Cape buyers
ET = "https://www.etenders.gov.za/Home/PaginatedTenderOpportunities"
ET_STATUS = {1: "Open", 2: "Awarded", 3: "Closed", 4: "Cancelled"}
WC = re.compile(r"western cape|cape town|\bcct\b|stellenbosch|drakenstein|saldanha|swartland|overstrand|george|knysna|mossel bay|bitou|"
                r"oudtshoorn|hessequa|cederberg|bergrivier|matzikama|theewaterskloof|cape agulhas|swellendam|langeberg|breede|witzenberg|"
                r"beaufort west|laingsburg|prince albert|kannaland|cape winelands|overberg|garden route|west coast|central karoo", re.I)
KEEP = ["id", "tender_No", "description", "category", "type", "organ_of_State", "department", "status", "closing_Date", "date_Published",
        "compulsory_briefing_session", "briefingVenue", "briefingSession", "briefingCompulsory", "conditions", "contactPerson", "email", "telephone",
        "province", "delivery", "eSubmission", "preferencePointsSystem", "validity", "awardDate", "tenderAmount", "awardContact", "contactNumber"]


def et_page(status, start, length):
    q = urllib.parse.urlencode({"draw": 1, "start": start, "length": length, "status": status})
    for k in range(6):
        try:
            return json.loads(http(f"{ET}?{q}", tries=1, timeout=240, headers={**BROWSER, "Accept": "application/json"}))
        except Exception as e:
            err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"eTenders status {status} start {start}: {err}")


def slim(t):
    r = {k: t.get(k) for k in KEEP if t.get(k) not in (None, "", [], "N/A")}
    r["documents"] = [{"name": d.get("fileName"), "url": "https://www.etenders.gov.za/home/Download?blobName=" + urllib.parse.quote(f"{d['supportDocumentID']}{d.get('extension') or ''}")
                       + "&downloadedFileName=" + urllib.parse.quote(d.get("fileName") or "document"), "modified": d.get("dateModified")}
                      for d in (t.get("supportDocument") or []) if d.get("supportDocumentID")]
    r["bidders_docs"] = [{"name": d.get("fileName"), "url": "https://www.etenders.gov.za/home/Download?blobName=" + urllib.parse.quote(f"{d.get('supportDocumentID') or d.get('biddersListDocumentID') or ''}{d.get('extension') or ''}")}
                         for d in (t.get("biddersListDocuments") or []) if (d.get("supportDocumentID") or d.get("biddersListDocumentID"))]
    r["bidders"] = [{"name": b.get("biddersName"), "amount": b.get("amount"), "entered_by": b.get("updatedBy"), "modified": b.get("dateModified")}
                    for b in (t.get("bidders") or []) if not b.get("isDeleted")]
    r["awards"] = [{"company": a.get("company"), "contact": a.get("contactPerson"), "phone": a.get("contactNumber"), "enterprise": a.get("enterpriseType"),
                    "points": a.get("pointsAwarded"), "amount": a.get("tenderAmount"), "date": a.get("awardDate"), "bee": a.get("beeScoring"),
                    "subcontractors": [s.get("subContractorName") for s in (a.get("subContractor") or []) if s.get("subContractorName")]}
                   for a in (t.get("awards") or t.get("company") or []) if not a.get("isDeleted")]
    if t.get("cancelled"): r["cancelled"] = {k: t["cancelled"].get(k) for k in ("reason", "dateModified", "updatedBy") if t["cancelled"].get(k)}
    if t.get("closed"): r["closed"] = {k: t["closed"].get(k) for k in ("reason", "dateModified") if t["closed"].get(k)}
    return r


def etenders():
    path = os.path.join(CACHE, "etenders.json")
    old = json.load(open(path)) if os.path.exists(path) else {"tenders": {}}
    keep = {str(k): v for k, v in old.get("tenders", {}).items()}   # earlier runs: the portal drops old records, we keep them
    stats, gaps = {}, []
    for st, label in ET_STATUS.items():
        first = et_page(st, 0, 10); total = first["recordsTotal"]; got = 0; n = 1000
        # closed tenders: the newest 40 000 are enough each week once the archive is built
        limit = total if (st != 3 or not old.get("tenders")) else min(total, 40000)
        starts = list(range(0, limit, n))
        def page(s):
            try: return et_page(st, s, n)["data"]
            except Exception:
                out = []
                for k in range(s, s + n, 100):   # the portal fails on some large pages: read the same range in small pages
                    try: out += et_page(st, k, 100)["data"]
                    except Exception as e: gaps.append({"status": label, "start": k, "length": 100, "error": str(e)[:120]})
                return out
        with cf.ThreadPoolExecutor(3) as ex:
            for data in ex.map(page, starts):
                for t in data:
                    got += 1
                    if (t.get("province") == "Western Cape") or WC.search(f"{t.get('organ_of_State')} {t.get('department')} {t.get('delivery')}"):
                        r = slim(t); r["portal_status"] = label; r["seen"] = now()[:10]
                        keep[str(t["id"])] = {**keep.get(str(t["id"]), {}), **r}
        stats[label] = {"portal_total": total, "read": got}
        log("etenders", label, stats[label], "kept so far", len(keep))
    dump({"id": "etenders", "title": "National eTender portal: tenders placed by Western Cape buyers (all spheres)", "url": "https://www.etenders.gov.za/Home/opportunities?id=1",
          "retrieved": now(), "stats": stats, "gaps": gaps, "tenders": keep}, path)
    return f"{len(keep)} Western Cape tenders kept; {len(gaps)} unreadable 100-record pages"


if __name__ == "__main__":
    jobs = {"odp": lambda: [odp(i) for i in ODP], "docs+registers": lambda: city_registers(city_docs()), "etenders": etenders}
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    failed = []
    for name, fn in jobs.items():
        if only and name not in only: continue
        t = time.time()
        try: log(name, "→", fn(), f"({time.time() - t:.0f}s)")
        except Exception as e:
            failed.append(name); log(name, "FAILED", e)
    json.dump({"failed": failed, "at": now()}, open(os.path.join(CACHE, "_status.json"), "w"))
    if len(failed) == len(jobs): sys.exit(1)   # partial failures keep the last good cache for that part
