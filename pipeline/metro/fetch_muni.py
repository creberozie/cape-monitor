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
         "bids": ["tender-opening"], "cancelled": ["tender-cancellations"], "open": ["open-tenders"], "fq_open": ["open-formal-quotations"],
         "rfq_open": ["request-for-quotations-open"], "rfq30": ["rfq-under-r30-000"], "scm": ["scm-reports"]}
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


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def ocr_done(url):
    f = local(url)
    if not os.path.exists(f): return False
    return os.path.exists(os.path.join(CACHE, "ocr", f"{sha256(f)}-{DPI}-4c.json")) or os.path.exists(f + f".ocr-{DPI}-4c.json")


def write_manifest():
    """files.sha256: one line per downloaded file and OCR result; the data workflow keys its cache on this file's hash"""
    lines = []
    for d in ("pdf", "ocr", "agenda"):
        for name in sorted(os.listdir(os.path.join(CACHE, d))) if os.path.isdir(os.path.join(CACHE, d)) else []:
            p = os.path.join(CACHE, d, name)
            if os.path.isfile(p) and not name.endswith((".part",)): lines.append(f"{sha256(p) if name.endswith('.pdf') else os.path.getsize(p)}  {d}/{name}")
    open(os.path.join(CACHE, "files.sha256"), "w").write("\n".join(lines) + "\n")


def fetch_file(url):
    f = local(url)
    if not os.path.exists(f):
        b = http(url)
        if url.lower().endswith(".pdf") and not b.startswith(b"%PDF"): raise RuntimeError("not a PDF")
        open(f + ".part", "wb").write(b); os.replace(f + ".part", f)
    return f


def upright_chars(page):
    """pdfplumber page keeping only characters set horizontally (upright, no rotation or skew in their matrix)"""
    return page.filter(lambda o: o.get("object_type") != "char" or (o.get("upright", True) and abs(o["matrix"][1]) < 1e-3 and abs(o["matrix"][2]) < 1e-3))


def text_without_rotated(pdf_path):
    """(layout text, number of rotated or skewed characters left out). Text set at an angle (stamps, watermarks, labels laid across a
    table) is not part of any row; pdftotext prints it into the columns it crosses."""
    import pdfplumber
    out, n = [], 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            n += sum(1 for c in page.chars if not (c.get("upright", True) and abs(c["matrix"][1]) < 1e-3 and abs(c["matrix"][2]) < 1e-3))
            out.append(upright_chars(page).extract_text(layout=True, x_density=5.5, y_density=13) or "")
    return "\f".join(out), n


def pdf_text(url):
    """layout text of a PDF (pdftotext); when the PDF has rotated or skewed text, the text is rebuilt from horizontal characters only and
    the number left out is kept next to it (.meta.json) for the sources manifest"""
    f = fetch_file(url); t = f + ".txt"; meta = f + ".meta.json"
    if not os.path.exists(t): subprocess.run(["pdftotext", "-layout", f, t], check=True, timeout=300)
    if not os.path.exists(meta):
        info = {"rotated_chars": 0}
        try:
            text, n = text_without_rotated(f)
            if n:
                open(t, "w", encoding="utf-8").write(text); info = {"rotated_chars": n, "how": "pdfplumber, horizontal characters only"}
        except Exception as e: info["error"] = str(e)[:120]
        json.dump(info, open(meta, "w"))
    return open(t, encoding="utf-8", errors="replace").read()


def pdf_meta(url):
    p = local(url) + ".meta.json"
    return json.load(open(p)) if os.path.exists(p) else {}


def ocr_pages(url):
    """[(page, [words])] where a word is {x, y, w, h, conf, text, line}; pages are turned upright first. Cached as JSON next to the PDF."""
    f = fetch_file(url)
    # OCR results are kept by the SHA-256 of the PDF itself (and the OCR settings): a file re-uploaded under another name is not read again,
    # and the data workflow's cache restores them by the same key
    os.makedirs(os.path.join(CACHE, "ocr"), exist_ok=True)
    out = os.path.join(CACHE, "ocr", f"{sha256(f)}-{DPI}-4c.json")
    legacy = f + f".ocr-{DPI}-4c.json"
    if not os.path.exists(out) and os.path.exists(legacy): shutil.copy(legacy, out)
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
                nxt = min((x for x in words if x["line"] == w["line"] and x["x"] > w["x"]), key=lambda x: x["x"], default=None)
                if w["x"] > W * 0.35 and (re.fullmatch(r"-?R\S*\d\S*", w["text"]) or (w["text"] in ("R", "-R") and nxt is not None and re.match(r"\d", nxt["text"]))):
                    line = [x for x in words if x["line"] == w["line"] and x["x"] >= w["x"] and x["x"] < w["x"] + int(W * 0.22) and (x is w or re.fullmatch(r"-?R?[\d.,]*\d[\d.,]*\.?", x["text"]))]
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
        award_col = hx is None and any(re.search(r"(?i)award date", l) for l in lines[:25])   # older quotation registers: one date column, the award date
        if hx is None:   # a page without the header: the closing-date column is where the first date on a numbered line sits
            for i, _ in anchors:
                d = next((x for x, t in chunks(lines[i]) if classify(t) == "date"), None)
                if d is not None: hx = d; break
        if hx is None: continue
        first = anchors[0][0]
        start = max([i for i in range(first) if re.search(r"CONTRIBUTOR|DESCRIPTION|SUCCESSFUL|APPROVED|DELIVERY|PERIOD\s*$|Awarded to|Award Date|CIDB", lines[i], re.I)] or [-1]) + 1
        blocks = {a: {"ref": r, "desc": [], "closing": None, "bidders": [], "offers": [], "amounts": [], "dates": [], "levels": []} for a, r in anchors}
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
                    if x <= hx + 4 and not award_col:
                        if not prev["closing"]: prev["closing"] = iso(t)
                    else: prev["dates"].append(iso(t))
                elif k == "text" and re.match(r"\d{1,2}\.\s", t):   # a numbered offer ('1. BEE Online Advisory'): an offer received, not the award; kept, marked
                    prev["offers"].append({"name": re.sub(r"^\d{1,2}\.\s*", "", t), "amount": None}); continue
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
        for o in b["offers"]:
            rows.append({"ref": b["ref"], "desc": re.sub(r"\s+", " ", " ".join(b["desc"])).strip(), "closing": b["closing"], "bidder": re.sub(r"\s+", " ", o["name"]).strip(" -"),
                         "level": None, "amount_text": None, "amount": None, "approved": None, "completion": None, "panel": 0, "status": "offer"})
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


def prefetch(docs, ocr=False):
    """download (and, with ocr=True, OCR the scanned ones) four at a time; newest first, within the run's OCR budget. Results are cached on disk."""
    t0 = time.time(); os.environ.setdefault("OMP_THREAD_LIMIT", "1")   # one thread per tesseract, four in parallel
    def one(d):
        try:
            text = pdf_text(d["file"])
            if ocr and len(text.strip()) < 200 and time.time() - t0 < OCR_BUDGET: ocr_pages(d["file"])
        except Exception as e: log("prefetch", d["file"][-80:], str(e)[:100])
    with cf.ThreadPoolExecutor(4) as ex: list(ex.map(one, sorted(docs, key=lambda d: d["published"], reverse=True)))


def awards():
    D = json.load(open(os.path.join(CACHE, "docs.json")))["docs"]
    out = {"awards": [], "fq": []}; read = []; failed = []
    prefetch([d for d in D if d["kind"] in ("awards", "fq", "rfq") and d.get("file", "").lower().endswith(".pdf")], ocr=True)
    t0 = time.time()
    for d in D:
        if d["kind"] not in ("awards", "fq", "rfq") or not d.get("file") or not d["file"].lower().endswith(".pdf"): continue
        if re.search(r"bid open|opening register|cancel|notice to", d["title"], re.I): continue   # registers filed under the wrong heading
        try:
            text = pdf_text(d["file"]); how = "text"
            if len(text.strip()) < 200:
                if not ocr_done(d["file"]): read.append({**slimdoc(d), "how": "waiting for OCR", "rows": 0}); continue
                text = ocr_text(ocr_pages(d["file"])); how = "ocr"
            if re.search(r"INVITATION\s+TO\s+BID", text.split("\f")[0], re.I) and re.search(r"(?i)TOTAL\s+BID\s+PRICE|NAME\s+OF\s+BIDDER|[MS]BD\s*\d", text.split("\f")[0]):
                read.append({**slimdoc(d), "how": "bid invitation, not an award register", "rows": 0}); continue   # the quotation pack itself, filed with the awards
            kind = "fq" if d["kind"] == "rfq" else d["kind"]
            rows = parse_awards(text, kind)
            if not rows and kind == "fq": rows = parse_awards(text, "rfq")
            if not rows and re.search(r"^\s*NONE\s*$", text, re.M): how += ", none awarded that month"
            if how == "ocr":
                # a register read by OCR: keep a row only when the name reads as a name; its amount is shown as read but not parsed
                # (it was read once; the bid-register check of two agreeing readings is not done for these yet)
                for r in rows:
                    r["amount"] = None; r["amount_note"] = "read by OCR; not parsed"
                    if not (re.fullmatch(r"[A-Za-z][A-Za-z0-9&'.,()/\- ]{2,}", r["bidder"]) and len(re.sub(r"[^A-Za-z]", "", r["bidder"])) >= 4):
                        r["status"] = "illegible"   # kept, marked: the name did not read cleanly
            for r in rows: r.update({"doc": d["file"], "doc_page": d["page"], "doc_title": d["title"], "published": d["published"], "how": how, "kind": d["kind"]})
            out["awards" if kind == "awards" else "fq"] += rows
            read.append({**slimdoc(d), "how": how, "rows": len(rows), **({"rotated_chars": pdf_meta(d["file"])["rotated_chars"]} if pdf_meta(d["file"]).get("rotated_chars") else {})})
        except Exception as e:
            failed.append({**slimdoc(d), "error": str(e)[:160]})
    name_warnings = []
    for k in out:
        out[k], w = check_names(out[k]); name_warnings += w
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
              "retrieved": now(), "rows": out[k], "documents": [x for x in read if (x["kind"] == "awards") == (k == "awards")], "failed": failed, "warnings": warnings,
              "parse_warnings": [w for w in name_warnings if (k == "awards") == bool(re.match(r"B", w["ref"] or ""))]},
             os.path.join(CACHE, f"muni-{k}.json"))
    return f"{len(out['awards'])} tender award rows, {len(out['fq'])} quotation award rows from {len(read)} registers ({sum(1 for x in read if x['how'] == 'ocr')} by OCR); {len(failed)} failed"


def slimdoc(d): return {k: d.get(k) for k in ("id", "kind", "title", "published", "page", "file")}


COMPANY = re.compile(r"\b(?:\(?PTY\)?|LTD|LIMITED|CC|INC|INCORPORATED|JV|JOINT VENTURE|NPC|SOC|ATTORNEYS|CONSULTING|ENGINEERS|TRADING|PROJECTS|HOLDINGS|"
                     r"ENTERPRISES?|SERVICES|SOLUTIONS|GROUP|PARTNERS(?:HIP)?|BANK|ASSOCIATES|CONSTRUCTION|CIVILS|T/A)\b", re.I)
DESCRIPTIVE = re.compile(r"\b(?:SUPPLY AND|DELIVERY OF|FOR A PERIOD|PERIOD ENDING|AS AND WHEN|MAINTENANCE OF|CONSTRUCTION OF|APPOINTMENT OF|PROVISION OF|"
                         r"INSTALLATION OF|UPGRADING OF|STELLENBOSCH MUNICIPALITY|WC024|ENDING 30|(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|"
                         r"OCTOBER|NOVEMBER|DECEMBER) 20\d\d)\b", re.I)


def name_problem(name):
    """why a bidder name read from a register is not a name (None when it reads as one): description text that strayed into the bidder
    column, a header word, or a fragment"""
    n = name.strip(); w = n.split()
    if len(w) > 12: return "too many words for a name"
    # a fragment in lower case ('of TENDER', 'on ZTD GROUP'), or OF / AND in capitals; capital ON, AT, IN start real names ('ON POINT ON TIME SOLUTIONS')
    if re.match(r"(?:of|and|for|to|in|with|at|on|by|from|as|including|ending|period)\b", n) or re.match(r"(?:OF|AND)\b", n): return "starts like a sentence fragment"
    if re.search(r"(?i)\bname of bidders?\b|\btender number\b|^number\b|…{3,}|\.{6,}", n): return "form or header text"
    if re.fullmatch(r"\(?[A-Z](?:\s[A-Z]){1,3}\)?", n): return "initials only"
    if DESCRIPTIVE.search(n) and not COMPANY.search(n): return "reads as tender description"
    if re.search(r"\bL\d(?:FOR|AND|OF)\b|\b\w+(?:FOR|AND)\s+A\s+PERIOD\b", n, re.I): return "columns run together"
    if len(re.sub(r"[^A-Za-z]", "", n)) < 3: return "too short"
    if not distinctive(n): return "only a company suffix"
    return None


SUFFIX_WORDS = {"PTY", "LTD", "LIMITED", "CC", "INC", "INCORPORATED", "JV", "NPC", "SOC", "T/A", "AND", "THE", "OF"}


def distinctive(name):
    return [w for w in re.findall(r"[A-Z0-9&'.]+", name.upper()) if w.strip("().") not in SUFFIX_WORDS and len(w) > 1]


def split_merged(name):
    """several company names printed on one line ('A (PTY) LTD B CC C (PTY) LTD'): split after each company suffix"""
    parts = [p.strip(" ,") for p in re.split(r"(?<=\bLTD)\s+|(?<=\bLIMITED)\s+|(?<=\bCC)\s+(?!T/A)|(?<=\bINC)\s+|(?<=\bINCORPORATED)\s+", name, flags=re.I) if p.strip(" ,")]
    return parts if len(parts) > 1 and all(not name_problem(p) for p in parts) else None


def check_names(rows):
    """Rows whose bidder text is not a name are taken out and listed as parse warnings. Several names run together on one line are split.
    Where the text contains a bidder name accepted elsewhere (two or more distinctive words), that name is kept, with a note.
    Returns (rows, warnings)."""
    out, bad = [], []
    for r in rows:
        why = None if r.get("status") else name_problem(r["bidder"])
        if not why: out.append(r); continue
        parts = split_merged(r["bidder"])
        if parts:
            out += [{**r, "bidder": p, "name_note": f"one of several names printed on one line: '{r['bidder']}'"} for p in parts]
            bad.append({"ref": r["ref"], "text": r["bidder"], "reason": why, "doc": r.get("doc"), "recovered": parts}); continue
        bad.append((r, why))
    known = sorted({re.sub(r"\s+", " ", x["bidder"].upper()).strip() for x in out if len(distinctive(x["bidder"])) >= 2}, key=len, reverse=True)
    warn = [b for b in bad if isinstance(b, dict)]
    for b in bad:
        if isinstance(b, dict): continue
        r, why = b; up = re.sub(r"\s+", " ", r["bidder"].upper())
        hit = next((k for k in known if re.search(r"(?<![A-Z0-9])" + re.escape(k) + r"(?![A-Z0-9])", up)), None)
        warn.append({"ref": r["ref"], "text": r["bidder"], "reason": why, "doc": r.get("doc"), "recovered": [hit] if hit else []})
        if hit: out.append({**r, "bidder": hit, "name_note": f"name recovered from text mixed with the description: '{r['bidder']}'"})
        else: out.append({**r, "status": "unclear", "status_why": why})   # kept as printed, marked: not a supplier name
    return out, warn


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
    for pno, words in enumerate(pages, 1):
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
        # rows: each serial number at the left starts a row; every other word below the header and above the signature block joins the
        # row whose middle is nearest its own (OCR sometimes puts a row's price on a separate text line)
        head_y = max(w["y"] + w["h"] for ws in L for w in ws if "BIDDER" in " ".join(x["text"] for x in ws).upper() and ("PRICE" in " ".join(x["text"] for x in ws).upper() or "AMOUNT" in " ".join(x["text"] for x in ws).upper()))
        foot = [min(w["y"] for w in ws) for ws in L if min(w["y"] for w in ws) > head_y and re.search(r"\bNB\b|information read out|Names? and Signatures?|SCM Official|SCM PRA|opened and announced|evaluation process", " ".join(w["text"] for w in ws), re.I)]
        foot_y = min(foot) if foot else 10 ** 9
        body = [w for w in words if head_y < w["y"] + w["h"] / 2 < foot_y and not re.fullmatch(r"[|\[\](){}_\-—=~:;.,'\"‘’“”]+", w["text"])]
        anchors = sorted([w for w in body if re.fullmatch(r"[\[\(|/'\"‘]*\d{1,3}[\.|)\]]*", w["text"]) and w["x"] < (name_x if name_x is not None else 400 * px) + 40 * px], key=lambda w: w["y"])
        hgt = sorted(w["h"] for w in body)[len(body) // 2] if body else 40
        rows = {id(a): [] for a in anchors}
        for w in body:
            if any(w is a for a in anchors): continue
            cy = w["y"] + w["h"] / 2
            near = min(anchors, key=lambda a: abs(a["y"] + a["h"] / 2 - cy), default=None)
            if near is not None and abs(near["y"] + near["h"] / 2 - cy) < 2 * hgt and w["x"] > near["x"]: rows[id(near)].append(w)
        for a in anchors:
            ws = sorted(rows[id(a)], key=lambda w: (w["x"]))
            n = int(re.sub(r"\D", "", a["text"]))
            last = out["bids"][-1]["n"] if out["bids"] else 0
            if n != last + 1 and str(n).endswith(str(last + 1)[-1]) and n > last + 1: n = last + 1   # '15' read for '5' (a table rule before the digit)
            name_w = [w for w in ws if w["x"] < price_x and re.search(r"[A-Za-z0-9&]", w["text"])]
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
            AM = r"-?R\s?(\d[\d .]*?)[,.](\d\d)(?!\d)"
            m1 = re.search(AM, pt); m2 = re.search(AM, alt)
            lead = re.match(r"-?R\s?([\d .,]+)", pt)   # first reading without its decimal comma ('R5475070788')
            d1 = re.sub(r"\D", "", m1.group(1) + m1.group(2)) if m1 else re.sub(r"\D", "", lead.group(1)) if lead else ""
            d2 = re.sub(r"\D", "", m2.group(1) + m2.group(2)) if m2 else ""
            if d2 and d1 == d2 and len(d2) >= 4:
                m = m2 or m1; price = float(re.sub(r"\D", "", m.group(1)) + "." + m.group(2))
            lv = [x for x in " ".join(w["text"] for w in level_w).split() if re.fullmatch(r"(?i)L\d|[1-8]|N/?A|NC|NIA", x)]
            if re.search(r"NAME OF BIDDER", name, re.I): continue
            if conf < MIN_CONF or len(re.sub(r"[^A-Za-z]", "", name)) < 3:   # kept, marked: not legible enough to name a bidder or rank a price
                out["unreadable"] += 1
                if re.search(r"[A-Za-z0-9]", name + (pt or "")) and conf > 0:
                    out["bids"].append({"n": n, "bidder": name, "price_text": pt or "", "price": None, "hdi": [], "conf": conf, "page": pno, "status": "illegible"})
                continue
            out["bids"].append({"n": n, "bidder": name, "price_text": pt or "", "price": price, "hdi": [lv[0].replace("NIA", "N/A")] if lv else [], "conf": conf, "page": pno,
                                **({"price_alt": alt} if alt and alt != pt else {})})
    return out


def bids():
    D = json.load(open(os.path.join(CACHE, "docs.json")))["docs"]
    path = os.path.join(CACHE, "muni-bids.json")
    regs = [d for d in D if d["kind"] in ("bids", "awards") and d.get("file") and re.search(r"bid\s*open|opening\s*regist|bid\s*register", d["title"] + " " + d["file"], re.I)]
    tenders, status, failed = [], [], []
    prefetch(regs, ocr=True)
    t0 = time.time() - OCR_BUDGET   # the budget was spent in prefetch: only registers already read are parsed now
    for d in sorted(regs, key=lambda d: d["published"], reverse=True):   # newest first, so a time-limited run reads the latest registers
        try:
            text = pdf_text(d["file"])
            done = ocr_done(d["file"])
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


# ================================================================ 4b. deviations (MFMA SCM Regulation 36), as reported to Council
# Stellenbosch reports the deviations its accounting officer approved to every ordinary Council meeting, in an agenda item
# "MONTHLY FINANCIAL STATUTORY REPORTING: DEVIATIONS FOR ..." with one table: deviation number (D/SM 3/27), contract date, name of
# contractor, contract description, reason, why the SCM process could not be followed, total contract price. The agendas (often
# hundreds of MB) are read once; only their text is kept.
DEV_COLS = ["number", "date", "contractor", "description", "reason", "substantiation", "price"]


def dev_header(line):
    """character positions of the seven columns from the table's first header line, or None"""
    if not (re.search(r"\bDEVIATION\b", line) and re.search(r"\bNAME OF\b", line) and re.search(r"\bREASON\b", line)): return None
    pos = [m.start() for m in re.finditer(r"DEVIATION|CONTRACT|NAME OF|REASON|SUBSTANTIATION|TOTAL", line)]
    return pos if len(pos) == 7 else None


def parse_deviations(text):
    """[{number, date, contractor, description, reason, substantiation, price_text, price, period, page}] from an agenda's text (pages split by form feeds)"""
    rows, cols, cur, period = [], None, None, None
    for pno, page in enumerate(text.split("\f"), 1):
        for line in page.splitlines():
            h = re.search(r"DEVIATIONS\s+FOR\s+(?:THE\s+)?(?:PERIOD\s+|MONTH\s+OF\s+)?(.{6,60}?)\s*$", line)
            if h and "....." not in line: period = re.sub(r"\s+\d{1,4}$", "", re.sub(r"\s+", " ", h.group(1))).strip()
            hp = dev_header(line)
            if hp: cols = hp; cur = None; continue
            if cols is None: continue
            if re.search(r"Page \d+\s*$|MEETING OF (THE )?COUNCIL|OF STELLENBOSCH MUNICIPALITY|^\s*\d{1,3}\s*$|^\s*NUMBER\s+DATE|^\s*FOLLOWED\s|PRICE R\s*$", line): continue
            if not line.strip(): continue
            # the table ends at the next numbered heading or section of the report
            if re.match(r"^\s{0,24}(?:\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z]|RECOMMEND|FINANCIAL IMPLICATION|LEGAL IMPLICATION|ANNEXURE|FOR FURTHER DETAILS|NOTED|RESOLVED)", line) and not re.match(r"^\s*D\s*/\s*SM", line):
                cols = None; cur = None; continue
            m = re.match(r"^\s*(D\s*/\s*SM\s*\d{1,3}\s*/\s*\d\d)\b", line)
            chunks_ = [(mm.start(), mm.group(0)) for mm in re.finditer(r"\S+(?: \S+)*", line)]
            if m:
                cur = {k: [] for k in DEV_COLS}; cur["page"] = pno; cur["period"] = period; rows.append(cur)
                # the row's own column starts: its first line usually has a piece in every column, so the table's drift from page to page is followed
                rc = list(cols)
                for x, _ in chunks_:
                    k = min(range(7), key=lambda i: abs(cols[i] - x))
                    if abs(cols[k] - x) <= 8: rc[k] = x
                cur["_cols"] = rc
            if cur is None: continue
            rc = cur["_cols"]
            for x, t in chunks_:
                k = max([i for i, c in enumerate(rc) if c <= x + 2] or [0])
                if pno != cur["page"]: k = max(k, 3)   # a row running onto the next page continues its long columns only
                cur[DEV_COLS[k]].append(t)
    out = []
    for r in rows:
        d = {k: re.sub(r"\s+", " ", " ".join(r[k])).strip() for k in DEV_COLS}
        d["number"] = re.sub(r"\s+", " ", re.sub(r"\s*/\s*", "/", d["number"].split("  ")[0])).replace("D/SM", "D/SM ").replace("  ", " ")
        d["number"] = re.match(r"D/SM ?\d{1,3}/\d\d", d["number"]).group(0).replace("D/SM", "D/SM ").replace("  ", " ") if re.match(r"D/SM ?\d{1,3}/\d\d", d["number"]) else d["number"]
        dm = re.search(r"(20\d\d)[/-](\d\d)[/-](\d\d)", d["date"])
        dw = re.search(r"(\d{1,2})\s*([A-Za-z]{3})[a-z]*\s*(20\d\d)", d["date"])
        d["date"] = (f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else f"{dw.group(3)}-{MON[dw.group(2).lower()]:02d}-{int(dw.group(1)):02d}" if dw and dw.group(2).lower() in MON
                     else iso(d["date"]) or None)
        d["price_text"] = d.pop("price")
        pm = re.search(r"R\s?(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[,.](\d{2}))?", d["price_text"])
        d["price"] = float(re.sub(r"\D", "", pm.group(1)) + ("." + pm.group(2) if pm.group(2) else "")) if pm else None
        d.update(page=r["page"], period=r["period"])
        if d["contractor"]: out.append(d)
    return out


def agenda_text(d):
    """the text of one agenda, kept in the cache; a damaged PDF is read page by page and unreadable pages are counted"""
    key = os.path.join(CACHE, "agenda", f"{d['id']}.txt"); os.makedirs(os.path.dirname(key), exist_ok=True)
    if os.path.exists(key): return open(key, encoding="utf-8", errors="replace").read(), json.load(open(key + ".json"))
    pdf = key[:-4] + ".pdf"
    subprocess.run(["curl", "-sL", "--fail", "-m", "1800", "-A", UA["User-Agent"], "-o", pdf, urllib.parse.quote(d["file"], safe=":/?&=%#+,;@")], check=True)
    meta = {"bytes": os.path.getsize(pdf), "unreadable_pages": 0, "pages": 0}
    r = subprocess.run(["pdftotext", "-layout", pdf, key], capture_output=True, timeout=1800)
    if r.returncode or not os.path.exists(key) or os.path.getsize(key) < 1000:
        import pypdfium2 as P   # pdftotext refuses a PDF whose index is damaged; pdfium reads the pages it can
        doc = P.PdfDocument(pdf); parts = []
        for i in range(len(doc)):
            try: parts.append(doc[i].get_textpage().get_text_range())
            except Exception: parts.append(""); meta["unreadable_pages"] += 1
        meta["pages"] = len(doc); meta["note"] = "PDF damaged on the municipality's site: read page by page; layout not kept"
        open(key, "w").write("\f".join(parts))
    else: meta["pages"] = open(key, errors="replace").read().count("\f")
    meta["readable_pages"] = meta["pages"] - meta["unreadable_pages"]
    os.remove(pdf); json.dump(meta, open(key + ".json", "w"))
    return open(key, encoding="utf-8", errors="replace").read(), meta


def agendas():
    out, p = {}, 1
    while True:
        d = jget(f"{WP}stb_document?search=agenda+council&per_page=100&page={p}&_fields=id,date,title,link")
        for x in d:
            t = html.unescape(re.sub(r"<[^>]+>", "", x["title"]["rendered"]))
            if re.search(r"agenda", t, re.I) and re.search(r"council", t, re.I) and x["date"] >= "2023-01-01": out[x["id"]] = {"id": x["id"], "published": x["date"][:10], "title": t, "page": x["link"]}
        if len(d) < 100: break
        p += 1
    return list(out.values())


def deviations():
    path = os.path.join(CACHE, "muni-deviations.json")
    old = json.load(open(path)) if os.path.exists(path) else {"agendas": []}
    known = {a["id"]: a for a in old.get("agendas", [])}
    A = agendas(); read, failed, rows = [], [], []
    t0 = time.time(); budget = int(os.environ.get("AGENDA_MINUTES", "40")) * 60
    for a in sorted(A, key=lambda a: a["published"], reverse=True):
        a = {**known.get(a["id"], {}), **a}
        try:
            if not a.get("file"):
                h = http(a["page"], tries=3).decode("utf-8", "replace"); m = re.search(r'class="btn stb-doc-dl" href="([^"]+)"', h)
                if not m: failed.append({**a, "error": "no file on the document page"}); continue
                a["file"] = html.unescape(m.group(1))
            if not os.path.exists(os.path.join(CACHE, "agenda", f"{a['id']}.txt")) and time.time() - t0 > budget: read.append({**a, "how": "waiting"}); continue
            text, meta = agenda_text(a)
            devs = parse_deviations(text)
            for r in devs: r.update(agenda=a["title"], agenda_date=a["published"], doc=a["file"] + f"#page={r['page']}", doc_page=a["page"])
            rows += devs; read.append({**a, **meta, "how": "read", "deviations": len(devs)})
        except Exception as e:
            failed.append({**a, "error": str(e)[:160]})
    # the same deviation is printed in the agenda that reports it and again in the minutes in later agendas: keep one, list the others
    seen = {}
    for r in sorted(rows, key=lambda r: r["agenda_date"]):
        k = (r["number"].replace(" ", ""), re.sub(r"[^a-z]", "", r["contractor"].lower())[:20])
        if k in seen: seen[k].setdefault("also_in", []).append(r["doc"])
        else: seen[k] = r
    rows = sorted(seen.values(), key=lambda r: (r["date"] or "", r["number"]), reverse=True)
    warnings = [f"{x['title']}: {x['unreadable_pages']} of {x['pages']} pages could not be read (the PDF on the municipality's site is damaged)" for x in read if x.get("unreadable_pages")]
    warnings += [f"{x['title']}: no deviations table found" for x in read if x.get("how") == "read" and not x.get("deviations") and x.get("bytes", 0) > 5e6]
    dump({"id": "muni-deviations", "title": f"{M['label']}: deviations (MFMA SCM Regulation 36) reported to Council", "url": M["site"] + "council/",
          "retrieved": now(), "rows": rows, "agendas": read, "failed": failed, "warnings": warnings}, path)
    return f"{len(rows)} deviations from {sum(1 for x in read if x.get('how') == 'read')} council agendas; {sum(1 for x in read if x.get('how') == 'waiting')} waiting; {len(failed)} failed"


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
    q = lambda cube, cut, dd, agg: jget(f"{MD}{cube}/aggregate?cut=demarcation.code:{code}{cut}&drilldown={dd}&aggregates={agg}&pagesize=20000", timeout=300)["cells"]
    cap = q("capital_v2", "|period_length.length:year", "financial_year_end.year|amount_type.code", "amount.sum")
    rm = q("repmaint_v2", "|period_length.length:year", "financial_year_end.year|amount_type.code", "amount.sum")
    ac = q("aged_creditor_v2", "|period_length.length:month", "financial_year_end.year|financial_period.period|item.code|item.label", "l30_amount.sum|total_amount.sum")
    yearly = lambda cells: sorted([{"year": c["financial_year_end.year"], "type": c["amount_type.code"], "type_label": ATYPES[c["amount_type.code"]], "amount": c["amount.sum"]}
                                   for c in cells if c["amount_type.code"] in ATYPES], key=lambda r: (r["year"], r["type"]))
    # MFMA s65(2)(e): creditors are to be paid within 30 days. The aged-creditor return splits what is owed by age; over 30 days = total less 0-30 days.
    # The municipal financial year ends in June: period 1 is July of the year before financial_year_end.
    creditors = sorted([{"year": c["financial_year_end.year"], "period": c["financial_period.period"],
                         "month": f"{c['financial_year_end.year'] - (1 if c['financial_period.period'] <= 6 else 0)}-{(c['financial_period.period'] + 5) % 12 + 1:02d}",
                         "item": c["item.code"], "label": c["item.label"], "total": c["total_amount.sum"], "over_30": round((c["total_amount.sum"] or 0) - (c["l30_amount.sum"] or 0), 2)}
                        for c in ac if c["item.code"] in ("0700", "1000")], key=lambda r: (r["month"], r["item"]))
    dump({"id": "finance", "title": "National Treasury Municipal Money: income and expenditure, budget against audited actual", "url": "https://municipalmoney.gov.za/profiles/municipality-" + code + "/",
          "api": MD + "incexp_v2", "data_updated": model.get("last_updated"), "retrieved": ret, "rows": rows,
          "capital": {"title": "Capital expenditure (capital_v2), all functions", "api": MD + "capital_v2", "rows": yearly(cap)},
          "repairs": {"title": "Repairs and maintenance (repmaint_v2), all items", "api": MD + "repmaint_v2", "rows": yearly(rm)},
          "creditors": {"title": "Amounts owed to creditors by age, monthly section 71 returns (aged_creditor_v2)", "api": MD + "aged_creditor_v2",
                        "rule": "MFMA section 65(2)(e): money owed by the municipality must be paid within 30 days of receiving the invoice or statement, unless prescribed otherwise.",
                        "rule_url": "https://www.gov.za/sites/default/files/gcis_document/201409/a56-03.pdf", "rows": creditors},
          "uifw": {"title": "Unauthorised, irregular, fruitless and wasteful expenditure (notes to the audited annual financial statements)", "api": MD + "uifwexp", "retrieved": ret,
                   "rows": sorted([{"year": x["financial_year_end.year"], "item": x["item.code"], "label": x["item.label"], "amount": x.get("amount")} for x in uif], key=lambda r: (r["year"], r["item"]))}},
         os.path.join(CACHE, "finance.json"))
    dump({"id": "audit", "title": "Auditor-General audit outcomes (National Treasury audit_opinions data set)", "url": "https://municipalmoney.gov.za/profiles/municipality-" + code + "/",
          "api": MD + "audit_opinions", "agsa": "https://www.agsa.co.za/Reporting/MFMAReports.aspx", "retrieved": ret,
          "rows": sorted([{"year": x["financial_year_end.year"], "opinion": x["opinion.label"], "code": x["opinion.code"], "report": x.get("opinion.report_url")} for x in aud], key=lambda r: r["year"], reverse=True)},
         os.path.join(CACHE, "audit.json"))
    return f"{len(rows)} income/expenditure figures, {len(cap)} capital, {len(rm)} repairs, {len(creditors)} creditor months, {len(uif)} UIFW figures, {len(aud)} audit opinions"


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
    jobs = {"docs": docs, "awards": awards, "bids": bids, "deviations": deviations, "etenders": etenders, "finance": finance, "restricted": restricted}
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    failed = []
    for name, fn in jobs.items():
        if only and name not in only: continue
        t = time.time()
        try: log(name, "→", fn(), f"({time.time() - t:.0f}s)")
        except Exception as e: failed.append(name); log(name, "FAILED", repr(e)[:300])
    json.dump({"failed": failed, "at": now()}, open(os.path.join(CACHE, "_status.json"), "w"))
    write_manifest()
    if len(failed) == len([j for j in jobs if not only or j in only]): sys.exit(1)
