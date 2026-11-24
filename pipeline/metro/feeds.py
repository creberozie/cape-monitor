"""Metro: news and NGO feeds, each item tagged with the suburbs (and so the districts) it names. Writes public/data/metro/feed.json.
National outlets are included for breaking news; Daily Maverick and GI-TOC for investigations and organised crime."""
import json, os, re, sys, html, urllib.request, email.utils, concurrent.futures as cf
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, now, dump
from places import tag

FEEDS = [("news24", "News24 South Africa", "https://feeds.capi24.com/v1/Search/articles/news24/SouthAfrica/rss", "news"),
         ("iol-wc", "IOL Western Cape", "https://iol.co.za/rss/iol/news/south-africa/western-cape", "news"),
         ("capetownetc", "Cape Town ETC", "https://www.capetownetc.com/feed/", "local"),
         ("citizen", "The Citizen", "https://www.citizen.co.za/feed/", "news"),
         ("dailymaverick", "Daily Maverick", "https://www.dailymaverick.co.za/dmrss/", "investigations"),
         ("gitoc", "Global Initiative Against Transnational Organized Crime", "https://globalinitiative.net/feed/", "organised crime"),
         ("gitoc-assassination", "GI-TOC Assassination Witness", "https://globalinitiative.net/initiatives/assassination-witness/feed/", "organised crime")]
UA = {"User-Agent": "Mozilla/5.0 (compatible; cape-monitor/2.0)"}
PATH = os.path.join(ROOT, "public", "data", "metro", "feed.json")


def iso(d):
    try: return email.utils.parsedate_to_datetime(d).isoformat()
    except Exception: return d


def one(f):
    fid, name, url, kind = f
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
        root = ET.fromstring(raw); items = []
        for it in root.iter("item"):
            g = lambda t: (it.findtext(t) or "").strip()
            summ = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", g("description")))).strip()[:500]
            title = html.unescape(g("title"))
            places, erfs = tag(f"{title} {summ}")
            items.append({"feed": fid, "title": title, "link": g("link"), "date": iso(g("pubDate")), "summary": summ, "places": places, "erfs": erfs})
        return fid, {"id": fid, "name": name, "url": url, "kind": kind, "n": len(items), "retrieved": now()}, items, None
    except Exception as e:
        return fid, {"id": fid, "name": name, "url": url, "kind": kind, "n": 0, "retrieved": now(), "error": str(e)[:200]}, [], str(e)


old = json.load(open(PATH)) if os.path.exists(PATH) else {"items": []}
feeds, items = [], {}
for it in old.get("items", []): items[it["link"]] = it          # keep earlier items: feeds only show the latest few
with cf.ThreadPoolExecutor(6) as ex:
    for fid, meta, its, err in ex.map(one, FEEDS):
        feeds.append(meta); print(fid, meta["n"], err or "")
        for it in its: items[it["link"]] = it
keep = sorted(items.values(), key=lambda i: i.get("date") or "", reverse=True)[:3000]
dump({"built": now(), "feeds": feeds, "items": keep}, PATH)
print(len(keep), "items kept,", sum(1 for i in keep if i["places"]), "name a Cape Town suburb")
