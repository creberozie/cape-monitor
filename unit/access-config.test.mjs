// Unit tests for the access switch. Run: node --experimental-strip-types --test unit/
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/access/config.ts";

// the module reads import.meta.env at load; in Node that is undefined and parseConfig is tested directly
const sb = { VITE_SUPABASE_URL: "https://abcd.supabase.co", VITE_SUPABASE_ANON_KEY: "x".repeat(40) };
test("no Supabase: always open, whatever the switch says", () => {
  for (const v of [undefined, "true", "false", ""]) assert.equal(parseConfig({ VITE_REQUIRE_ACCOUNT_ACCESS: v }).requireAccount, false);
});
test("Supabase configured: wall on by default, and when the switch is empty", () => {
  assert.equal(parseConfig(sb).requireAccount, true);
  assert.equal(parseConfig({ ...sb, VITE_REQUIRE_ACCOUNT_ACCESS: "" }).requireAccount, true);
  assert.equal(parseConfig({ ...sb, VITE_REQUIRE_ACCOUNT_ACCESS: "true" }).requireAccount, true);
});
test("one switch opens the app", () => {
  for (const v of ["false", "FALSE", " 0 ", "no", "off"]) assert.equal(parseConfig({ ...sb, VITE_REQUIRE_ACCOUNT_ACCESS: v }).requireAccount, false, v);
});
test("bad URL or short key counts as not configured", () => {
  assert.equal(parseConfig({ ...sb, VITE_SUPABASE_URL: "http://abcd.supabase.co" }).configured, false);
  assert.equal(parseConfig({ ...sb, VITE_SUPABASE_ANON_KEY: "short" }).configured, false);
  assert.equal(parseConfig({ ...sb, VITE_SUPABASE_URL: "https://abcd.supabase.co/" }).supabaseUrl, "https://abcd.supabase.co");
});
