// Owner view (bottom panel tab "Users"): who has been active and what they did, read from user_activity. The database
// lets only e-mail addresses listed in the owners table read it, so this view is empty for everyone else.
import { backend } from "./backend";

export async function ownerView(host: HTMLElement, esc: (s: any) => string, exportCSV: (n: string, h: string[], r: any[][], s?: string) => void) {
  const sb = await backend(); if (!sb) { host.innerHTML = `<div class="empty">Accounts are not configured.</div>`; return; }
  const since = new Date(Date.now() - 15 * 60 * 1000).toISOString();
  const { data, error } = await sb.from("user_activity").select("at,email,action,district,detail").order("at", { ascending: false }).limit(500);
  if (error) { host.innerHTML = `<div class="empty">Not available: ${esc(error.message)}</div>`; return; }
  const rows = data || []; const active = [...new Set(rows.filter((r: any) => r.at >= since).map((r: any) => r.email))];
  host.innerHTML = `<div class="toolbar"><b>Active in the last 15 minutes: ${active.length}</b><span class="note">${active.map(esc).join(", ")}</span><button class="tb" id="ov-x">Export CSV</button></div>
    <div class="tscroll"><table class="t"><thead><tr><th>When</th><th>User</th><th>Action</th><th>District</th><th>Detail</th></tr></thead><tbody>
    ${rows.map((r: any) => `<tr><td class="mono">${esc(String(r.at).slice(0, 19).replace("T", " "))}</td><td>${esc(r.email)}</td><td>${esc(r.action)}</td><td>${esc(r.district || "")}</td><td class="sm">${esc(JSON.stringify(r.detail || {}))}</td></tr>`).join("")}</tbody></table></div>`;
  (host.querySelector("#ov-x") as HTMLElement).onclick = () => exportCSV("user-activity", ["at", "email", "action", "district", "detail"], rows.map((r: any) => [r.at, r.email, r.action, r.district, JSON.stringify(r.detail || {})]), "Cape Monitor user_activity (owner view)");
}
