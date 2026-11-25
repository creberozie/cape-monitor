import type { Page } from "@playwright/test";
// Stands in for Supabase in browser tests: auth (sign-up returns a session at once), the two tables, and Realtime presence.
// Matches any Supabase host, so it works for the test build and for a deployed build with the wall on. No real accounts are made.
export interface Mock { activity: any[]; signups: number }

export async function mockSupabase(page: Page, opts: { owner?: boolean } = {}): Promise<Mock> {
  const m: Mock = { activity: [], signups: 0 };
  const user = { id: "00000000-0000-4000-8000-000000000001", aud: "authenticated", role: "authenticated", email: "tester@example.org", user_metadata: { name: "Tester" }, app_metadata: {}, created_at: new Date().toISOString() };
  const session = () => ({ access_token: "test." + Buffer.from(JSON.stringify({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url") + ".sig",
    token_type: "bearer", expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, refresh_token: "refresh", user });
  await page.route(/\/auth\/v1\//, async (route) => {
    const u = route.request().url();
    if (u.includes("/signup")) { m.signups++; return route.fulfill({ json: session() }); }
    if (u.includes("/token")) return route.fulfill({ json: session() });
    if (u.includes("/user")) return route.fulfill({ json: user });
    if (u.includes("/logout")) return route.fulfill({ status: 204, body: "" });
    return route.fulfill({ json: {} });
  });
  await page.route(/\/rest\/v1\//, async (route) => {
    const r = route.request(); const u = r.url();
    if (u.includes("/user_activity") && r.method() === "POST") { m.activity.push(...JSON.parse(r.postData() || "[]")); return route.fulfill({ status: 201, body: "" }); }
    if (u.includes("/owners")) return route.fulfill({ json: opts.owner ? [{ email: user.email }] : [] });
    if (u.includes("/user_activity")) return route.fulfill({ json: m.activity.map((a) => ({ ...a, email: user.email })) });
    return route.fulfill({ json: [] });
  });
  await page.routeWebSocket(/\/realtime\/v1\/websocket/, (ws) => {
    ws.onMessage((raw) => {
      const text = String(raw); const arr = text.startsWith("[");
      const msg = arr ? (([join_ref, ref, topic, event, payload]) => ({ join_ref, ref, topic, event, payload }))(JSON.parse(text)) : JSON.parse(text);
      const send = (topic: string, event: string, payload: any, ref: string | null = null) =>
        ws.send(arr ? JSON.stringify([msg.join_ref ?? null, ref, topic, event, payload]) : JSON.stringify({ topic, event, payload, ref }));
      if (msg.event === "heartbeat" || msg.event === "access_token") return send(msg.topic, "phx_reply", { status: "ok", response: {} }, msg.ref);
      if (msg.event === "phx_join") {
        send(msg.topic, "phx_reply", { status: "ok", response: { postgres_changes: [] } }, msg.ref);
        send(msg.topic, "presence_state", { "tab-1": { metas: [{ phx_ref: "p1", at: new Date().toISOString() }] } });
      }
      if (msg.event === "presence") send(msg.topic, "phx_reply", { status: "ok", response: {} }, msg.ref);
    });
  });
  return m;
}

/** sign up through the gate when the wall is on; does nothing when the app opens directly */
export async function enter(page: Page) {
  const gate = page.locator("#gate");
  // the gate is drawn after the saved-session check, so wait for whichever comes first: the gate, or the app starting
  await Promise.race([gate.waitFor({ state: "visible", timeout: 30000 }), page.locator("#boot").waitFor({ state: "detached", timeout: 30000 })]).catch(() => {});
  if (await gate.count() && await gate.isVisible()) {
    await gate.locator("input[name=name]").fill("Tester");
    await gate.locator("input[name=email]").fill("tester@example.org");
    await gate.locator("input[name=password]").fill("correct horse battery");
    await gate.locator("button[type=submit]").click();
    await gate.waitFor({ state: "detached", timeout: 20000 });
  }
}
