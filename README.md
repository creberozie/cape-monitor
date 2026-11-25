# Cape Monitor

A public accountability instrument for the City of Cape Town. It republishes, joined and sourced, what the City, the
Province, the courts and the national state have already published: tender decisions, bids read out at tender openings,
quotation orders, eTender records, City land sales, gazette notices, tribunal cases and every City GIS layer, plot by plot,
for all eight planning districts. Every record carries its source, publication date, retrieval date and a link to the
original. Pattern flags are labelled as patterns in published data, with the records behind them one click away.

## What is in it

**Money and tenders (city-wide)**
- City tender and adjudication decisions 2021–2026 (Open Data Portal; duplicated source rows collapsed, record numbers kept).
- Bids read out at City tender openings 2016–2026, parsed from the City's monthly *Receiving / Opening of Tenders* registers.
- City quotation (RFQ) orders 2020–2026 (values that form a spreadsheet fill-series in the source are marked and left out of totals).
- National eTender portal: every tender placed by a Western Cape buyer (any sphere): briefing sessions, responsible official,
  documents, bidders with amounts, awards with contact details. Kept across runs, because the portal drops old records.
- City land sales; the City's tender-page documents (awards registers, tender-sum increases, s33 contracts).
- Supplier profiles (identified by published name only), department profiles, tender dossiers, network views.
- Pattern flags: threshold splitting, near-threshold orders, repeat winners, post-award expansions, deviations,
  co-bidding, award above the lowest price read out, shared contact numbers, single-bid tenders. Thresholds are cited to
  the MFMA SCM Regulations (GN 868 of 2005; GN 4198, GG 49863 of 14 Dec 2023).

**Justice**: Competition Tribunal decided cases tagged to suppliers and suburbs; police stations and other justice layers per district;
SAFLII search link on every supplier.
**Labour**: statutory minimum wages copied from the Government Gazette (GN R.7083, GG 54075, binding 1 March 2026); collective
agreements, wage schedules, circulars and exemptions as published by MEIBC, MIBCO, NBCRFLI and SALGBC; Labour Research Service
publications. Employer names in document titles are matched to supplier profiles, each with a SAFLII labour-courts search link.
**Company register**: registration numbers printed in published records; a licensed provider can be configured with the
`REGISTRY_API_URL` and `REGISTRY_API_KEY` secrets (up to 200 suppliers a day, flagged first, results kept between runs).
Plot dossiers list registered businesses whose register address matches the plot's address.
**Notices**: Western Cape Provincial Gazette, notice by notice, with the erven and suburbs each names, linked from plot dossiers.
**Districts**: every City GIS layer with records in the district, building plans, service requests, City sales and the plot dossier.
**Live**: news and NGO feeds tagged to suburbs; NASA FIRMS fires; AIS ships (needs an aisstream.io key).

## Stellenbosch Watch (/watch/)

A second app in the same build for Stellenbosch Municipality (WC024), money and governance first, with no map: `watch/index.html`
and `src/watch.ts`, built to `dist/watch/`, with its own manifest, icon and service worker so it installs as a separate app.
It reuses the money views in `src/money.ts` (data folder and wording set by `configureMoney`).

Data: `MUNI=stellenbosch` runs the same money pipeline (`pipeline/metro/muni.py` holds the buyer names, place names and the
R300 000 local-municipality threshold of GN 4198, GG 49863). `fetch_muni.py` reads the municipality's document library through its
public WordPress API, the monthly tender and quotation award registers (scanned ones by OCR), the bid-opening registers (all scanned:
OCR with tesseract; a price is parsed only when a second digits-only reading of the cell has the same digits), its eTender records
(filtered from the Western Cape archive), Treasury Municipal Money (budget against actual; unauthorised, irregular, fruitless and
wasteful expenditure; audit opinions) and Treasury's restricted-supplier report (name matches only). Supplier profiles show the
same normalised name in Cape Town's records. Output: `public/data/muni/stellenbosch/`. The data workflow runs it after Cape Town in
the metro job and keeps its own last good data.

## How it runs

```
pipeline/            per district (CM_DISTRICT=<slug>): catalogue.py → fetch_city.py → fetch_extra.py → build.py
pipeline/metro/      run.py: districts.py, fetch_money.py, build_money.py, feeds.py, justice.py, gazettes.py
pipeline/check.py    checks before anything is saved or deployed; index.py lists what is built; smoke.py tests the live site
functions/live/      Cloudflare Pages Functions: /live/fires, /live/ships, /live/news
src/                 the app (MapLibre + PMTiles over HTTP range requests)
.github/workflows/   data.yml (weekly districts, metro daily; also Actions > Data > Run workflow), deploy.yml (build, deploy, test, report)
```

Each part (each district, the metro set) saves its own last good data. A part that fails keeps its last good data, so the
live site never loses a district because one source was down. Status of every deploy is written to the `ci-status` branch.
Saved data belongs to the branch that built it: a push to `main` that changes the data workflow or the metro pipeline runs a full
refresh for production, and a deploy with no saved data for its branch holds back instead of publishing an empty site.

**Interface.** Layer names, groups, quick views, field words and legend wording live in `src/catalog.ts`; group names also in
`pipeline/themes.py`. The app keeps the browser's chosen layers under `cm-layers-v2-<district>`.

Local: `npm ci && pip install shapely pmtiles`, then `CM_DISTRICT=blaauwberg npm run data`, `python3 -I pipeline/metro/run.py full`,
`python3 -I pipeline/index.py`, `npm run dev`.

## Limits, stated plainly

- **Identity.** Suppliers are matched by published name only (normalised for case, punctuation, "(Pty) Ltd", "CC"); there is no fuzzy matching.
  Two spellings of one company are two profiles. Directors and registration dates are not in any free public source used here.
- **Personal information.** Some records name private individuals and their contact details (City land buyers, sole proprietors,
  contact people on awards), exactly as published by the state. Likely private individuals are labelled and can be hidden in the
  browser; nothing is removed. Whether to redact is the owner's legal decision.
- **Places.** News, tribunal cases and gazette notices are placed at the centre of the official suburb they name (with an alias list for
  everyday names), never at an address. Plots are linked to notices only by erf number plus suburb as printed.
- **PDF parsing.** The City's bid registers and the Provincial Gazette are read from PDFs. Each run checks for layout changes (registers
  yielding nothing, bids not matching the register's TOTAL line, sharp drops) and lists warnings under Sources.
- **Performance.** A full-screen vector map scores about 45 on Lighthouse's lab mobile test, because the lab renders WebGL in software
  on a throttled CPU. Real phones render the map on the GPU and Cloudflare serves files compressed; the practical targets are first map
  on screen within about 3 s on 4G and no layer styles built until a layer is switched on. Accessibility and best practices score 100.
- **Live ships (AIS)** are not active: they need a persistent listener (Cloudflare Durable Object) and an aisstream.io key.
- **Language.** Map, layers and plot dossiers are in English and Afrikaans; Money, Justice and Notices panels are English only for now.
- **Tiers.** `src/auth/entitlements.ts` defines free and Pro. Every record is free to view; Pro adds exports of more than 500
  rows, watchlist alert rules and the weekly brief. `?preview_tier=pro` previews Pro in one browser tab. Accounts (Clerk or
  Supabase) and PayFast billing plug in through `setSession()` once the server verifies payment.
- **Actions minutes.** In a private repository GitHub allows 2 000 free minutes a month; the metro refresh therefore runs daily, not
  three-hourly. A public repository has no minute limit.

## Accounts (optional)

The app can require a free account, show a live count of people online and log key actions for the owner. It is off until a
Supabase project is configured, and it never touches the data, tiles or pipelines.

- **Switch:** GitHub repository variable `REQUIRE_ACCOUNT_ACCESS` (`true` or `false`; empty means `true` once Supabase is set).
  Set it to `false` and re-run the Deploy workflow to open the app to everyone. Without Supabase the app is always open.
- **Supabase:** repository variables `SUPABASE_URL` and `SUPABASE_ANON_KEY` (the anon key is public by design; the table rules in
  `supabase/schema.sql` protect the data). Run that file once in the Supabase SQL editor; add your e-mail to the `owners` table.
  Turn off "Confirm email" (Authentication > Providers > Email) so sign-up signs the user straight in.
- **What is logged:** sign-up, sign-in, opening the app, district, tabs, plot dossiers, supplier/tender/flag profiles, exports.
  Only signed-in users are logged; only owners can read the log (owner-only "Users" tab). The online count is anonymous.
- **Wall type:** the wall hides the app, not the public data files, which stay at their addresses.
- **Code:** `src/access/` (config, backend, auth, gate, presence, activity, owner). Tests: `tests/access.spec.ts` (gated and
  open modes, with Supabase stood in by `tests/mock-supabase.ts`), `unit/access-config.test.mjs`.
