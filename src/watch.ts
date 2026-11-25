// Stellenbosch Watch: Cape Monitor's money views for Stellenbosch Municipality (WC024), money and governance first, no map.
// Data: ../data/muni/stellenbosch/ (built by pipeline/metro with MUNI=stellenbosch). Profiles open in the right-hand panel.
import "./styles.css";
import "./watch.css";
import { getJSON } from "./data";
import { esc, fmt, money as rand } from "./i18n";
import { bars, columns, short, bindWatch, exportCSV, toast } from "./util";
import { accessGate } from "./access/gate";
import { configureMoney, moneyMeta, tableView, supplierList, flagList, deptList, openSupplier, openTender, openFlag, openDepartment, bindMoney, suppliers, flagsData, allRows,
  supNames, type Flag } from "./money";

const $ = (s: string) => document.querySelector(s) as HTMLElement;
const ROOT = "../data/muni/stellenbosch/";

configureMoney(ROOT, {
  scope: "Stellenbosch Municipality's award registers, bid-opening registers and eTender records", awards: "Tenders awarded by Stellenbosch Municipality",
  bids: "Bids read out at Stellenbosch tender openings (OCR)", et: "eTender portal (Stellenbosch Municipality)", rfq: "Formal quotations awarded", land: "Land",
  tender: "Stellenbosch tender or quotation", notender: "No Stellenbosch record with this number in this build.", factAwards: "tender awards", factRfq: "quotations awarded",
  bidsRead: "bids read (OCR)", refCols: ["ref", "number", "tracking"],
  supHeads: [[1, "Supplier"], [2, "Tender awards"], [3, "Value of tender awards"], [4, "Quotations"], [5, "Quotation value"], [6, "Bids read (OCR)"], [7, "eTenders"], [11, "Flags"], [14, "Also in Cape Town records"]],
  awardCols: ["date", "ref", "desc", "value_text", "bbbee", "completion", "doc"], bidCols: ["closing", "ref", "desc", "price_text", "rank", "n_bids", "conf", "doc"],
  rfqCols: ["date", "tracking", "group_text", "value_text", "bbbee", "doc"], tenderAwardCols: ["date", "vendor", "value_text", "bbbee", "closing", "completion", "sup", "doc"],
  tenderBidCols: ["n", "bidder", "price_text", "rank", "hdi", "conf", "doc"],
  flagCols: { rfq: ["date", "tracking", "group_text", "supplier", "value_text", "doc"], awards: ["date", "ref", "desc", "vendor", "value_text", "doc"],
    bids: ["closing", "ref", "bidder", "price_text", "rank", "n_bids", "conf", "doc"], etenders: ["published", "number", "buyer", "desc", "awards", "official"] },
  tenderRef: (e: any) => { const m = String(e.tender_No || "").match(/\b(B\s*\/?\s*SM|FQ\s*\/?\s*(?:SM)?)\s*\d{1,3}\s*\/\s*\d\d\b/i); return m ? m[0] : null; },
  refKey: (ref: string) => { const r = ref.replace(/\s/g, "").toUpperCase(); const m = r.match(/^(B\/?SM|FQ(?:\/?SM)?|RFQ)[-:/]?0*(\d+)\/(\d\d)/);
    return m ? (m[1].startsWith("B") ? "BSM" : m[1].startsWith("FQ") ? "FQ" : "RFQ") + `${+m[2]}/${m[3]}` : r.replace(/^0+/, ""); },
});

// severity: how directly a pattern points at a rule (restricted list, threshold, price) rather than at a habit (repeat, co-bidding)
const SEV: Record<string, number> = { restricted: 1, split: 1, notlowest: 1, deviation: 2, growth: 2, near: 2, official: 2, phone: 2, single: 3, repeat: 3, cobid: 3, young: 2 };
const SEVL = ["", "High", "Medium", "Low"];
const rankFlags = (F: Flag[]) => [...F].sort((a, b) => (SEV[a.kind] || 3) - (SEV[b.kind] || 3) || (b.value || 0) - (a.value || 0) || b.records.length - a.records.length);

const TABS: [string, string][] = [["overview", "Overview"], ["flags", "Pattern flags"], ["suppliers", "Suppliers"], ["awards", "Tenders awarded"], ["rfq", "Quotations"],
  ["bids", "Bids read out"], ["etenders", "eTenders"], ["departments", "Departments"], ["finance", "Finances and audit"], ["notices", "Notices and courts"], ["docs", "Documents"], ["sources", "Sources"]];
let tab = "overview";
const body = () => $("#dockbody");

async function openTab(k: string) {
  tab = k; $("#tabs").querySelectorAll("button").forEach((b) => b.classList.toggle("on", (b as HTMLElement).dataset.tab === k));
  const el = body(); el.scrollTop = 0;
  try {
    if (k === "overview") await overview(el);
    else if (k === "flags") await flagList(el);
    else if (k === "suppliers") await supplierList(el);
    else if (k === "departments") await departments(el);
    else if (k === "finance") await finance(el);
    else if (k === "sources") await sources(el);
    else if (k === "notices") await notices(el);
    else await tableView(k, el);
  } catch (e) { el.innerHTML = `<div class="empty">This part is not in this build yet (${esc(e)}).</div>`; }
}

const kpi = (v: any, l: string, tabk = "") => `<div class="kpi${tabk ? " click" : ""}" ${tabk ? `data-go="${tabk}" style="cursor:pointer"` : ""}><b>${v}</b><span>${esc(l)}</span></div>`;
const fy = (y: number) => `${y - 1}/${String(y).slice(2)}`;

async function overview(el: HTMLElement) {
  el.innerHTML = `<div class="empty">Loading…</div>`;
  const [m, F, S, names, fin, aud] = await Promise.all([moneyMeta(), flagsData(), suppliers(), supNames(), getJSON<any>(ROOT + "finance.json").catch(() => null), getJSON<any>(ROOT + "audit.json").catch(() => null)]);
  const [aw, fq] = await Promise.all([allRows("awards").catch(() => []), allRows("rfq").catch(() => [])]);
  const c = m.counts; const flags = rankFlags(F.flags);
  const top = [...S.rows].sort((a, b) => (b[3] + b[5]) - (a[3] + a[5])).filter((r) => r[3] + r[5] > 0).slice(0, 12);
  const latest = [...aw.map((r) => ({ d: r[0], ref: r[1], desc: r[5], sup: r[12]?.[0], name: r[6], v: r[7], kind: "Tender" })),
    ...fq.map((r) => ({ d: r[0], ref: r[1], desc: r[4], sup: r[8], name: r[5], v: r[11], kind: "Quotation" }))].sort((a, b) => String(b.d).localeCompare(String(a.d))).slice(0, 14);
  const U = fin?.uifw?.rows || []; const years = [...new Set(U.map((r: any) => r.year))].sort() as number[];
  const uv = (y: number, k: string) => U.find((r: any) => r.year === y && r.item === k)?.amount;
  const restricted = F.flags.filter((f) => f.kind === "restricted").length; const ct = S.fields.indexOf("cape_town");
  el.innerHTML = `<div class="kpis">${kpi(fmt(c.awards || 0), "tender award rows", "awards")}${kpi(fmt(c.rfq || 0), "quotations awarded", "rfq")}${kpi(fmt(c.bids || 0), "bids read out (OCR)", "bids")}
      ${kpi(fmt(c.etenders || 0), "eTender records", "etenders")}${kpi(fmt(c.suppliers), "supplier profiles", "suppliers")}${kpi(fmt(c.flags), "pattern flags", "flags")}
      ${kpi(fmt(restricted), "restricted-list name matches", "flags")}${ct >= 0 ? kpi(fmt(S.rows.filter((r) => r[ct]).length), "also in Cape Town records", "suppliers") : ""}</div>
    <div class="wgrid">
      <div class="tile"><div class="caps">Pattern flags, highest severity and value first</div>
        ${flags.slice(0, 12).map((f) => `<div class="row" data-flag="${esc(f.id)}"><span class="t"><span class="sev s${SEV[f.kind] || 3}">${SEVL[SEV[f.kind] || 3]}</span>${esc(f.title)}</span><small>${f.value ? short(f.value) : fmt(f.records.length) + " rec."}</small></div>`).join("") || `<div class="empty">No pattern flags in this build.</div>`}
        <div class="note">${esc(F.note)}</div><button class="mini" data-go="flags">All ${fmt(F.flags.length)} flags</button></div>
      <div class="tile"><div class="caps">Largest suppliers by value of published awards and quotations</div>${bars(top.map((r) => [r[1], r[3] + r[5]] as [string, number]), 12, short, "supname")}
        <div class="note">Counts each published amount naming the supplier. Rates-based awards (no single total) add nothing to value; see Suppliers for counts.</div></div>
      <div class="tile wide"><div class="caps">Irregular, fruitless and unauthorised expenditure (audited, per financial year)</div>
        ${years.length ? `<div class="tscroll"><table class="t"><thead><tr><th>Year</th><th class="num">Irregular</th><th class="num">Fruitless and wasteful</th><th class="num">Unauthorised</th><th>Audit opinion</th></tr></thead><tbody>
        ${years.slice().reverse().slice(0, 10).map((y) => { const o = aud?.rows?.find((r: any) => r.year === y); return `<tr><td class="mono">${fy(y)}</td><td class="num mono">${uv(y, "irregular") != null ? rand(uv(y, "irregular")) : "—"}</td><td class="num mono">${uv(y, "fruitless") != null ? rand(uv(y, "fruitless")) : "—"}</td><td class="num mono">${uv(y, "unauthorised") != null ? rand(uv(y, "unauthorised")) : "—"}</td><td>${o ? (o.report ? `<a href="${esc(o.report)}" target="_blank" rel="noopener">${esc(o.opinion)}</a>` : esc(o.opinion)) : ""}</td></tr>`; }).join("")}</tbody></table></div>
        <div class="note">National Treasury Municipal Money, from the notes to the audited annual financial statements; audit opinions from Treasury's audit-opinion data with the Auditor-General's report linked. <button class="mini" data-go="finance">Finances and audit</button></div>` : `<div class="empty">Not in this build.</div>`}</div>
      <div class="tile"><div class="caps">Departments</div><div id="ov-dep"></div>
        <div class="note">Stellenbosch's award registers do not name the directorate, and it publishes no deviations register (see Sources). Departments here are those the eTender portal names.</div></div>
      <div class="tile" style="grid-column:1/-1"><div class="caps">Latest awards</div><div class="tscroll"><table class="t"><thead><tr><th>Date</th><th>Number</th><th>Kind</th><th>Description</th><th>Awarded to</th><th>Amount as published</th></tr></thead><tbody>
        ${latest.map((r) => `<tr><td class="mono">${esc(r.d || "")}</td><td><a href="#t=${esc(r.ref)}" data-tender="${esc(r.ref)}">${esc(r.ref)}</a></td><td>${r.kind}</td><td>${esc(String(r.desc || "").slice(0, 140))}</td><td>${r.sup ? `<a href="#s=${esc(r.sup)}" data-sup="${esc(r.sup)}">${esc(names.get(r.sup) || r.name)}</a>` : esc(r.name)}</td><td class="mono">${esc(r.v || "")}</td></tr>`).join("")}</tbody></table></div></div>
    </div>`;
  const D = await getJSON<any[]>(ROOT + "money/departments.json").catch((): any[] => []);
  const dep = el.querySelector("#ov-dep") as HTMLElement | null;
  if (dep) dep.innerHTML = D.slice(0, 10).map((d) => `<div class="row" data-dept="${D.indexOf(d)}"><span class="t">${esc(d.name.replace(/^Stellenbosch Municipality: /, ""))}</span><small>${fmt(d.n)} records${d.value ? " · " + short(d.value) : ""}</small></div>`).join("");
  el.querySelectorAll("[data-supname]").forEach((b) => (b as HTMLElement).onclick = () => { const r = top.find((x) => x[1] === (b as HTMLElement).dataset.supname); if (r) openSupplier(r[0]); });
}

async function departments(el: HTMLElement) {
  await deptList(el);
  el.insertAdjacentHTML("afterbegin", `<div class="note warnbox">Stellenbosch publishes its tender and quotation awards without the directorate, and publishes no deviations register. Departments below are the
    municipality's registers as a whole and the departments named on the eTender portal. Irregular expenditure is published for the municipality as a whole: see Finances and audit.</div>`);
}

async function finance(el: HTMLElement) {
  const [fin, aud] = await Promise.all([getJSON<any>(ROOT + "finance.json"), getJSON<any>(ROOT + "audit.json").catch(() => null)]);
  const rows = fin.rows as any[]; const years = [...new Set(rows.map((r) => r.year))].sort() as number[];
  const items: [string, string][] = [["2900", "Total revenue (excluding capital transfers)"], ["4400", "Total expenditure"], ["3100", "Employee related costs"], ["3800", "Contracted services"], ["3400", "Inventory consumed"], ["4100", "Operational cost"], ["4500", "Surplus / (deficit)"]];
  const v = (y: number, t: string, i: string) => rows.find((r) => r.year === y && r.type === t && r.item === i)?.amount;
  const cell = (n: any) => n == null ? `<td class="num dim">—</td>` : `<td class="num mono">${rand(n)}</td>`;
  const U = fin.uifw.rows as any[]; const uy = [...new Set(U.map((r) => r.year))].sort() as number[];
  el.innerHTML = `<div class="toolbar"><b>Stellenbosch Municipality (WC024): finances and audit outcomes</b><button class="tb" id="fx">Export CSV</button>
      <span class="note">Source: <a href="${esc(fin.url)}" target="_blank" rel="noopener">National Treasury Municipal Money</a> (data API <a href="${esc(fin.api)}" target="_blank" rel="noopener">${esc(fin.api)}</a>), updated ${esc(String(fin.data_updated || "").slice(0, 10))}, fetched ${esc(fin.retrieved.slice(0, 10))}.</span></div>
    <h3>Budget against audited actual (rand, financial year ending June)</h3>
    <div class="tscroll"><table class="t"><thead><tr><th>Item</th><th>Year</th><th class="num">Original budget</th><th class="num">Adjusted budget</th><th class="num">Audited actual</th><th class="num">Actual less adjusted budget</th></tr></thead><tbody>
    ${items.map(([i, l]) => years.slice().reverse().filter((y) => v(y, "ORGB", i) != null || v(y, "AUDA", i) != null).slice(0, 6).map((y, k) => { const a = v(y, "AUDA", i), b = v(y, "ADJB", i);
      return `<tr><td>${k ? "" : esc(l)}</td><td class="mono">${fy(y)}</td>${cell(v(y, "ORGB", i))}${cell(b)}${cell(a)}${a != null && b != null ? cell(a - b) : cell(null)}</tr>`; }).join("")).join("")}</tbody></table></div>
    <div class="note">Amounts as published by Treasury (mSCOA section 71 aggregation). A blank means Treasury publishes no figure for that year and type.</div>
    <h3>Unauthorised, irregular, fruitless and wasteful expenditure</h3>
    <div class="tscroll"><table class="t"><thead><tr><th>Year</th><th class="num">Irregular</th><th class="num">Fruitless and wasteful</th><th class="num">Unauthorised</th></tr></thead><tbody>
    ${uy.slice().reverse().map((y) => { const g = (k: string) => U.find((r) => r.year === y && r.item === k)?.amount; return `<tr><td class="mono">${fy(y)}</td>${cell(g("irregular"))}${cell(g("fruitless"))}${cell(g("unauthorised"))}</tr>`; }).join("")}</tbody></table></div>
    <div class="note">${esc(fin.uifw.title)}. Data API: <a href="${esc(fin.uifw.api)}" target="_blank" rel="noopener">${esc(fin.uifw.api)}</a>. Shown exactly as published, including repeated values.</div>
    ${aud ? `<h3>Audit outcomes (Auditor-General)</h3><div class="tscroll"><table class="t"><thead><tr><th>Year</th><th>Opinion</th><th>Audit report</th></tr></thead><tbody>
      ${aud.rows.map((o: any) => `<tr><td class="mono">${fy(o.year)}</td><td class="opinion${/^unqualified - no findings/i.test(o.opinion) ? " clean" : ""}">${esc(o.opinion)}</td><td>${o.report ? `<a href="${esc(o.report)}" target="_blank" rel="noopener">Report ↗</a>` : `<span class="dim">no link published</span>`}</td></tr>`).join("")}</tbody></table></div>
      <div class="note">Source: <a href="${esc(aud.url)}" target="_blank" rel="noopener">National Treasury Municipal Money</a>, audit_opinions data set (<a href="${esc(aud.api)}" target="_blank" rel="noopener">API</a>), fetched ${esc(aud.retrieved.slice(0, 10))}. The Auditor-General's own MFMA reports: <a href="${esc(aud.agsa)}" target="_blank" rel="noopener">agsa.co.za</a>.</div>` : ""}`;
  (el.querySelector("#fx") as HTMLElement).onclick = () => exportCSV("stellenbosch-finances", ["year_end", "type", "item", "label", "amount"], [...rows.map((r) => [r.year, r.type_label, r.item, r.label, r.amount]),
    ...U.map((r) => [r.year, "Audited (AFS notes)", r.item, r.label, r.amount])], `Stellenbosch Municipality (WC024). Source: National Treasury Municipal Money ${fin.api}, fetched ${fin.retrieved}.`);
}

let nq = "";
async function notices(el: HTMLElement) {
  const [N, J] = await Promise.all([getJSON<any>(ROOT + "notices.json").catch(() => null), getJSON<any>(ROOT + "justice.json").catch(() => null)]);
  const q = nq.toLowerCase(); const hit = (x: any) => !q || JSON.stringify([x.title, x.kind, x.places, x.issuer, x.parties, x.subject]).toLowerCase().includes(q);
  const ns = (N?.notices || []).filter(hit); const cs = (J?.items || []).filter(hit);
  el.innerHTML = `<div class="toolbar"><b>Notices and courts</b><input class="nq" placeholder="Filter: place, kind, party…" value="${esc(nq)}" aria-label="Filter notices"></div>
    <h3>Western Cape Provincial Gazette: notices naming a Stellenbosch place<span class="c">${fmt(ns.length)}</span></h3>
    ${N ? `<div class="note">Source: <a href="${esc(N.url)}" target="_blank" rel="noopener">Western Cape Provincial Gazette (Department of the Premier)</a>, years ${esc((N.source?.years || []).join(", "))}, read ${esc(String(N.built).slice(0, 10))}. A notice is listed when it names one of: ${esc((N.places || []).join(", "))}.</div>
      ${ns.slice(0, 200).map((n: any) => `<div class="feeditem"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title || n.issuer)}</a><div class="meta">${esc(n.date)} · ${esc(n.gazette)} · ${esc(n.kind)} · ${esc(n.issuer)} · names ${esc(n.places.join(", "))}${n.erfs?.length ? " · erf " + esc(n.erfs.slice(0, 6).join(", ")) : ""}</div></div>`).join("") || `<div class="empty">None in this build.</div>`}` : `<div class="empty">Gazette notices are not in this build yet.</div>`}
    <h3>Competition Tribunal: decided cases naming a Stellenbosch place or supplier<span class="c">${fmt(cs.length)}</span></h3>
    ${J ? `<div class="note">Source: <a href="${esc(J.source.url)}" target="_blank" rel="noopener">${esc(J.source.name)}</a>, fetched ${esc(String(J.source.retrieved || "").slice(0, 10))}.</div>
      ${cs.slice(0, 200).map((c: any) => `<div class="feeditem"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.parties)}</a><div class="meta">${esc(c.case || "")} · ${esc(c.type || "")} · ${esc(c.date || "")}${c.places?.length ? " · names " + esc(c.places.join(", ")) : ""}${c.suppliers?.length ? " · supplier in Stellenbosch records: " + c.suppliers.map((s: string) => `<a href="#s=${esc(s)}" data-sup="${esc(s)}">${esc(s)}</a>`).join(", ") : ""}</div></div>`).join("") || `<div class="empty">None in this build.</div>`}` : `<div class="empty">Tribunal cases are not in this build yet.</div>`}`;
  let tm: any; (el.querySelector(".nq") as HTMLInputElement).oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { nq = (e.target as HTMLInputElement).value; notices(el).then(() => { const i = el.querySelector(".nq") as HTMLInputElement; i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 250); };
}

async function sources(el: HTMLElement) {
  const [S, m] = await Promise.all([getJSON<any>(ROOT + "sources.json"), moneyMeta()]);
  el.innerHTML = `<div class="toolbar"><b>Sources</b><span class="note">Built ${esc(String(S.built).slice(0, 16).replace("T", " "))} UTC. Every record in this app links to the document it was read from.</span></div>
    <div class="tscroll"><table class="t"><thead><tr><th>Source</th><th class="num">Records</th><th>Published</th><th>Fetched</th><th>Notes</th></tr></thead><tbody>
    ${S.sources.map((s: any) => `<tr><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a></td><td class="num mono">${fmt(s.n)}</td><td class="mono">${esc(s.published || "")}</td><td class="mono">${esc(s.retrieved)}</td>
      <td class="sm">${esc(s.note || "")}${(s.warnings || []).map((w: string) => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}</td></tr>`).join("")}</tbody></table></div>
    <h3>Competitive-bidding threshold used in the flags</h3>${S.thresholds.map((t: any) => `<div class="note"><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.text)}</a></div>`).join("")}
    <h3>Not added, and why</h3>${S.not_added.map((n: any) => `<div class="feeditem"><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.name)}</a><div class="meta">${esc(n.why)}</div></div>`).join("")}
    <h3>Limits</h3><div class="note">Suppliers are identified by published name only (normalised for case, punctuation and suffixes). Names read by OCR are also matched ignoring spaces, because OCR often drops them; nothing else is merged.
    A pattern flag is a pattern in published data, not a finding. Restricted-list matches are name matches only. Some records name private individuals exactly as the municipality published them.</div>
    <div class="note">Money tables in this build: ${Object.values(m.tables).map((t: any) => `${esc(t.name)} (${fmt(t.n)})`).join("; ")}.</div>`;
}

// ---------------------------------------------------------------- search: supplier, tender or quotation number, department
let searchRows: Promise<{ l: string; s: string; go: () => void; k: string }[]> | null = null;
function searchIndex() {
  return searchRows ??= (async () => {
    const [S, aw, fq, bd, et, D] = await Promise.all([suppliers(), allRows("awards").catch(() => []), allRows("rfq").catch(() => []), allRows("bids").catch(() => []), allRows("etenders").catch(() => []),
      getJSON<any[]>(ROOT + "money/departments.json").catch((): any[] => [])]);
    const out: { l: string; s: string; go: () => void; k: string }[] = [];
    for (const r of S.rows) out.push({ l: r[1], s: `supplier · ${fmt(r[2] + r[4] + r[6] + r[7])} records`, go: () => openSupplier(r[0]), k: String(r[1]).toLowerCase() });
    const refs = new Map<string, string>();
    for (const r of aw) if (!refs.has(r[1])) refs.set(r[1], r[5] || "");
    for (const r of fq) if (!refs.has(r[1])) refs.set(r[1], r[4] || "");
    for (const r of bd) if (!refs.has(r[1])) refs.set(r[1], r[2] || "");
    for (const r of et) if (/^\s*(B\s*\/?\s*SM|FQ)/i.test(String(r[1])) && !refs.has(r[1])) refs.set(r[1], r[5] || "");
    for (const [ref, d] of refs) out.push({ l: `${ref}: ${String(d).slice(0, 90)}`, s: "tender or quotation", go: () => openTender(ref), k: (ref + " " + ref.replace(/[\s/]/g, "") + " " + d).toLowerCase() });
    D.forEach((d, i) => out.push({ l: d.name, s: `department · ${fmt(d.n)} records`, go: () => openDepartment(i), k: d.name.toLowerCase() }));
    return out;
  })();
}
function bindSearch() {
  const q = $("#q") as HTMLInputElement, box = $("#results"); let tm: any, res: any[] = [], k = -1;
  const run = async () => {
    const v = q.value.trim().toLowerCase(); if (!v) { box.hidden = true; return; }
    const vv = v.replace(/[\s/]/g, ""); const all = await searchIndex();
    res = all.filter((r) => r.k.includes(v) || (vv.length >= 3 && r.k.replace(/[\s/]/g, "").includes(vv))).sort((a, b) => Number(b.k.startsWith(v)) - Number(a.k.startsWith(v))).slice(0, 14); k = 0;
    box.innerHTML = res.length ? res.map((r, n) => `<div class="res${n === 0 ? " on" : ""}" role="option" data-n="${n}"><span>${esc(r.l)}</span><small>${esc(r.s)}</small></div>`).join("")
      : `<div class="res dim">No match. Try a company name, a tender number (B/SM 25/27), a quotation number (FQ 29/27) or a department.</div>`;
    box.hidden = false;
  };
  q.oninput = () => { clearTimeout(tm); tm = setTimeout(run, 150); };
  q.onkeydown = async (e) => { if (e.key === "Enter") { e.preventDefault(); clearTimeout(tm); await run(); res[Math.max(0, k)]?.go(); box.hidden = true; q.blur(); } else if (e.key === "Escape") box.hidden = true;
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") { k = Math.max(0, Math.min(res.length - 1, k + (e.key === "ArrowDown" ? 1 : -1))); box.querySelectorAll(".res").forEach((el, n) => el.classList.toggle("on", n === k)); e.preventDefault(); } };
  box.onmousedown = (e) => { const el = (e.target as HTMLElement).closest("[data-n]") as HTMLElement | null; if (el) { e.preventDefault(); res[+el.dataset.n!].go(); box.hidden = true; q.blur(); } };
  q.onblur = () => setTimeout(() => (box.hidden = true), 150);
}

// share links: #s=<supplier> #t=<tender> #fl=<flag> #dep=<n> #tab=<section>
function openHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (h.startsWith("s=")) return openSupplier(h.slice(2));
  if (h.startsWith("t=")) return openTender(h.slice(2));
  if (h.startsWith("fl=")) return openFlag(h.slice(3));
  if (h.startsWith("dep=")) return openDepartment(+h.slice(4));
  if (h.startsWith("tab=") && TABS.some(([k]) => k === h.slice(4))) return openTab(h.slice(4));
}

async function boot() {
  await accessGate("STELLENBOSCH WATCH", "Public records of Stellenbosch Municipality, joined and sourced.");
  let m;
  try { m = await moneyMeta(); } catch { $("#bootmsg").textContent = "The Stellenbosch data is not in this build yet."; return; }
  $("#fresh").innerHTML = `Data <b>${esc(m.built.slice(0, 10))}</b>`;
  $("#tabs").innerHTML = TABS.map(([k, l]) => `<button data-tab="${k}">${l}</button>`).join("");
  $("#tabs").onclick = (e) => { const b = (e.target as HTMLElement).closest("[data-tab]") as HTMLElement | null; if (b) { history.replaceState(null, "", "#tab=" + b.dataset.tab); openTab(b.dataset.tab!); } };
  body().addEventListener("click", (e) => { const g = (e.target as HTMLElement).closest("[data-go]") as HTMLElement | null; if (g) openTab(g.dataset.go!); });
  bindMoney($("#right"), body()); bindWatch($("#right")); bindWatch(body()); bindSearch();
  $("#right").addEventListener("click", async (e) => { const sh = (e.target as HTMLElement).closest("[data-share]") as HTMLElement | null; if (!sh) return;
    const u = location.href.split("#")[0] + "#" + sh.dataset.share; try { await navigator.clipboard.writeText(u); sh.textContent = "Link copied"; } catch { sh.textContent = u; } });
  $("#closeinspect").onclick = () => document.body.classList.remove("inspect");
  addEventListener("keydown", (e) => { if (e.key === "Escape") document.body.classList.remove("inspect"); });
  let deferred: any = null;
  addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; $("#install").hidden = false; });
  $("#install").onclick = async () => { if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; $("#install").hidden = true; } };
  if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => {});
  const h = decodeURIComponent(location.hash.slice(1));
  await openTab(h.startsWith("tab=") && TABS.some(([k]) => k === h.slice(4)) ? h.slice(4) : "overview");
  addEventListener("hashchange", openHash);
  if (h && !h.startsWith("tab=")) openHash();
  $("#boot").remove();
}
boot().catch((e) => { toast(String(e)); });

