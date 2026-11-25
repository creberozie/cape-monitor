import { test, expect } from "@playwright/test";
import { mockSupabase, enter } from "./mock-supabase";
// Accounts. GATED_URL: a build with VITE_SUPABASE_* set and the wall on (npm run test:gated builds and serves one).
// The open-mode test runs against the normal BASE_URL.
const GATED = process.env.GATED_URL;

test("gated: sign-up signs straight in, shows the online count, logs actions", async ({ page }) => {
  test.skip(!GATED, "no gated build (set GATED_URL)");
  const m = await mockSupabase(page);
  await page.goto(GATED!);
  await expect(page.locator("#gate")).toBeVisible({ timeout: 20000 });
  await expect(page.locator("#map")).toBeAttached();             // the app is behind the wall, not missing
  await enter(page);
  expect(m.signups).toBe(1);
  await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  if ((page.viewportSize()?.width || 0) > 900) await expect(page.locator("#online")).toHaveText(/1 online/, { timeout: 15000 });
  await page.locator("#tabs [data-tab=money]").click();
  await expect.poll(() => m.activity.map((a) => a.action), { timeout: 15000 }).toEqual(expect.arrayContaining(["sign_up", "open", "tab"]));
  // the session survives a reload: no wall the second time
  await page.reload(); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 }); await expect(page.locator("#gate")).toHaveCount(0);
});

test("gated: owners get the Users tab, others do not", async ({ page }) => {
  test.skip(!GATED, "no gated build (set GATED_URL)");
  await mockSupabase(page, { owner: true }); await page.goto(GATED!); await enter(page);
  await expect(page.locator("#tabs [data-tab=users]")).toBeVisible({ timeout: 20000 });
});

test("open: no wall, straight into the app, nothing overflows", async ({ page }) => {
  test.skip(!!process.env.EXPECT_GATE, "this deployment has the wall on");
  await page.goto("./"); await expect(page.locator("#boot")).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator("#gate")).toHaveCount(0);
  const over = await page.evaluate(() => [...document.querySelectorAll("#top *, #tabs")].filter((el) => { const r = el.getBoundingClientRect(); return r.width && r.right > innerWidth + 1; }).length);
  expect(over).toBe(0);
  // the tab bar itself stays on screen and scrolls sideways; no label is squeezed narrower than its text
  const squeezed = await page.$$eval("#tabs button", (bs) => bs.filter((b) => b.scrollWidth > b.clientWidth + 1).map((b) => b.textContent));
  expect(squeezed).toEqual([]);
});
