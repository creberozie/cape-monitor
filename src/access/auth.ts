// Accounts: sign-up signs the new user straight in (the Supabase project must have "Confirm email" off; if it is on, the
// user is told to confirm and then signs in). Sessions persist across reloads (stored by the Supabase client).
import { backend } from "./backend";
import { setUser, track } from "./activity";

export interface User { id: string; email: string; name?: string }
let current: User | null = null;
const listeners = new Set<(u: User | null) => void>();
export const user = () => current;
export function onUser(l: (u: User | null) => void) { listeners.add(l); return () => listeners.delete(l); }
function set(u: User | null) { current = u; setUser(u?.id || null); listeners.forEach((l) => l(u)); }
const toUser = (u: any): User | null => u ? { id: u.id, email: u.email, name: u.user_metadata?.name } : null;

/** restore a saved session; true if signed in */
export async function restore() {
  const sb = await backend(); if (!sb) return false;
  const { data } = await sb.auth.getSession();
  set(toUser(data.session?.user));
  sb.auth.onAuthStateChange((_e, s) => set(toUser(s?.user)));
  return !!current;
}

export async function signUp(email: string, password: string, name: string): Promise<{ ok: boolean; message?: string }> {
  const sb = await backend(); if (!sb) return { ok: false, message: "Accounts are not configured." };
  const { data, error } = await sb.auth.signUp({ email, password, options: { data: { name } } });
  if (error) return { ok: false, message: error.message };
  if (!data.session) {   // project still asks for e-mail confirmation: try to sign in at once, else explain
    const r = await signIn(email, password, true);
    if (!r.ok) return { ok: false, message: "Account created. Confirm it from the e-mail Supabase sent, then sign in." };
  } else set(toUser(data.session.user));
  track("sign_up", {});
  return { ok: true };
}

export async function signIn(email: string, password: string, quiet = false): Promise<{ ok: boolean; message?: string }> {
  const sb = await backend(); if (!sb) return { ok: false, message: "Accounts are not configured." };
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error || !data.session) return { ok: false, message: error?.message || "Could not sign in." };
  set(toUser(data.session.user));
  if (!quiet) track("sign_in", {});
  return { ok: true };
}

export async function signOut() { const sb = await backend(); await sb?.auth.signOut(); set(null); }

/** the owner view is offered when the database lets this user read their own row in the owners table */
export async function isOwner() {
  const sb = await backend(); if (!sb || !current) return false;
  const { data, error } = await sb.from("owners").select("email").limit(1);
  return !error && !!data?.length;
}
