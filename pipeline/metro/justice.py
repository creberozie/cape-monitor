"""Metro: court and tribunal records that can be read automatically, tagged to the companies and places they name.

  Competition Tribunal decided cases (mergers, prohibited practices, consent orders): parties, status, order date, orders and reasons.
Companies are matched to supplier profiles only by exact normalised name (done in the app's data join below). Places are tagged by
official suburb names and erf numbers in the case title. SAFLII and the Laws.Africa law library sit behind a browser challenge that
blocks automated reading, so the app links each supplier to a SAFLII search instead. Writes public/data/metro/justice.json."""
import json, os, re, sys, html, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, HERE, now, dump
from places import tag
from names import norm

BASE = "https://www.comptrib.co.za/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; cape-monitor/2.0; public-records index)"}
CACHE = os.path.join(HERE, "cache", "metro", "comptrib.json")
txt = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def page(n):
    for k in range(4):
        try: return urllib.request.urlopen(urllib.request.Request(f"{BASE}decided-cases?page={n}", headers=UA), timeout=90).read().decode("utf-8", "replace")
        except Exception as e: err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"page {n}: {err}")


def parse(h):
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", h, re.S):
        tds = re.findall(r"<td>(.*?)</td>", row, re.S)
        if len(tds) < 6: continue
        href = re.search(r'href="(cases-case-files/[^"]+)"', tds[1] + tds[2])
        docs = [{"title": txt(t), "url": urllib.parse.urljoin(BASE, u.replace(" ", "%20"))} for u, t in re.findall(r'href="([^"]+\.pdf)"[^>]*>(.*?)</a>', tds[5], re.S)]
        subject = urllib.parse.unquote(href.group(1).split("/", 1)[1]).replace("-", " ") if href else ""
        out.append({"type": txt(tds[0]), "case": txt(tds[1]), "parties": txt(tds[2]), "status": txt(tds[3]), "date": txt(tds[4]),
                    "url": urllib.parse.urljoin(BASE, href.group(1).replace(" ", "%20")) if href else None, "subject": subject, "docs": docs})
    return out


def run():
    old = json.load(open(CACHE)) if os.path.exists(CACHE) else {"cases": {}}
    cases = dict(old.get("cases", {}))
    full = "--full" in sys.argv or not cases
    n = 1
    while n <= 400:
        rows = parse(page(n))
        if not rows: break
        fresh = sum(1 for r in rows if (r["case"] or r["url"]) not in cases)
        for r in rows: cases[r["case"] or r["url"]] = r
        n += 1
        if not full and fresh == 0: break
    json.dump({"retrieved": now(), "cases": cases}, open(CACHE, "w"))
    # tag companies and places
    sup_path = os.path.join(ROOT, "public", "data", "metro", "money", "suppliers.json")
    sup = {r[0] for r in json.load(open(sup_path))["rows"]} if os.path.exists(sup_path) else set()
    items = []
    for c in sorted(cases.values(), key=lambda c: c["date"] or "", reverse=True):
        names = [p.strip() for p in re.split(r"\s+(?:and|And|AND|v|vs|V)\s+|;\s*", c["parties"]) if len(p.strip()) > 2]
        ids = []
        for p in names:
            k = re.sub(r"[^a-z0-9]+", "-", norm(p).lower()).strip("-")[:60]
            if k in sup and k not in ids: ids.append(k)
        places, erfs = tag(f"{c['parties']} {c['subject']}")
        items.append({**c, "companies": names, "suppliers": ids, "places": places, "erfs": erfs})
    dump({"built": now(), "sources": [{"id": "comptrib", "name": "Competition Tribunal: decided cases", "url": BASE + "decided-cases", "retrieved": now(), "n": len(items)}],
          "not_added": [{"name": "SAFLII (Western Cape High Court, Labour Court, LAC, SCA, Constitutional Court judgments)", "url": "https://www.saflii.org/",
                         "why": "The site serves automated requests a browser challenge (Cloudflare), so judgments cannot be read in bulk. Each supplier profile links to a SAFLII search for its name."},
                        {"name": "Laws.Africa law library (lawlibrary.org.za)", "url": "https://lawlibrary.org.za/", "why": "Same browser challenge on judgment pages. Its Content API needs an account token."}],
          "items": items}, os.path.join(ROOT, "public", "data", "metro", "justice.json"))
    print(n - 1, "pages;", len(items), "Competition Tribunal cases;", sum(1 for i in items if i["suppliers"]), "name a City supplier;", sum(1 for i in items if i["places"]), "name a Cape Town suburb")


if __name__ == "__main__":
    run()
