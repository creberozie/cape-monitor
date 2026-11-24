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

CACHE = os.path.join(HERE, "cache", "metro", "money")
PUB = os.path.join(ROOT, "public", "data", "metro", "money")
NOW = now()
SHARD = 5000
BUCKETS = 128

# ---------------------------------------------------------------- thresholds (verified; cited in the flag text)
# Municipal Supply Chain Management Regulations, reg. 12 and 19 (GN 868 of 30 May 2005): competitive bidding above R200 000 (VAT incl.).
# Amended by GN 4198, Government Gazette 49863, 14 December 2023: metropolitan municipalities R750 000 (VAT incl.), from publication.
THRESHOLDS = [("2023-12-14", 750000, "R750 000 (VAT incl.) for metros since 14 Dec 2023: MFMA SCM Regulations reg. 12, as amended by GN 4198, GG 49863",
               "https://www.gov.za/sites/default/files/gcis_document/202312/49863gon4198.pdf"),
              ("0000-00-00", 200000, "R200 000 (VAT incl.) before 14 Dec 2023: MFMA SCM Regulations reg. 12 (GN 868 of 2005)",
               "https://www.gov.za/documents/notices/local-government-municipal-finance-management-act-regulations-supply-chain-1")]
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
from names import norm, SUFFIX


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
class Registry:
    def __init__(self): self.by = {}
    def get(self, raw):
        k = norm(raw)
        if len(k) < 3: return None
        sid = re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")[:60]
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
                if (val or bud) and str(r.get("Reason") or "").startswith(("Award", "Preferred", "Expansion", "Deviation", "Amendment")) and r.get("Decision_Code") in ("Approved", "Partial Award", "Recommended to CM - Approved"):
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

# ================================================================ 3. Bids received at City tender openings (City PDF registers)
BD = load("city-bids")
bids, bid_tenders = [], collections.defaultdict(list)
if BD:
    for t in BD["tenders"]:
        for b in t["bids"]:
            if b["price"] is not None and b["price"] < 1000: b["price"] = None   # a stray number (points, serial) rather than a price; the text stays
        prices = [b["price"] for b in t["bids"] if b["price"]]
        lo = min(prices) if prices else None
        for b in t["bids"]:
            s = REG.get(b["bidder"]); sid = s["id"] if s else None
            i = len(bids)
            if s:
                s["refs"]["bids"].append(i); s["n_bids"] += 1
                if t.get("closing"): s["years"].add(t["closing"][:4])
            rank = (sorted(prices).index(b["price"]) + 1) if b["price"] and prices else None
            bids.append([t.get("closing"), t["ref"], t["description"], b["n"], b["bidder"], b["price_text"], b["price"], rank, len(t["bids"]),
                         " / ".join(b["hdi"]), sid, t["doc"]])
            bid_tenders[t["ref"]].append(i)
    table("bids", BD["title"], [["closing", "Closing date"], ["ref", "Tender reference"], ["desc", "Description"], ["n", "Serial no."], ["bidder", "Bidder as published"],
          ["price_text", "Price as published"], ["price", "Price (parsed, R)"], ["rank", "Price rank (1 = lowest)"], ["n_bids", "Bids on this tender"],
          ["hdi", "HDI points claimed"], ["sup", "Supplier"], ["doc", "Register (PDF)"]], bids, "City of Cape Town: Tenders received", BD["url"], BD["retrieved"],
          "Read from the City's monthly 'Receiving / Opening of Tenders' registers. Prices are as read out at the opening, before evaluation; "
          "'Various Rates' means a rates-based bid with no single total.")

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
                        win, bidders, t.get("id")])
        et_detail[i] = t
    table("etenders", ET["title"], [["published", "Published"], ["number", "Tender number"], ["buyer", "Organ of state"], ["type", "Type"], ["category", "Category"],
          ["desc", "Description"], ["status", "Status on portal"], ["closing", "Closing"], ["province", "Province"], ["official", "Contact person (buyer)"],
          ["email", "Contact e-mail (buyer)"], ["awards", "Awarded to (amount as published)"], ["award_date", "Award date"], ["n_bidders", "Bidders listed"],
          ["sup", "Winning suppliers"], ["bidders", "Bidding suppliers"], ["portal_id", "Portal record"]], et_rows, "National Treasury eTender Portal",
          ET["url"], ET["retrieved"], "Every tender a Western Cape buyer (any sphere) placed on the national portal, with briefing details, documents, bidders and awards as published.")
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

# ================================================================ tender dossiers: one entry per tender reference, joining every source
def ref_key(r): return re.sub(r"^0+", "", re.sub(r"\s", "", str(r or "")).upper())
tender = collections.defaultdict(lambda: {"awards": [], "bids": [], "et": [], "docs": []})
for i, a in enumerate(awards): tender[ref_key(a[1])]["awards"].append(i)
for ref, idx in bid_tenders.items(): tender[ref_key(ref)]["bids"] += idx
for i, r in enumerate(et_rows):
    m = re.search(r"\b(\d{1,3}[A-Z]/20\d\d/\d\d)\b", str(r[1] or "").upper().replace(" ", ""))
    if m and "CAPE TOWN" in str(r[2] or "").upper(): tender[ref_key(m.group(1))]["et"].append(i)
for ref, idx in docs_by_ref.items(): tender[ref_key(ref)]["docs"] += idx
tender = {k: v for k, v in tender.items() if k}
buckets = collections.defaultdict(dict)
for k, v in tender.items(): buckets[bucket(k)][k] = {x: y for x, y in v.items() if y}
for b, v in buckets.items(): dump(v, os.path.join(PUB, "tender", f"{b}.json"))

# ================================================================ pattern flags
def flag(kind, title, text, records, subjects, value=None, basis=None):
    flags.append({"id": f"{kind}-{len(flags)}", "kind": kind, "title": title, "text": text, "records": records, "subjects": subjects,
                  **({"value": value} if value is not None else {}), **({"basis": basis} if basis else {})})

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
}

# repeat winners: share of a directorate's RFQ orders (count and value) going to one supplier
by_dir = collections.defaultdict(lambda: collections.defaultdict(list))
for i, r in enumerate(rfq):
    if r[8] and not r[10]: by_dir[r[2]][r[8]].append(i)
for d, sup in by_dir.items():
    total_n = sum(len(v) for v in sup.values()); total_v = sum(float(rfq[i][7] or 0) for v in sup.values() for i in v)
    if total_n < 200: continue
    for sid, idx in sup.items():
        v = sum(float(rfq[i][7] or 0) for i in idx)
        if len(idx) >= 50 and (len(idx) / total_n >= 0.05 or (total_v and v / total_v >= 0.05)):
            flag("repeat", f"{REG.by[sid]['names'].most_common(1)[0][0]}: {len(idx):,} quotation orders from {d}",
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
                 f"{len(win)} quotation orders from {d} for '{g}', each below and together above the competitive-bidding threshold of the day ({T[2]}).",
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
    ok = ("Approved", "Partial Award", "Recommended to CM - Approved")
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
    if str(a[3] or "").startswith(("Award", "Preferred")) and a[4] in ("Approved", "Partial Award"):
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
         f"Both appear on {n} of the City's published bid-opening registers. Per the published award decisions, {na} won {wa} and {nb} won {wb} of these.",
         recs, [["supplier", a], ["supplier", b]])

# award not to the lowest price read out (80/20 and 90/10 preference points can lawfully change the order)
for ref, idx in bid_tenders.items():
    k = ref_key(ref); prices = [(bids[i][6], bids[i][10], i) for i in idx if bids[i][6]]
    if len(prices) < 2 or not winners.get(k): continue
    lo = min(p[0] for p in prices)
    for p, sid, i in prices:
        if sid in winners[k] and p > lo * 1.10:
            flag("notlowest", f"Tender {ref}: awarded bidder priced {p / lo - 1:.0%} above the lowest",
                 f"Price read out at opening R{p:,.0f}; lowest R{lo:,.0f}. Preference points (80/20 or 90/10), functionality and responsiveness lawfully affect the award; "
                 "the evaluation report is not published here.", [["bids", j] for j in idx] + [["awards", a] for a in by_ref.get(k, [])],
                 [["tender", k], ["supplier", sid]], p - lo)

# the same buyer official on several eTender awards to one supplier
off = collections.defaultdict(list)
for i, r in enumerate(et_rows):
    if r[9] and r[14]:
        for s in r[14]: off[(str(r[9]).strip().upper(), str(r[2]), s)].append(i)
for (o, buyer, sid), idx in off.items():
    if len(idx) >= 3:
        flag("official", f"{o.title()} ({buyer}): contact person on {len(idx)} awards to {REG.by[sid]['names'].most_common(1)[0][0]}",
             "The buyer's contact person named on the eTender portal for each of these awards to the same supplier.", [["etenders", i] for i in idx],
             [["supplier", sid], ["official", o], ["department", buyer]])

# shared contact numbers between differently named companies (eTender award records)
ph = collections.defaultdict(set)
for s in REG.by.values():
    for p in s["phones"]:
        if len(p) == 9 and len(set(p)) > 2: ph[p].add(s["id"])
for p, sids in ph.items():
    if len(sids) >= 2:
        recs = [["etenders", i] for s in sids for i in REG.by[s]["refs"]["et"]]
        flag("phone", f"{len(sids)} companies share the contact number ending {p[-4:]}",
             "Award records on the eTender portal give the same contact number for these differently named companies: " + "; ".join(REG.by[s]["names"].most_common(1)[0][0] for s in sorted(sids)) + ".",
             recs, [["supplier", s] for s in sorted(sids)])

# single-bid tenders, grouped by winner
single = collections.defaultdict(list)
for ref, idx in bid_tenders.items():
    if len(idx) == 1:
        for s in winners.get(ref_key(ref), ()) or ([bids[idx[0]][10]] if bids[idx[0]][10] else []):
            single[s].append(idx[0])
for sid, idx in single.items():
    if len(idx) >= 2 and sid in REG.by:
        flag("single", f"{REG.by[sid]['names'].most_common(1)[0][0]}: sole bidder on {len(idx)} City tenders", "Tenders where the published opening register lists one bid only.",
             [["bids", i] for i in idx], [["supplier", sid]])

for f in flags:
    for kind, sid in f["subjects"]:
        if kind == "supplier" and sid in REG.by: REG.by[sid].setdefault("flags", []).append(f["id"])

# ================================================================ write suppliers, departments, flags
active = [s for s in REG.by.values() if any(s["refs"].values())]
index = []
prof = collections.defaultdict(dict)
cob = collections.defaultdict(collections.Counter)
for (a, b), n in pairs.items(): cob[a][b] = n; cob[b][a] = n
for s in active:
    yrs = sorted(s["years"])
    index.append([s["id"], s["names"].most_common(1)[0][0], len(s["refs"]["awards"]), round(s["award_value"]), len(s["refs"]["rfq"]), round(s["rfq_value"]),
                  len(s["refs"]["bids"]), len(s["refs"]["et"]), len(s["refs"]["land"]), yrs[0] if yrs else None, yrs[-1] if yrs else None, len(s.get("flags", [])), round(s["award_budget"])])
    prof[bucket(s["id"])][s["id"]] = {
        "names": s["names"].most_common(), "refs": {k: v for k, v in s["refs"].items() if v}, "phones": sorted(s["phones"]), "contacts": sorted(s["contacts"]),
        "flags": s.get("flags", []), "cobid": cob[s["id"]].most_common(30)}
index.sort(key=lambda r: -(r[3] + r[5]))
dump({"fields": ["id", "name", "awards", "award_value", "rfq", "rfq_value", "bids", "etenders", "land", "first", "last", "flags", "award_budget"], "rows": index}, os.path.join(PUB, "suppliers.json"))
for b, v in prof.items(): dump(v, os.path.join(PUB, "sup", f"{b}.json"))

deps = collections.defaultdict(lambda: {"n": 0, "value": 0.0, "years": collections.Counter(), "sup": collections.Counter(), "src": set()})
for i, r in enumerate(rfq):
    v = 0 if r[10] else float(r[7] or 0)
    d = deps["City of Cape Town: " + str(r[2] or "Unassigned").strip().title()]; d["n"] += 1; d["value"] += v; d["src"].add("rfq")
    d["years"][str(r[0] or "")[:4]] += v; d["sup"][r[8]] += v
for i, r in enumerate(et_rows):
    d = deps[str(r[2] or "?")]; d["n"] += 1; d["src"].add("etenders")
    for s in r[14]: d["sup"][s] += 1
dump([{"name": k, "n": v["n"], "value": round(v["value"]), "years": sorted(v["years"].items()), "top": [[s, round(x)] for s, x in v["sup"].most_common(15) if s],
       "sources": sorted(v["src"])} for k, v in sorted(deps.items(), key=lambda kv: -kv[1]["n"])], os.path.join(PUB, "departments.json"))

flags.sort(key=lambda f: (list(KINDS).index(f["kind"]), -(f.get("value") or 0)))
dump({"kinds": KINDS, "note": "Patterns in published data. Each lists the records it rests on. A pattern is not a finding of wrongdoing; most have lawful explanations.",
      "thresholds": [{"from": t[0], "value": t[1], "text": t[2], "url": t[3]} for t in THRESHOLDS], "flags": flags}, os.path.join(PUB, "flags.json"))

dump({"built": NOW, "tables": tables, "counts": {"suppliers": len(index), "flags": len(flags), "tenders": len(tender), **{k: v["n"] for k, v in tables.items()}},
      "buckets": BUCKETS, "shard": SHARD, "et_shard": 2000,
      "registers": {"cipc": "https://www.bizportal.gov.za/", "csd": "https://secure.csd.gov.za/", "restricted": "https://www.treasury.gov.za/ocpo/",
                    "etenders": "https://www.etenders.gov.za/"}}, os.path.join(PUB, "money.json"))
print("money:", {k: v["n"] for k, v in tables.items()}, "suppliers", len(index), "flags", collections.Counter(f["kind"] for f in flags), "tenders", len(tender))
