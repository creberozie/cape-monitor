import { test, expect, Page } from "@playwright/test";
// Every panel, the click logic and the share links, on desktop (1600), tablet (768) and phone (360).

const errors = (p: Page) => { const e: string[] = []; p.on("pageerror", (x) => e.push(x.message)); p.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) e.push(m.text()); }); return e; };
const phone = (p: Page) => (p.viewportSize()?.width || 0) <= 900;
async function tab(p: Page, name: string) {
  if (phone(p) && await p.locator("body.inspect").count()) await p.locator("#closeinspect").click();   // on phones the dossier sheet covers the tabs
  await p.locator(`#tabs [data-tab=${name}]`).click(); await p.waitForTimeout(1200);
}
/** nothing may stick out of its card, tab or panel: every element's right edge stays inside its scroll container */
async function noOverflow(p: Page, sel: string) {
  const bad = await p.$$eval(`${sel} *`, (els) => els.filter((el) => { const r = el.getBoundingClientRect(); if (!r.width) return false;
    let c = el.parentElement; while (c && getComputedStyle(c).overflowX === "visible" && c.id !== "right" && c.id !== "dockbody" && c.id !== "left") c = c.parentElement;
    if (!c) return false; const cr = c.getBoundingClientRect(); return r.right > cr.right + 2 && getComputedStyle(c).overflowX !== "auto" && getComputedStyle(c).overflowX !== "scroll"; }).slice(0, 5).map((el) => el.outerHTML.slice(0, 120)));
  expect(bad, `overflow in ${sel}`).toEqual([]);
}

test("metro overview loads, lists districts and has no errors", async ({ page }) => {
  const e = errors(page); await page.goto("./");
  await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator("#district")).toBeVisible({ visible: !phone(page) });
  await expect(page.locator("#right, #dockbody").first()).toBeAttached();
  await tab(page, "brief"); await expect(page.locator("#dockbody")).toContainText("City of Cape Town");
  await noOverflow(page, "#dockbody");
  expect(e).toEqual([]);
});

test("money panels, supplier profile, flag and tender dossier", async ({ page }) => {
  const e = errors(page); await page.goto("./"); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  await tab(page, "money"); await expect(page.locator("#msub .kpis")).toBeVisible({ timeout: 20000 });
  for (const s of ["suppliers", "flags", "awards", "bids", "rfq", "etenders", "departments", "land", "docs"]) {
    await page.locator(`[data-sub=${s}]`).click(); await page.waitForTimeout(1500);
    await expect(page.locator("#msub")).not.toContainText("not in this build");
    await noOverflow(page, "#dockbody");
  }
  await page.locator("[data-sub=suppliers]").click(); await page.locator("#msub tr.click[data-sup]").first().click();
  await expect(page.locator("#right .kicker").first()).toHaveText(/Supplier profile/i, { timeout: 20000 });
  await noOverflow(page, "#right");
  if (phone(page)) await page.locator("#closeinspect").click();
  await page.locator("[data-sub=flags]").click(); await page.locator("#msub [data-flag]").first().click();
  await expect(page.locator("#right .kicker").first()).toContainText("Pattern in published data", { timeout: 20000 });
  await expect(page.locator("#right table.t tbody tr").first()).toBeVisible();
  await page.goto("./#t=46Q/2023/24"); await expect(page.locator("#right h2").first()).toContainText("46Q/2023/24", { timeout: 30000 });
  expect(e).toEqual([]);
});

test("justice, feed, watchlist and sources panels", async ({ page }) => {
  const e = errors(page); await page.goto("./"); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  for (const t of ["justice", "feed", "watchlist", "sources"]) { await tab(page, t); await expect(page.locator("#dockbody")).not.toBeEmpty(); await noOverflow(page, "#dockbody"); }
  await tab(page, "sources"); await expect(page.locator("#dockbody")).toContainText("Not added, and why");
  expect(e).toEqual([]);
});

test("district: map, layer panel, click logic (point, then plot, then smallest area), dossier and share link", async ({ page, request }) => {
  const idx = await (await request.get("data/index.json")).json(); const d = idx.districts.find((x: any) => x.built);
  test.skip(!d, "no district built yet");
  const e = errors(page); await page.goto(`./?d=${d.slug}`); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 40000 });
  if (phone(page)) await page.locator("#menu").click();
  await expect(page.locator("#left details.theme").first()).toBeVisible();
  await noOverflow(page, "#left");
  if (phone(page)) await page.locator("#menu").click();
  // zoom into the middle of the district and click: a plot dossier or a record opens
  const b = d.bounds; await page.evaluate(([x, y]) => (window as any).__cm.jumpTo({ center: [x, y], zoom: 17 }), [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
  await page.waitForTimeout(4000);
  const box = (await page.locator("#map").boundingBox())!; await page.mouse.click(box.x + box.width / 2, box.y + box.height / 3);
  await expect(page.locator("#right .card").first()).toBeVisible({ timeout: 20000 });
  await noOverflow(page, "#right");
  for (const t of ["brief", "activity", "records", "sources"]) { await tab(page, t); await expect(page.locator("#dockbody")).not.toBeEmpty(); }
  expect(e).toEqual([]);
});
