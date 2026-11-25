// Interface words in English and Afrikaans. Source records stay exactly as recorded.
const W = {
  en: { search: "Search erf, address, suburb, supplier, tender no., layer…", layers: "Layers", findlayer: "Find a layer…", presets: "Quick views", brief: "Brief", activity: "Activity",
    feed: "Feed", spending: "City spending", records: "Records", sources: "Sources", heritage: "Heritage", plot: "Plot", alsohere: "Also at this point",
    nothing: "Nothing mapped at this point in the visible layers. Switch on more layers on the left, or zoom in to pick a plot.", zoomplot: "Zoom in to select a plot.",
    allfields: "All fields, as recorded", showempty: "Show empty fields", zones: "Zones, overlays and areas covering this plot", recs: "Records on this plot",
    plans: "Building plans", requests: "Service requests on this plot", sales: "Sold by the City", near: "Nearest services", share: "Share link", copied: "Link copied",
    cityrec: "City record", fresh: "Data", install: "Install", offline: "Offline: showing saved data", loading: "Loading…", district: "District", suburb: "Suburb",
    ward: "Ward", total: "Total", latest: "Latest", none: "None recorded", left: "left out", why: "why", money: "Money", justice: "Justice", watchlist: "Watchlist", notices: "Notices", labour: "Labour" },
  af: { search: "Soek erf, adres, voorstad, verskaffer, tendernr., laag…", layers: "Lae", findlayer: "Soek 'n laag…", presets: "Vinnige aansigte", brief: "Opsomming", activity: "Aktiwiteit",
    feed: "Nuus", spending: "Stadsbesteding", records: "Rekords", sources: "Bronne", heritage: "Erfenis", plot: "Erf", alsohere: "Ook op hierdie punt",
    nothing: "Niks gekarteer op hierdie punt in die sigbare lae nie. Skakel meer lae aan, of zoem in om 'n erf te kies.", zoomplot: "Zoem in om 'n erf te kies.",
    allfields: "Alle velde, soos aangeteken", showempty: "Wys leë velde", zones: "Sones, oorlegte en gebiede oor hierdie erf", recs: "Rekords op hierdie erf",
    plans: "Bouplanne", requests: "Diensversoeke op hierdie erf", sales: "Deur die Stad verkoop", near: "Naaste dienste", share: "Deel skakel", copied: "Skakel gekopieer",
    cityrec: "Stadsrekord", fresh: "Data", install: "Installeer", offline: "Vanlyn: gestoorde data", loading: "Laai…", district: "Distrik", suburb: "Voorstad",
    ward: "Wyk", total: "Totaal", latest: "Nuutste", none: "Niks aangeteken nie", left: "uitgelaat", why: "hoekom", money: "Geld", justice: "Justisie", watchlist: "Dophou", notices: "Kennisgewings", labour: "Arbeid" },
};
export type Key = keyof typeof W.en;
export let LANG: "en" | "af" = (localStorage.getItem("cm-lang") as any) || "en";
export const t = (k: Key) => W[LANG][k] ?? W.en[k];
export const setLang = (l: "en" | "af") => { LANG = l; localStorage.setItem("cm-lang", l); };
export const esc = (s: any) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
export const fmt = (n: number) => Number(n).toLocaleString("en-ZA");
export const money = (n: number) => "R " + Math.round(Number(n)).toLocaleString("en-ZA");
