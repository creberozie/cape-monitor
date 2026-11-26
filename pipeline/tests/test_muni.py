"""Unit tests for the ZopStopper readers (pipeline/metro/fetch_muni.py, muni.py). Fixtures are excerpts of the municipality's own
published registers and of Treasury's restricted-supplier report. Run: python3 -m unittest discover -s pipeline/tests"""
import json, os, re, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "metro"))
os.environ["MUNI"] = "stellenbosch"
import fetch_muni as F
from muni import ref_key, is_buyer, cfg
FIX = os.path.join(HERE, "fixtures")
fx = lambda n: open(os.path.join(FIX, n), encoding="utf-8").read()


class References(unittest.TestCase):
    def test_one_key_per_number_whatever_the_spelling(self):
        for a in ("B/SM 06/27", "BSM 6/27", "B/SM06/27", "bsm 06/27"): self.assertEqual(ref_key(a), "BSM6/27")
        for a in ("FQ/SM 84/27", "FQ 84/27", "FQSM84/27", "FQ84/27"): self.assertEqual(ref_key(a), "FQ84/27")
        self.assertEqual(ref_key("046Q/2023/24"), "46Q/2023/24")   # Cape Town references keep their form

    def test_buyer_names(self):
        self.assertTrue(is_buyer("Stellenbosch Municipality", "stellenbosch")); self.assertTrue(is_buyer("STELLENBOSCH LOCAL MUNICIPALITY", "stellenbosch"))
        self.assertFalse(is_buyer("Stellenbosch University", "stellenbosch")); self.assertFalse(is_buyer("City of Cape Town", "stellenbosch"))

    def test_local_municipality_threshold(self):
        t = cfg("stellenbosch")["thresholds"]
        self.assertEqual((t[0][0], t[0][1]), ("2023-12-14", 300000)); self.assertEqual(t[1][1], 200000); self.assertIn("49863", t[0][2])


class AwardRegisters(unittest.TestCase):
    def test_2026_layout_single_award_and_panel(self):
        rows = F.parse_awards(fx("stb-awards-2026-10.txt"), "awards")
        gapp = next(r for r in rows if r["bidder"] == "GAPP ZUTARI JV")
        self.assertEqual((gapp["ref"], gapp["closing"], gapp["level"], gapp["amount"], gapp["approved"], gapp["completion"]),
                         ("BSM 117/26", "2026-07-27", "L1", 11368249.10, "2026-10-02", "2029-06-30"))
        self.assertTrue(gapp["desc"].startswith("APPOINTMENT OF A SERVICE PROVIDER TO ESTABLISH AND OPERATE A DEVELOPMENT FACILITATION UNIT"))
        panel = [r for r in rows if r["ref"] == "BSM 65/26"]
        self.assertGreater(len(panel), 10)
        self.assertTrue(all(r["amount_text"] == "RATES" and r["amount"] is None for r in panel))   # a rates panel: no amount is invented
        self.assertIn("ATARAH CO T/A ATARAH PROJECTS (PTY) LTD", [r["bidder"] for r in panel])
        self.assertFalse(any(r["bidder"] in ("PERIOD", "DATE", "CONTRIBUTOR") for r in rows))   # header words are not bidders

    def test_2021_layout_bidders_below_the_number(self):
        rows = F.parse_awards(fx("stb-awards-2021-05.txt"), "awards")
        by = {r["bidder"]: r for r in rows}
        self.assertEqual(by["SOSEBENZA CONSTRUCTION (PTY) LTD"]["ref"], "B/SM 66/21")
        self.assertEqual(by["BONSOLO TRADING (PTY) LTD"]["ref"], "B/SM 49/21")   # never joined to the name on the line above
        self.assertEqual(by["CK RUMBOLL AND PARTNERS - PLANNING"]["ref"], "B/SM 55/21")
        self.assertEqual(by["AVALON TECHNOLOGY GROUP (PTY) LTD"]["closing"], "2021-04-21")
        self.assertIn("ICT HARDWARE", by["AVALON TECHNOLOGY GROUP (PTY) LTD"]["desc"])

    def test_panel_continues_on_the_next_page(self):
        rows = F.parse_awards(fx("stb-awards-2025-10.txt"), "awards")
        legal = [r["bidder"] for r in rows if r["ref"] == "BSM 111/25"]
        self.assertIn("September & Associates", legal); self.assertIn("Smuts & co Attorneys", legal)
        self.assertIn("Fairbridge Arderne & Lawton Inc. t/a Fairbridges Wertheim Becker", legal)   # a name wrapped over two lines

    def test_quotation_register(self):
        rows = F.parse_awards(fx("stb-fq-2026-09.txt"), "fq")
        first = rows[0]
        self.assertEqual((first["ref"], first["bidder"], first["amount"], first["level"], first["closing"], first["approved"]),
                         ("FQ 29/27", "Durbanville Stationers (Pty) Ltd", 179105.62, "NC", "2026-09-10", "2026-09-23"))
        grease = next(r for r in rows if r["ref"] == "FQ 47/27")
        self.assertEqual(grease["closing"], "2026-08-20")   # '30 June 2027' inside the description is not a date column
        self.assertEqual(len([r for r in rows if r["ref"] == "FQ 66/27"]), 2)   # two suppliers on one quotation


class RotatedAndStrayText(unittest.TestCase):
    def test_rotated_text_across_the_table_is_left_out(self):
        try:
            from reportlab.pdfgen import canvas; from reportlab.lib.pagesizes import A4, landscape
        except ImportError: self.skipTest("reportlab not installed")
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "reg.pdf")
        c = canvas.Canvas(path, pagesize=landscape(A4)); c.setFont("Helvetica", 8)
        for x, t in ((20, "BID NUMBER"), (90, "DESCRIPTION"), (330, "CLOSING DATE"), (400, "SUCCESSFUL BIDDER"), (590, "AMOUNT APPROVED"), (680, "DATE APPROVED")):
            c.drawString(x, 520, t)
        c.drawString(20, 480, "BSM 12/26"); c.drawString(90, 480, "SUPPLY OF WATER METERS"); c.drawString(330, 480, "2026-05-04")
        c.drawString(400, 480, "ACME METERS (PTY) LTD"); c.drawString(590, 480, "R 1 250 000,00"); c.drawString(680, 480, "2026-06-01")
        c.saveState(); c.translate(380, 430); c.rotate(35); c.setFont("Helvetica", 14); c.drawString(0, 0, "OF BULK WATER AND ASSOCIATED INFRASTRUCTURE"); c.restoreState()
        c.save()
        text, n = F.text_without_rotated(path)
        self.assertGreater(n, 20)
        self.assertNotIn("INFRASTRUCTURE", text)
        rows = F.parse_awards(text, "awards")
        self.assertEqual([(r["ref"], r["bidder"], r["amount"]) for r in rows], [("BSM 12/26", "ACME METERS (PTY) LTD", 1250000.00)])

    def test_staggered_description_text_is_not_a_bidder(self):
        # August 2023 register: the description of B/SM 30/23 drifts right line by line into the bidder column
        rows = [{"ref": "B/SM 30/23", "bidder": "OF BULK WATER EXEO KHOKELA AND ASSOCIATED INFRASTRUCTURE"},
                {"ref": "B/SM 46/23", "bidder": "AND EQUIPMENT AT THE STELLENBOSCH MUNICIPALITY L1FOR A PERIOD"},
                {"ref": "B/SM 11/24", "bidder": "EXEO KHOKELA"}, {"ref": "B/SM 43/22", "bidder": "THE STANDARD BANK OF SOUTH AFRICA LIMITED"}]
        out, warn = F.check_names(rows)
        names = sorted(r["bidder"] for r in out)
        self.assertEqual(names, ["EXEO KHOKELA", "EXEO KHOKELA", "THE STANDARD BANK OF SOUTH AFRICA LIMITED"])   # the first recovered from the mixed line
        self.assertEqual(len(warn), 2); self.assertEqual(warn[0]["recovered"], ["EXEO KHOKELA"]); self.assertEqual(warn[1]["recovered"], [])

    def test_names_run_together_are_split_and_fragments_not_recovered(self):
        rows = [{"ref": "BSM 51/23", "bidder": "GUNDO EVOLUTION (PTY) LTD VK DISTRIBUTORS (PTY) LTD AMILA INVESTMENT (PTY) LTD CHLORCAPE (PTY) LTD"},
                {"ref": "BSM 84/25", "bidder": "CC"}, {"ref": "BSM 1/25", "bidder": "(PTY) LTD"}]
        out, warn = F.check_names(rows)
        self.assertEqual([r["bidder"] for r in out], ["GUNDO EVOLUTION (PTY) LTD", "VK DISTRIBUTORS (PTY) LTD", "AMILA INVESTMENT (PTY) LTD", "CHLORCAPE (PTY) LTD"])
        self.assertEqual(len(warn), 3)


class OffersReceivedRegisters(unittest.TestCase):
    def test_numbered_offers_are_not_awards(self):
        # March 2021 quotation register: numbered offers received, then the award date, the awardee and the amount
        rows = F.parse_awards(fx("stb-fq-offers-2021-03.txt"), "fq")
        first = rows[0]
        self.assertEqual((first["ref"], first["bidder"], first["amount"], first["approved"], first["closing"]), ("FQ75/21", "MSCT BEE Services", 115000.00, "2021-02-01", None))
        self.assertFalse(any(re.match(r"\d{1,2}\.\s", r["bidder"]) for r in rows))


class ScannedBidRegister(unittest.TestCase):
    def test_ocr_register_names_prices_and_checks(self):
        t = F.parse_register(json.load(open(os.path.join(FIX, "stb-register-bsm-25-27.ocr.json"))))
        self.assertEqual((t["ref"], t["closing"]), ("B/SM 25/27", "2026-11-16"))
        self.assertTrue(t["description"].startswith("THE CONSTRUCTION OF POLKADRAAI WATER SUPPLY SCHEME"))
        self.assertEqual([b["n"] for b in t["bids"]], list(range(1, 15)))
        by = {b["n"]: b for b in t["bids"]}
        self.assertEqual(by[1]["bidder"], "AFRILINE CIVILS (PTY) LTD"); self.assertEqual(by[1]["price"], 40626900.00)
        self.assertEqual(by[5]["price"], 54750707.88)    # first reading lost the spaces: taken from the digits-only reading, same digits
        self.assertEqual(by[13]["price"], 51987797.99)
        self.assertEqual(by[6]["price"], 25648979.00)
        self.assertTrue(all(b["conf"] >= F.MIN_CONF for b in t["bids"]))

    def test_price_needs_two_readings_that_agree(self):
        pages = json.load(open(os.path.join(FIX, "stb-register-bsm-25-27.ocr.json")))
        for w in pages[0]:
            if w.get("alt", "").startswith("R40"): w["alt"] = "R49 626 900,00"   # a misread digit in one reading
        t = F.parse_register(pages)
        self.assertIsNone(next(b for b in t["bids"] if b["n"] == 1)["price"])


class CouncilDeviations(unittest.TestCase):
    def test_deviation_table_rows(self):
        rows = F.parse_deviations(fx("stb-council-deviations-2025-10.txt"))
        by = {r["number"]: r for r in rows}
        self.assertEqual(sorted(by), ["D/SM 2/26", "D/SM 3/26", "D/SM 5/26", "D/SM 6/26"])
        a = by["D/SM 2/26"]
        self.assertEqual((a["date"], a["contractor"], a["price"]), ("2025-08-27", "Enderstein Malumbete Attorneys", 77165.00))
        self.assertTrue(a["reason"].startswith("Exceptional case"))
        self.assertEqual(by["D/SM 3/26"]["contractor"], "Visit Stellenbosch & Franschhoek Wine Valley")   # a row running onto the next page
        self.assertEqual(by["D/SM 3/26"]["price"], 9774425.00)
        self.assertEqual(by["D/SM 5/26"]["price"], 292626.63)


class RestrictedSuppliers(unittest.TestCase):
    def test_report_rows(self):
        rows = F.parse_restricted(fx("restricted-report.txt"))
        self.assertGreater(len(rows), 15)
        a = rows[0]
        self.assertEqual((a["n"], a["name"], a["reg"], a["type"], a["from"], a["to"]), (1, "ADAMS, HELENA ROSE", "6704030828082", "Restricted Supplier", "2023-09-04", "2028-09-03"))
        self.assertEqual(a["by"], "Drakenstein - WC Local Municipality")
        b = next(r for r in rows if r["n"] == 4)
        self.assertEqual(b["name"], "AMANZIAMAHLE PROJECT SOLUTIONS"); self.assertEqual(b["reason"], "Collusive bidding and fronting")


if __name__ == "__main__":
    unittest.main()
