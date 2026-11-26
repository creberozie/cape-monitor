"""Gate for ZopStopper (MUNI=stellenbosch) data, run before the data is saved as last good data and before any deploy.
Exit 1 (and nothing is saved or deployed) when:
  * any JSON file under public/data/muni/<slug>/ does not parse, or a main file does not match its schema below;
  * the municipality's award rows, quotations, eTender records, Treasury finance figures or sources manifest are empty;
  * any supplier name matches a known corruption pattern (table header words, description text that strayed into a name column,
    sentence fragments, bare company suffixes): the same rules the readers use (fetch_muni.name_problem), so nothing slips through.
Usage: MUNI=stellenbosch python3 -I pipeline/metro/validate_watch.py [data folder]"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonschema
from muni import cfg
from fetch_muni import name_problem, HEADER_WORDS

M = cfg()
D = sys.argv[1] if len(sys.argv) > 1 else M["pub_root"]
errors = []
ARR = {"type": "array"}; STR = {"type": "string"}; NUM = {"type": "number"}
SCHEMAS = {
    "money/money.json": {"type": "object", "required": ["built", "tables", "counts", "buckets", "shard", "muni"],
                         "properties": {"built": STR, "tables": {"type": "object", "additionalProperties": {"type": "object", "required": ["id", "name", "fields", "n", "shards", "source", "url", "retrieved"]}},
                                        "counts": {"type": "object", "additionalProperties": {"type": "integer"}}}},
    "money/suppliers.json": {"type": "object", "required": ["fields", "rows"], "properties": {"fields": {"type": "array", "items": STR}, "rows": {"type": "array", "items": ARR}}},
    "money/flags.json": {"type": "object", "required": ["kinds", "note", "flags"], "properties": {"flags": {"type": "array", "items": {"type": "object",
                         "required": ["id", "kind", "title", "text", "records", "subjects"], "properties": {"records": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2}},
                         "verification_status": {"enum": ["NEEDS_SCAN_REVIEW", "OCR_DUAL_PASS_AGREED"]}}}}}},
    "money/departments.json": {"type": "array", "items": {"type": "object", "required": ["name", "n", "value", "top"]}},
    "sources_manifest.json": {"type": "object", "required": ["built", "sources", "not_added", "documents", "parse_warnings", "thresholds"],
                              "properties": {"sources": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "name", "url", "retrieved", "n", "method"]}},
                                             "documents": {"type": "array", "items": {"type": "object", "required": ["title", "kind", "method"]}}}},
    "finance.json": {"type": "object", "required": ["rows", "uifw", "retrieved", "api"], "properties": {"rows": {"type": "array", "items": {"type": "object", "required": ["year", "type", "item", "amount"]}}}},
    "audit.json": {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "items": {"type": "object", "required": ["year", "opinion"]}}}},
}


def need(cond, msg):
    if not cond: errors.append(msg)


files = sorted(glob.glob(os.path.join(D, "**", "*.json"), recursive=True))
need(files, f"no data in {D}")
data = {}
for f in files:
    try: data[os.path.relpath(f, D)] = json.load(open(f, encoding="utf-8"))
    except Exception as e: errors.append(f"{os.path.relpath(f, D)}: does not parse ({str(e)[:80]})")
for name, schema in SCHEMAS.items():
    if name not in data: errors.append(f"missing {name}"); continue
    try: jsonschema.validate(data[name], schema)
    except jsonschema.ValidationError as e: errors.append(f"{name}: {e.message[:160]} at {'/'.join(map(str, e.absolute_path))}")

c = (data.get("money/money.json") or {}).get("counts", {})
for k, label in (("awards", "tender award rows"), ("rfq", "quotations awarded"), ("etenders", "eTender records")):
    need(c.get(k, 0) > 0, f"{label}: none")
fin = data.get("finance.json") or {}
need(len(fin.get("rows", [])) > 0 and len(fin.get("uifw", {}).get("rows", [])) > 0, "Treasury finance: no figures")
man = data.get("sources_manifest.json") or {}
need(len(man.get("sources", [])) >= 5, "sources manifest: fewer than five sources")

S = data.get("money/suppliers.json") or {"rows": []}
bad = []
for r in S["rows"]:
    name = str(r[1])
    why = name_problem(name) if not re.search(r"(?i)\b(?:joint venture|consortium)\b", name) or len(name.split()) > 20 else None
    if HEADER_WORDS.match(name.strip()) or re.search(r"(?i)name of bidders?|successful bidder|^tender price$", name): why = "table header text"
    if why: bad.append(f"{name[:70]} ({why})")
need(not bad, f"{len(bad)} supplier names match corruption patterns: " + "; ".join(bad[:8]))
# a quotation above the competitive-bidding threshold of its date must carry a notice (ABOVE QUOTATION LIMIT); one without points at a build fault
rfq_f = [f[0] for f in (data.get("money/money.json") or {}).get("tables", {}).get("rfq", {}).get("fields", [])]
if rfq_f:
    big = []
    for f in sorted(glob.glob(os.path.join(D, "money", "t", "rfq-*.json"))):
        for r in json.load(open(f)):
            v, d = r[rfq_f.index("value")], str(r[rfq_f.index("date")] or "")
            if r[rfq_f.index("dq")]: continue   # kept, with a notice that says so
            if v and d and v > next(t[1] for t in M["thresholds"] if d >= t[0]): big.append(f"{r[rfq_f.index('tracking')]} {d} R{v:,.0f}")
    need(not big, f"{len(big)} quotations above the competitive-bidding threshold (misread rows?): " + "; ".join(big[:5]))

print(f"validate_watch: {len(files)} files, counts {({k: c.get(k) for k in ('awards', 'rfq', 'bids', 'etenders', 'suppliers', 'flags')})}")
if errors:
    print("VALIDATION FAILED:\n  " + "\n  ".join(errors)); sys.exit(1)
print("validation ok")
