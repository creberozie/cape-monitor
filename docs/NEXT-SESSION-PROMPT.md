You are taking over Cape Monitor (repo: creberozie/cape-monitor). A working Blaauwberg pilot is live on Cloudflare Pages. Build the PRODUCTION-GRADE full City of Cape Town version. Read README.md, docs/, pipeline/ and src/ first.

PURPOSE: A serious public-interest intelligence desk that gives effect to the constitutional right of access to information (s32). Not a toy. The value is in information published by law but buried: gazettes, court records, tender documents, notices. Look where nobody looks.

OWNER: Crehan de Jager. Address him as Meneer. He directs and approves; you do the work. Very concise reports. Ask only for what only he can do (account clicks, approvals), and give him the exact link to click. Never make him type commands.

SCOPE: All 8 City planning districts (Blaauwberg, Table Bay, Tygerberg, Northern, Southern, Cape Flats, Mitchells Plain/Khayelitsha, Helderberg) plus a metro overview. District switcher; data loads per district; fast on phones.

PRINCIPLES
1. Integrate before building: use existing data, services and libraries; write code only to join them.
2. Every record carries source, retrieval date and link. Nothing invented. Conflicting sources are shown side by side.
3. Maximum depth. Companies, directors, officials, tenders, judgments and anything else a public source publishes go in, linked as the source links it. Legal judgement is the owner's. Do not withhold or dilute. Report every source you could not add and why.

INFRASTRUCTURE (first)
- GitHub Actions: one job per district in parallel, weekly + manual; live feeds on a short schedule. Fetch → build → deploy to Cloudflare Pages with wrangler (repo secrets CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID; give the owner the exact links to create and paste them). R2 for files over 25 MiB. Real PMTiles with range requests (drop the base64 packing used for the pilot host). Last good deploy stays live if anything fails.
- Live layers (ships, alerts) through a Cloudflare Worker.

PRIORITY DATA (verify each; record status in docs/Source register.csv)
1. JUSTICE (own layer group): Western Cape High Court and special courts judgments (SAFLII, judiciary.org.za), court rolls, magistrates' court outcomes wherever published, Labour Court, Equality Court, Land Claims; each tagged to the places, companies and people it names, with link to the judgment. Recent year first, then the archive. Police stations, SAPS station crime statistics and boundaries, ISS Crime Hub, GI-TOC reports and Assassination Witness.
2. GAZETTES AND NOTICES: Government Gazette and Western Cape Provincial Gazette (gazettes.africa and official sources): land-use and rezoning notices, removal of restrictions, township establishment, liquor licence applications, expropriations, deeds and estate notices, municipal notices. City land-use / development applications and public participation notices. Map each notice to the erf or place it names.
3. TENDERS AND MONEY: open City tenders (specifications, requirements, closing dates, responsible department), bidders lists and bid-opening registers, awards (supplier, amount, department, decision reference), quotations, land sales, National eTender Portal / OCDS data. Supplier profile: every tender, quote and land deal across years, plus CIPC details and directors via public company registers (link out to CIPC/BizPortal, B2BHint and similar). Flag patterns: repeat winners, related directors, splitting below thresholds.
4. LOCAL INTELLIGENCE, as live as possible: community newspapers (e.g. Tygerburger, Tabletalk, other Caxton/Media24 locals), SAPS Western Cape and City alert channels, ward councillor and CPF/neighbourhood-watch public posts, public Facebook pages where accessible. National outlets only for live breaking news; Daily Maverick/GroundUp only for investigations. Geotag every item to suburb/erf.
5. SHIPPING: live AIS ship positions around the Cape (aisstream.io or equivalent through a Worker), plus a MarineTraffic-style vessel panel; port calls, anchorage, incidents.
6. Also: City valuation roll (GV2022) per plot, IEC results by voting district, Municipal Money, Census 2022/Wazimap ward profiles, OpenStreetMap, SAHRIS, NASA FIRMS fires, SAWS warnings, water-quality results per point, tree canopy (optional heavy layer).

PRODUCT
- Keep: plot dossier, click logic (point/line, then plot, then smallest area), panels, search, share links, Afrikaans/English, install as app.
- Regroup layers: Justice; Notices and gazettes; Money and tenders; Property and planning; Safety; Utilities (collapse the hundreds of pipe/cable layers into one group); Community; Environment; Heritage; Live (ships, alerts, news).
- Remove duplicate layers (e.g. two copies of plots and zoning).
- Add: district and metro briefs; suburb and ward comparisons; time sliders; supplier and official profiles; watchlists and alerts kept in the browser; export of any table or dossier.
- Fix: text overflowing tab and card borders; check every panel at 360, 768 and 1600 px.

QUALITY BAR
Playwright tests for every panel and the click logic on desktop and phone; mobile Lighthouse ≥ 90; first map within 3 s on 4G; accessible. Test before saying anything works; say plainly what is untested.

DELIVER
Live self-updating URL, the repo, and a one-page plain report: what is in it, what could not be added and why, what to do next.
