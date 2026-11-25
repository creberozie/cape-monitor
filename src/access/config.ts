// Access configuration, read once at build time from Vite environment variables (set as GitHub repository variables):
//   VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY   the Supabase project (the anon key is public by design; table rules protect data)
//   VITE_REQUIRE_ACCOUNT_ACCESS                 "true" (default) or "false". THE ONE SWITCH: "false" opens the app to everyone.
// The wall only switches on when Supabase is configured; without it the app is always open, so a build can never lock everyone out.
// The wall is an app-level gate: it hides the interface, not the public data files, which stay at their public addresses.
export interface AccessConfig { supabaseUrl: string; anonKey: string; configured: boolean; requireAccount: boolean }

export function parseConfig(env: Record<string, string | undefined>): AccessConfig {
  const supabaseUrl = (env.VITE_SUPABASE_URL || "").trim().replace(/\/+$/, "");
  const anonKey = (env.VITE_SUPABASE_ANON_KEY || "").trim();
  const configured = /^https:\/\/[^/]+$/.test(supabaseUrl) && anonKey.length > 20;
  const flag = (env.VITE_REQUIRE_ACCOUNT_ACCESS ?? "true").trim().toLowerCase();
  const requireAccount = configured && !["false", "0", "no", "off"].includes(flag);
  return { supabaseUrl, anonKey, configured, requireAccount };
}

export const ACCESS: AccessConfig = parseConfig((import.meta as any).env || {});
