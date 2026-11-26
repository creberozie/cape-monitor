"""Metro step 2: join every money record into supplier, department and tender profiles, and compute pattern flags.

Rules that keep this defensible:
  * every row is kept exactly as published (text fields unchanged), with its source document and retrieval date;
  * a supplier is identified only by its published name (normalised for spelling: case, punctuation, "(Pty) Ltd", "CC");
    two names are never merged on any other ground, and every published spelling is listed on the profile;
  * a decision that names several suppliers is shown in full on each supplier's profile; its value is never divided or
    attributed: totals are "value of decisions naming this supplier";
  * flags are patterns in published data, each listing the exact records behind it. They are not findings.
Writes public/data/metro/money/."""
import json, os, re, sys, math, glob, hashlib, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, ROOT, now, dump
from muni import cfg, is_buyer, ref_key as muni_ref

# MUNI=<slug> (default cape-town): which municipality this build is for. Cape Town reads the City's Open Data Portal, bid registers and
# eTender records; another municipality reads what pipeline/metro/fetch_muni.py collected (its award registers, OCR-read bid registers,
# its eTender records, Treasury finance and audit data, Treasury's restricted-supplier report).
M = cfg(); MUNI = M["slug"]; CT = MUNI == "cape-town"
CACHE = M["cache"]
PUB = M["pub"]
NOW = now()
SHARD = 5000
BUCKETS = 128

# ---------------------------------------------------------------- thresholds (verified; cited in the flag text)
# Municipal Supply Chain Management Regulations, reg. 12 and 19 (GN 868 of 30 May 2005): competitive bidding above R200 000 (VAT incl.).
# Amended by GN 4198, Government Gazette 49863, 14 December 2023: metropolitan municipalities R750 000 (VAT incl.), from publication.
# Local municipalities: R300 000 (VAT incl.) since 14 Dec 2023 under the same notice. The values per municipality are in muni.py.
THRESHOLDS = M["thresholds"]
OK = ("Approved", "Partial Award", "Recommended to CM - Approved", "Awarded")   # decision codes that mean the award stands
def bucket(key):
    """FNV-1a 32-bit of the UTF-8 key, modulo BUCKETS (the app computes the same to find a profile file)"""
    h = 2166136261
    for b in key.encode("utf-8"): h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h % BUCKETS


def threshold(date):
    return next(t for t in THRESHOLDS if (date or "") >= t[0])


def load(sid):
    p = os.path.join(CACHE, sid + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


# ---------------------------------------------------------------- names
from names import norm, SUFFIX, looks_like_person


def split_vendors(raw):
    """a decision's vendor field may list several suppliers: one per line, bulleted, or separated by ';' or by ', ' after a company suffix"""
    if not raw: return []
    s = str(raw).replace(" ", " ").replace("•", "\n").replace(";", "\n")
    s = re.sub(r"\(\s*\n", "(", s); s = re.sub(r"\n\s*\(Pty\)", " (Pty)", s, flags=re.I)
    parts = []
    for line in s.split("\n"):
        line = line.strip(" ,.-\t")
        if not line: continue
        parts += [p.strip(" ,.-") for p in re.split(r"(?:(?<=Ltd)|(?<=LTD)|(?<=CC)|(?<=cc)|(?<=Inc)|(?<=Limited)|(?<=\)))\s*,\s*(?=[A-Z0-9])", line)]
    out = []
    for p in parts:
        p = re.sub(r"\s+\d{1,2}$", "", p).strip()      # lot numbers after the name
        if len(norm(p)) >= 3 and not re.match(r"^(and|the|jv)$", p, re.I): out.append(p)
    # a lone wrapped tail such as "(Pty) Ltd" belongs to the line above
    merged = []
    for p in out:
        if merged and re.match(r"^\(?(pty|ply)\)?\s*(ltd)?$", p, re.I): merged[-1] += " " + p
        else: merged.append(p)
    return merged


def money_val(v):
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).replace(" ", " ")
    m = re.search(r"R?\s*(\d{1,3}(?:[ ,]\d{3})+|\d+)(?:[.,](\d{1,2}))?", s)
    if not m: return None
    whole = re.sub(r"[ ,]", "", m.group(1))
    try: return float(whole + ("." + m.group(2) if m.group(2) else ""))
    except ValueError: return None


# ---------------------------------------------------------------- suppliers registry
# words that are never a supplier on their own: price-column leftovers in the bid registers and fragments of split vendor lists
GENERIC = {"GROUP", "RATES", "VARIOUS", "VARIOUS RATES", "BLANK", "SERVICES", "MAINTENANCE", "ATTORNEYS", "SCHEDULE", "SUBMISSION", "AUTOMOTIVE", "TRADING",
           "PROJECTS", "CONSTRUCTION", "HOLDINGS", "INCORPORATED", "AND", "JV", "JOINT VENTURE", "CONSORTIUM", "NOT STATED", "NIL", "NONE", "N A", "TBC"}
if not CT: from fetch_muni import name_problem   # municipalities read from PDFs and scans: text that is not a name gets no supplier profile
REJECTED = collections.Counter()
class Registry:
    def __init__(self): self.by = {}; self.compact = {}
    def get(self, raw, ocr=False):
        if not CT and name_problem(str(raw or "")): REJECTED[str(raw)[:80]] += 1; return None
        """ocr=True: a name read by OCR, where spaces between words are often lost ('DZIVHACIVILS(PTY)LTD'): if no profile has its exact
        normalised name, a profile whose name has the same letters and digits in the same order, ignoring spaces, is used. Nothing else is merged."""
        k = norm(raw)
        if len(k) < 3 or k in GENERIC: return None
        sid = re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")[:60]
        if ocr and sid not in self.by: sid = self.compact.get(re.sub(r"[^a-z0-9]", "", k.lower()), sid)
        self.compact.setdefault(re.sub(r"[^a-z0-9]", "", k.lower()), sid)
        s = self.by.get(sid)
        if not s:
            s = self.by[sid] = {"id": sid, "names": collections.Counter(), "refs": collections.defaultdict(list), "phones": set(), "contacts": set(),
                                "years": set(), "award_value": 0.0, "award_budget": 0.0, "rfq_value": 0.0, "et_value": 0.0, "n_wins": 0, "n_bids": 0}
        s["names"][str(raw).strip()] += 1
        return s
REG = Registry()

import shutil
for d in ("t", "sup", "tender", "etd"): shutil.rmtree(os.path.join(PUB, d), ignore_errors=True)
tables, flags = {}, []


def table(tid, title, fields, rows, source, url, retrieved, note=None):
    """write a table in shards; fields are [key, label]; rows are lists"""
    for i in range(0, max(1, len(rows)), SHARD):
        dump(rows[i:i + SHARD], os.path.join(PUB, "t", f"{tid}-{i // SHARD}.json"))
    tables[tid] = {"id": tid, "name": title, "fields": fields, "n": len(rows), "shards": max(1, math.ceil(len(rows) / SHARD)), "source": source,
                   "url": url, "retrieved": retrieved, **({"note": note} if note else {})}


# ================================================================ 1. City tender awards and decisions (Open Data Portal)
AW = load("odp-tender-awards")
awards = []
if AW:
    # the published table repeats most decisions several times, identical in every field but the record number: keep one, list all record numbers
    uniq = {}
    for r in AW["rows"]:
        k = tuple(sorted((a, str(b)) for a, b in r.items() if a != AW["oid"]))
        if k in uniq: uniq[k]["_oids"].append(r.get(AW["oid"]))
        else: uniq[k] = {**r, "_oids": [r.get(AW["oid"])]}
    AW_DUP = len(AW["rows"]) - len(uniq)
    for i, r in enumerate(sorted(uniq.values(), key=lambda r: (r.get("Date_of_decision") or "", r.get("TTS_Reference") or ""))):
        ref = re.sub(r"[\s:]", "", str(r.get("TTS_Reference") or "")).upper()
        vendors = split_vendors(r.get("Vendor"))
        val = money_val(r.get("Value_of_Decision__Fixed_")); bud = money_val(r.get("Budget_Value__Rates_based_"))
        sids = []
        for v in vendors:
            s = REG.get(v)
            if s and s["id"] not in sids:
                sids.append(s["id"]); s["refs"]["awards"].append(i)
                if (r.get("Date_of_decision") or "")[:4]: s["years"].add(r["Date_of_decision"][:4])
                if (val or bud) and str(r.get("Reason") or "").startswith(("Award", "Preferred", "Expansion", "Deviation", "Amendment")) and r.get("Decision_Code") in OK:
                    if val: s["award_value"] += val
                    else: s["award_budget"] += bud
        awards.append([r.get("Date_of_decision"), ref, r.get("Decision_Reference"), r.get("Reason"), r.get("Decision_Code"), r.get("Description"),
                       r.get("Vendor"), r.get("Value_of_Decision__Fixed_"), val, r.get("Budget_Value__Rates_based_"), bud, r.get("Rates_Based"), sids, ", ".join(map(str, r["_oids"]))])
    table("awards", AW["title"], [["date", "Date of decision"], ["ref", "Tender (TTS) reference"], ["decision", "Decision reference"], ["reason", "Reason"],
          ["code", "Decision"], ["desc", "Description"], ["vendor", "Vendor(s) as published"], ["value_text", "Value of decision (fixed), as published"],
          ["value", "Value (parsed, R)"], ["budget_text", "Budget value (rates-based), as published"], ["budget", "Budget (parsed, R)"], ["rates", "Rates based"],
          ["sup", "Suppliers"], ["oid", "Record number(s) in the source"]], awards, "City of Cape Town Open Data Portal", AW["url"], AW["retrieved"],
          f"Decisions of the City's bid adjudication structures. A decision may name several suppliers; its value is for the whole decision. "
          f"The source table repeats decisions: {AW_DUP:,} rows identical in every field except the record number were collapsed into one (all record numbers kept).")

# ================================================================ 2. City quotations (RFQs)
RQ = load("odp-rfq-awards")
rfq = []
def fill_series(rows):
    """record numbers of orders whose values form a spreadsheet fill-series (20+ orders on one date, each exactly the same amount below the next)"""
    out = {}
    by = collections.defaultdict(list)
    for r in rows:
        if r.get("Order_Value"): by[r.get("Date")].append(r)
    for d, rs in by.items():
        if len(rs) < 50: continue
        rs = sorted(rs, key=lambda r: -r["Order_Value"]); run = [rs[0]]
        for a, b in zip(rs, rs[1:]):
            step = round(a["Order_Value"] - b["Order_Value"], 2)
            if len(run) >= 2 and abs(step - round(run[-2]["Order_Value"] - run[-1]["Order_Value"], 2)) <= 0.02 and step > 0: run.append(b)
            else:
                if len(run) >= 20:
                    st = round(run[0]["Order_Value"] - run[1]["Order_Value"], 2)
                    for x in run: out[x[RQ["oid"]]] = f"Suspect value: one of {len(run)} orders dated {d} whose published values fall by exactly R{st:,.2f} each (a spreadsheet fill-series). Shown as published; left out of totals and flags."
                run = [a, b] if step > 0 else [b]
        if len(run) >= 20:
            st = round(run[0]["Order_Value"] - run[1]["Order_Value"], 2)
            for x in run: out[x[RQ["oid"]]] = f"Suspect value: one of {len(run)} orders dated {d} whose published values fall by exactly R{st:,.2f} each (a spreadsheet fill-series). Shown as published; left out of totals and flags."
    return out
if RQ:
    DQ = fill_series(RQ["rows"])
    for i, r in enumerate(sorted(RQ["rows"], key=lambda r: (r.get("Date") or "", r.get("Tracking_Number") or ""))):
        s = REG.get(r.get("Supplier_Name")); sid = s["id"] if s else None
        dq = DQ.get(r.get(RQ["oid"]))
        if s:
            s["refs"]["rfq"].append(i); s["rfq_value"] += 0 if dq else float(r.get("Order_Value") or 0)
            if r.get("Date"): s["years"].add(r["Date"][:4])
        rfq.append([r.get("Date"), r.get("Tracking_Number"), r.get("Directorate"), r.get("Material_Group_Description"), r.get("Material_group_Long_Text"),
                    r.get("Supplier_Name"), r.get("BBBEE_Level"), r.get("Order_Value"), sid, r.get(RQ["oid"]), dq])
    table("rfq", RQ["title"], [["date", "Date"], ["tracking", "Tracking number"], ["directorate", "Directorate"], ["group", "Material group"],
          ["group_text", "Material group (long text)"], ["supplier", "Supplier as published"], ["bbbee", "B-BBEE level"], ["value", "Order value (R)"],
          ["sup", "Supplier"], ["oid", "Record number"], ["dq", "Data-quality note"]], rfq, "City of Cape Town Open Data Portal", RQ["url"], RQ["retrieved"],
          f"{len(DQ):,} orders carry values that form a spreadsheet fill-series in the source; they are marked, shown as published, and left out of totals and flags.")

# ================================================================ 1b/2b. another municipality: its own award registers (fetch_muni.py)
def method(how):
    """how a row was read, in the words the app shows"""
    h = str(how or "")
    return ("PDF Text (Council agenda)" if "agenda" in h else "Single-pass OCR (amount not parsed)" if h.startswith("ocr") else "PDF Text" if h.startswith("text") else h)
def notice(r, kind):
    """the data-quality notice for a row kept but not taken at face value; None for a clean row. 'LABEL: explanation' (the app shows the label)"""
    st = r.get("status")
    if st == "offer": return ("OFFER, NOT THE AWARD: listed in the register as an offer received for this quotation; the award is the row marked as awarded. "
                              "Not counted in totals or supplier profiles.")
    if st == "unclear": return (f"NAME UNCLEAR: the supplier column holds text that does not read as a supplier name ({r.get('status_why')}). Shown as printed; "
                                "not linked to a supplier and its amount is not counted. Check the register.")
    if st == "illegible": return ("NOT LEGIBLE (OCR): the scan did not read cleanly enough to name the supplier or parse the amount. Shown as read; "
                                  "not linked to a supplier and not counted. Check the scan.")
    if kind == "rfq" and r.get("amount"):
        date = r.get("approved") or r.get("published") or ""
        lim = next((t[1] for t in M["thresholds"] if date >= t[0]), None) if date else None
        if lim and r["amount"] > lim:
            return (f"ABOVE QUOTATION LIMIT: R{r['amount']:,.0f} is above the R{lim:,.0f} limit for formal written price quotations on {date}. Either the register was "
                    "misread or a quotation was used above the limit (which needs a competitive bid). Not counted in totals until checked against the register.")
    return None
if not CT:
    MA = load("muni-awards")
    if MA:
        for i, r in enumerate(sorted(MA["rows"], key=lambda r: (r.get("approved") or r.get("published") or "", muni_ref(r["ref"])))):
            dq = notice(r, "awards")
            s = None if dq else REG.get(r["bidder"]); sids = [s["id"]] if s else []
            date = r.get("approved") or r.get("published")
            rates = "Yes" if r.get("amount_text") and not r.get("amount") and re.match(r"(?i)rates", r["amount_text"]) else ""
            if s:
                s["refs"]["awards"].append(i)
                if date: s["years"].add(date[:4])
                if r.get("amount"): s["award_value"] += r["amount"]
            awards.append([date, r["ref"], r.get("doc_title"), "Offer received" if r.get("status") == "offer" else "Award" + (f" (panel of {r['panel']})" if r.get("panel", 1) > 1 else ""),
                           "Offer (not the award)" if r.get("status") == "offer" else "Awarded", r.get("desc"),
                           r["bidder"], r.get("amount_text"), None if dq else r.get("amount"), None, None, rates, sids, r.get("doc"), r.get("closing"), r.get("level"), r.get("completion"), method(r.get("how")),
                           r.get("published"), dq])
        table("awards", MA["title"], [["date", "Date approved"], ["ref", "Bid number"], ["decision", "Register"], ["reason", "Reason"], ["code", "Decision"], ["desc", "Description"],
              ["vendor", "Successful bidder as published"], ["value_text", "Amount approved, as published"], ["value", "Amount (parsed, R)"], ["budget_text", "Budget, as published"],
              ["budget", "Budget (parsed, R)"], ["rates", "Rates based"], ["sup", "Suppliers"], ["doc", "Register (PDF)"], ["closing", "Closing date"], ["bbbee", "B-BBEE level"],
              ["completion", "Completion"], ["how", "Extraction method"], ["published", "Register published"], ["dq", "Data-quality note"]], awards, f"{M['label']}: tenders awarded", MA["url"], MA["retrieved"],
              "Read from the municipality's monthly 'Tenders awarded' registers (PDF). One row per successful bidder; a panel award lists every member with the tender's amount "
              "(usually 'RATES': a rates-based contract with no single total). Amounts are as published. Rows are read from the register's layout; check them against the PDF linked on each row.")
    DV = load("muni-deviations")
    if DV and DV["rows"] and "awards" in tables:
        first_dev = len(awards)
        for r in sorted(DV["rows"], key=lambda r: (r.get("date") or r["agenda_date"], r["number"])):
            i = len(awards); s = REG.get(r["contractor"]); sids = [s["id"]] if s else []
            if s:
                s["refs"]["awards"].append(i); s["award_value"] += r.get("price") or 0
                if r.get("date"): s["years"].add(r["date"][:4])
            awards.append([r.get("date") or r["agenda_date"], r["number"], f"Reported to Council: {r['agenda']}", f"Deviation (reg. 36): {r.get('reason') or 'reason not stated'}", "Approved",
                           f"{r.get('description')}. Why the SCM process was not followed, as reported: {r.get('substantiation')}", r["contractor"], r.get("price_text"), r.get("price"),
                           None, None, "", sids, r["doc"], None, None, None, method("council agenda"), r.get("agenda_date"), None])
        tables["awards"]["n"] = len(awards)
        for k in range(0, max(1, len(awards)), SHARD): dump(awards[k:k + SHARD], os.path.join(PUB, "t", f"awards-{k // SHARD}.json"))
        tables["awards"]["shards"] = max(1, math.ceil(len(awards) / SHARD))
        tables["awards"]["name"] = f"{M['label']}: tenders awarded, and deviations reported to Council"
        tables["awards"]["note"] += (f" Also {len(awards) - first_dev} deviations (MFMA SCM Regulation 36) approved by the accounting officer and reported to Council, "
                                     "read from the monthly deviations item in the Council agendas; each links to the agenda page.")
    MF = load("muni-fq")
    if MF:
        for i, r in enumerate(sorted(MF["rows"], key=lambda r: (r.get("approved") or r.get("published") or "", muni_ref(r["ref"])))):
            dq = notice(r, "rfq")
            s = None if dq and r.get("status") else REG.get(r["bidder"]); sid = s["id"] if s else None
            date = r.get("approved") or r.get("published")
            if s:
                s["refs"]["rfq"].append(i); s["rfq_value"] += 0 if dq else r.get("amount") or 0
                if date: s["years"].add(date[:4])
            rfq.append([date, r["ref"], r.get("department") or "Directorate not published", "No category published", r.get("desc"), r["bidder"], r.get("level"), None if r.get("status") else r.get("amount"), sid, r.get("doc"), dq,
                        r.get("amount_text"), r.get("closing"), r.get("doc_title"), method(r.get("how")), r.get("published")])
        table("rfq", MF["title"], [["date", "Award date"], ["tracking", "Quotation number"], ["directorate", "Directorate"], ["group", "Category"], ["group_text", "Description"],
              ["supplier", "Awarded to, as published"], ["bbbee", "B-BBEE level"], ["value", "Amount (parsed, R)"], ["sup", "Supplier"], ["doc", "Register (PDF)"], ["dq", "Data-quality note"],
              ["value_text", "Amount as published"], ["closing", "Closing date"], ["register", "Register"], ["how", "Extraction method"], ["published", "Register published"]], rfq, f"{M['label']}: formal written price quotations awarded",
              MF["url"], MF["retrieved"], "Formal written price quotations (and requests for quotation) awarded, read from the municipality's monthly registers (PDF). The registers do not "
              "name the directorate or a spending category. 'Rates' means a rates-based order with no single total. Check each row against the PDF linked on it.")

# ================================================================ 3. Bids received at City tender openings (City PDF registers)
BD = load("city-bids" if CT else "muni-bids")
bids, bid_tenders = [], collections.defaultdict(list)
if BD:
    for t in BD["tenders"]:
        for b in t["bids"]:
            if b["price"] is not None and b["price"] < 1000: b["price"] = None   # a stray number (points, serial) rather than a price; the text stays
        prices = [b["price"] for b in t["bids"] if b["price"]]
        lo = min(prices) if prices else None
        for b in t["bids"]:
            s = None if b.get("status") else REG.get(b["bidder"], ocr="conf" in b); sid = s["id"] if s else None
            i = len(bids)
            if s:
                s["refs"]["bids"].append(i); s["n_bids"] += 1
                if t.get("closing"): s["years"].add(t["closing"][:4])
            rank = (sorted(prices).index(b["price"]) + 1) if b["price"] and prices else None
            bids.append([t.get("closing"), t["ref"], t["description"], b["n"], b["bidder"], b["price_text"], b["price"], rank, len(t["bids"]),
                         " / ".join(b["hdi"]), sid, t["doc"] + (f"#page={b['page']}" if b.get("page") else "")] + ([b.get("conf"), b.get("page"), "Dual-Pass OCR", t.get("published"), notice(b, "bids")] if not CT else []))
            bid_tenders[t["ref"]].append(i)
    if CT:
        table("bids", BD["title"], [["closing", "Closing date"], ["ref", "Tender reference"], ["desc", "Description"], ["n", "Serial no."], ["bidder", "Bidder as published"],
              ["price_text", "Price as published"], ["price", "Price (parsed, R)"], ["rank", "Price rank (1 = lowest)"], ["n_bids", "Bids on this tender"],
              ["hdi", "HDI points claimed"], ["sup", "Supplier"], ["doc", "Register (PDF)"]], bids, "City of Cape Town: Tenders received", BD["url"], BD["retrieved"],
              "Read from the City's monthly 'Receiving / Opening of Tenders' registers. Prices are as read out at the opening, before evaluation; "
              "'Various Rates' means a rates-based bid with no single total.")
    else:
        table("bids", BD["title"], [["closing", "Closing date"], ["ref", "Tender reference"], ["desc", "Description"], ["n", "Serial no."], ["bidder", "Bidder as read (OCR)"],
              ["price_text", "Price as read (OCR)"], ["price", "Price (parsed, R)"], ["rank", "Price rank (1 = lowest)"], ["n_bids", "Bids read on this tender"],
              ["hdi", "B-BBEE level as read"], ["sup", "Supplier"], ["doc", "Register (scan)"], ["conf", "OCR confidence (0-100)"], ["page", "Page of the scan"], ["how", "Extraction method"], ["published", "Register published"], ["dq", "Data-quality note"]], bids, f"{M['label']}: bid-opening registers", BD["url"], BD["retrieved"],
              "The municipality publishes its bid-opening registers as scanned images. Each was read by OCR (tesseract): every row here is machine-read, with its confidence, "
              f"and links to the scan. Rows below confidence {BD.get('min_conf', 60)} and handwritten registers are not shown. Prices are as read out at the opening, before evaluation.")

# ================================================================ 4. eTender portal (all spheres, Western Cape buyers)
ET = load("etenders")
et_rows, et_detail = [], {}
if ET:
    recs = sorted(ET["tenders"].values(), key=lambda t: t.get("date_Published") or "")
    for i, t in enumerate(recs):
        win = []
        for a in t.get("awards", []):
            s = REG.get(a.get("company"))
            if s:
                win.append(s["id"]); s["refs"]["et"].append(i); s["n_wins"] += 1
                v = money_val(a.get("amount"));  s["et_value"] += v or 0
                if a.get("phone"): s["phones"].add(re.sub(r"\D", "", a["phone"])[-9:])
                if a.get("contact"): s["contacts"].add(a["contact"].strip().upper())
                if t.get("date_Published"): s["years"].add(t["date_Published"][:4])
        bidders = []
        for b in t.get("bidders", []):
            s = REG.get(b.get("name"))
            if s:
                bidders.append(s["id"])
                if i not in s["refs"]["et"]: s["refs"]["et"].append(i)
                s["n_bids"] += 1
        et_rows.append([(t.get("date_Published") or "")[:10], t.get("tender_No"), t.get("organ_of_State"), t.get("type"), t.get("category"), t.get("description"),
                        t.get("portal_status"), (t.get("closing_Date") or "")[:16].replace("T", " "), t.get("province"), t.get("contactPerson"), t.get("email"),
                        "; ".join(f"{a.get('company')} ({a.get('amount')})" for a in t.get("awards", [])), (t.get("awardDate") or "")[:10], len(t.get("bidders", [])),
                        win, bidders, t.get("id")] + ([] if CT else ["eTender API", f"https://www.etenders.gov.za/Home/opportunities?id={ {'Open': 1, 'Awarded': 2, 'Closed': 3, 'Cancelled': 4}.get(t.get('portal_status'), 1) }"]))
        et_detail[i] = t
    table("etenders", ET["title"], [["published", "Published"], ["number", "Tender number"], ["buyer", "Organ of state"], ["type", "Type"], ["category", "Category"],
          ["desc", "Description"], ["status", "Status on portal"], ["closing", "Closing"], ["province", "Province"], ["official", "Contact person (buyer)"],
          ["email", "Contact e-mail (buyer)"], ["awards", "Awarded to (amount as published)"], ["award_date", "Award date"], ["n_bidders", "Bidders listed"],
          ["sup", "Winning suppliers"], ["bidders", "Bidding suppliers"], ["portal_id", "Portal record"]] + ([] if CT else [["how", "Extraction method"], ["url", "Portal list"]]), et_rows, "National Treasury eTender Portal",
          ET["url"], ET["retrieved"], "Every tender a Western Cape buyer (any sphere) placed on the national portal, with briefing details, documents, bidders and awards as published." if CT
          else f"Every tender {M['label']} placed on the national portal (buyer names: {', '.join(ET.get('buyer_names', []))}), with briefing details, documents, bidders and awards as published.")
    # full detail (documents, bidders with amounts, award contacts) in shards, opened from the table
    for k in range(0, len(recs), 2000):
        dump({str(i): et_detail[i] for i in range(k, min(k + 2000, len(recs)))}, os.path.join(PUB, "etd", f"{k // 2000}.json"))

# ================================================================ 5. City land sales
PD = load("odp-property-disposals")
disp = []
if PD:
    for i, r in enumerate(PD["rows"]):
        s = REG.get(r.get("NEW_OWNERS_NAME")); sid = s["id"] if s else None
        if s: s["refs"]["land"].append(i)
        disp.append([r.get("DATE_OF_FINAL_IPAC_COUNCIL_APPROVAL"), r.get("DATE_OF_REGISTRATION"), r.get("ERF_ERVEN_NO"), r.get("AREA"), r.get("EXTENT__M__"),
                     r.get("USAGE__Buss_Res_Place_of_Worship__Garden_"), r.get("AUCTION___DIRECT___CALL_FOR_ALT_PROP___VESTING"),
                     money_val(r.get("PURCHASE_PRICE__INCL_ESCALATION_WHERE_APPLICABLE_")), money_val(r.get("TOTAL__INCL_VAT____COC_COSTS_DEDUCTED_WHERE_APPLICABLE")),
                     r.get("NEW_OWNERS_NAME"), r.get("SUBCOUNCIL"), r.get("OFFICE___REGION"), sid, r.get(PD["oid"])])
    table("land", PD["title"], [["approved", "Final council (IPAC) approval"], ["registered", "Date of registration"], ["erf", "Erf"], ["area", "Area"], ["extent", "Extent (m²)"],
          ["usage", "Usage"], ["method", "Auction / direct / call / vesting"], ["price", "Purchase price (R)"], ["total", "Total incl. VAT (R)"], ["owner", "New owner"],
          ["subcouncil", "Subcouncil"], ["region", "Region"], ["sup", "Buyer profile"], ["oid", "Record number"]], disp, "City of Cape Town Open Data Portal", PD["url"], PD["retrieved"])

# ================================================================ 6. City tender-page documents
DC = load("city-docs")
docs_by_ref = collections.defaultdict(list)
if DC:
    rows = []
    for i, d in enumerate(sorted(DC["docs"], key=lambda d: (d["page"], d.get("month") or ""), reverse=True)):
        rows.append([d.get("month"), d["page_title"], d["title"], ", ".join(d["tenders"]), d["url"]])
        for r in d["tenders"]: docs_by_ref[r].append(i)
    table("docs", DC["title"], [["month", "Month"], ["kind", "Register"], ["title", "Title"], ["refs", "Tenders named in the file name"], ["url", "Document"]], rows,
          "City of Cape Town: tenders, RFQs and supply pages", DC["url"], DC["retrieved"])

if not CT:
    MD = load("docs")
    if MD:
        rows = []
        KL = {"awards": "Tenders awarded", "fq": "Formal quotations awarded", "rfq": "RFQs awarded", "bids": "Bid-opening register", "cancelled": "Notice of cancellation",
              "open": "Tender advertised", "fq_open": "Formal quotation invited", "rfq_open": "RFQ invited", "rfq30": "RFQ under R30 000", "scm": "SCM report"}
        for i, d in enumerate(MD["docs"]):
            refs = sorted({muni_ref(m.group(0)) for m in re.finditer(r"\b(?:B\s*/?\s*SM|FQ\s*/?\s*(?:SM)?)\s*[-_]?\s*\d{1,3}\s*[-_/]\s*\d\d\b", d["title"] + " " + (d.get("file") or "").rsplit("/", 1)[-1].replace("_", "/"), re.I)})
            rows.append([d["published"], KL.get(d["kind"], d["kind"]), d["title"], ", ".join(refs), d.get("file") or d["page"]])
            for r in refs: docs_by_ref[r].append(i)
        table("docs", MD["title"], [["month", "Published"], ["kind", "Register"], ["title", "Title"], ["refs", "Tenders named"], ["url", "Document"]], rows,
              f"{M['label']}: document library (procurement categories)", MD["url"], MD["retrieved"])

# ================================================================ tender dossiers: one entry per tender reference, joining every source
def ref_key(r): return muni_ref(r)
OWN_REF = re.compile(r"\b(?:B\s*/?\s*SM|FQ\s*/?\s*(?:SM)?|RFQ)\s*[-_:]?\s*0*\d{1,3}\s*[-_/]\s*(?:20)?\d\d\b", re.I)
tender = collections.defaultdict(lambda: {"awards": [], "bids": [], "et": [], "docs": [], "rfq": []})
for i, a in enumerate(awards): tender[ref_key(a[1])]["awards"].append(i)
for ref, idx in bid_tenders.items(): tender[ref_key(ref)]["bids"] += idx
for i, r in enumerate(et_rows):
    if CT:
        m = re.search(r"\b(\d{1,3}[A-Z]/20\d\d/\d\d)\b", str(r[1] or "").upper().replace(" ", ""))
        if m and "CAPE TOWN" in str(r[2] or "").upper(): tender[ref_key(m.group(1))]["et"].append(i)
    else:   # the municipality's own number, wherever the buyer typed it (tender number field or description): BSM 12/26, BSM12-26, BSM 012/2026
        m = OWN_REF.search(f"{r[1] or ''} {r[5] or ''}")
        if m:
            k = ref_key(m.group(0)); tender[k]["et"].append(i); et_detail[i]["muni_ref"] = k
for ref, idx in docs_by_ref.items(): tender[ref_key(ref)]["docs"] += idx
if not CT:   # a municipality's formal quotations carry their own numbers (FQ 29/27): each gets a dossier too
    for i, r in enumerate(rfq): tender[ref_key(r[1])]["rfq"].append(i)
tender = {k: v for k, v in tender.items() if k}
buckets = collections.defaultdict(dict)
for k, v in tender.items(): buckets[bucket(k)][k] = {x: y for x, y in v.items() if y}
for b, v in buckets.items(): dump(v, os.path.join(PUB, "tender", f"{b}.json"))

# ================================================================ pattern flags
def flag(kind, title, text, records, subjects, value=None, basis=None, **extra):
    flags.append({"id": f"{kind}-{len(flags)}", "kind": kind, "title": title, "text": text, "records": records, "subjects": subjects,
                  **({"value": value} if value is not None else {}), **({"basis": basis} if basis else {}), **extra})

KINDS = {
    "repeat": "Repeat winner in one directorate",
    "split": "Orders to one supplier just under the competitive-bidding threshold",
    "near": "Repeated orders just below the threshold",
    "growth": "Contract value increased by later decisions",
    "deviation": "Several deviations naming the same supplier",
    "cobid": "The same companies bidding against each other repeatedly",
    "notlowest": "Award to a bidder that was not the lowest price read out",
    "official": "The same buyer official on several awards to one supplier",
    "phone": "Different companies sharing a published contact number",
    "single": "Tenders with a single bid",
    "young": "Award within 12 months of company registration",
}

# repeat winners: share of a directorate's RFQ orders (count and value) going to one supplier
by_dir = collections.defaultdict(lambda: collections.defaultdict(list))
for i, r in enumerate(rfq):
    if r[8] and not r[10]: by_dir[r[2]][r[8]].append(i)
for d, sup in by_dir.items():
    total_n = sum(len(v) for v in sup.values()); total_v = sum(float(rfq[i][7] or 0) for v in sup.values() for i in v)
    if total_n < (200 if CT else 40): continue   # a local municipality publishes far fewer orders: the same shares, lower counts
    for sid, idx in sup.items():
        v = sum(float(rfq[i][7] or 0) for i in idx)
        if len(idx) >= (50 if CT else 5) and (len(idx) / total_n >= 0.05 or (total_v and v / total_v >= 0.05)):
            flag("repeat", f"{REG.by[sid]['names'].most_common(1)[0][0]}: {len(idx):,} quotation orders from {d if CT else M['label']}",
                 f"{len(idx):,} of the directorate's {total_n:,} published quotation orders ({len(idx) / total_n:.1%}), worth R{v:,.0f} of R{total_v:,.0f} ({v / max(total_v, 1):.1%}).",
                 [["rfq", i] for i in idx], [["supplier", sid], ["directorate", d]], v)

# threshold splitting: same supplier, directorate and material group within 30 days, each order under the threshold, together over it
def days(a, b): return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
grp = collections.defaultdict(list)
for i, r in enumerate(rfq):
    if r[8] and r[0] and r[7] and not r[10]: grp[(r[8], r[2], r[3])].append(i)
for (sid, d, g), idx in grp.items():
    idx.sort(key=lambda i: rfq[i][0]); j = 0
    used = set()
    for k in range(len(idx)):
        while days(rfq[idx[j]][0], rfq[idx[k]][0]) > 30: j += 1
        win = [i for i in idx[j:k + 1] if i not in used]
        T = threshold(rfq[idx[k]][0])
        if len(win) >= 2 and all(float(rfq[i][7]) < T[1] for i in win) and sum(float(rfq[i][7]) for i in win) > T[1]:
            tot = sum(float(rfq[i][7]) for i in win)
            flag("split", f"{REG.by[sid]['names'].most_common(1)[0][0]}: {len(win)} orders in {days(rfq[win[0]][0], rfq[win[-1]][0]) + 1} days, R{tot:,.0f} together",
                 (f"{len(win)} quotation orders from {d} for '{g}', each below and together above the competitive-bidding threshold of the day ({T[2]})." if CT else
                  f"{len(win)} formal quotations awarded by {M['label']} to this supplier within 30 days, each below and together above the competitive-bidding threshold of the day ({T[2]}). "
                  "The registers name no spending category, so orders for different items are counted together; read the descriptions."),
                 [["rfq", i] for i in win], [["supplier", sid], ["directorate", d]], tot, {"text": T[2], "url": T[3]})
            used.update(win)

# orders priced in the last 10% below the threshold, three or more for one supplier
near = collections.defaultdict(list)
for i, r in enumerate(rfq):
    if r[8] and r[7] and r[0] and not r[10]:
        T = threshold(r[0])
        if 0.9 * T[1] <= float(r[7]) < T[1]: near[r[8]].append(i)
for sid, idx in near.items():
    if len(idx) >= 3:
        flag("near", f"{REG.by[sid]['names'].most_common(1)[0][0]}: {len(idx)} orders within 10% below the threshold",
             "Quotation orders valued between 90% and 100% of the competitive-bidding threshold that applied on the order date.",
             [["rfq", i] for i in idx], [["supplier", sid]], sum(float(rfq[i][7]) for i in idx), {"text": THRESHOLDS[0][2] + "; " + THRESHOLDS[1][2], "url": THRESHOLDS[0][3]})

# contract growth: expansions and amendments after the award, per tender reference
by_ref = collections.defaultdict(list)
for i, a in enumerate(awards): by_ref[ref_key(a[1])].append(i)
for ref, idx in by_ref.items():
    V = lambda i: awards[i][8] or awards[i][10] or 0
    ok = OK
    base = [i for i in idx if str(awards[i][3] or "").startswith(("Award", "Preferred")) and awards[i][4] in ok]
    grow = [i for i in idx if awards[i][3] in ("Expansion", "Amendment") and awards[i][4] in ok]
    if not base or not grow: continue
    b = sum(V(i) for i in base); g = sum(V(i) for i in grow); valued = [i for i in grow if V(i)]
    if len(grow) >= 2 or (b and g / b >= 0.5):
        sids = sorted({s for i in base + grow for s in awards[i][12]})
        if valued and b:
            txt = (f"Award decision(s) total R{b:,.0f}. {len(grow)} later expansion or amendment decision(s); {len(valued)} published with values totalling R{g:,.0f} "
                   f"({g / b:.0%} of the award). Whether a value is the increase or the new total is as stated in each record.")
        else:
            txt = (f"Award decision(s) total R{b:,.0f}. " if b else "") + f"{len(grow)} later expansion or amendment decision(s), published without a value."
        flag("growth", f"Tender {awards[base[0]][1]}: {len(grow)} expansion or amendment decision(s) after award", txt,
             [["awards", i] for i in sorted(base + grow)], [["tender", ref]] + [["supplier", s] for s in sids], g or None)

# deviations
dev = collections.defaultdict(list)
for i, a in enumerate(awards):
    if str(a[3] or "").startswith("Deviation") or a[3] == "Condonation":
        for s in a[12]: dev[s].append(i)
for sid, idx in dev.items():
    if len(idx) >= 2:
        flag("deviation", f"{REG.by[sid]['names'].most_common(1)[0][0]}: named in {len(idx)} deviation or condonation decisions",
             "Decisions to procure outside the normal competitive process (emergency, single source, sole provider, exceptional circumstances) or to condone it.",
             [["awards", i] for i in idx], [["supplier", sid]], sum(awards[i][8] or awards[i][10] or 0 for i in idx))

# co-bidding: pairs of companies on the same bid registers
tender_bidders = collections.defaultdict(set)
for i, b in enumerate(bids):
    if b[10]: tender_bidders[ref_key(b[1])].add(b[10])
winners = collections.defaultdict(set)
for i, a in enumerate(awards):
    if str(a[3] or "").startswith(("Award", "Preferred")) and a[4] in OK:
        winners[ref_key(a[1])].update(a[12])
pairs = collections.Counter(); pair_refs = collections.defaultdict(list)
for ref, s in tender_bidders.items():
    if 2 <= len(s) <= 15:
        for a in s:
            for b in s:
                if a < b: pairs[(a, b)] += 1; pair_refs[(a, b)].append(ref)
for (a, b), n in pairs.most_common(400):
    if n < 5: break
    refs = pair_refs[(a, b)]
    wa = sum(1 for r in refs if a in winners.get(r, ())); wb = sum(1 for r in refs if b in winners.get(r, ()))
    recs = [["bids", i] for r in refs for i in bid_tenders.get(next((k for k in bid_tenders if ref_key(k) == r), ""), []) if bids[i][10] in (a, b)]
    na, nb = (REG.by[x]["names"].most_common(1)[0][0] for x in (a, b))
    flag("cobid", f"{na} and {nb}: bid on the same {n} tenders",
         f"Both appear on {n} of the {'City' if CT else M['label']}'s published bid-opening registers. Per the published award decisions, {na} won {wa} and {nb} won {wb} of these.",
         recs, [["supplier", a], ["supplier", b]])

# award not to the lowest price read out (80/20 and 90/10 preference points can lawfully change the order)
for ref, idx in bid_tenders.items():
    k = ref_key(ref); prices = [(bids[i][6], bids[i][10], i) for i in idx if bids[i][6]]
    if len(prices) < 2 or not winners.get(k): continue
    lo = min(p[0] for p in prices); lo_i = next(i for p, _, i in prices if p == lo)
    for p, sid, i in prices:
        if sid in winners[k] and p > lo * 1.10:
            review = not CT and p > lo * 4   # a gap above 300% (more than four times the lowest) in an OCR-read register: more often a misread digit or a bid for part of the work
            extra = {}
            if not CT:
                extra = {"verification_status": "NEEDS_SCAN_REVIEW" if review else "OCR_DUAL_PASS_AGREED", "method": "Dual-Pass OCR",
                         "scan": bids[i][11], "scan_lowest": bids[lo_i][11]}
                if review: extra["review_reason"] = "HIGH_VARIANCE_OR_PARTIAL_BID"
            flag("notlowest", f"Tender {ref}: awarded bidder priced {p / lo - 1:.0%} above the lowest",
                 f"Price read out at opening R{p:,.0f}; lowest R{lo:,.0f}. Preference points (80/20 or 90/10), functionality and responsiveness lawfully affect the award; "
                 "the evaluation report is not published here." + (" The gap is more than 300% of the lowest price: check both prices against the scanned register "
                 "before relying on it; it may be a misread digit or a bid for only part of the work." if review else ""),
                 [["bids", j] for j in idx] + [["awards", a] for a in by_ref.get(k, [])], [["tender", k], ["supplier", sid]], p - lo, **extra)

# the same buyer official on several eTender awards to one supplier
off = collections.defaultdict(list)
for i, r in enumerate(et_rows):
    if r[9] and r[14] and not re.search(r"help ?desk|tender|office|\bscm\b|supply chain|procurement|\bbid|desk|unit|section|enquir|department", str(r[9]), re.I):
        for s in r[14]: off[(str(r[9]).strip().upper(), str(r[2]), s)].append(i)
for (o, buyer, sid), idx in off.items():
    if len(idx) >= 3:
        flag("official", f"{o.title()} ({buyer}): contact person on {len(idx)} awards to {REG.by[sid]['names'].most_common(1)[0][0]}",
             "The buyer's contact person named on the eTender portal for each of these awards to the same supplier. A buyer's supply-chain officer is often the contact on many tenders, so this shows who handled them, not who decided.", [["etenders", i] for i in idx],
             [["supplier", sid], ["official", o], ["department", buyer]])

# shared contact numbers between differently named companies (eTender award records)
# Buyers often type their own office number or a placeholder into the award contact field, so a number only counts when it is
# not any buyer's published number, is not placeholder-like (few distinct digits, ending 0000), and links 2 to 5 companies.
buyer_phones = {re.sub(r"\D", "", str(t.get("telephone") or ""))[-9:] for t in et_detail.values()}
ph = collections.defaultdict(set)
for s in REG.by.values():
    for p in s["phones"]:
        if len(p) == 9 and len(set(p)) > 3 and not p.endswith("0000") and p not in buyer_phones: ph[p].add(s["id"])
for p, sids in ph.items():
    if 2 <= len(sids) <= 5:
        recs = [["etenders", i] for s in sids for i in REG.by[s]["refs"]["et"]]
        flag("phone", f"{len(sids)} companies share the contact number ending {p[-4:]}",
             "Award records on the eTender portal give the same contact number for these differently named companies: " + "; ".join(REG.by[s]["names"].most_common(1)[0][0] for s in sorted(sids)) + ".",
             recs, [["supplier", s] for s in sorted(sids)])

# single-bid tenders, grouped by winner
single = collections.defaultdict(list)
def only_bid(i):
    """the one row read is the whole register: serial number 1 (or none printed) and readable. A serial above 1 means rows above it were
    not read (OCR), so the tender had more bids than were read."""
    sn = str(bids[i][3] or "").strip().lstrip("0")
    return sn in ("", "1", "None") and not (not CT and bids[i][16])
for ref, idx in bid_tenders.items():
    if len(idx) == 1 and only_bid(idx[0]):
        for s in winners.get(ref_key(ref), ()) or ([bids[idx[0]][10]] if bids[idx[0]][10] else []):
            single[s].append(idx[0])
for sid, idx in single.items():
    if len(idx) >= 2 and sid in REG.by:
        flag("single", f"{REG.by[sid]['names'].most_common(1)[0][0]}: sole bidder on {len(idx)} {'City' if CT else M['label']} tenders",
             "Tenders where the published opening register lists one bid only." + ("" if CT else " Registers are read by OCR: a tender counts only when the one row read is serial number 1 and readable."),
             [["bids", i] for i in idx], [["supplier", sid]])

# award within 12 months of registration: only where a registration date came from a company-register source (registry.json),
# never from the year inside a registration number
REG_PATH = os.path.join(ROOT, "public", "data", "metro", "registry.json")
if os.path.exists(REG_PATH):
    regs = json.load(open(REG_PATH)).get("records", {})
    for sid, rec in regs.items():
        d = str(rec.get("reg_date") or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}$", d) or sid not in REG.by: continue
        early = [i for i in REG.by[sid]["refs"]["awards"] if awards[i][0] and str(awards[i][3] or "").startswith(("Award", "Preferred", "Deviation")) and 0 <= days(d, awards[i][0]) <= 365]
        early += [("rfq", i) for i in REG.by[sid]["refs"]["rfq"] if rfq[i][0] and 0 <= days(d, rfq[i][0]) <= 365]
        if early:
            recs = [["awards", i] if isinstance(i, int) else list(i) for i in early]
            flag("young", f"{REG.by[sid]['names'].most_common(1)[0][0]}: {len(recs)} award(s) or order(s) within 12 months of registration",
                 f"Registered {d} according to {rec.get('source', 'the company register')} (retrieved {str(rec.get('retrieved', ''))[:10]}). New companies win work lawfully; this lists the records.",
                 recs, [["supplier", sid]])

# ---------------------------------------------------------------- portal discrepancy and cancel-and-re-tender (municipalities other than Cape Town)
if not CT and et_rows:
    KINDS["portal"] = "Award above the competitive-bidding threshold with no award notice on the eTender portal"
    et_dates = sorted(r[0] for r in et_rows if r[0])
    # the archive covers a year only once it holds a fair number of this buyer's records (the portal drops old ones before Cape Monitor
    # began keeping them): flags start three months into the first such year, and skip the last 60 days, while notices are still posted
    per_year = collections.Counter(d[:4] for d in et_dates)
    cover = next((y for y in sorted(per_year) if per_year[y] >= 20), et_dates[0][:4])
    first_et = f"{cover}-04-01"; last_et = et_dates[-1]
    last_ok = (datetime.date.fromisoformat(last_et) - datetime.timedelta(days=60)).isoformat()
    seen_award = set()
    for i, a in enumerate(awards):
        if not str(a[3] or "").startswith("Award") or not a[8] or not a[0]: continue   # tender awards with a published amount; not deviations or rates
        k = ref_key(a[1]); T = threshold(a[0])
        if a[8] <= T[1] or k in seen_award or a[0] < first_et or a[0] > last_ok: continue
        ets = tender.get(k, {}).get("et", [])
        if any(et_detail[j].get("awards") for j in ets): continue
        seen_award.add(k)
        state = ", ".join(sorted({str(et_rows[j][6]) for j in ets})) or "no record at all"
        rows_k = [j for j in tender[k]["awards"]]
        flag("portal", f"Tender {a[1]}: R{a[8]:,.0f} award, no award notice on the eTender portal",
             f"The municipality's register shows an award of {a[7]} on {a[0]}, above the threshold of the day ({T[2]}). Cape Monitor's archive of the national eTender "
             f"portal (this buyer's records complete enough from {first_et}; latest {last_et}) holds for this number: {state}. Award notices may have been published under another number, or "
             "removed by the portal; the archive keeps what it has seen since it was started.",
             [["awards", j] for j in rows_k] + [["etenders", j] for j in ets], [["tender", k]] + [["supplier", s] for j in rows_k for s in awards[j][12]],
             a[8], {"text": T[2], "url": T[3]})

    KINDS["retender"] = "Cancelled tender followed within 180 days by a similar tender"
    STOP = set("the and for of to in a an at as on by with from or be is are this that until ending period when required stellenbosch municipality municipal wc024 date award "
               "appointment provision service services supply delivery tender tenders bsm sm".split())
    def words(t): return {w for w in re.findall(r"[a-z]{3,}", str(t or "").lower()) if w not in STOP}
    later = []   # (date, key, description, source, index)
    for j, r in enumerate(et_rows):
        if r[0]: later.append((r[0], et_detail[j].get("muni_ref"), r[5], "etenders", j))
    for i, a in enumerate(awards):
        if a[0] and str(a[3] or "").startswith("Award"): later.append((a[0], ref_key(a[1]), a[5], "awards", i))
    for i, d in enumerate((MD or {}).get("docs", [])):
        if d["kind"] in ("open", "fq_open"): later.append((d["published"], None, d["title"], "docs", i))
    cancels = [(i, d) for i, d in enumerate((MD or {}).get("docs", [])) if d["kind"] == "cancelled"]
    done = set()
    for i, d in cancels:
        m = OWN_REF.search(d["title"])
        if not m: continue
        k = ref_key(m.group(0)); w0 = words(re.sub(r"^.*?\d\d\s*[:\-]?", "", d["title"], count=1)) | words(" ".join(str(awards[j][5]) for j in tender.get(k, {}).get("awards", [])))
        if len(w0) < 4 or k in done: continue
        d0 = d["published"]; end = (datetime.date.fromisoformat(d0) + datetime.timedelta(days=180)).isoformat()
        hits = []
        for dt, k2, desc, src, j in later:
            if not (d0 < dt <= end) or (k2 and k2 == k): continue
            w1 = words(desc); shared = w0 & w1
            if len(shared) >= 4 and len(shared) / len(w0 | w1) >= 0.5: hits.append((dt, src, j, desc, sorted(shared)))
        bidders = {bids[j][10] for j in tender.get(k, {}).get("bids", []) if bids[j][10]}
        if not hits: continue
        done.add(k)
        recs = [["docs", i]] + [[src, j] for _, src, j, _, _ in hits[:20]]
        winners_later = sorted({s for _, src, j, _, _ in hits if src == "awards" for s in awards[j][12]} & bidders)
        flag("retender", f"Tender {m.group(0)}: cancelled {d0}, similar tender within 180 days ({len(hits)} record{'s' if len(hits) > 1 else ''})",
             f"Notice of cancellation published {d0}. Within 180 days the municipality published records with a similar description (at least half of the distinctive "
             f"words shared), first on {hits[0][0]}: '{str(hits[0][3])[:160]}'." + (f" A later award went to a supplier that bid on the cancelled tender." if winners_later else "")
             + " Re-tendering after a cancellation is lawful and common; this lists the records so the reasons can be compared.",
             recs, [["tender", k]] + [["supplier", s] for s in winners_later])

# Treasury's restricted-supplier report: a supplier whose normalised name equals a restricted name. Name match only.
RS = load("restricted")
if RS:
    KINDS["restricted"] = "Name matches Treasury's restricted-supplier list"
    for r in RS["rows"]:
        k = re.sub(r"[^a-z0-9]+", "-", norm(r["name"]).lower()).strip("-")[:60]
        if k in REG.by and any(REG.by[k]["refs"].values()):
            S = REG.by[k]; recs = [["awards", i] for i in S["refs"]["awards"]] + [["rfq", i] for i in S["refs"]["rfq"]] + [["etenders", i] for i in S["refs"]["et"]] + [["bids", i] for i in S["refs"]["bids"]]
            # where the municipality's records fall against the restriction period: the first thing a reader needs to know
            dates = sorted(d for d in [awards[i][0] for i in S["refs"]["awards"]] + [rfq[i][0] for i in S["refs"]["rfq"]] + [et_rows[i][0] for i in S["refs"]["et"]]
                           + [bids[i][0] for i in S["refs"]["bids"]] if d)
            inside = [d for d in dates if r["from"] and r["to"] and r["from"] <= d <= r["to"]]
            timing = (f"Of the {len(dates)} dated records here ({dates[0]} to {dates[-1]}), {len(inside)} fall inside the restriction period"
                      + (f" (first {inside[0]})." if inside else "; the others are before or after it.")) if dates else "The records here carry no date."
            flag("restricted", f"{S['names'].most_common(1)[0][0]}: same name as '{r['name']}' on Treasury's restricted list",
                 f"NAME MATCH ONLY. Treasury's Restricted Supplier and Tender Defaulter Report (generated {RS.get('generated')}) lists '{r['name']}' (registration or ID number {r['reg'] or 'not given'}): "
                 f"{r['type']}, reason '{r['reason']}', restricted {r['from']} to {r['to']} by {r['by']}. The records here name a supplier with the same normalised name; they do not show "
                 "a registration number, so it may be a different entity. Check the registration number on the CSD before relying on this. " + timing,
                 recs, [["supplier", k]], basis={"text": "National Treasury: Restricted Supplier and Tender Defaulter Report", "url": RS["url"]})

for f in flags:
    for kind, sid in f["subjects"]:
        if kind == "supplier" and sid in REG.by: REG.by[sid].setdefault("flags", []).append(f["id"])

# ================================================================ write suppliers, departments, flags
def likely_person(s):
    return looks_like_person(s["names"].most_common(1)[0][0], land_only=bool(s["refs"].get("land")) and not s["refs"].get("awards") and not s["refs"].get("rfq"))

active = [s for s in REG.by.values() if any(s["refs"].values())]
index = []
prof = collections.defaultdict(dict)
cob = collections.defaultdict(collections.Counter)
for (a, b), n in pairs.items(): cob[a][b] = n; cob[b][a] = n
for s in active:
    yrs = sorted(s["years"])
    index.append([s["id"], s["names"].most_common(1)[0][0], len(s["refs"]["awards"]), round(s["award_value"]), len(s["refs"]["rfq"]), round(s["rfq_value"]),
                  len(s["refs"]["bids"]), len(s["refs"]["et"]), len(s["refs"]["land"]), yrs[0] if yrs else None, yrs[-1] if yrs else None, len(s.get("flags", [])), round(s["award_budget"]), 1 if likely_person(s) else 0])
    prof[bucket(s["id"])][s["id"]] = {
        "names": s["names"].most_common(), "refs": {k: v for k, v in s["refs"].items() if v}, "phones": sorted(s["phones"]), "contacts": sorted(s["contacts"]),
        "flags": s.get("flags", []), "cobid": cob[s["id"]].most_common(30)}
# the same normalised name in Cape Town's records (built first, in the same run): shown on each profile, linked to Cape Monitor
if not CT:
    p = os.path.join(ROOT, "public", "data", "metro", "money", "suppliers.json")
    ct = {r[0]: r for r in json.load(open(p))["rows"]} if os.path.exists(p) else {}
    for r in index:
        c = ct.get(r[0])
        r.append(1 if c else 0)
        if c: prof[bucket(r[0])][r[0]]["elsewhere"] = {"cape-town": {"name": c[1], "awards": c[2], "award_value": c[3], "rfq": c[4], "rfq_value": c[5], "bids": c[6],
                                                                     "etenders": c[7], "first": c[9], "last": c[10], "flags": c[11], "url": "/#s=" + r[0]}}
index.sort(key=lambda r: -(r[3] + r[5]))
dump({"fields": ["id", "name", "awards", "award_value", "rfq", "rfq_value", "bids", "etenders", "land", "first", "last", "flags", "award_budget", "person"] + ([] if CT else ["cape_town"]), "rows": index}, os.path.join(PUB, "suppliers.json"))
for b, v in prof.items(): dump(v, os.path.join(PUB, "sup", f"{b}.json"))

deps = collections.defaultdict(lambda: {"n": 0, "value": 0.0, "years": collections.Counter(), "sup": collections.Counter(), "src": set()})
for i, r in enumerate(rfq):
    v = 0 if r[10] else float(r[7] or 0)
    d = deps["City of Cape Town: " + str(r[2] or "Unassigned").strip().title() if CT else f"{M['label']}: formal quotations (directorate not published)"]; d["n"] += 1; d["value"] += v; d["src"].add("rfq")
    d["years"][str(r[0] or "")[:4]] += v; d["sup"][r[8]] += v
if not CT:
    for i, a in enumerate(awards):
        d = deps[f"{M['label']}: tenders awarded (directorate not published)"]; d["n"] += 1; d["value"] += a[8] or 0; d["src"].add("awards")
        d["years"][str(a[0] or "")[:4]] += a[8] or 0
        for s in a[12]: d["sup"][s] += a[8] or 0
for i, r in enumerate(et_rows):
    dep = str(r[2] or "?") if CT else (f"{M['label']}: " + str(et_detail[i].get("department") or "department not stated").strip().title())
    d = deps[dep]; d["n"] += 1; d["src"].add("etenders")
    for s in r[14]: d["sup"][s] += 1
dump([{"name": k, "n": v["n"], "value": round(v["value"]), "years": sorted(v["years"].items()), "top": [[s, round(x)] for s, x in v["sup"].most_common(15) if s],
       "sources": sorted(v["src"])} for k, v in sorted(deps.items(), key=lambda kv: -kv[1]["n"])], os.path.join(PUB, "departments.json"))

flags.sort(key=lambda f: (list(KINDS).index(f["kind"]), -(f.get("value") or 0)))
dump({"kinds": KINDS, "note": "Patterns in published data. Each lists the records it rests on. A pattern is not a finding of wrongdoing; most have lawful explanations.",
      "thresholds": [{"from": t[0], "value": t[1], "text": t[2], "url": t[3]} for t in THRESHOLDS], "flags": flags}, os.path.join(PUB, "flags.json"))

dump({"built": NOW, "warnings": (BD or {}).get("warnings", []) + [f"eTender portal: {len((ET or {}).get('gaps', []))} pages could not be read this run"] * bool((ET or {}).get("gaps")), "tables": tables, "counts": {"suppliers": len(index), "flags": len(flags), "tenders": len(tender), **{k: v["n"] for k, v in tables.items()}},
      "buckets": BUCKETS, "shard": SHARD, "et_shard": 2000, "muni": {"slug": MUNI, "label": M["label"], "code": M.get("code"), "category": M["category"]},
      "registers": {"cipc": "https://www.bizportal.gov.za/", "csd": "https://secure.csd.gov.za/", "restricted": "https://ocpo.treasury.gov.za/RestrictedSupplier/RestrictedSuppliersReport.pdf",
                    "etenders": "https://www.etenders.gov.za/"}}, os.path.join(PUB, "money.json"))
if REJECTED: print(f"money: {sum(REJECTED.values())} rows name no supplier (text that is not a name), e.g. {list(REJECTED)[:5]}")
print("money:", {k: v["n"] for k, v in tables.items()}, "suppliers", len(index), "flags", collections.Counter(f["kind"] for f in flags), "tenders", len(tender))
