// Live count of people using Cape Monitor, through Supabase Realtime Presence. Each open tab joins one shared channel with an
// anonymous key and no personal data, so every browser can see how many are online but not who. Without Supabase this is a
// no-op and the indicator stays hidden. Who is active, by name, is visible to the owner only (owner view, from user_activity).
import { backend } from "./backend";

let count = 0;
const listeners = new Set<(n: number) => void>();
export const onlineCount = () => count;
export function onCount(l: (n: number) => void) { listeners.add(l); l(count); return () => listeners.delete(l); }

export async function joinPresence() {
  const sb = await backend(); if (!sb) return false;
  try {
    const key = crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2);
    const ch = sb.channel("online", { config: { presence: { key } } });
    ch.on("presence", { event: "sync" }, () => { count = Object.keys(ch.presenceState()).length; listeners.forEach((l) => l(count)); });
    ch.subscribe(async (status) => { if (status === "SUBSCRIBED") await ch.track({ at: new Date().toISOString() }); });
    return true;
  } catch { return false; }
}
