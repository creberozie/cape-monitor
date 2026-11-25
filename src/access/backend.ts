// The Supabase client, loaded on first use and only when Supabase is configured (open builds never download it).
import type { SupabaseClient } from "@supabase/supabase-js";
import { ACCESS } from "./config";

let client: Promise<SupabaseClient | null> | null = null;
export function backend(): Promise<SupabaseClient | null> {
  if (!ACCESS.configured) return Promise.resolve(null);
  client ??= import("@supabase/supabase-js").then(({ createClient }) => createClient(ACCESS.supabaseUrl, ACCESS.anonKey, {
    auth: { persistSession: true, autoRefreshToken: true, storageKey: "cm-auth" },
    realtime: { params: { eventsPerSecond: 2 } },
  })).catch(() => null);
  return client;
}
