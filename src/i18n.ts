// Interface words in English and Afrikaans. Source records stay exactly as recorded.
const W = {
  en: { search: "Search erf, address, suburb, supplier, tender no., layer…", layers: "Layers", findlayer: "Locate layer…", presets: "Quick views", brief: "Situation Report", activity: "Incident Log",
    feed: "Press Monitor", spending: "City spending", records: "Records", sources: "Sources", heritage: "Historical Record", plot: "Erf", alsohere: "Also at this point",
    nothing: "No mapped feature at this position in the active layers.", zoomplot: "Erf selection requires a closer scale.",
    allfields: "All fields, as recorded", showempty: "Show empty fields", zones: "Zoning, overlays and jurisdictions", recs: "Records on this erf",
    plans: "Building plan submissions", requests: "Incidents and Service Requests logged on this erf", sales: "State disposals", near: "Nearest services", share: "Share link", copied: "Link copied",
    cityrec: "Municipal Source record", fresh: "Data", install: "Install", offline: "Offline: showing saved data", loading: "Loading…", district: "District", suburb: "Suburb",
    ward: "Ward", total: "Total", latest: "Latest", none: "None recorded", left: "left out", why: "why", money: "Money", justice: "Justice", watchlist: "Watchlist", notices: "Notices", labour: "Labour", users: "Users" },
  af: { search: "Soek erf, adres, voorstad, verskaffer, tendernr., laag…", layers: "Lae", findlayer: "Vind laag…", presets: "Vinnige aansigte", brief: "Situasieverslag", activity: "Insidentlogboek",
    feed: "Persmonitor", spending: "Stadsbesteding", records: "Rekords", sources: "Bronne", heritage: "Historiese Rekord", plot: "Erf", alsohere: "Ook op hierdie punt",
    nothing: "Geen gekarteerde kenmerk op hierdie posisie in die aktiewe lae nie.", zoomplot: "Erfkeuse vereis 'n nader skaal.",
    allfields: "Alle velde, soos aangeteken", showempty: "Wys leë velde", zones: "Sonering, oorlegte en jurisdiksies", recs: "Rekords op hierdie erf",
    plans: "Bouplanvoorleggings", requests: "Insidente en diensversoeke op hierdie erf", sales: "Staatsvervreemdings", near: "Naaste dienste", share: "Deel skakel", copied: "Skakel gekopieer",
    cityrec: "Munisipale bronrekord", fresh: "Data", install: "Installeer", offline: "Vanlyn: gestoorde data", loading: "Laai…", district: "Distrik", suburb: "Voorstad",
    ward: "Wyk", total: "Totaal", latest: "Nuutste", none: "Niks aangeteken nie", left: "uitgelaat", why: "hoekom", money: "Geld", justice: "Justisie", watchlist: "Dophou", notices: "Kennisgewings", labour: "Arbeid", users: "Gebruikers" },
};
export type Key = keyof typeof W.en;
const ls = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
export let LANG: "en" | "af" = (ls("cm-lang") as any) || "en";
export const t = (k: Key) => W[LANG][k] ?? W.en[k];
export const setLang = (l: "en" | "af") => { LANG = l; try { localStorage.setItem("cm-lang", l); } catch { /* private mode */ } };
export const esc = (s: any) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
export const fmt = (n: number) => Number(n).toLocaleString("en-ZA");
export const money = (n: number) => "R " + Math.round(Number(n)).toLocaleString("en-ZA");
