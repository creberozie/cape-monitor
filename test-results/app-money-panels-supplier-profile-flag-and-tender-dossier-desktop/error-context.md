# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: app.spec.ts >> money panels, supplier profile, flag and tender dossier
- Location: tests/app.spec.ts:28:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('#msub .kpis')
Expected: visible
Timeout: 20000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" locator('#msub .kpis') with timeout 20000ms
  - waiting for locator('#msub .kpis')

```

```yaml
- banner:
  - text: CAPE MONITOR
  - combobox "Planning district":
    - option "Metro overview" [selected]
    - option "Blaauwberg"
    - option "Table Bay (not built yet)" [disabled]
    - option "Tygerberg (not built yet)" [disabled]
    - option "Northern (not built yet)" [disabled]
    - option "Southern (not built yet)" [disabled]
    - option "Cape Flats (not built yet)" [disabled]
    - option "Mitchells Plain / Khayelitsha (not built yet)" [disabled]
    - option "Helderberg (not built yet)" [disabled]
  - searchbox "Search"
  - text: Wed, 25 Nov, 01:05 SAST Data 2026-11-24
  - button "Map" [pressed]
  - button "Satellite"
  - button "AF"
- complementary:
  - textbox "Find a layer…"
  - group: ▸ Money and tenders 0
  - group: ▸ Justice 1
  - group: ▸ Notices and gazettes 1
  - group:
    - text: ▾ Live 1/3
    - checkbox "News naming a suburb 6 items · 2026-11-24 22:21" [checked]
    - text: News naming a suburb 6 items · 2026-11-24 22:21
    - checkbox "Active fires (NASA FIRMS, last 24 h)"
    - text: Active fires (NASA FIRMS, last 24 h)
    - checkbox "Ships around the Cape (AIS)"
    - text: Ships around the Cape (AIS)
  - paragraph: Metro overview. Choose a planning district on the map or in the list above for its plots and map layers. Sources and what was left out are under Sources.
- main:
  - region "Map":
    - region "Map"
    - text: 10 km
    - button "Zoom in"
    - button "Zoom out"
    - group:
      - text: ©
      - link "OpenStreetMap":
        - /url: https://openstreetmap.org/copyright
      - text: ·
      - link "Protomaps":
        - /url: https://protomaps.com
      - text: · Aerial photography © City of Cape Town
- complementary:
  - text: City of Cape Town · metro overview
  - heading "Public records, joined and sourced" [level=2]
  - paragraph: "Cape Monitor brings together what the City, the courts and the state have already published, often in obscure places: tender decisions, bids read out at openings, quotations, eTenders, City land sales, tribunal cases and every City GIS layer, plot by plot. Every record links to its source."
  - text: 1/8 districts built 1 977 pattern flags 67 114 plots
  - paragraph: Choose a planning district on the map for its plots and layers. Money, flags, courts and news are in the panel below for the whole city.
  - paragraph: Some records name private individuals as the state published them; see Sources.
  - heading "Planning districts" [level=3]
  - link "Blaauwberg 67 114 plots · 253 layers · data 2026-11-24":
    - /url: /?d=blaauwberg
  - text: Table Bay not built yet Tygerberg not built yet Northern not built yet Southern not built yet Cape Flats not built yet Mitchells Plain / Khayelitsha not built yet Helderberg not built yet
- navigation:
  - button "Brief"
  - button "Money"
  - button "Justice"
  - button "Notices"
  - button "Feed"
  - button "Watchlist"
  - button "Sources"
  - button "⇕"
- text: City of Cape Town District figures come from each district's own build; money is city-wide. 27 358 supplier profiles 3 818 award decisions 32 048 bids read out 91 748 quotation orders 13 117 WC eTenders 1 977 pattern flags
- table:
  - rowgroup:
    - row "District Plots Map layers Service requests Building plans matched Data built":
      - columnheader "District"
      - columnheader "Plots"
      - columnheader "Map layers"
      - columnheader "Service requests"
      - columnheader "Building plans matched"
      - columnheader "Data built"
  - rowgroup:
    - row "Blaauwberg 67 114 253 248 809 26 837 2026-11-24":
      - cell "Blaauwberg":
        - link "Blaauwberg":
          - /url: /?d=blaauwberg
      - cell "67 114"
      - cell "253"
      - cell "248 809"
      - cell "26 837"
      - cell "2026-11-24"
    - row "Table Bay not built yet":
      - cell "Table Bay":
        - link "Table Bay":
          - /url: /?d=table-bay
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
    - row "Tygerberg not built yet":
      - cell "Tygerberg":
        - link "Tygerberg":
          - /url: /?d=tygerberg
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
    - row "Northern not built yet":
      - cell "Northern":
        - link "Northern":
          - /url: /?d=northern
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
    - row "Southern not built yet":
      - cell "Southern":
        - link "Southern":
          - /url: /?d=southern
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
    - row "Cape Flats not built yet":
      - cell "Cape Flats":
        - link "Cape Flats":
          - /url: /?d=cape-flats
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
    - row "Mitchells Plain / Khayelitsha not built yet":
      - cell "Mitchells Plain / Khayelitsha":
        - link "Mitchells Plain / Khayelitsha":
          - /url: /?d=mitchells-plain-khayelitsha
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
    - row "Helderberg not built yet":
      - cell "Helderberg":
        - link "Helderberg":
          - /url: /?d=helderberg
      - cell
      - cell
      - cell
      - cell
      - cell "not built yet"
```

# Test source

```ts
  1  | import { test, expect, Page } from "@playwright/test";
  2  | // Every panel, the click logic and the share links, on desktop (1600), tablet (768) and phone (360).
  3  | 
  4  | const errors = (p: Page) => { const e: string[] = []; p.on("pageerror", (x) => e.push(x.message)); p.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) e.push(m.text()); }); return e; };
  5  | const phone = (p: Page) => (p.viewportSize()?.width || 0) <= 900;
  6  | async function tab(p: Page, name: string) {
  7  |   if (phone(p) && await p.locator("body.inspect").count()) await p.locator("#closeinspect").click();   // on phones the dossier sheet covers the tabs
  8  |   await p.locator(`#tabs [data-tab=${name}]`).click(); await p.waitForTimeout(1200);
  9  | }
  10 | /** nothing may stick out of its card, tab or panel: every element's right edge stays inside its scroll container */
  11 | async function noOverflow(p: Page, sel: string) {
  12 |   const bad = await p.$$eval(`${sel} *`, (els) => els.filter((el) => { const r = el.getBoundingClientRect(); if (!r.width) return false;
  13 |     let c = el.parentElement; while (c && getComputedStyle(c).overflowX === "visible" && c.id !== "right" && c.id !== "dockbody" && c.id !== "left") c = c.parentElement;
  14 |     if (!c) return false; const cr = c.getBoundingClientRect(); return r.right > cr.right + 2 && getComputedStyle(c).overflowX !== "auto" && getComputedStyle(c).overflowX !== "scroll"; }).slice(0, 5).map((el) => el.outerHTML.slice(0, 120)));
  15 |   expect(bad, `overflow in ${sel}`).toEqual([]);
  16 | }
  17 | 
  18 | test("metro overview loads, lists districts and has no errors", async ({ page }) => {
  19 |   const e = errors(page); await page.goto("./");
  20 |   await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  21 |   await expect(page.locator("#district")).toBeVisible({ visible: !phone(page) });
  22 |   await expect(page.locator("#right, #dockbody").first()).toBeAttached();
  23 |   await tab(page, "brief"); await expect(page.locator("#dockbody")).toContainText("City of Cape Town");
  24 |   await noOverflow(page, "#dockbody");
  25 |   expect(e).toEqual([]);
  26 | });
  27 | 
  28 | test("money panels, supplier profile, flag and tender dossier", async ({ page }) => {
  29 |   const e = errors(page); await page.goto("./"); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
> 30 |   await tab(page, "money"); await expect(page.locator("#msub .kpis")).toBeVisible({ timeout: 20000 });
     |                                                                       ^ Error: expect(locator).toBeVisible() failed
  31 |   for (const s of ["suppliers", "flags", "awards", "bids", "rfq", "etenders", "departments", "land", "docs"]) {
  32 |     await page.locator(`[data-sub=${s}]`).click(); await page.waitForTimeout(1500);
  33 |     await expect(page.locator("#msub")).not.toContainText("not in this build");
  34 |     await noOverflow(page, "#dockbody");
  35 |   }
  36 |   await page.locator("[data-sub=suppliers]").click(); await page.locator("#msub tr.click[data-sup]").first().click();
  37 |   await expect(page.locator("#right .kicker").first()).toHaveText(/Supplier profile/i, { timeout: 20000 });
  38 |   await noOverflow(page, "#right");
  39 |   if (phone(page)) await page.locator("#closeinspect").click();
  40 |   await page.locator("[data-sub=flags]").click(); await page.locator("#msub [data-flag]").first().click();
  41 |   await expect(page.locator("#right .kicker").first()).toContainText("Pattern in published data", { timeout: 20000 });
  42 |   await expect(page.locator("#right table.t tbody tr").first()).toBeVisible();
  43 |   await page.goto("./#t=46Q/2023/24"); await expect(page.locator("#right h2").first()).toContainText("46Q/2023/24", { timeout: 30000 });
  44 |   expect(e).toEqual([]);
  45 | });
  46 | 
  47 | test("justice, feed, watchlist and sources panels", async ({ page }) => {
  48 |   const e = errors(page); await page.goto("./"); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  49 |   for (const t of ["justice", "feed", "watchlist", "sources"]) { await tab(page, t); await expect(page.locator("#dockbody")).not.toBeEmpty(); await noOverflow(page, "#dockbody"); }
  50 |   await tab(page, "sources"); await expect(page.locator("#dockbody")).toContainText("Not added, and why");
  51 |   expect(e).toEqual([]);
  52 | });
  53 | 
  54 | test("district: map, layer panel, click logic (point, then plot, then smallest area), dossier and share link", async ({ page, request }) => {
  55 |   const idx = await (await request.get("data/index.json")).json(); const d = idx.districts.find((x: any) => x.built);
  56 |   test.skip(!d, "no district built yet");
  57 |   const e = errors(page); await page.goto(`./?d=${d.slug}`); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 40000 });
  58 |   if (phone(page)) await page.locator("#menu").click();
  59 |   await expect(page.locator("#left details.theme").first()).toBeVisible();
  60 |   await noOverflow(page, "#left");
  61 |   if (phone(page)) await page.locator("#menu").click();
  62 |   // zoom into the middle of the district and click: a plot dossier or a record opens
  63 |   const b = d.bounds; await page.evaluate(([x, y]) => (window as any).__cm.jumpTo({ center: [x, y], zoom: 17 }), [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
  64 |   await page.waitForTimeout(4000);
  65 |   const box = (await page.locator("#map").boundingBox())!; await page.mouse.click(box.x + box.width / 2, box.y + box.height / 3);
  66 |   await expect(page.locator("#right .card").first()).toBeVisible({ timeout: 20000 });
  67 |   await noOverflow(page, "#right");
  68 |   for (const t of ["brief", "activity", "records", "sources"]) { await tab(page, t); await expect(page.locator("#dockbody")).not.toBeEmpty(); }
  69 |   expect(e).toEqual([]);
  70 | });
  71 | 
```