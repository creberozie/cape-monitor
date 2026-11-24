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
**Notices**: Western Cape Provincial Gazette, notice by notice, with the erven and suburbs each names, linked from plot dossiers.
**Districts**: every City GIS layer with records in the district, building plans, service requests, City sales and the plot dossier.
**Live**: news and NGO feeds tagged to suburbs; NASA FIRMS fires; AIS ships (needs an aisstream.io key).

## How it runs

```
pipeline/            per district (CM_DISTRICT=<slug>): catalogue.py → fetch_city.py → fetch_extra.py → build.py
pipeline/metro/      run.py: districts.py, fetch_money.py, build_money.py, feeds.py, justice.py, gazettes.py
pipeline/check.py    checks before anything is saved or deployed; index.py lists what is built; smoke.py tests the live site
functions/live/      Cloudflare Pages Functions: /live/fires, /live/ships, /live/news
src/                 the app (MapLibre + PMTiles over HTTP range requests)
.github/workflows/   data.yml (weekly districts, metro every three hours), deploy.yml (build, deploy, test, report)
```

Each part (each district, the metro set) saves its own last good data. A part that fails keeps its last good data, so the
live site never loses a district because one source was down. Status of every deploy is written to the `ci-status` branch.

Local: `npm ci && pip install shapely pmtiles`, then `CM_DISTRICT=blaauwberg npm run data`, `python3 -I pipeline/metro/run.py full`,
`python3 -I pipeline/index.py`, `npm run dev`.
