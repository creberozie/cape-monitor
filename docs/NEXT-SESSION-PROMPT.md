You are taking over Cape Monitor (repo: creberozie/cape-monitor). A working Blaauwberg pilot is live on Cloudflare Pages. Build the PRODUCTION-GRADE full City of Cape Town version. Read README.md, docs/, pipeline/ and src/ first.

MISSION
Cape Monitor is a public accountability instrument. It gives effect to section 32 of the Constitution (access to information) and the PAIA principle that public records belong to the public. Its job is radical, maximum disclosure of what the state and those who do business with the state have already published, but buried: gazettes, court records, tender documents, bidder lists, award notices, land deals, planning notices, council records. In South Africa the more boring and obscure the publication, the more it reveals. Look exactly there. The app should be impossible for officials and tendering companies to ignore, because everything in it is already public, sourced and linked.

INFORMATION, NOT NOISE
Every layer must answer: who decided, who paid, who was paid, who benefited, where, when, under which rule. Prefer one linked, sourced fact over ten headlines. Leave out filler, duplicates and decoration. The targets are institutions and anyone exercising public power or spending public money: City departments, officials, councillors, entities, contractors, suppliers, their directors, and the courts' public record. Residential detail about private people with no public role (home addresses, contact details, movements) is noise. Skip it.

UNASSAILABLE BY DESIGN
Attackers will try to discredit or shut this down. The defence is precision: every record carries its source, publication date, retrieval date and a link to the original. Nothing is inferred and shown as fact. Pattern flags are labelled as patterns in published data, with the underlying records one click away. Conflicting sources are shown side by side. This makes the app hard to dismiss and hard to attack.

OWNER
Crehan de Jager. Address him as Meneer. He directs and approves; you do the work. Very concise reports. Ask only for what only he can do (account clicks, approvals), with the exact link to click and what he will see. Never make him type commands. Never paste or request secrets in chat.

SCOPE
All 8 City planning districts (Blaauwberg, Table Bay, Tygerberg, Northern, Southern, Cape Flats, Mitchells Plain/Khayelitsha, Helderberg) plus a metro overview. District switcher; data loads per district; fast on phones.

PRINCIPLES
1. Integrate before building: use existing data, services and libraries; write code only to join them.
2. Maximum disclosure of public records. Legal judgement is the owner's; do not withhold or dilute published information. Report every source you could not add and why.
3. Every record sourced and linked; nothing invented.

INFRASTRUCTURE (first)
- GitHub Actions: one job per district in parallel, weekly plus manual; live feeds on a short schedule. Fetch → build → deploy to Cloudflare Pages with wrangler. Repo secret already set: CLOUDFARE_API_TOKEN (the workflow accepts this spelling). The Pages project is created on first deploy. R2 for files over 25 MiB. Real PMTiles with HTTP range requests (drop the base64 packing used for the pilot host). Last good deploy stays live if anything fails.
- Live layers (ships, alerts) through a Cloudflare Worker.

PRIORITY 1: MONEY AND TENDERS (the core)
- Open City tenders: specifications, requirements, closing dates, briefing sessions, responsible department and official.
- Bidder lists and bid-opening registers (who competed, at what price), evaluation and adjudication outcomes, awards (supplier, amount, decision reference, department), quotations (RFQs), deviations and emergency procurement, contract extensions and variations, City land sales and leases.
- National eTender Portal / OCDS data for all spheres touching Cape Town; provincial tenders.
- Supplier profile: every tender, quote and land deal across all years, with CIPC registration, directors and status via public company registers (link to CIPC/BizPortal, B2BHint and similar). Director network: companies linked through shared directors, shared addresses or shared contact details.
- Pattern flags: repeat winners per department; linked bidders competing against each other; contracts split just under approval thresholds; awards soon after company registration; deviations and extensions that multiply contract value; the same official or committee across linked awards. Each flag lists the records behind it.

PRIORITY 2: JUSTICE (own layer group)
- Western Cape High Court and special courts (Labour, Land Claims, Equality, Competition Tribunal, Tax), SAFLII and judiciary.org.za; court rolls; magistrates' court outcomes wherever published. Recent year first, then the archive.
- Each judgment tagged to the places, companies, officials and public bodies it names, with a link to the judgment. Cross-link companies in judgments to the supplier profiles above.
- Police stations and boundaries, SAPS station crime statistics, ISS Crime Hub, GI-TOC reports and Assassination Witness.

PRIORITY 3: GAZETTES AND NOTICES
Government Gazette and Western Cape Provincial Gazette (gazettes.africa and official sources): rezoning and land-use notices, removal of restrictions, township establishment, liquor licence applications, expropriations, deeds and estate notices, municipal notices and by-laws. City development applications and public participation notices. Council and committee agendas and minutes, mayoral decisions, delegations. Each notice mapped to the erf or place it names and linked to the related plot dossier.

PRIORITY 4: LOCAL INTELLIGENCE, as live as possible
Community newspapers (e.g. Tygerburger, Tabletalk, other Caxton/Media24 locals), SAPS Western Cape and City alert channels, ward councillor and CPF/neighbourhood-watch public posts, public Facebook pages where accessible. National outlets only for live breaking news; Daily Maverick/GroundUp for investigations. Every item geotagged to suburb or erf.

PRIORITY 5: LIVE AND CONTEXT
Live AIS ship positions around the Cape (aisstream.io or similar through a Worker) with port calls and anchorage. City valuation roll (GV2022) per plot, IEC results by voting district, Municipal Money finances and audit outcomes, Census 2022/Wazimap ward profiles, OpenStreetMap, SAHRIS, NASA FIRMS fires, SAWS warnings, water quality per monitoring point.

PRODUCT
- Keep: plot dossier, click logic (point/line, then plot, then smallest area), panels, search, share links, Afrikaans/English, install as app.
- Regroup layers: Money and tenders; Justice; Notices and gazettes; Property and planning; Safety; Utilities (collapse the hundreds of pipe and cable layers into one group); Community; Environment; Heritage; Live.
- Remove duplicate layers.
- Add: supplier, director, official and department profiles with network views; district and metro briefs; suburb and ward comparisons; time sliders; watchlists and alerts kept in the browser; export of any table or dossier.
- Fix: text overflowing tab and card borders; check every panel at 360, 768 and 1600 px.

QUALITY BAR
Playwright tests for every panel and the click logic on desktop and phone; mobile Lighthouse ≥ 90; first map within 3 s on 4G; accessible. Test before saying anything works; say plainly what is untested.

DELIVER
Live self-updating URL, the repo, and a one-page plain report: what is in it, what could not be added and why, what to do next.
