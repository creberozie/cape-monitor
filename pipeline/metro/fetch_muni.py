"""Money sources for a municipality other than Cape Town (MUNI=stellenbosch). Every record keeps its source link, publication date
and retrieval date. Lands in pipeline/cache/metro/muni/<slug>/:

  docs.json         the municipality's document index (WordPress REST, post type stb_document), per procurement category, with the file
                    each document links to
  muni-awards.json  tenders awarded: rows read from the monthly 'Tenders awarded' registers (PDF text; scanned ones by OCR)
  muni-fq.json      formal written price quotations and RFQs awarded: rows from the monthly quotation award registers
  muni-bids.json    bids read out at tender openings: rows from the bid-opening registers, which are scanned images, read by OCR (tesseract)
  etenders.json     the national eTender portal records of this buyer, filtered from the metro eTender archive (same schema)
  finance.json      National Treasury Municipal Money (municipaldata.treasury.gov.za): budget against actual, unauthorised, irregular,
                    fruitless and wasteful expenditure
  audit.json        Auditor-General audit opinions per year (Treasury's audit_opinions data set, with the link to each audit report)
  restricted.json   National Treasury Restricted Supplier and Tender Defaulter Report, and the Register for Tender Defaulters

Text recognition: a register whose PDF has no text layer is rendered at 300 dpi, turned upright with tesseract's orientation check,
and read word by word. Rows keep the OCR confidence; rows below MIN_CONF, and handwritten registers, are counted, not kept.
Run: MUNI=stellenbosch python3 -I pipeline/metro/fetch_muni.py [docs awards bids etenders finance restricted] [--refresh]"""
import json, os, re, sys, time, html, shutil, datetime, subprocess, tempfile, urllib.parse, urllib.request, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import HERE, now, dump
from muni import cfg, is_buyer, ref_key

M = cfg()
CACHE = M["cache"]; PDFS = os.path.join(CACHE, "pdf"); os.makedirs(PDFS, exist_ok=True)
REFRESH = "--refresh" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (compatible; cape-monitor/2.0; public-records index)"}
log = lambda *a: print(*a, flush=True)
MIN_CONF = 60          # mean tesseract word confidence a bidder name needs to be kept
DPI = 400              # 400 dpi and page segmentation mode 4 (one column of rows) read the registers' table best in tests
OCR_BUDGET = int(os.environ.get("OCR_MINUTES", "40")) * 60   # per run; registers not read in time are read on the next run


def http(url, tries=4, timeout=180):
    err = None
    for k in range(tries):
        try:
            u = urllib.parse.quote(url, safe=":/?&=%#+,;@")
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout) as r: return r.read()
        except Exception as e:
            err = e
            if getattr(e, "code", 0) == 404: break
            time.sleep(3 * (k + 1) ** 2)
    raise RuntimeError(f"{url[:160]}: {err}")


def jget(url, **kw): return json.loads(http(url, **kw))


# ================================================================ 1. document index (Stellenbosch: WordPress REST API)
WP = "https://stellenbosch.gov.za/wp-json/wp/v2/"
# category slugs (stb_doc_category) per register kind; child categories (per year) are found through the API
KINDS = {"awards": ["tenders-awarded"], "fq": ["formal-quotations-awarded"], "rfq": ["request-for-quotations-awarded"],
         "bids": ["tender-opening"], "cancelled": ["tender-cancellations"], "scm": ["scm-reports"]}
RESOLVE = {"awards", "fq", "rfq", "bids"}   # kinds whose files are read


def categories():
    out, p = [], 1
    while True:
        d = jget(f"{WP}stb_doc_category?per_page=100&page={p}&_fields=id,slug,parent,count")
        out += d
        if len(d) < 100: return out
        p += 1


def docs():
    path = os.path.join(CACHE, "docs.json")
    old = {str(d["id"]): d for d in (json.load(open(path))["docs"] if os.path.exists(path) else [])}
    cats = categories(); by_slug = {c["slug"]: c for c in cats}
    kids = {}
    for c in cats: kids.setdefault(c["parent"], []).append(c)
    def tree(cid):
        out = [cid]
        for k in kids.get(cid, []): out += tree(k["id"])
        return out
    found = {}
    for kind, slugs in KINDS.items():
        for s in slugs:
            if s not in by_slug: log("docs: category missing on the site:", s); continue
            for cid in tree(by_slug[s]["id"]):
                p = 1
                while True:
                    d = jget(f"{WP}stb_document?stb_doc_category={cid}&per_page=100&page={p}&_fields=id,date,modified,title,link,stb_doc_category")
                    for x in d:
                        k = str(x["id"])
                        if k in found: continue
                        found[k] = {**old.get(k, {}), "id": x["id"], "kind": kind, "published": x["date"][:10], "modified": x["modified"][:10],
                                    "title": html.unescape(re.sub(r"<[^>]+>", "", x["title"]["rendered"])).strip(), "page": x["link"]}
                    if len(d) < 100: break
                    p += 1
    # the file behind each document: the first download button on its page (a published file does not change, so this is asked once)
    todo = [d for d in found.values() if d["kind"] in RESOLVE and not d.get("file")]
    def res(d):
        try:
            h = http(d["page"], tries=3).decode("utf-8", "replace")
            m = re.search(r'class="btn stb-doc-dl" href="([^"]+)"', h)
            return d, html.unescape(m.group(1)) if m else None
        except Exception as e: return d, None
    with cf.ThreadPoolExecutor(4) as ex:
        for d, f in ex.map(res, todo):
            if f: d["file"] = f
    out = sorted(found.values(), key=lambda d: d["published"], reverse=True)
    dump({"id": "docs", "title": f"{M['label']}: procurement documents", "url": M["site"], "api": WP + "stb_document", "retrieved": now(), "docs": out},
         path)
    return f"{len(out)} documents; " + ", ".join(f"{k} {sum(1 for d in out if d['kind'] == k)}" for k in KINDS)


# ================================================================ 2. reading files: text layer, else OCR
def local(url):
    key = re.sub(r"[^A-Za-z0-9.]+", "_", urllib.parse.unquote(url.split("/uploads/", 1)[-1]))[-150:]
    return os.path.join(PDFS, key)


def fetch_file(url):
    f = local(url)
    if not os.path.exists(f):
        b = http(url)
        if url.lower().endswith(".pdf") and not b.startswith(b"%PDF"): raise RuntimeError("not a PDF")
        open(f + ".part", "wb").write(b); os.replace(f + ".part", f)
    return f


def pdf_text(url):
    f = fetch_file(url); t = f + ".txt"
    if not os.path.exists(t): subprocess.run(["pdftotext", "-layout", f, t], check=True, timeout=300)
    return open(t, encoding="utf-8", errors="replace").read()


def ocr_pages(url):
    """[(page, [words])] where a word is {x, y, w, h, conf, text, line}; pages are turned upright first. Cached as JSON next to the PDF."""
    f = fetch_file(url); out = f + f".ocr-{DPI}-4c.json"   # the settings are in the name: changing them reads the scans again
    if os.path.exists(out): return json.load(open(out))
    from PIL import Image
    pages = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-gray", "-png", f, os.path.join(tmp, "p")], check=True, timeout=600)
        for img in sorted(os.listdir(tmp), key=lambda s: int(re.sub(r"\D", "", s) or 0)):
            p = os.path.join(tmp, img)
            osd = subprocess.run(["tesseract", p, "-", "--psm", "0"], capture_output=True, text=True, timeout=120).stdout
            rot = re.search(r"Rotate:\s*(\d+)", osd)
            if rot and int(rot.group(1)): Image.open(p).rotate(-int(rot.group(1)), expand=True).save(p)
            tsv = subprocess.run(["tesseract", p, "-", "--psm", "4", "tsv"], capture_output=True, text=True, timeout=300).stdout
            words = []
            for ln in tsv.splitlines()[1:]:
                c = ln.split("\t")
                if len(c) < 12 or not c[11].strip() or float(c[10]) < 0: continue
                words.append({"x": int(c[6]), "y": int(c[7]), "w": int(c[8]), "h": int(c[9]), "conf": float(c[10]), "text": c[11],
                              "line": f"{c[2]}.{c[3]}.{c[4]}"})
            # a second, independent reading of every amount: the cell cropped and read as one line of digits only. A price is
            # parsed later only when both readings have the same digits.
            im = Image.open(p); W = im.width
            for w in words:
                if re.fullmatch(r"-?R\S*\d\S*", w["text"]) and w["x"] > W * 0.35:
                    line = [x for x in words if x["line"] == w["line"] and x["x"] >= w["x"] and x["x"] < w["x"] + int(W * 0.22) and re.fullmatch(r"-?R?[\d.,]*\d[\d.,]*\.?", x["text"])]
                    x1 = max(x["x"] + x["w"] for x in line); y0 = min(x["y"] for x in line); y1 = max(x["y"] + x["h"] for x in line)
                    pad = int(12 * DPI / 300); crop = os.path.join(tmp, "c.png")
                    im.crop((max(0, w["x"] - pad), max(0, y0 - pad), min(W, x1 + pad), min(im.height, y1 + pad))).save(crop)
                    w["alt"] = subprocess.run(["tesseract", crop, "-", "--psm", "7", "-c", "tessedit_char_whitelist=R0123456789 ,."], capture_output=True, text=True, timeout=60).stdout.strip()
            pages.append(words)
    json.dump(pages, open(out, "w"))
    return pages


def ocr_text(pages):
    """plain text from OCR words, one line per tesseract line, words spaced by their position (so the layout parser can read columns)"""
    out = []
    for words in pages:
        lines = {}
        for w in words: lines.setdefault(w["line"], []).append(w)
        for ws in sorted(lines.values(), key=lambda ws: min(w["y"] for w in ws)):
            s = ""
            for w in sorted(ws, key=lambda w: w["x"]):
                col = w["x"] * 300 // (22 * DPI)   # about 22 px per character column at 300 dpi
                s += (" " * max(1 if s else 0, col - len(s))) + w["text"]
            out.append(s)
        out.append("\f")
    return "\n".join(out)


# ================================================================ 3. award registers (tenders, formal quotations, RFQs)
DATE = r"(?:\d{1,2}[-/ ](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[-/ ](?:20)?\d\d|20\d\d[-/]\d\d[-/]\d\d|\d\d[-/]\d\d[-/]20\d\d)"
AMOUNT = r"R\s*\d{1,3}(?:[  ]?\d{3})*(?:[,.]\d{2})?"
LEVEL = r"(?:L\s?[1-8]|LEVEL\s?[1-8]|Level\s?[1-8]|NC|N/?C|Non[- ]?(?:compliant|contributor)|NON[- ]?COMPLIANT|NON[- ]?CONTRIBUTOR)"
REFRX = {"awards": r"B\s*/?\s*SM\s*\d{1,3}\s*/\s*\d\d", "fq": r"(?:FQ|PNQ)\s*/?\s*(?:SM)?\s*\d{1,3}\s*/\s*\d\d", "rfq": r"(?:RFQ|FQ)\s*/?\s*(?:SM)?\s*\d{1,3}\s*/\s*\d\d"}
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
TOKEN = re.compile(r"\S+(?: \S+)*")


def iso(d):
    d = d.strip()
    m = re.match(r"(\d{1,2})[-/ ]([A-Za-z]{3})[a-z]*[-/ ]((?:20)?\d\d)$", d)
    if m: y = int(m.group(3)); return f"{y + 2000 if y < 100 else y:04d}-{MON[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"(20\d\d)[-/](\d\d)[-/](\d\d)$", d)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d\d)[-/](\d\d)[-/](20\d\d)$", d)
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def money(s):
    m = re.search(r"(\d{1,3}(?:[  ]?\d{3})*)(?:[,.](\d{2}))?", s or "")
    if not m: return None
    try: return float(re.sub(r"\D", "", m.group(1)) + ("." + m.group(2) if m.group(2) else ""))
    except ValueError: return None


DATE_SPLIT = r"(?:\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*-(?:20)?\d\d|20\d\d[-/]\d\d[-/]\d\d|\d\d[-/]\d\d[-/]20\d\d)"
SPLIT = r"(?:" + DATE_SPLIT + r"|" + AMOUNT + r"|\b" + LEVEL + r"\b|\bRATES\b|\bRates\b)"
HEADER_WORDS = re.compile(r"^(?:BID|NUMBER|BID NUMBER|DESCRIPTION|CLOSING|DATE|CLOSING DATE|SUCCESSFUL BIDDER|B-BBEE|B-BBEE STATUS|STATUS|LEVEL OF|CONTRIBUTOR|AMOUNT|APPROVED|"
                          r"AMOUNT APPROVED|DATE APPROVED|ESTIMATED|COMPLETION|COMPLETION /|DELIVERY|DELIVERY PERIOD|PERIOD|CIDB|LOCALITY|LOCAL|CONTENT|CAPITAL OR|OPERATIONAL|"
                          r"B-BBEE STATUS CLOSING|STATUS LEVEL|OF|Awarded to.*|Description of FQ|FQ No|Closing Date|Award Date|Amount|BBBEE|Locality)$", re.I)
COMPANY_END = re.compile(r"(?:\(PTY\)|PTY|LTD|LTD\.|LIMITED|CC|INC|INC\.|INCORPORATED|JV|NPC|SOC)$", re.I)


def chunks(line):
    """[(x, text)]: runs of text separated by two or more spaces, with dates, amounts and B-BBEE levels split off as their own pieces"""
    out = []
    for m in re.finditer(r"\S+(?: \S+)*", line):
        x, t = m.start(), m.group(0)
        pos = 0
        for p in re.finditer(SPLIT, t):
            if p.start() > pos and t[pos:p.start()].strip(): out.append((x + pos, t[pos:p.start()].strip()))
            out.append((x + p.start(), p.group(0).strip())); pos = p.end()
        if t[pos:].strip(): out.append((x + pos + len(t[pos:]) - len(t[pos:].lstrip()), t[pos:].strip()))
    return out


def classify(t):
    if re.fullmatch(DATE, t): return "date"
    if re.fullmatch(AMOUNT, t) or re.fullmatch(r"(?i)rates?(?: based)?|as per rates|various rates", t): return "amount"
    if re.fullmatch(LEVEL + r"|[1-8]", t): return "level"
    if re.fullmatch(r"(?i)yes|no|n/?a|capital|operational|opex|capex|\d[A-Z]{2}\d?(?: or higher)?|\d{1,2}[A-Z]{1,2}(?: ?PE)?|[1-9](?:GB|CE|EB|EP|ME)\b.*", t): return "flag"
    if HEADER_WORDS.match(t): return "header"
    return "text"


def parse_awards(text, kind):
    """Rows of an award register: [{ref, desc, closing, bidder, level, amount_text, amount, approved, completion, panel}].
    Layout (2019 to now): one tender per block that starts at its bid number. The description wraps in its column, beside the number or
    centred around it; then the closing date; then one or more successful bidders (panels list many), each with a B-BBEE level; then
    amount, date approved, completion and flags. The closing-date column is found from the header ('CLOSING' / 'Closing Date').
    A description belongs to the tender whose number sits in the same unbroken run of description lines; a run with no number in it
    continues the tender above. Bidders, amounts and dates belong to the tender above them."""
    rx = re.compile(r"^\s{0,14}(" + REFRX[kind] + r")\b")
    rows, carry, all_blocks = [], None, []   # carry: the last tender of the previous page (a panel list often runs onto the next page)
    for page in text.split("\f"):
        lines = page.splitlines()
        hx = None
        for l in lines[:25]:
            c = re.search(r"\bCLOSING\b|Closing Date", l, re.I)
            if c and hx is None: hx = c.start()
        anchors = [(i, re.sub(r"\s+", " ", m.group(1)).strip()) for i, l in enumerate(lines) for m in [rx.match(l)] if m]
        if not anchors: continue
        if hx is None:   # a page without the header: the closing-date column is where the first date on a numbered line sits
            for i, _ in anchors:
                d = next((x for x, t in chunks(lines[i]) if classify(t) == "date"), None)
                if d is not None: hx = d; break
        if hx is None: continue
        first = anchors[0][0]
        start = max([i for i in range(first) if re.search(r"CONTRIBUTOR|DESCRIPTION|SUCCESSFUL|APPROVED|DELIVERY|PERIOD\s*$|Awarded to|Award Date|CIDB", lines[i], re.I)] or [-1]) + 1
        blocks = {a: {"ref": r, "desc": [], "closing": None, "bidders": [], "amounts": [], "dates": [], "levels": []} for a, r in anchors}
        arow = [a for a, _ in anchors]
        if carry is not None: blocks[-1] = carry
        prev_of = lambda i: max([a for a in arow if a <= i] or [-1 if carry is not None else first])
        run, run_owner, pending = [], None, None
        def close_run():
            owner = run_owner if run_owner is not None else (max([a for a in arow if a < run[0][0]] or [None]) if run else None)
            if owner is None and run: owner = min([a for a in arow if a > run[0][0]] or [first])
            for _, t in run: blocks[owner]["desc"].append(t)
        for i in range(start, len(lines)):
            l = lines[i]
            if re.search(r"TENDERS? AWARDED|QUOTATIONS AWARDED|^\s*Page \d", l, re.I): continue
            m = rx.match(l)
            cs = chunks(l)
            if m:
                cs = [(x, t[len(m.group(1)):].strip()) if t.startswith(m.group(1)) else (x, t) for x, t in cs]
                cs = [(x, t) for x, t in cs if t]
            descs = [(x, t) for x, t in cs if classify(t) == "text" and x < hx - 1]
            if descs or m:
                if not run: run_owner = None
                if m and run_owner is None: run_owner = i
                elif m and run_owner is not None and run:   # a new number inside a run: the run so far belongs to the earlier number
                    close_run(); run, run_owner = [], i
                run += [(i, t) for _, t in descs]
            elif run:
                close_run(); run, run_owner = [], None
            prev = blocks[prev_of(i)]
            line_bidder = None
            for x, t in cs:
                k = classify(t)
                if k == "date":   # at the closing-date column: closing date; to its right: date approved, then completion
                    if x <= hx + 4:
                        if not prev["closing"]: prev["closing"] = iso(t)
                    else: prev["dates"].append(iso(t))
                elif k == "text" and x >= hx - 1 and line_bidder is None and len(re.sub(r"[^A-Za-z]", "", t)) >= 2 and not re.fullmatch(r"(?i)\d+ (?:years?|months?)", t):
                    p = pending[1] if pending and pending[0] == i - 1 else None
                    if (p is not None and not m and not p["level"] and len(t.split()) <= 4
                            and (re.match(r"(?i)t/a|trading|ta\b|&|and\b|\(|[a-z]", t) or not COMPANY_END.search(p["name"]))):
                        p["name"] += " " + t; line_bidder = p
                    else:
                        line_bidder = {"name": t, "level": None, "amount": None}; prev["bidders"].append(line_bidder)
                elif k == "level":
                    if line_bidder is not None and not line_bidder["level"]: line_bidder["level"] = t
                    elif prev["bidders"] and not prev["bidders"][-1]["level"]: prev["bidders"][-1]["level"] = t
                    else: prev["levels"].append(t)
                elif k == "amount":
                    if line_bidder is not None and not line_bidder["amount"]: line_bidder["amount"] = t
                    else: prev["amounts"].append(t)
            pending = (i, line_bidder) if line_bidder is not None else None
        if run: close_run()
        carry = blocks[arow[-1]]
        all_blocks += [b for a, b in blocks.items() if a != -1]
    for b in all_blocks:
        if not b["bidders"]: continue
        dates = [d for d in b["dates"] if d]
        rate_only = [bd["amount"] for bd in b["bidders"] if bd["amount"]] + b["amounts"]
        rates = bool(rate_only) and all(not re.search(r"\d", x) for x in rate_only)
        for k, bd in enumerate(b["bidders"]):
            amt = bd["amount"] or (b["amounts"][0] if b["amounts"] and (k == 0 or len(b["amounts"]) == 1) else None) or (rate_only[0] if rates else None)
            rows.append({"ref": b["ref"], "desc": re.sub(r"\s+", " ", " ".join(b["desc"])).strip(), "closing": b["closing"],
                         "bidder": re.sub(r"\s+", " ", bd["name"]).strip(" -"), "level": bd["level"] or (b["levels"][0] if b["levels"] else None),
                         "amount_text": amt, "amount": money(amt) if amt and re.search(r"\d", amt) else None,
                         "approved": dates[0] if dates else None, "completion": dates[1] if len(dates) > 1 else None, "panel": len(b["bidders"])})
    return rows


def awards():
    D = json.load(open(os.path.join(CACHE, "docs.json")))["docs"]
    out = {"awards": [], "fq": []}; read = []; failed = []
    t0 = time.time()
    for d in D:
        if d["kind"] not in ("awards", "fq", "rfq") or not d.get("file") or not d["file"].lower().endswith(".pdf"): continue
        if re.search(r"bid open|opening register|cancel|notice to", d["title"], re.I): continue   # registers filed under the wrong heading
        try:
            text = pdf_text(d["file"]); how = "text"
            if len(text.strip()) < 200:
                if time.time() - t0 > OCR_BUDGET and not os.path.exists(local(d["file"]) + f".ocr-{DPI}-4c.json"): read.append({**slimdoc(d), "how": "waiting for OCR", "rows": 0}); continue
                text = ocr_text(ocr_pages(d["file"])); how = "ocr"
            kind = "fq" if d["kind"] == "rfq" else d["kind"]
            rows = parse_awards(text, kind)
            if not rows and kind == "fq": rows = parse_awards(text, "rfq")
            if not rows and re.search(r"^\s*NONE\s*$", text, re.M): how += ", none awarded that month"
            for r in rows: r.update({"doc": d["file"], "doc_page": d["page"], "doc_title": d["title"], "published": d["published"], "how": how, "kind": d["kind"]})
            out["awards" if kind == "awards" else "fq"] += rows
            read.append({**slimdoc(d), "how": how, "rows": len(rows)})
        except Exception as e:
            failed.append({**slimdoc(d), "error": str(e)[:160]})
    # a register published twice (a 'revised' copy, a re-upload) gives the same rows: keep one, list every document that has it
    for k in out:
        seen = {}
        for r in out[k]:
            key = (ref_key(r["ref"]), r["bidder"].upper(), r["amount_text"] or "", r["approved"] or "")
            if key in seen: seen[key]["also_in"] = seen[key].get("also_in", []) + [r["doc"]]
            else: seen[key] = r
        out[k] = list(seen.values())
    warnings = [f"{x['title']}: no rows read (new layout?)" for x in read if not x["rows"] and x["how"] in ("text", "ocr")]
    for k, title in (("awards", "Tenders awarded"), ("fq", "Formal quotations and RFQs awarded")):
        dump({"id": f"muni-{k}", "title": f"{M['label']}: {title.lower()} (read from the monthly award registers)", "url": M["site"] + ("tenders-awarded/" if k == "awards" else "formal-quotations-awarded/"),
              "retrieved": now(), "rows": out[k], "documents": [x for x in read if (x["kind"] == "awards") == (k == "awards")], "failed": failed, "warnings": warnings},
             os.path.join(CACHE, f"muni-{k}.json"))
    return f"{len(out['awards'])} tender award rows, {len(out['fq'])} quotation award rows from {len(read)} registers ({sum(1 for x in read if x['how'] == 'ocr')} by OCR); {len(failed)} failed"


def slimdoc(d): return {k: d.get(k) for k in ("id", "kind", "title", "published", "page", "file")}


# ================================================================ 4. bid-opening registers (scanned: OCR)
def parse_register(pages):
    """One tender per register. Header: 'TENDER NUMBER B/SM 25/27: <description>', 'CLOSING DATE: 16 NOVEMBER 2026'. Then a table:
    serial number, NAME OF BIDDERS, TENDER PRICE, B-BBEE LEVEL, LOCALITY. Columns are taken from the header words' positions."""
    words = [w for p in pages for w in p]
    text = ocr_text(pages)
    ref = re.search(r"TENDER\s*(?:NUMBER|NO)[.:]?\s*(B\s*/?\s*SM\s*\d{1,3}\s*/\s*\d\d)", text, re.I)
    desc = re.search(r"TENDER\s*(?:NUMBER|NO)[.:]?\s*B\s*/?\s*SM\s*\d{1,3}\s*/\s*\d\d\s*[:\-]?\s*(.+?)(?:\n\s*(?:VENUE|CLOSING)|$)", text, re.I | re.S)
    cd = re.search(r"CLOSING\s*DATE\s*[:;]?\s*(\d{1,2})\s*([A-Za-z]+)\s*(20\d\d)", text, re.I)
    closing = None
    if cd and cd.group(2)[:3].lower() in MON: closing = f"{cd.group(3)}-{MON[cd.group(2)[:3].lower()]:02d}-{int(cd.group(1)):02d}"
    out = {"ref": re.sub(r"\s", "", ref.group(1)).upper().replace("B/SM", "B/SM ").replace("BSM", "B/SM ") if ref else None,
           "description": re.sub(r"\s+", " ", desc.group(1)).strip()[:400] if desc else "", "closing": closing, "bids": [], "unreadable": 0}
    px = DPI / 300   # pixel distances below are for 300 dpi
    for words in pages:
        lines = {}
        for w in words: lines.setdefault(w["line"], []).append(w)
        L = sorted(lines.values(), key=lambda ws: min(w["y"] for w in ws))
        price_x = level_x = name_x = None
        for ws in L:
            t = " ".join(w["text"] for w in ws).upper()
            if "BIDDER" in t and ("PRICE" in t or "AMOUNT" in t):
                for w in ws:
                    if re.match(r"(TENDER|TOTAL|BID)$", w["text"].upper()) and price_x is None and w["x"] > 600 * px: price_x = w["x"] - 40 * px
                    if re.match(r"PRICE|AMOUNT", w["text"].upper()) and price_x is None: price_x = w["x"] - 200 * px
                    if re.match(r"B-?BBEE|LEVEL|STATUS", w["text"].upper()) and level_x is None and (price_x is None or w["x"] > price_x + 100 * px): level_x = w["x"] - 40 * px
                    if w["text"].upper() == "NAME" and name_x is None: name_x = w["x"] - 60 * px
        if price_x is None: continue
        for ws in L:
            ws = sorted(ws, key=lambda w: w["x"])
            ws = [w for w in ws if not re.fullmatch(r"[|\[\](){}_\-—=~:;.,'\"‘’“”]+", w["text"])]   # table rules read as punctuation
            if not ws or not re.fullmatch(r"[\[\(|/'\"‘]*\d{1,3}[\.|)\]]*", ws[0]["text"]) or ws[0]["x"] > (name_x or 400 * px): continue
            n = int(re.sub(r"\D", "", ws[0]["text"]))
            last = out["bids"][-1]["n"] if out["bids"] else 0
            if n != last + 1 and str(n).endswith(str(last + 1)[-1]) and n > last + 1: n = last + 1   # '15' read for '5' (a table rule before the digit)
            name_w = [w for w in ws[1:] if w["x"] < price_x and re.search(r"[A-Za-z0-9&]", w["text"])]
            # trailing OCR noise after a name ('oe', '7', 'Oe'); a rand amount that strayed left belongs to the price
            spill = []
            while name_w and (re.fullmatch(r"R\d[\d ,.]*", name_w[-1]["text"]) or (re.fullmatch(r"[a-z]{1,2}|[A-Z][a-z]|\d{1,2}|[^A-Za-z0-9&()]+", name_w[-1]["text"]) and name_w[-1]["text"].upper() not in ("CC", "JV", "SA"))):
                w = name_w.pop()
                if w["text"].startswith("R"): spill.insert(0, w)
            right = spill + [w for w in ws if w["x"] >= price_x]
            price_w = [w for w in right if re.fullmatch(r"-?R?[\d.,]*\d[\d.,]*\.?|R", w["text"])]
            level_w = [w for w in right if w not in price_w]
            name = re.sub(r"^[|\[\](){}_\-—=~:;., ]+|[|\[\]{}_\-—=~:;., ]+$", "", " ".join(w["text"] for w in name_w))
            name = re.sub(r"\s*[|_=~]+\s*", " ", name).strip()
            conf = round(sum(w["conf"] for w in name_w) / len(name_w)) if name_w else 0
            pt = " ".join(w["text"] for w in price_w).strip(" |_-")
            alt = next((w.get("alt") for w in price_w if w.get("alt")), "")
            price = None
            # 'R44 117 759,23', 'R57 849.479,20', 'R61 088 367.22', 'R53 180000,00'. Parsed only when the second (digits-only) reading has
            # exactly the same digits; the decimal comma is taken from whichever reading shows one. Otherwise the text is kept, unparsed.
            dig = re.sub(r"\D", "", pt); adig = re.sub(r"\D", "", alt)
            if dig and dig == adig and len(dig) >= 4:
                pm = next((m for m in (re.fullmatch(r"-?R?\s?(\d[\d .]*?)[,.](\d\d)\.?", x.strip()) for x in (pt, alt)) if m), None)
                if pm: price = float(re.sub(r"\D", "", pm.group(1)) + "." + pm.group(2))
            lv = [x for x in " ".join(w["text"] for w in level_w).split() if re.fullmatch(r"(?i)L\d|[1-8]|N/?A|NC|NIA", x)]
            if conf < MIN_CONF or len(re.sub(r"[^A-Za-z]", "", name)) < 3:
                out["unreadable"] += 1; continue
            out["bids"].append({"n": n, "bidder": name, "price_text": pt or "", "price": price, "hdi": [lv[0].replace("NIA", "N/A")] if lv else [], "conf": conf})
    return out


def bids():
    D = json.load(open(os.path.join(CACHE, "docs.json")))["docs"]
    path = os.path.join(CACHE, "muni-bids.json")
    regs = [d for d in D if d["kind"] in ("bids", "awards") and d.get("file") and re.search(r"bid\s*open|opening\s*regist|bid\s*register", d["title"] + " " + d["file"], re.I)]
    tenders, status, failed = [], [], []
    t0 = time.time()
    for d in sorted(regs, key=lambda d: d["published"], reverse=True):   # newest first, so a time-limited run reads the latest registers
        try:
            text = pdf_text(d["file"])
            done = os.path.exists(local(d["file"]) + f".ocr-{DPI}-4c.json")
            if len(text.strip()) >= 200: how = "text"; pages = None
            elif not done and time.time() - t0 > OCR_BUDGET: status.append({**slimdoc(d), "how": "waiting for OCR", "bids": 0}); continue
            else: how = "ocr"; pages = ocr_pages(d["file"])
            if pages is None: status.append({**slimdoc(d), "how": "text layer (not a scan); not parsed", "bids": 0}); continue
            t = parse_register(pages)
            if not t["ref"]:
                m = re.search(r"B\s*[-_/]?\s*SM\s*[-_]?\s*(\d{1,3})\s*[-_/]\s*(\d\d)", d["title"] + " " + d["file"], re.I)
                if m: t["ref"] = f"B/SM {m.group(1)}/{m.group(2)}"
            t.update({"doc": d["file"], "doc_page": d["page"], "doc_title": d["title"], "published": d["published"], "how": "ocr"})
            if t["bids"]: tenders.append(t)
            status.append({**slimdoc(d), "how": "ocr", "bids": len(t["bids"]), "unreadable": t["unreadable"]})
        except Exception as e:
            failed.append({**slimdoc(d), "error": str(e)[:160]})
    # one register per tender: an addendum or re-upload repeats the opening; keep the copy that read the most bids
    best = {}
    for t in tenders:
        k = ref_key(t["ref"])
        if k not in best or len(t["bids"]) > len(best[k]["bids"]): best[k] = t
    tenders = list(best.values())
    for t in tenders:
        ns = [b["n"] for b in t["bids"]]
        t["total"] = None
        t["parse_complete"] = not t["unreadable"] and ns == list(range(1, len(ns) + 1))
    read = [s for s in status if s["how"] == "ocr"]
    warnings = []
    if read and sum(1 for s in read if not s["bids"]) / len(read) > 0.5:
        warnings.append(f"{sum(1 for s in read if not s['bids'])} of {len(read)} scanned registers gave no readable bids (handwritten, or a new layout?)")
    if os.path.exists(path):
        prev = sum(len(t["bids"]) for t in json.load(open(path)).get("tenders", []))
        cur = sum(len(t["bids"]) for t in tenders)
        if prev and cur < 0.8 * prev: warnings.append(f"OCR-read bids fell from {prev} to {cur}")
    for w in warnings: log("WARNING muni-bids:", w)
    dump({"id": "muni-bids", "title": f"{M['label']}: bids read out at tender openings (bid-opening registers, scanned; read by OCR)", "url": M["site"] + "tender-opening/",
          "retrieved": now(), "tenders": tenders, "registers": status, "failed": failed, "warnings": warnings, "min_conf": MIN_CONF,
          "method": "Scanned registers rendered at 300 dpi, turned upright and read with tesseract 5 (page segmentation mode 6). A bidder is kept when the mean confidence of the words in its name is at least "
                    f"{MIN_CONF}; prices are kept as read and parsed only when they read as R n nnn,nn. Check every OCR row against the scan, linked on each row."}, path)
    return f"{len(tenders)} tenders, {sum(len(t['bids']) for t in tenders)} bids from {len(read)} scanned registers; {sum(1 for s in status if s['how'] == 'waiting for OCR')} waiting; {len(failed)} failed"


# ================================================================ 5. eTender portal: this buyer's records from the metro archive
def etenders():
    src = os.path.join(HERE, "cache", "metro", "money", "etenders.json")
    if not os.path.exists(src): raise RuntimeError("metro eTender archive not built yet (run fetch_money.py etenders first)")
    E = json.load(open(src))
    keep = {k: t for k, t in E["tenders"].items() if is_buyer(t.get("organ_of_State")) or is_buyer(t.get("department"))}
    names = sorted({str(t.get("organ_of_State")) for t in keep.values()})
    near = sorted({str(t.get("organ_of_State")) for t in E["tenders"].values() if re.search(M["label"].split()[0], str(t.get("organ_of_State")), re.I)} - set(names))
    dump({**{k: v for k, v in E.items() if k != "tenders"}, "id": "etenders", "title": f"National eTender portal: tenders placed by {M['label']}",
          "buyer_names": names, "other_names_seen": near, "tenders": keep}, os.path.join(CACHE, "etenders.json"))
    return f"{len(keep)} of {len(E['tenders'])} Western Cape records; buyer names {names}; similar names left out: {near[:8]}"


# ================================================================ 6. National Treasury Municipal Money
MD = "https://municipaldata.treasury.gov.za/api/cubes/"
ITEMS = {"2900": "Total revenue (excluding capital transfers)", "4400": "Total expenditure", "3100": "Employee related costs", "3800": "Contracted services",
         "3400": "Inventory consumed", "4100": "Operational cost", "4500": "Surplus / (deficit)"}
ATYPES = {"ORGB": "Original budget", "ADJB": "Adjusted budget", "AUDA": "Audited actual"}


def finance():
    code = M["code"]
    uif = jget(f"{MD}uifwexp/facts?cut=demarcation.code:{code}&pagesize=1000")["data"]
    aud = jget(f"{MD}audit_opinions/facts?cut=demarcation.code:{code}&pagesize=1000")["data"]
    agg = jget(f"{MD}incexp_v2/aggregate?cut=demarcation.code:{code}|period_length.length:year&drilldown=financial_year_end.year|amount_type.code|item.code|item.label&aggregates=amount.sum&pagesize=20000", timeout=300)["cells"]
    model = jget(f"{MD}incexp_v2/model")["model"]
    rows = [{"year": c["financial_year_end.year"], "type": c["amount_type.code"], "type_label": ATYPES[c["amount_type.code"]], "item": c["item.code"], "label": c["item.label"], "amount": c["amount.sum"]}
            for c in agg if c["amount_type.code"] in ATYPES and c["item.code"] in ITEMS]
    ret = now()
    dump({"id": "finance", "title": "National Treasury Municipal Money: income and expenditure, budget against audited actual", "url": "https://municipalmoney.gov.za/profiles/municipality-" + code + "/",
          "api": MD + "incexp_v2", "data_updated": model.get("last_updated"), "retrieved": ret, "rows": rows,
          "uifw": {"title": "Unauthorised, irregular, fruitless and wasteful expenditure (notes to the audited annual financial statements)", "api": MD + "uifwexp", "retrieved": ret,
                   "rows": sorted([{"year": x["financial_year_end.year"], "item": x["item.code"], "label": x["item.label"], "amount": x.get("amount")} for x in uif], key=lambda r: (r["year"], r["item"]))}},
         os.path.join(CACHE, "finance.json"))
    dump({"id": "audit", "title": "Auditor-General audit outcomes (National Treasury audit_opinions data set)", "url": "https://municipalmoney.gov.za/profiles/municipality-" + code + "/",
          "api": MD + "audit_opinions", "agsa": "https://www.agsa.co.za/Reporting/MFMAReports.aspx", "retrieved": ret,
          "rows": sorted([{"year": x["financial_year_end.year"], "opinion": x["opinion.label"], "code": x["opinion.code"], "report": x.get("opinion.report_url")} for x in aud], key=lambda r: r["year"], reverse=True)},
         os.path.join(CACHE, "audit.json"))
    return f"{len(rows)} income/expenditure figures, {len(uif)} UIFW figures, {len(aud)} audit opinions"


# ================================================================ 7. National Treasury restricted suppliers and tender defaulters
RS = "https://ocpo.treasury.gov.za/RestrictedSupplier/RestrictedSuppliersReport.pdf"
TD = "https://www.treasury.gov.za/publications/other/Register%20for%20Tender%20Defaulters.pdf"
TD_PAGE = "https://www.treasury.gov.za/tenderinfo/default.aspx"


def parse_restricted(text):
    """'Restricted Supplier and Tender Defaulter Report': numbered entries; name, registration or ID number, type, reason, period, authority,
    each wrapped over several lines in fixed columns."""
    out = []; cur = None; cols = None
    for page in text.split("\f"):
        for l in page.splitlines():
            h = re.search(r"Name of Supplier", l)
            if h:
                cols = {"name": h.start(), "reg": l.find("Registration"), "type": l.find("Restriction Type"), "reason": l.find("Restriction Reason"),
                        "from": l.find("Period From"), "to": l.find("Period To"), "by": l.find("Authorized")}
                continue
            if not cols or re.search(r"^\s*(Page:|Restricted Supplier and Tender)", l) or not l.strip(): continue
            m = re.match(r"^\s*(\d{1,4})\s+(\S.*)$", l)
            if m and m.start(2) <= cols["name"] + 3:
                cur = {"n": int(m.group(1)), "name": [], "reg": [], "type": [], "reason": [], "from": "", "to": "", "by": []}; out.append(cur)
            if cur is None: continue
            for x, t in [(mm.start(), mm.group(0)) for mm in re.finditer(r"\S+(?: \S+)*", l)]:
                if m and x < cols["name"] - 1 and re.fullmatch(r"\d{1,4}", t): continue
                d = re.findall(r"20\d\d-\d\d-\d\d", t)
                if d and x >= cols["from"] - 15:
                    if not cur["from"]: cur["from"] = d[0]; d = d[1:]
                    if d: cur["to"] = d[0]
                    rest = re.sub(r"20\d\d-\d\d-\d\d", "", t).strip()
                    if rest: cur["by"].append(rest)
                    continue
                col = "by" if x >= cols["to"] + 8 else "reason" if x >= cols["reason"] - 2 else "type" if x >= cols["type"] - 2 else "reg" if x >= cols["reg"] - 2 else "name"
                cur[col].append(t)
    for r in out:
        for k in ("name", "reg", "type", "reason", "by"): r[k] = re.sub(r"\s+", " ", " ".join(r[k])).strip()
        if r["name"].startswith(f"{r['n']} "): r["name"] = r["name"][len(str(r["n"])) + 1:]   # the entry number runs into the name
    return out


def restricted():
    b = http(RS, timeout=300)
    if not b.startswith(b"%PDF"): raise RuntimeError("Treasury's restricted supplier report link does not return a PDF")
    p = os.path.join(CACHE, "restricted.pdf"); open(p, "wb").write(b)
    subprocess.run(["pdftotext", "-layout", p, p + ".txt"], check=True)
    text = open(p + ".txt", encoding="utf-8", errors="replace").read()
    gen = re.search(r"Generated on:\s*(20\d\d-\d\d-\d\d)", text)
    rows = parse_restricted(text)
    td = http(TD, timeout=300); tp = os.path.join(CACHE, "defaulters.pdf"); open(tp, "wb").write(td)
    subprocess.run(["pdftotext", "-layout", tp, tp + ".txt"], check=True)
    tdt = re.sub(r"\s+", " ", open(tp + ".txt", errors="replace").read()).strip()
    dump({"id": "restricted", "title": "National Treasury: Restricted Supplier and Tender Defaulter Report", "url": RS, "page": TD_PAGE, "generated": gen.group(1) if gen else None,
          "retrieved": now(), "rows": rows, "defaulters": {"url": TD, "text": tdt[:600], "none": bool(re.search(r"no Tender Defaulters", tdt, re.I))}},
         os.path.join(CACHE, "restricted.json"))
    return f"{len(rows)} restricted suppliers (report of {gen.group(1) if gen else '?'}); tender defaulters register: {'none listed' if re.search(r'no Tender Defaulters', tdt, re.I) else 'entries present'}"


if __name__ == "__main__":
    if M["slug"] == "cape-town": raise SystemExit("fetch_muni.py is for municipalities other than Cape Town; set MUNI")
    jobs = {"docs": docs, "awards": awards, "bids": bids, "etenders": etenders, "finance": finance, "restricted": restricted}
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    failed = []
    for name, fn in jobs.items():
        if only and name not in only: continue
        t = time.time()
        try: log(name, "→", fn(), f"({time.time() - t:.0f}s)")
        except Exception as e: failed.append(name); log(name, "FAILED", repr(e)[:300])
    json.dump({"failed": failed, "at": now()}, open(os.path.join(CACHE, "_status.json"), "w"))
    if len(failed) == len([j for j in jobs if not only or j in only]): sys.exit(1)
