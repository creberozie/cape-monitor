# Cape Monitor

An intelligence desk for the City of Cape Town: every public record we can reach, joined plot by plot, on one map.
Phase 1 covers the City's **Blaauwberg** planning district. The pipeline is written per district, so the other seven
districts (Table Bay, Tygerberg, Northern, Southern, Cape Flats, Mitchells Plain/Khayelitsha, Helderberg) are a data run,
not a rebuild.

## What is in it

- **Every City GIS layer** that has records in the district (around 270 layers: plots, zoning, overlays, heritage,
  water, sewer, electricity, stormwater, telecoms, roads, transport, facilities, environment, safety, Koeberg zones),
  all fields as recorded.
- **City records**: service requests since January 2023 (with map positions), building plan approvals 2014 onward
  (matched to plots), City property sales, quotation and tender awards (city-wide, with supplier names and values),
  traffic crashes, fire incidents, business licences, food-premises certificates, population estimates.
- **Feeds**: News24, IOL Western Cape, Daily Maverick, GI-TOC analysis and Assassination Witness, tagged with the
  places they name.
- **Heritage module** (from Blaauwberg TimeFlyer): sourced finds, audited heritage records, stories.

Click a plot: the right panel shows the plot, then its building plans, service requests, City sales, the records on it,
every zone and overlay covering it, and the nearest police, fire, clinic, school and library. Click anything else: that
record first, then everything else at that point.

## Run it

```bash
npm install
pip install shapely pmtiles
npm run data          # fetch everything for Blaauwberg (first run: 1-2 hours) and build public/data
npm run dev           # local site at http://localhost:5173
npm run build         # production site in dist/
```

`npm run data:refresh` fetches everything again instead of using the download cache.

## Layout

```
pipeline/   catalogue.py (find layers) → fetch_city.py, fetch_extra.py (download) → build.py (join, tile, write)
            arcgis.py (robust ArcGIS client), themes.py (grouping and exclusions, with reasons), tile.mjs, pack_pmtiles.py
src/        main.ts (layers, search, links), map.ts (rendering, exact picking), inspector.ts (dossiers), dock.ts (panels)
public/     basemap (Cape Town vector tiles, fonts, icons), web app manifest, service worker; data/ is generated
docs/       source register, research register, audit of heritage pins
.github/    weekly data refresh and deploy to Cloudflare Pages
```

## Publish

1. Create a GitHub repository `cape-monitor` and push this folder.
2. In Cloudflare: Workers & Pages → Create → Pages → "Upload assets" is not needed; instead create an API token
   (template "Edit Cloudflare Workers") and note the account ID.
3. In GitHub: Settings → Secrets → Actions: add `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
4. Actions → "Build data and deploy" → Run workflow. The site appears at `https://cape-monitor.pages.dev`.
   It then refreshes itself every Monday. If any step fails nothing is deployed and the last good version stays live.
5. Optional: restrict the site to invited people with Cloudflare Zero Trust → Access (free up to 50 users).
