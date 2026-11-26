import { test, expect, Page } from "@playwright/test";
import { mockSupabase, enter } from "./mock-supabase";
import { readFileSync } from "node:fs";
// ZopStopper (/watch/): start page, supplier profile, flag dossier, search and sources, on desktop (1440) and phone (390).

const errors = (p: Page) => { const e: string[] = []; p.on("pageerror", (x) => e.push(x.message)); p.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) e.push(m.text()); }); return e; };
const phone = (p: Page) => (p.viewportSize()?.width || 0) <= 900;
async function noOverflow(p: Page, sel: string) {
  const bad = await p.$$eval(`${sel} *`, (els) => els.filter((el) => { const r = el.getBoundingClientRect(); if (!r.width) return false;
    let c = el.parentElement; while (c && getComputedStyle(c).overflowX === "visible" && c.id !== "right" && c.id !== "dockbody") c = c.parentElement;
    if (!c) return false; const cr = c.getBoundingClientRect(); return r.right > cr.right + 2 && getComputedStyle(c).overflowX !== "auto" && getComputedStyle(c).overflowX !== "scroll"; }).slice(0, 5).map((el) => el.outerHTML.slice(0, 120)));
  expect(bad, `overflow in ${sel}`).toEqual([]);
}
async function start(page: Page, hash = "") {
  const t0 = Date.now(); await page.goto("./watch/" + hash); await enter(page);
  await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  return Date.now() - t0;
}
const closeSheet = async (p: Page) => { if (phone(p) && await p.locator("body.inspect").count()) await p.locator("#closeinspect").click(); };

test.beforeEach(async ({ page }) => { await mockSupabase(page); });

test("start page: flags, suppliers, finances and latest awards, with sources, fast and without errors", async ({ page }) => {
  const e = errors(page); const ms = await start(page);
  await expect(page.locator(".brand").first()).toContainText("ZOPSTOPPER");
  await expect(page.locator("#dockbody .kpis")).toBeVisible();
  await expect(page.locator("#dockbody")).toContainText("Pattern flags, highest severity");
  await expect(page.locator("#dockbody")).toContainText("Largest suppliers");
  await expect(page.locator("#dockbody")).toContainText("Irregular, fruitless and unauthorised");
  await expect(page.locator("#dockbody")).toContainText("Latest awards");
  expect(await page.locator("#dockbody a[href*='municipalmoney.gov.za'], #dockbody a[href*='treasury.gov.za']").count()).toBeGreaterThan(0);
  console.log(`watch start page ready in ${ms} ms`);
  expect(ms, "start page ready in under 2 s").toBeLessThan(2000);
  await noOverflow(page, "#dockbody");
  await expect(page.locator("link[rel=manifest]")).toHaveAttribute("href", "manifest.webmanifest");
  const man = await (await page.request.get("./watch/manifest.webmanifest")).json();
  expect(man.name).toBe("ZopStopper Stellenbosch"); expect(man.scope).toBe("/watch/");
  expect(e).toEqual([]);
});

test("supplier profile: records with source links, and the same name in Cape Town", async ({ page, request }) => {
  const e = errors(page); await start(page, "#tab=suppliers");
  await page.locator("#dockbody tr.click[data-sup]").first().click();
  await expect(page.locator("#right .kicker").first()).toHaveText(/Supplier profile/i, { timeout: 20000 });
  await expect(page.locator("#right [data-dossier=print]")).toBeVisible(); await expect(page.locator("#right [data-dossier=json]")).toBeVisible();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.locator("#right [data-dossier=json]").click()]);
  const dossier = JSON.parse(readFileSync(await dl.path(), "utf8"));
  expect(dossier.sections.length).toBeGreaterThan(0); expect(dossier.sections[0].source_url).toMatch(/^https:/); expect(dossier.sections[0].retrieved).toMatch(/^20\d\d-/);
  await expect(page.locator("#right .note a").first()).toBeVisible();   // "Source: ..." under each records table
  await noOverflow(page, "#right");
  const S = await (await request.get("./data/muni/stellenbosch/money/suppliers.json")).json();
  const ct = S.fields.indexOf("cape_town"); const both = ct >= 0 ? S.rows.find((r: any[]) => r[ct]) : null;
  if (both) {
    await page.goto(`./watch/#s=${both[0]}`); await expect(page.locator("#right")).toContainText("Also in other municipalities' records", { timeout: 20000 });
    await expect(page.locator("#right .badge.nm").first()).toHaveText("NAME MATCH ONLY");
    await expect(page.locator("#right a[href^='/#s=']").first()).toBeVisible();
  }
  expect(e).toEqual([]);
});

test("flag dossier lists the records behind the pattern; scan-review and name-match labels", async ({ page, request }) => {
  const F = await (await request.get("./data/muni/stellenbosch/money/flags.json")).json();
  const review = F.flags.find((f: any) => f.verification_status === "NEEDS_SCAN_REVIEW"); const named = F.flags.find((f: any) => f.kind === "restricted");
  const e = errors(page);
  if (review) {
    await start(page, `#fl=${review.id}`); await expect(page.locator("#right .badge.rv")).toHaveText("NEEDS SCAN REVIEW", { timeout: 20000 });
    await expect(page.locator("#right a[href*='#page=']").first()).toBeVisible();
  }
  if (named) { await page.goto(`./watch/#fl=${named.id}`); await expect(page.locator("#right .badge.nm")).toHaveText("NAME MATCH ONLY", { timeout: 20000 }); }
  await page.goto("./watch/#tab=flags"); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  await page.locator("#dockbody [data-flag]").first().click();
  await expect(page.locator("#right .kicker").first()).toContainText("Pattern in published data", { timeout: 20000 });
  await expect(page.locator("#right table.t tbody tr").first()).toBeVisible();
  await noOverflow(page, "#right");
  expect(e).toEqual([]);
});

test("search finds a supplier and a tender number", async ({ page, request }) => {
  const e = errors(page); await start(page);
  const S = await (await request.get("./data/muni/stellenbosch/money/suppliers.json")).json();
  const name = String(S.rows[0][1]);
  await page.locator("#q").fill(name.slice(0, 12)); await expect(page.locator("#results .res").first()).toBeVisible();
  await page.locator("#q").press("Enter");
  await expect(page.locator("#right .kicker").first()).toHaveText(/Supplier profile/i, { timeout: 20000 });
  await closeSheet(page);
  await page.locator("#q").fill("B/SM"); await expect(page.locator("#results .res").first()).toContainText(/B\/?SM/i);
  await page.locator("#q").press("Enter");
  await expect(page.locator("#right h2").first()).toContainText(/B\/?SM/i, { timeout: 20000 });
  expect(e).toEqual([]);
});

test("sections and sources: every tab renders, sources list what was left out", async ({ page }) => {
  const e = errors(page); await start(page);
  for (const k of ["awards", "rfq", "bids", "etenders", "departments", "finance", "notices", "docs", "sources"]) {
    await closeSheet(page);
    await page.locator(`#tabs [data-tab=${k}]`).click(); await page.waitForTimeout(800);
    await expect(page.locator("#dockbody")).not.toContainText("not in this build");
    await noOverflow(page, "#dockbody");
  }
  await expect(page.locator("#dockbody")).toContainText("Not added, and why");
  await closeSheet(page); await page.locator("#tabs [data-tab=finance]").click();
  await expect(page.locator("#dockbody")).toContainText("older than 30 days"); await expect(page.locator("#dockbody")).toContainText("Capital expenditure");
  expect(e).toEqual([]);
});
