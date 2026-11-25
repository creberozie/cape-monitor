"""Metro: labour and employment records relevant to Cape Town.

  * Statutory minimums: figures copied from the Government Gazette (each with notice number, gazette number, date and link).
  * Bargaining councils for Cape Town industries: every collective agreement, wage schedule, circular and exemption the council
    publishes on its own site (MEIBC metal and engineering, MIBCO motor, NBCRFLI road freight, SALGBC local government),
    listed with council, kind, year and link. Documents are linked, not re-typed.
  * Labour Research Service: published reports and articles on wages and bargaining (WordPress feed of lrs.org.za).
  * Employer names in document titles are matched to supplier profiles by exact normalised name (the same rule as money);
    each matched employer gets a SAFLII search link for Labour Court and Labour Appeal Court judgments (SAFLII cannot be
    read automatically: it serves a browser challenge).
Each part runs on its own; a source that cannot be reached is listed under "not added" with the reason. The step never fails
the metro run. Writes public/data/metro/labour.json."""
import json, os, re, sys, html, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, now, dump
from names import norm

UA = {"User-Agent": "Mozilla/5.0 (compatible; cape-monitor/2.0; public-records index)"}
OUT = os.path.join(ROOT, "public", "data", "metro", "labour.json")
DOC = re.compile(r"\.(pdf|docx?|xlsx?)(\?|$)|wpfd.*file\.download|/download/", re.I)

# Statutory figures, each verified against the gazette text itself. Update only from a gazette.
GG54075 = {"source": "Government Gazette No. 54075, Notice R.7083, 3 February 2026 (Minister of Employment and Labour, National Minimum Wage Act 9 of 2018)",
           "url": "https://www.gov.za/sites/default/files/gcis_document/202602/54075rg11941gon7083.pdf", "binding_from": "2026-03-01"}
STATUTORY = [
    {"item": "National minimum wage", "rate": "R30,23 per ordinary hour", "scope": "All workers not covered by a higher rate, including farm and domestic workers", **GG54075},
    {"item": "Expanded public works programme", "rate": "R16,62 per hour", "scope": "Workers employed on an EPWP", **GG54075},
    {"item": "Contract cleaning (Sectoral Determination 1), Area A", "rate": "R33,27 per hour (R1497,15 a week; R6487,15 a month)",
     "scope": "Area A includes the City of Cape Town", **GG54075},
    {"item": "Wholesale and retail (Sectoral Determination 9), Area A", "rate": "Rates by job category: see the gazette table",
     "scope": "Area A includes the City of Cape Town", **GG54075},
]

COUNCILS = [
    {"id": "meibc", "name": "Metal and Engineering Industries Bargaining Council (MEIBC)", "sector": "Metal and engineering", "base": "https://www.meibc.co.za/",
     "seeds": ["", "agreements/main-agreement", "agreements/plastic-agreement", "agreements/lift-agreement", "agreements/dispute-resolution", "agreements/sick-pay-fund", "circulars"],
     "doc_hosts": ["firebasestorage.googleapis.com/v0/b/meibcweb"]},   # MEIBC keeps its documents in its own Firebase storage bucket
    {"id": "mibco", "name": "Motor Industry Bargaining Council (MIBCO)", "sector": "Motor retail and repair", "base": "https://www.mibco.org.za/",
     "seeds": ["collective-agreements/", "documents/", "news-resources/circulars/"]},
    {"id": "nbcrfli", "name": "National Bargaining Council for the Road Freight and Logistics Industry (NBCRFLI)", "sector": "Road freight and logistics",
     "base": "https://www.nbcrfli.org.za/", "seeds": ["collective-agreements/main", "collective-agreements/wage-table", "collective-agreements/other", "resources/circulars"]},
    {"id": "salgbc", "name": "South African Local Government Bargaining Council (SALGBC)", "sector": "Local government (City of Cape Town staff)",
     "base": "https://salgbc.org.za/", "seeds": ["", "circulars/", "enforcement-of-collective-agreements/"]},
]
KIND = [(r"wage[\s_-]*(table|schedule)|wages|minimum (rates|wage)|salary", "Wage schedule"), (r"exempt", "Exemption"), (r"circular|bulletin|notice", "Circular"),
        (r"levy|levies", "Levy"), (r"pension|provident|sick pay|fund", "Benefit fund"), (r"dispute", "Dispute resolution"),
        (r"agreement|extension|main|substantive", "Collective agreement")]


def get(url, tries=3):
    err = None
    for k in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "replace")
        except Exception as e: err = e; time.sleep(3 * (k + 1))
    raise RuntimeError(f"{url[:100]}: {err}")


def links(page_html, base):
    for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page_html, re.I | re.S):
        href = html.unescape(m.group(1)).strip()
        if "{{" in href: continue   # unrendered template placeholders
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        yield urllib.parse.urljoin(base, href), text


def year_of(s):
    ys = re.findall(r"(?<!\d)(20[0-3]\d|19[89]\d)(?!\d)", s)
    return ys[0] if ys else None   # the first year named: the start of an agreement period, or the publication year


def kind_of(s):
    return next((k for pat, k in KIND if re.search(pat, s, re.I)), "Document")


def council_docs(c, fetch=get):
    """documents linked from the council's seed pages (and from same-site pages those seeds link to under the same section)"""
    seen_pages, docs, errors = set(), {}, []
    queue = [urllib.parse.urljoin(c["base"], s) for s in c["seeds"]]
    host = urllib.parse.urlparse(c["base"]).netloc.replace("www.", "")
    while queue and len(seen_pages) < 40:
        url = queue.pop(0)
        if url in seen_pages: continue
        seen_pages.add(url)
        try: page = fetch(url)
        except Exception as e: errors.append(str(e)[:160]); continue
        for href, text in links(page, url):
            own = urllib.parse.urlparse(href).netloc.replace("www.", "") == host
            hosted = any(h in href for h in c.get("doc_hosts", []))
            if not own and not hosted: continue
            label = text or urllib.parse.unquote(href.rsplit("/", 1)[-1])
            if DOC.search(href.split("?")[0]) or (hosted and DOC.search(urllib.parse.unquote(href.split("?")[0]))):
                name = urllib.parse.unquote(href.split("?")[0]).rsplit("/", 1)[-1]
                name = re.sub(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-", "", name)   # storage ids before the file name
                name = re.sub(r"[_-]+", " ", re.sub(r"(\.pdf)+$", ".pdf", name))
                label = re.sub(r"^(PDF|DOCX?|XLSX?)\s+", "", label)   # file-type badge in the link text
                title = label if len(label) > 6 and not re.match(r"^(download|view|read more|pdf|click here)$", label, re.I) else name
                d = docs.setdefault(href, {"council": c["id"], "sector": c["sector"], "title": title, "url": href, "found_on": url})
                d["year"] = year_of(f"{title} {href}"); d["kind"] = kind_of(f"{title} {href}")
            else:   # follow same-site pages inside a seed section, e.g. /agreements/main-agreement/2024
                path = urllib.parse.urlparse(href).path.strip("/")
                if any(sd.strip("/") and path.startswith(sd.strip("/").split("/")[0] + "/") for sd in c["seeds"]) and href not in seen_pages and len(queue) < 80:
                    queue.append(href.split("#")[0])
    return list(docs.values()), errors, len(seen_pages)


def lrs_items(fetch=get):
    """Labour Research Service posts about wages and bargaining, from the site's public WordPress feed"""
    out = {}
    for q in ("wage", "bargaining", "minimum wage", "collective agreement"):
        raw = fetch("https://lrs.org.za/wp-json/wp/v2/posts?" + urllib.parse.urlencode({"search": q, "per_page": 50, "_fields": "id,date,link,title,excerpt"}))
        for p in json.loads(raw):
            out[p["id"]] = {"title": html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"])).strip(), "url": p["link"], "date": p["date"][:10],
                            "summary": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", p.get("excerpt", {}).get("rendered", "")))).strip()[:400]}
    return sorted(out.values(), key=lambda x: x["date"], reverse=True)


def match_employers(docs, supplier_ids):
    """exact normalised supplier names found inside document titles (whole words), e.g. exemptions granted to a named company"""
    # only distinctive names: two words or more and 10+ characters, so generic fragments ("services", "maintenance") never match
    names = sorted((s for s in supplier_ids if len(s) >= 10 and s.count("-") >= 1), key=len, reverse=True)
    for d in docs:
        t = "-" + re.sub(r"[^a-z0-9]+", "-", norm(d["title"]).lower()).strip("-") + "-"
        d["employers"] = [s for s in names if f"-{s}-" in t][:5]
    return docs


def saflii_labour(name):
    q = urllib.parse.quote(f'"{name}"')
    return f"https://www.saflii.org/cgi-bin/sinosrch-adw.cgi?query={q}&method=boolean&meta=%2Fsaflii&mask_path=za%2Fcases%2FZALCCT+za%2Fcases%2FZALAC+za%2Fcases%2FZALCJHB+za%2Fcases%2FZALCD+za%2Fcases%2FZALCPE"


def run():
    out = {"built": now(), "statutory": STATUTORY, "documents": [], "lrs": [], "sources": [], "not_added": [
        {"name": "Department of Employment and Labour (labour.gov.za)", "url": "https://www.labour.gov.za/", "why": "Did not answer from the build machine. Statutory rates are taken from the Government Gazette instead (listed with each figure)."},
        {"name": "City of Cape Town staff establishment and workforce numbers", "url": "https://odp-cctegis.opendata.arcgis.com/", "why": "Not published as data on the City's Open Data Portal; the figures appear only inside the City's annual report PDFs."},
        {"name": "Labour Research Service AGREED and AWARD databases", "url": "https://lrs.dedicated.co.za/agreed/", "why": "Interactive search behind a sign-in; the LRS's published reports and articles are listed instead."},
        {"name": "SAFLII Labour Court and Labour Appeal Court judgments", "url": "https://www.saflii.org/", "why": "Browser challenge blocks automated reading; each matched employer links to a SAFLII search of the labour courts."}]}
    sup_path = os.path.join(ROOT, "public", "data", "metro", "money", "suppliers.json")
    sups = {r[0]: r[1] for r in json.load(open(sup_path))["rows"]} if os.path.exists(sup_path) else {}
    for c in COUNCILS:
        try:
            docs, errors, pages = council_docs(c)
            out["documents"] += docs
            out["sources"].append({"id": c["id"], "name": c["name"], "url": c["base"], "n": len(docs), "pages": pages, "retrieved": now(), "errors": errors[:5]})
            print(c["id"], len(docs), "documents from", pages, "pages", f"({len(errors)} page errors)")
            if not docs: out["not_added"].append({"name": c["name"], "url": c["base"], "why": "No documents found on its pages this run (site down or layout changed)." + (f" {errors[0]}" if errors else "")})
        except Exception as e:
            out["not_added"].append({"name": c["name"], "url": c["base"], "why": f"Could not be read this run: {str(e)[:120]}"})
    try:
        out["lrs"] = lrs_items(); out["sources"].append({"id": "lrs", "name": "Labour Research Service (lrs.org.za)", "url": "https://lrs.org.za/", "n": len(out["lrs"]), "retrieved": now()})
        print("lrs", len(out["lrs"]), "posts")
    except Exception as e:
        out["not_added"].append({"name": "Labour Research Service", "url": "https://lrs.org.za/", "why": f"Could not be read this run: {str(e)[:120]}"})
    match_employers(out["documents"], sups)
    out["employers"] = {s: {"name": sups.get(s, s), "saflii": saflii_labour(sups.get(s, s))} for d in out["documents"] for s in d["employers"]}
    out["documents"].sort(key=lambda d: (d.get("year") or "0", d["council"]), reverse=True)
    # keep last run's documents when a council could not be read this time
    if os.path.exists(OUT):
        prev = json.load(open(OUT)); have = {d["council"] for d in out["documents"]}
        for d in prev.get("documents", []):
            if d["council"] not in have: d["kept_from"] = prev.get("built"); out["documents"].append(d)
    dump(out, OUT)
    print(len(out["documents"]), "documents;", len(out["employers"]), "employers matched to supplier profiles")


if __name__ == "__main__":
    try: run()
    except Exception as e:   # never fail the metro run over labour sources
        print("labour: WARNING", e)
