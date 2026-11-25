"""Metro: company-register details for supplier profiles, built up a little at a time.

Sources, in order of trust:
  1. Registration numbers printed in the records we already hold (award decisions, bid registers, eTender records, gazette
     notices, tribunal cases), next to a supplier's name. A CIPC company number has the form YYYY/NNNNNN/NN; the first part is
     the year of registration. Only this number and where it was printed are recorded: nothing is inferred.
  2. A licensed company-register provider, used only when its address and key are configured (REGISTRY_API_URL,
     REGISTRY_API_KEY as GitHub secrets). Without them this part is skipped. CIPC BizPortal needs a personal login (POPIA)
     and allows about 20 searches a day; B2BHint answers automated requests with a block page; neither is scraped.
Each daily run takes at most BATCH suppliers from a priority queue (flagged suppliers first, then by value of published
decisions and orders), waits between requests, and stops at the first refusal (HTTP 429/403). Every answer is kept in
pipeline/cache/metro/registry/ (carried between runs by the Actions cache), so the register grows without repeating work.
Writes public/data/metro/registry.json: per supplier the register fields with source and date, and an address index that
plot dossiers use to list registered businesses at an address."""
import json, os, re, sys, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, HERE, now, dump
from names import norm

CACHE = os.path.join(HERE, "cache", "metro", "registry"); os.makedirs(CACHE, exist_ok=True)
STORE = os.path.join(CACHE, "records.json")
MONEY = os.path.join(ROOT, "public", "data", "metro", "money")
OUT = os.path.join(ROOT, "public", "data", "metro", "registry.json")
BATCH = int(os.environ.get("REGISTRY_BATCH", "200"))
PAUSE = float(os.environ.get("REGISTRY_PAUSE", "2.0"))
REGNO = re.compile(r"\b((?:19|20)\d{2})\s?/\s?(\d{6})\s?/\s?(\d{2})\b")
sid_of = lambda name: re.sub(r"[^a-z0-9]+", "-", norm(name).lower()).strip("-")[:60]


def norm_address(s):
    """'12 Main Road, Bellville' -> '12 MAIN RD BELLVILLE' (the same rule as the app uses for plot addresses)"""
    s = str(s or "").upper().replace(",", " ")
    for a, b in ((r"\bROAD\b", "RD"), (r"\bSTREET\b", "ST"), (r"\bAVENUE\b", "AVE"), (r"\bDRIVE\b", "DR"), (r"\bCRESCENT\b", "CRES"), (r"\bCLOSE\b", "CL"),
                 (r"\bLANE\b", "LN"), (r"\bBOULEVARD\b", "BLVD"), (r"\bPLACE\b", "PL"), (r"\bWAY\b", "WAY")):
        s = re.sub(a, b, s)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def numbers_in_records():
    """registration numbers printed next to supplier names in the money tables; returns {supplier_id: [{reg_no, table, row, text}]}"""
    found = {}
    meta = json.load(open(os.path.join(MONEY, "money.json")))
    for tid, cols in (("awards", ("vendor", "desc")), ("bids", ("bidder",)), ("etenders", ("awards", "desc"))):
        t = meta["tables"].get(tid)
        if not t: continue
        ks = [i for i, f in enumerate(t["fields"]) if f[0] in cols]; sk = next((i for i, f in enumerate(t["fields"]) if f[0] == "sup"), None)
        for sh in range(t["shards"]):
            for r, row in enumerate(json.load(open(os.path.join(MONEY, "t", f"{tid}-{sh}.json")))):
                for k in ks:
                    text = str(row[k] or "")
                    for m in REGNO.finditer(text):
                        # the supplier is the name printed just before the number on the same line
                        before = text[:m.start()].splitlines()[-1] if text[:m.start()].splitlines() else ""
                        before = re.sub(r"\(?\s*(reg(istration)?\.?\s*(no|number)?\.?|ck|co\.? ?reg)\s*[:.]?\s*$", "", before.strip(), flags=re.I).strip(" (,-")
                        sids = [sid_of(before)] if before else []
                        if sk is not None and not before: sids = row[sk] if isinstance(row[sk], list) else [row[sk]]
                        for s in sids:
                            if s: found.setdefault(s, []).append({"reg_no": "/".join(m.groups()), "table": tid, "row": sh * meta["shard"] + r, "text": text[:200]})
    return found


class NotConfigured(Exception): pass
class Refused(Exception): pass


def provider_lookup(name):
    """licensed provider: GET {REGISTRY_API_URL}?q=<name> with the key in the Authorization header; must return JSON with
    registration_number, status, registration_date, registered_address, directors[]. Not configured: raise NotConfigured."""
    url, key = os.environ.get("REGISTRY_API_URL"), os.environ.get("REGISTRY_API_KEY")
    if not url or not key: raise NotConfigured()
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + urllib.parse.urlencode({"q": name}), headers={"Authorization": f"Bearer {key}", "User-Agent": "cape-monitor/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429): raise Refused(f"HTTP {e.code}")
        raise
    hit = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) and data else None
    if not hit: return None
    return {"reg_no": hit.get("registration_number"), "status": hit.get("status"), "reg_date": hit.get("registration_date"),
            "address": hit.get("registered_address"), "directors": hit.get("directors") or [], "source": url.split("?")[0]}


def priority(sup_rows, flags):
    """flagged suppliers first (most flags), then by value of published fixed-value decisions and orders"""
    flagged = {}
    for f in flags:
        for kind, s in f["subjects"]:
            if kind == "supplier": flagged[s] = flagged.get(s, 0) + 1
    return [r[0] for r in sorted(sup_rows, key=lambda r: (-flagged.get(r[0], 0), -((r[3] or 0) + (r[5] or 0))))]


def run(lookup=provider_lookup, pause=PAUSE):
    store = {"records": {}, "tried": {}}
    if os.path.exists(STORE):
        with open(STORE) as fh: store = json.load(fh)
    sup = json.load(open(os.path.join(MONEY, "suppliers.json")))["rows"]
    names = {r[0]: r[1] for r in sup}
    flags = json.load(open(os.path.join(MONEY, "flags.json")))["flags"]
    # 1. numbers printed in our own records
    printed = numbers_in_records()
    for s, hits in printed.items():
        if s not in names: continue
        rec = store["records"].setdefault(s, {})
        rec["printed_reg_no"] = sorted({h["reg_no"] for h in hits}); rec["printed_in"] = hits[:5]
    # 2. licensed provider, one polite batch
    status = {"provider": "not configured", "looked_up": 0, "stopped": None}
    todo = [s for s in priority(sup, flags) if s not in store["tried"]][:BATCH]
    for s in todo:
        try:
            got = lookup(names[s])
        except NotConfigured:
            break
        except Refused as e:
            status["stopped"] = f"provider refused ({e}); the rest waits for the next run"; break
        except Exception as e:
            store["tried"][s] = {"at": now(), "error": str(e)[:120]}; continue
        status["provider"] = "configured"; status["looked_up"] += 1
        store["tried"][s] = {"at": now(), "found": bool(got)}
        if got: store["records"].setdefault(s, {}).update({**got, "retrieved": now()})
        time.sleep(pause)
    with open(STORE, "w") as fh: json.dump(store, fh)
    # output: register fields per supplier, and an address index for plot dossiers
    addr = {}
    for s, rec in store["records"].items():
        if rec.get("address"): addr.setdefault(norm_address(rec["address"]), []).append(s)
    dump({"built": now(), "status": status, "batch": BATCH, "queue_left": max(0, len(sup) - len(store["tried"])),
          "records": {s: {**rec, "name": names.get(s, s)} for s, rec in store["records"].items()}, "address_index": addr,
          "notes": ["A CIPC company registration number has the form YYYY/NNNNNN/NN; YYYY is the year of registration.",
                    "CIPC BizPortal requires a personal login under POPIA and limits searches (about 20 a day); it is not read automatically.",
                    "B2BHint answers automated requests with a block page; it is linked for manual searches only.",
                    f"With a licensed provider configured, up to {BATCH} suppliers are looked up per daily run, flagged suppliers first."]}, OUT)
    print(f"registry: {len(store['records'])} suppliers with register details ({sum(1 for r in store['records'].values() if r.get('printed_reg_no'))} with a number printed in published records); provider {status['provider']}; {status['looked_up']} looked up this run")
    return status


if __name__ == "__main__":
    try: run()
    except Exception as e: print("registry: WARNING", e)   # never fails the metro run
