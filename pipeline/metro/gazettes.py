"""Metro: Western Cape Provincial Gazette, read notice by notice.

The gazettes are listed by month on westerncape.gov.za (Department of the Premier, documents, category 9651). Each PDF is read
with pdftotext; notices are split at their headings (English left column, Afrikaans right). A notice is kept when it is a
City of Cape Town notice or names a Cape Town suburb. For each we keep: gazette number and date, the notice heading, the
English text as published, the erven and suburbs it names, and its kind (closure, removal of restrictions, rezoning, liquor
licence, by-law, ...). Plots are matched in the app by erf number and suburb. Writes public/data/metro/notices.json.
Run: gazettes.py [years...]   default: the current and previous year (the archive back to 2000 is listed with --all)."""
import json, os, re, sys, time, html, datetime, subprocess, urllib.request, urllib.error, urllib.parse, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, HERE, now, dump
from places import tag
from muni import MUNIS
# other municipalities (ZopStopper): a notice naming one of their places, or issued by them, is also written to public/data/muni/<slug>/notices.json
MUNI_RX = {k: re.compile(r"\b(" + "|".join(re.escape(p) for p in v["places"]) + r")\b", re.I) for k, v in MUNIS.items() if v.get("places")}

LIST = "https://www.westerncape.gov.za/department-premier/documents?media_category=9651"
UA = {"User-Agent": "Mozilla/5.0 (compatible; cape-monitor/2.0; public-records index)"}
PDFS = os.path.join(HERE, "cache", "metro", "gazettes"); os.makedirs(PDFS, exist_ok=True)


def get(url, binary=False):
    err = None
    for k in range(4):
        try:
            if k and binary and isinstance(err, urllib.error.HTTPError) and err.code == 404: break
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
            return b if binary else b.decode("utf-8", "replace")
        except Exception as e: err = e; time.sleep(4 * (k + 1))
    raise RuntimeError(f"{url[:120]}: {err}")


def folders():
    """year folder -> month folders -> PDF links"""
    top = get(LIST)
    years = {m.group(2).strip()[-4:]: m.group(1) for m in re.finditer(r'folder=(\d+)"[^>]*>\s*(Gazettes \d{4})\s*<', top)}
    return years


def month_links(year_folder):
    h = get(f"{LIST}&folder={year_folder}")
    months = [(m.group(1), m.group(2).strip()) for m in re.finditer(r'folder=(\d+)"[^>]*>\s*(Provincial Gazettes?\s*-?\s*[A-Za-z]+ \d{4})\s*<', h)]
    out = []
    for fid, title in months:
        mh = get(f"{LIST}&folder={fid}")
        for m in re.finditer(r'<a href="([^"]+\.pdf[^"]*)"[^>]*>([^<]+)</a>', mh):
            out.append({"url": html.unescape(m.group(1)), "title": m.group(2).strip(), "month": title})
    return out


HEAD = re.compile(r"^\s{4,}([A-Z][A-Z0-9 ’'&:,./()-]{6,}?)\s{6,}([A-Z][A-Z0-9 ’'&:,./()-]{4,})\s*$")
KINDS = [(r"remov\w* of (restrictive )?(title )?(conditions|restrictions)|removed (and (amended|deleted) )?(the following )?conditions|opheffing", "Removal of restrictions"), (r"closure|closed|sluiting", "Closure of public place or street"),
         (r"rezon|hersoner", "Rezoning"), (r"subdivi|onderverdel", "Subdivision"), (r"departure|afwyking", "Departure"), (r"consolidat", "Consolidation"),
         (r"liquor|drank", "Liquor licence"), (r"township|dorpstigting", "Township establishment"),
         (r"expropriat|onteien", "Expropriation"), (r"amendment of conditions|wysiging van voorwaardes", "Amendment of conditions"), (r"tariff|tarie", "Tariffs"),
         (r"lease|huur", "Lease"), (r"dispos|vervreem|sale|verkoop", "Disposal of City property"), (r"appoint|aanstel", "Appointment"), (r"budget|begroting", "Budget"),
         (r"(?<!planning )by-law|verordening", "By-law")]


def split_notices(text):
    lines = text.splitlines(); starts = []
    for i, l in enumerate(lines):
        m = HEAD.match(l)
        if m and (re.search(r"MUNICIPALITY|CITY OF CAPE TOWN|PROVINCIAL|DEPARTMENT|NOTICE|PREMIER|MINISTRY|LIQUOR", m.group(1)) or re.search(r"MUNISIPALITEIT|STAD KAAPSTAD|PROVINSIAL|DEPARTEMENT|KENNISGEWING", m.group(2))):
            starts.append((i, m.start(2), m.group(1).strip()))
    out = []
    for k, (i, col, head) in enumerate(starts):
        j = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = lines[i + 1:j]
        # the Afrikaans column: the most common start of text after a gap of 3+ spaces near the middle of the page
        hist = {}
        for l in body:
            for m in re.finditer(r"\s{3,}(?=\S)", l):
                p = m.end()
                if 0.35 * len(l) < p < 0.75 * max(len(l), 1) and 30 < p < 110: hist[p] = hist.get(p, 0) + 1
        cut = max(hist, key=hist.get) if hist and max(hist.values()) >= 3 else col - 2
        eng = "\n".join(l[:cut].rstrip() for l in body)
        eng = re.sub(r"[ \t]+", " ", eng); eng = re.sub(r"\n{3,}", "\n\n", eng).strip()
        if len(eng) < 60: continue
        out.append({"issuer": head.title(), "text": eng[:6000], "line": i})
    return out


def read_pdf(g):
    key = re.sub(r"[^A-Za-z0-9.-]+", "_", urllib.parse.unquote(g["url"].split("file=")[-1].split("&")[0]))[-120:]
    pdf = os.path.join(PDFS, key); txt = pdf + ".txt"
    if not os.path.exists(txt):
        if not os.path.exists(pdf):
            data = get(g["url"], binary=True)
            if not data.startswith(b"%PDF"): raise RuntimeError("the Province's link does not return a PDF (broken link on westerncape.gov.za)")
            open(pdf, "wb").write(data)
        r = subprocess.run(["pdftotext", "-layout", pdf, txt], capture_output=True, timeout=300)
        if r.returncode or not os.path.exists(txt):
            for f in (pdf, txt):
                if os.path.exists(f): os.remove(f)   # a broken download is fetched again next run
            raise RuntimeError("unreadable PDF: " + r.stderr.decode(errors="replace")[:100])
    return open(txt, encoding="utf-8", errors="replace").read()


def run():
    years = folders()
    this = datetime.date.today().year
    want = [str(y) for y in (sys.argv[1:] if len(sys.argv) > 1 and sys.argv[1] != "--all" else [this, this - 1, this - 2, this - 3])] if "--all" not in sys.argv else sorted(years)
    gaz = []
    for y in want:
        if y in years: gaz += month_links(years[y])
    notices, failed = [], []
    others = {k: [] for k in MUNI_RX}
    def one(g):
        try: return g, read_pdf(g), None
        except Exception as e: return g, None, str(e)[:150]
    with cf.ThreadPoolExecutor(4) as ex:
        for g, text, err in ex.map(one, gaz):
            if err: failed.append({"gazette": g["title"], "url": g["url"], "error": err}); continue
            no = re.search(r"\b(\d{4})\b", g["title"]); dt = re.search(r"(\d{1,2} [A-Z][a-z]+ \d{4})", g["title"])
            for n in split_notices(text):
                places, erfs = tag(n["text"])
                pairs = sorted({(e, re.sub(r"\s+", " ", sub).strip().upper()) for e, sub in re.findall(r"\bErf\s+(\d{1,6})(?:\s*-\s*RE)?,?\s+([A-Z][A-Za-z’'-]+(?:\s[A-Z][A-Za-z’'-]+){0,2})", n["text"])
                                if not re.match(r"(Is|Has|And|In|The|Which|Was|Removed|Situated|Being|Held)$", sub.split()[0])})
                ct = "CITY OF CAPE TOWN" in n["issuer"].upper() or "Stad Kaapstad" in n["text"] or "City of Cape Town" in n["text"][:400]
                hits = {k: sorted({m.group(1).title() for m in rx.finditer(n["issuer"] + " " + n["text"])}) for k, rx in MUNI_RX.items()}
                for k, h in hits.items():
                    if h:
                        first = next((l.strip() for l in n["text"].splitlines() if l.strip()), "")
                        kind = next((kk for pat, kk in KINDS if re.search(pat, n["text"].split("\n", 1)[-1][:900], re.I)), "Other notice")
                        others[k].append({"gazette": g["title"], "number": no.group(1) if no else None, "date": dt.group(1) if dt else g["month"], "url": g["url"], "issuer": n["issuer"],
                                          "kind": kind, "title": first[:200], "places": h, "text": n["text"][:4000],
                                          "erfs": sorted(set(re.findall(r"\b(?:erf|erven)\s+(?:no\.?\s*)?(\d{1,6})\b", n["text"], re.I)))})
                if not ct and not places: continue
                first = next((l.strip() for l in n["text"].splitlines() if l.strip()), "")
                body = re.sub(r"municipal planning by-law", "", n["text"].split("\n", 1)[-1][:900], flags=re.I)   # the heading line names the planning by-law on every planning notice
                kind = next((k for pat, k in KINDS if re.search(pat, body, re.I)), "Other notice")
                pn = re.search(r"\b(?:P\.?\s?N\.?|NOTICE NO\.?|M\.?N\.?)\s*(\d+\s*/\s*\d{4})", n["text"])
                notices.append({"gazette": g["title"], "number": no.group(1) if no else None, "date": dt.group(1) if dt else g["month"], "url": g["url"],
                                "issuer": n["issuer"], "city": ct, "kind": kind, "title": first[:200], "ref": pn.group(1).replace(" ", "") if pn else None,
                                "text": n["text"], "places": places, "erfs": erfs, "erf_suburbs": [list(x) for x in pairs]})
    def iso(d):
        try: return datetime.datetime.strptime(d, "%d %B %Y").date().isoformat()
        except Exception: return d
    for n in notices: n["date_iso"] = iso(n["date"])
    notices.sort(key=lambda n: (n["date_iso"] or "", n["number"] or ""), reverse=True)
    # layout-change detection: ordinary gazettes always carry notices; warn when many yield none, or the total falls sharply
    warnings = []
    per = {}
    for n in notices: per[n["url"]] = per.get(n["url"], 0) + 1
    ordinary = [x for x in gaz if re.search(r"ordinary|gaz-\d", x["title"] + x["url"], re.I) and not re.search(r"extra", x["title"], re.I)]
    blank = [x for x in ordinary if not per.get(x["url"])]
    if ordinary and len(blank) / len(ordinary) > 0.2: warnings.append(f"{len(blank)} of {len(ordinary)} ordinary gazettes gave no Cape Town notices (layout change?)")
    outp = os.path.join(ROOT, "public", "data", "metro", "notices.json")
    if os.path.exists(outp):
        prev = json.load(open(outp))
        if prev.get("source", {}).get("years") == want and len(notices) < 0.7 * len(prev.get("notices", [])):
            warnings.append(f"notices fell from {len(prev['notices'])} to {len(notices)} for the same years")
    for w in warnings: print("WARNING gazettes:", w)
    dump({"built": now(), "source": {"name": "Western Cape Provincial Gazette (Department of the Premier)", "url": LIST, "years": want, "gazettes": len(gaz)},
          "failed": failed, "warnings": warnings, "notices": notices}, os.path.join(ROOT, "public", "data", "metro", "notices.json"))
    for k, items in others.items():
        for n in items: n["date_iso"] = iso(n["date"])
        items.sort(key=lambda n: (n["date_iso"] or "", n["number"] or ""), reverse=True)
        dump({"built": now(), "url": LIST, "source": {"name": "Western Cape Provincial Gazette (Department of the Premier)", "url": LIST, "years": want, "gazettes": len(gaz)},
              "places": MUNIS[k]["places"], "notices": items}, os.path.join(ROOT, "public", "data", "metro", f"notices-{k}.json"))
        print(k, len(items), "gazette notices name one of its places")
    print(len(gaz), "gazettes;", len(notices), "notices kept;", sum(1 for n in notices if n["city"]), "City of Cape Town;", sum(1 for n in notices if n["erfs"]), "name an erf;", len(failed), "failed")


if __name__ == "__main__":
    run()
