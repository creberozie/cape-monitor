// Activity log: key actions (sign-in, sign-up, district, tab, dossier or profile opened, export) are written to the
// Supabase table user_activity for signed-in users. Without Supabase, or when offline, actions wait in a small queue in this
// browser (at most 200; oldest dropped) and are sent on the next successful flush. Anonymous visitors are never logged.
import { backend } from "./backend";
import { ACCESS } from "./config";

export interface Action { action: string; detail?: Record<string, unknown>; district?: string; at: string }
const KEY = "cm-activity-queue";
const MAX = 200;
let userId: string | null = null;
let flushing = false;

const read = (): Action[] => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
const write = (q: Action[]) => { try { localStorage.setItem(KEY, JSON.stringify(q.slice(-MAX))); } catch { /* storage full or blocked */ } };
export const queued = () => read();
export function setUser(id: string | null) { userId = id; if (id) void flush(); }

export function track(action: string, detail: Record<string, unknown> = {}) {
  if (!userId) return;   // only signed-in users are logged
  const district = new URLSearchParams(location.search).get("d") || "";
  write([...read(), { action, detail, district, at: new Date().toISOString() }]);
  void flush();
}

export async function flush() {
  if (flushing || !userId || !ACCESS.configured) return;
  const q = read(); if (!q.length) return;
  flushing = true;
  try {
    const sb = await backend(); if (!sb) return;
    const { error } = await sb.from("user_activity").insert(q.map((a) => ({ action: a.action, detail: a.detail, district: a.district, at: a.at })));
    if (!error) write(read().slice(q.length));
  } catch { /* offline: keep the queue */ } finally { flushing = false; }
}
addEventListener("online", () => void flush());
