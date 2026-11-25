"""Unit tests for the metro labour, company-register and private-individual rules. Run: python3 -m unittest discover -s pipeline/tests"""
import json, os, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "metro"))
import labour, business_registry as br
from names import looks_like_person, norm
FIX = os.path.join(HERE, "fixtures")


class Labour(unittest.TestCase):
    def setUp(self):
        self.page = open(os.path.join(FIX, "council.html")).read()
        self.council = {"id": "meibc", "sector": "Metal", "base": "https://www.meibc.co.za/", "seeds": [""], "doc_hosts": ["firebasestorage.googleapis.com/v0/b/meibcweb"]}

    def test_documents_found_on_own_site_and_own_storage_only(self):
        docs, errors, pages = labour.council_docs(self.council, fetch=lambda url: self.page)
        urls = [d["url"] for d in docs]
        self.assertTrue(any("Wage_Schedule_2024" in u for u in urls))
        self.assertTrue(any("firebasestorage" in u for u in urls))
        self.assertFalse(any("evil.example.com" in u for u in urls))
        self.assertFalse(any("{{" in u for u in urls))
        wage = next(d for d in docs if "Wage_Schedule" in d["url"])
        self.assertEqual(wage["kind"], "Wage schedule"); self.assertEqual(wage["year"], "2024")   # first year: start of the period
        ex = next(d for d in docs if "firebasestorage" in d["url"])
        self.assertEqual(ex["kind"], "Exemption"); self.assertFalse(ex["title"].startswith("PDF "))

    def test_employers_need_distinctive_names(self):
        docs = [{"title": "Exemption granted to Acme Steel Works (Pty) Ltd"}, {"title": "Circular on services"}]
        labour.match_employers(docs, {"acme-steel-works": "Acme Steel Works (Pty) Ltd", "services": "Services"})
        self.assertEqual(docs[0]["employers"], ["acme-steel-works"]); self.assertEqual(docs[1]["employers"], [])

    def test_lrs_feed(self):
        items = labour.lrs_items(fetch=lambda url: open(os.path.join(FIX, "lrs.json")).read())
        self.assertEqual(items[0]["title"], "Five benchmarks & wages"); self.assertEqual(items[0]["date"], "2026-10-02")

    def test_statutory_figures_carry_their_gazette(self):
        for r in labour.STATUTORY:
            self.assertIn("54075", r["source"]); self.assertTrue(r["url"].endswith(".pdf"))


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); m = os.path.join(self.tmp, "money"); os.makedirs(os.path.join(m, "t"))
        json.dump({"shard": 5000, "tables": {"awards": {"fields": [["vendor", "Vendor"], ["desc", "Desc"], ["sup", "Suppliers"]], "shards": 1}}}, open(os.path.join(m, "money.json"), "w"))
        json.dump([["Acme Steel Works (Pty) Ltd (2019/123456/07)", "x", ["acme-steel-works"]]], open(os.path.join(m, "t", "awards-0.json"), "w"))
        json.dump({"rows": [["acme-steel-works", "Acme Steel Works (Pty) Ltd", 1, 100, 0, 0], ["big-co", "Big Co", 1, 9e9, 0, 0], ["flagged-co", "Flagged Co", 1, 1, 0, 0]]}, open(os.path.join(m, "suppliers.json"), "w"))
        json.dump({"flags": [{"subjects": [["supplier", "flagged-co"]]}]}, open(os.path.join(m, "flags.json"), "w"))
        br.MONEY = m; br.CACHE = os.path.join(self.tmp, "cache"); os.makedirs(br.CACHE); br.STORE = os.path.join(br.CACHE, "records.json"); br.OUT = os.path.join(self.tmp, "registry.json")

    def test_number_printed_next_to_name(self):
        found = br.numbers_in_records()
        self.assertEqual(found["acme-steel-works"][0]["reg_no"], "2019/123456/07")

    def test_not_configured_reads_nothing(self):
        def lookup(name): raise br.NotConfigured()
        st = br.run(lookup=lookup, pause=0)
        self.assertEqual(st["provider"], "not configured")
        out = json.load(open(br.OUT)); self.assertEqual(out["records"]["acme-steel-works"]["printed_reg_no"], ["2019/123456/07"])

    def test_priority_batch_and_stop_on_refusal(self):
        calls = []
        def lookup(name):
            calls.append(name)
            if len(calls) == 2: raise br.Refused("HTTP 429")
            return {"reg_no": "2020/000001/07", "status": "In Business", "reg_date": "2020-01-15", "address": "12 Main Road, Bellville", "directors": [], "source": "test"}
        st = br.run(lookup=lookup, pause=0)
        self.assertEqual(calls[0], "Flagged Co")              # flagged first
        self.assertEqual(calls[1], "Big Co")                  # then by value
        self.assertIn("refused", st["stopped"])
        out = json.load(open(br.OUT)); self.assertIn("12 MAIN RD BELLVILLE", out["address_index"])
        calls.clear(); br.run(lookup=lookup, pause=0)
        self.assertNotIn("Flagged Co", calls)                 # cached: never asked twice

    def test_address_normalisation(self):
        self.assertEqual(br.norm_address("12 Main Road, Bellville"), "12 MAIN RD BELLVILLE")


class PrivateIndividual(unittest.TestCase):
    def test_people(self):
        for n in ["Mr. Rafik Sonday", "MS Cynteria Zolera Mgcozana"]: self.assertTrue(looks_like_person(n), n)
        self.assertTrue(looks_like_person("WILLIAMS, CEDRIC COHEN & ANTHEA STEPHANIE", land_only=True))

    def test_organisations_never_marked(self):
        for n in ["The Roman Catholic Archdiocese of Cape Town", "Greenpoint Assemblies of God Movement", "Smith Family Trust", "Masiphumelele NPC",
                  "Khayelitsha Residents Association", "Ubuntu Foundation", "Mamre Farmers Co-operative", "South African National Roads Agency",
                  "Dutch Reformed Church Bellville", "Western Cape Liquor Authority"]:
            self.assertFalse(looks_like_person(n, land_only=True), n)
        for n in ["DR Automation", "Nextec, Altron", "MS Davids Maintenance"]:   # suppliers, not land buyers: only the title rule applies
            self.assertFalse(looks_like_person(n), n)

    def test_generic_words_are_not_suppliers(self):
        self.assertEqual(norm("Various Rates"), "VARIOUS RATES")


if __name__ == "__main__":
    unittest.main()
