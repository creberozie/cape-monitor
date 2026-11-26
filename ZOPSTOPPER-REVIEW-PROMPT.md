You are reviewing and improving **ZopStopper Stellenbosch**. Work as a senior forensic auditor who specialises in municipal procurement corruption, and as a full-stack developer who fixes what you find.

## The app
- **Live app:** https://cape-monitor.pages.dev/watch/
  - Name: "ZopStopper Stellenbosch". It is a watchdog for Stellenbosch Municipality (WC024).
  - It shares a site with Cape Monitor (https://cape-monitor.pages.dev/), a separate app for the City of Cape Town. Do not break Cape Monitor.
- **Code:** GitHub `creberozie/cape-monitor`, branch `main`.
  - App: `watch/index.html`, `src/watch.ts`, `src/watch.css`, with shared views in `src/money.ts` and `src/styles.css`.
  - Data pipeline (Python): `pipeline/metro/fetch_muni.py`, `build_money.py`, `build_muni.py`, `validate_watch.py`, `muni.py`.
  - Unit tests: `pipeline/tests/test_muni.py`. Browser tests: `tests/watch.spec.ts`.
- **Built data:** public/data/muni/stellenbosch/, which includes:
  - `money/money.json`, the table index;
  - `money/t/*.json`, the table rows;
  - `money/suppliers.json` and `money/flags.json`;
  - `overview.json`, `finance.json` and `audit.json`;
  - `sources_manifest.json`, the sources, what was left out and parse warnings.
- **Rebuild locally:**

  ```
  MUNI=stellenbosch python3 -I pipeline/metro/fetch_muni.py && MUNI=stellenbosch python3 -I pipeline/metro/build_money.py && MUNI=stellenbosch python3 -I pipeline/metro/build_muni.py && MUNI=stellenbosch python3 -I pipeline/metro/validate_watch.py
  ```

- **Sign-in:** the app asks visitors to create a free account (Supabase). The data files themselves are public at their addresses.

## Purpose (this governs every decision)
ZopStopper puts the whole crime scene in one place for professionals: every published award, quotation, bid, deviation, eTender record, supplier, finance figure and audit outcome, each linked to its source document. Investigators then find the suspects themselves, far faster than by trawling archives.

It must **never accuse anyone**. It shows patterns in published records, says exactly how each was found, and lets the reader judge.

## Non-negotiable data rules
1. **Accuracy:** never invent or estimate a figure, date, name, threshold or legal reference. Verify every legal reference against an official source and cite it:
   - MFMA, MFMA SCM Regulations and Treasury circulars;
   - the R300 000 competitive-bidding threshold from 14 Dec 2023, GN 4198, GG 49863 (R200 000 before);
   - the MFMA s65(2)(e) 30-day creditor rule.
2. **Keep every readable row:** never drop data that can be read. Keep doubtful rows with a clear notice, and keep them out of totals and supplier links. The current notices are OFFER, NOT THE AWARD; NAME UNCLEAR; NOT LEGIBLE (OCR); and ABOVE QUOTATION LIMIT. A document with no data in it, such as a blank bid form, is listed under Sources with the reason.
3. **Sourcing:** every row keeps its source link (with `#page=` where known), its extraction method (PDF text, dual-pass OCR, single-pass OCR, council agenda) and the date it was retrieved.
4. **Name matches:** a match made on a name only (Treasury restricted list, Cape Town records) is labelled NAME MATCH ONLY and never presented as identity.
5. **Release gate:** `validate_watch.py` must pass before any deploy. Strengthen it where you find gaps; never weaken it to get green.

## Task 1: data integrity audit (do this first)
- **Sample against the sources:** take at least 40 rows across tender awards, quotations, bids, deviations and eTenders, spread over 2019–2026 and across extraction methods. Check each against its source PDF or scan and record mismatches.
- **Award registers:** test the column logic. Look for amounts attached to the wrong bidder, panel awards, dates and carry-over across pages.
- **Totals:** confirm marked rows are excluded from KPIs, supplier totals, charts and flags.
- **Supplier identity:** look for false merges, such as different companies under one profile, and missed merges, such as one company split across spellings. Explain the rule you apply.
- **Pattern flags:** for each kind in `flags.json` (notlowest, retender, portal, split, single, official, phone, restricted, deviation), check the rule, the threshold of the right date, false positives and the wording.
- **Finance:** cross-check the Treasury Municipal Money figures (`finance.json`, UIFW, audit opinions) against https://municipaldata.treasury.gov.za.
- **Gaps:** list what a forensic auditor would expect but cannot find, such as the contracts register (s33), CIPC directors, CSD numbers and bank details. For each, say whether a free public source exists.
- **Fix:** correct every defect in code, add a regression test for each, rebuild and re-run the gate.

## Task 2: presentation for investigators
Make it read as an investigation workspace, not a list of tabs. World Monitor (worldmonitor.app) shows the feel to aim for: dense, visual and live. Borrow ideas only, no code, because it is AGPL. Suggested, in order of value:
- **Timeline:** awards, quotations, deviations, bids and eTender notices on one zoomable time axis, filterable by supplier, tender or flag.
- **Network graph:** suppliers linked by shared tenders, co-bidding, shared phone numbers, shared officials and name matches. Cluster and highlight flagged links, and click through to the evidence.
- **Supplier dossier page:** a timeline, the money over time, who they bid against, every flag, and source links.
- **Flag page:** the rule in plain words, the evidence rows, how the ranking works, and what would clear the flag.
- **Charts:**
  - spending against threshold bands (quotations just under R300 000 or R200 000);
  - concentration (top suppliers' share by year);
  - deviations by year;
  - irregular expenditure against award volume.
- **Exports:** keep the evidence dossier export (print and JSON), and add CSV of any filtered view.

Use small, permissive-licence libraries only, for example d3 or cytoscape.js (MIT). The start page must stay under 2 seconds, with an overview payload under 150 KB gzipped. It must work at 1440 px and on a phone at 390 px.

## Also fix
- The sign-in screen on /watch/ says "Cape Monitor records your sign-in…". It should name ZopStopper.

## How to work and ship
1. Branch from `main`.
2. Run, all green:
   - `python3 -m pytest -q pipeline/tests`;
   - `validate_watch.py`;
   - Playwright projects `watch-desktop`, `watch-phone`, `desktop-1440` and `phone-390`. Set `PW_EXE=/opt/pw-browsers/chromium` if the pinned browser is missing.
3. Push. The branch deploys to a preview at `https://claude-<branch-with-dashes>.cape-monitor.pages.dev/`. Run the same tests there with `BASE_URL`.
4. Open a pull request. The owner has approved merging to `main` once the tests pass on the preview. A merge deploys to the live site; re-test there.
5. Never skip or weaken a test to get green.

## Reporting to the owner
- **Who:** Crehan de Jager. Address him as "Meneer".
- **Style:** plain language, short, no jargon, links in every report. Never ask him to type commands or paste secrets.
- **End with:**
  - what you checked;
  - what was wrong and what you fixed, with before and after figures;
  - what is still uncertain, and why;
  - what to add next.
