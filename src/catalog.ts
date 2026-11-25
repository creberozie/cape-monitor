// How layers are presented: plain names, one entry per subject (the City publishes some layers several times),
// themes in order of everyday use, and within each theme the layers people reach for first. The rest stay one click away.
// Base: the UI-review version (Blaauwberg). Full-city additions: the Justice, Money, Notices and Live groups, and the
// mapping from this branch's merged groups (utilities, community, property) back to the review's ten groups until the
// district data is rebuilt with pipeline/themes.py.
import { M, Layer, layerById } from "./data";

export const THEME_ORDER = ["property", "community", "safety", "justice", "transport", "complaints", "environment", "heritage", "boundaries", "economy", "infra", "money", "notices", "live"];
export const THEME_NAME: Record<string, string> = {
  property: "Property and planning", complaints: "Complaints and Incident Reports", safety: "Security", infra: "Installations and Utilities", transport: "Transport and roads",
  community: "Public Facilities", economy: "Trade and Commerce", environment: "Natural environment", heritage: "Historical Record", boundaries: "Jurisdictions",
  justice: "Law and Order", money: "Money and tenders", notices: "Notices and gazettes", live: "Live" };
export const THEME_NAME_AF: Record<string, string> = {
  property: "Eiendom en beplanning", complaints: "Insidentverslae", safety: "Sekuriteit", infra: "Installasies en Nutsdienste", transport: "Vervoer en paaie",
  community: "Openbare Fasiliteite", economy: "Handel", environment: "Natuurlike omgewing", heritage: "Historiese Rekord", boundaries: "Jurisdiksies",
  justice: "Wet en Orde", money: "Geld en tenders", notices: "Kennisgewings en koerante", live: "Regstreeks" };
export const THEME_HINT: Record<string, string> = {
  property: "Erven, street numbers, zoning, servitudes", community: "Schools, libraries, clinics, halls, grounds", safety: "Fire, Koeberg zones, evacuation routes",
  transport: "Roads, MyCiTi, rail, taxi routes", complaints: "Service requests lodged with the City", environment: "Wetlands, dunes, watercourses, vegetation",
  heritage: "Graded places, protected sites, recorded finds", boundaries: "Wards, suburbs, subcouncils", economy: "Wine farms, trading bays, tourism", infra: "Power, water, sewer, stormwater",
  justice: "Police stations, courts, tribunal cases", money: "City-wide awards, bids, quotations, suppliers", notices: "Provincial Gazette notices by erf", live: "News, satellite fire detections" };
export const topWording = (s: string) => s.replace(/safety (and|&) justice/gi, "Law and Order").replace(/human settlements?/gi, "Housing").replace(/social development/gi, "Welfare");
export const themeName = (id: string, lang: "en" | "af", fallback = "") => (lang === "af" ? THEME_NAME_AF[id] : THEME_NAME[id]) || topWording(fallback || id);

// ---------------------------------------------------------------- the review's ten groups from this branch's merged ones
// Same rules as pipeline/themes.py: the City service first, then words in the layer name.
const BY_SERVICE: Record<string, string> = { Land_Administration: "property", Land_Parcel_Zonning: "property", Open_Data_Service_Zonning: "property", Spatial_Planning: "property",
  Heritage: "heritage", Safety_Security: "safety", Transport: "transport", Basic_Services_Infrastructure: "infra", Wayleave_Infrastructure: "infra", Wayleaves_Regions: "boundaries",
  Natural_Resources_Environment: "environment", Water_Quality_Dashboard_Reporting: "environment", Community_Services: "community", Health: "community", Social_Development: "community",
  Human_Settlements: "community", Economic_Development: "economy", Political_Administrative_Boundaries: "boundaries" };
const KEYWORDS: [RegExp, string][] = [[/heritage|monument|nhra|hpoz|historic/i, "heritage"], [/zon|land parcel|erf|servitude|sectional|complex|estate|valuation|home owner|development|urban|corridor|node|overlay|subdivision|lftea|scheme/i, "property"],
  [/koeberg|police|fire|evacuat|protective|court/i, "safety"], [/electric|water|sewer|storm|refuse|waste|landfill|substation|drop off|recycl|load ?shed|survey mark|footprint|contour|building/i, "infra"],
  [/road|street|rail|myciti|taxi|parking|speed|pedestrian|intersection|traffic|bus/i, "transport"], [/wetland|dune|vegetation|biodivers|watercourse|coast|air quality|soil|rainfall|dam|park|beach|tidal/i, "environment"],
  [/school|library|clinic|health|hall|pool|sport|cemeter|worship|ecd|toilet|community|resort|recreation|old age|shelter|housing/i, "community"],
  [/tourism|wine|trading|business|scenic|film/i, "economy"], [/ward|suburb|subcouncil|district|region|area|improvement|ratepayer/i, "boundaries"]];
const themeCache = new Map<string, string>();
export function clientTheme(L: Layer): string {
  const t = L.theme;
  if (!["utilities", "community", "property"].includes(t)) return t;   // already one of the groups, or a full-city group
  const hit = themeCache.get(L.id); if (hit) return hit;
  let r: string;
  if (L.id === "service-requests") r = "complaints";
  else {
    const svc = (L.url.match(/\/(?:Theme_Based|ODP_SPLIT[^/]*)\/([^/]+)\/MapServer/) || [])[1] || "";
    r = BY_SERVICE[svc] || KEYWORDS.find(([re]) => re.test(L.name))?.[1] || t;
    if (t === "utilities" && !["transport", "infra"].includes(r)) r = L.sub === "Roads and transport" ? "transport" : "infra";
    if (t === "community" && !["community", "complaints", "economy", "environment"].includes(r)) r = "community";
    if (t === "property" && !["property", "boundaries", "heritage", "safety", "environment"].includes(r)) r = "property";
  }
  themeCache.set(L.id, r); return r;
}

const CORE: RegExp[] = [
  /^land-parcels$/, /^street-names?$/, /^address$/, /^zoning$/, /^property$/, /servitude/, /sectional-title/, /^split-zoning$/, /home-owners?-associations?-gv-2021/, /sg-approved/,
  /^schools?$/, /health-care|clinic|hospital/, /^libraries$/, /community-centres|halls/, /^parks?$|^public-open-space/, /sports-grounds/, /swimming-pools/, /^beaches$/, /places-of-worship/, /city-owned-ecd/,
  /police-stations/, /municipal-courts|magistrat|courts?$/, /fire-stations/, /koeberg-radii/, /evacuation/, /koeberg-restricted/,
  /myciti-bus-stops/, /myciti-bus-routes/, /rail-station/, /taxi-routes/,
  /^service-requests$/,
  /^wetlands$/, /^dunes$/, /stormwater-open-watercourse-main|^open-watercourses?$/, /terrestrial-biodiversity|biodiversity-network/, /indigenous-vegetation-current/, /coastal/, /flood/,
  /^heritage-inventory$/, /formal-protections?-nhra|nhra-protection/, /heritage-audit-areas/, /research|finds/, /^monuments?$/,
  /^wards?$/, /official-suburb|^suburbs?$/, /subcouncil/, /improvement-district/,
  /wine-route|wine-farm/, /informal-trading-bay/, /tourism-development/,
  /loadshedding|load-shedding/, /electricity-substations/, /bulk-water-reservoir/, /sewer-pump/, /sewer-treatment|wastewater/, /drop-offs|landfill/, /public-lighting/,
];
const SPECIALIST = /grid|catchment|depot|survey-mark|contour|authority|alias|gv-20(09|15)|low-detail|think-twice|smart-facilities|film|free-call|day-visitor|spray|historic-extent|objects|exemption|pt1|capacity|generation|^tct-|stw|raw|footprint|allotment|districts?$|regions?$|cct-buildings|confirmed-properties|registered-properties|^registered$|integrated-main|waterbodies|soils/;

const NAMES: Record<string, string> = {
  "land-parcels": "Erven and street numbers", "street-name": "Street names", "street-names": "Street names", "address": "Street addresses", "street-number": "Street numbers (address points)",
  "property": "Property register", "zoning": "Zoning", "split-zoning": "Split-zoned erven", "sg-approved": "Surveyor-General approved diagrams", "zoning-sg-approved-properties": "Surveyor-General approved diagrams",
  "servitude": "Servitudes (rights of way, services)", "servitudes": "Servitudes (rights of way, services)", "sectional-title-scheme": "Sectional-title schemes",
  "zoning-registered-properties": "Registered properties", "registered": "Registered properties", "zoning-confirmed-properties": "Erven with confirmed zoning",
  "home-owners-association-gv-2021": "Home owners' associations", "home-owners-associations-gv-2021": "Home owners' associations", "home-owners-association-gv-2009": "Home owners' associations (2009 roll)", "home-owner-association-gv-2015": "Home owners' associations (2015 roll)",
  "service-requests": "Service requests (complaints)", "wards": "Wards", "ward": "Wards", "official-suburb": "Suburbs", "official-suburb-suburbs": "Suburbs",
  "koeberg-radii-planning": "Koeberg emergency planning zones", "south-evacuation-direction-koeberg": "Koeberg evacuation routes: south", "east-evacuation-direction-koeberg": "Koeberg evacuation routes: east",
  "north-evacuation-direction-koeberg": "Koeberg evacuation routes: north",
  "koeberg-restricted-area": "Koeberg restricted area", "loadshedding-blocks": "Load-shedding blocks", "electricity-public-lighting": "Street lights",
  "heritage-inventory": "Heritage-graded places", "heritage-audit-areas": "Heritage survey areas", "formal-protections-nhra": "Protected heritage (national law)",
  "exemption-nhra": "Heritage-law exemptions", "heritage-inventory-objects": "Heritage objects", "world-heritage-site": "World Heritage Site",
  "pt1-zones": "Reduced-parking public transport zones (PT1)", "2d-building-footprints": "Building outlines", "2d-building-footprints-low-detail": "Building outlines (simplified)",
  "town-survey-marks": "Survey beacons", "5m-contours": "Height contours (5 m)", "city-owned-ecd-centres": "City crèches (early childhood development)",
  "cct-buildings": "City-owned buildings", "cct-free-call-lines": "City free-call phones", "tct-road-centreline": "Road centrelines", "transport-road-centreline": "Road centrelines",
  "informal-trading-bay-rental-status": "Informal trading bays", "informal-trading-location-planning-status": "Informal trading areas", "wine-route-farm-points": "Wine farms",
  "think-twice-areas": "Recycling collection areas", "think-twice-areas-recycling": "Recycling collection areas", "drop-offs": "Waste drop-off sites",
  "electricity-supply-authority": "Who supplies electricity (City or Eskom)", "electricity-distribution-capacity": "Spare electricity capacity",
  "bulk-water-ground-water-protection-zone": "Groundwater protection zones", "routine-inland-water-quality-monitoring": "River water-quality sampling points",
  "stormwater-water-quality-monitoring": "Stormwater quality sampling points", "municipal-courts": "Municipal courts", "police-stations": "Police stations",
  "monument": "Monuments", "monuments": "Monuments", "research-finds": "Recorded finds (middens, burials, wrecks)", "other-heritage-records": "Other heritage records (SAHRIS, Wikidata, OpenStreetMap)",
};
const WORDS: [RegExp, string][] = [[/\bNHRA\b/gi, "heritage law"], [/\bGV\s?(\d{4})\b/gi, "($1 roll)"], [/\bECD\b/g, "crèche"], [/\bCCT\b/g, "City"], [/\bTCT\b\s*/g, ""],
  [/\bSG\b/g, "Surveyor-General"], [/\bHPOZ\b/g, "heritage overlay zone"], [/\bSTW\b/g, "sewage works"], [/\bWWTW\b/g, "wastewater works"], [/\bCBD\b/g, "city centre"], [/\s*-\s*$/, ""]];
const tidy = (s: string) => { for (const [r, w] of WORDS) s = s.replace(r, w); s = s.replace(/\s+/g, " ").trim();
  return s === s.toUpperCase() ? s.toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase()) : s.charAt(0).toUpperCase() + s.slice(1); };
export const nameOf = (L: Layer | undefined) => !L ? "" : NAMES[L.id] || NAMES[L.id.replace(/-\d+$/, "")] || tidy(L.name);

const TWIN: Record<string, string> = { "tct-road-centreline": "road", "transport-road-centreline": "road", "registered": "regprop", "zoning-registered-properties": "regprop",
  "street-name": "streets", "street-names": "streets", "monument": "monument", "monuments": "monument", "ward": "wards", "wards": "wards" };
const norm = (L: Layer) => TWIN[L.id] || (/suburb/.test(L.id) && !/subcouncil/.test(L.id) ? "suburb" : "") || nameOf(L).toLowerCase().replace(/\(.*?\)/g, "").replace(/\b(cct|city|the)\b/g, "").replace(/[^a-z0-9]/g, "").replace(/s$/, "");
export const canonical = new Map<string, string>();
export const alsoFrom = new Map<string, Layer[]>();
const coreRank = (L: Layer) => { const k = CORE.findIndex((r) => r.test(L.id)); return k < 0 ? 999 : k; };
export const isCore = (L: Layer) => coreRank(L) < 999;
export const isSpecialist = (L: Layer) => SPECIALIST.test(L.id) && !isCore(L);
const drawable = (L: Layer) => !!(L.tilesets?.length || L.tileset);

export function buildCatalog() {
  canonical.clear(); alsoFrom.clear();
  const groups = new Map<string, Layer[]>();
  for (const L of M.layers) if (drawable(L)) { const k = norm(L); groups.set(k, [...(groups.get(k) || []), L]); }
  for (const ls of groups.values()) {
    ls.sort((a, b) => coreRank(a) - coreRank(b) || b.n - a.n || a.id.length - b.id.length);
    const [top, ...rest] = ls; canonical.set(top.id, top.id); for (const r of rest) canonical.set(r.id, top.id); if (rest.length) alsoFrom.set(top.id, rest);
  }
}
export const canon = (id: string) => canonical.get(id) || id;

export function themeLayers(theme: string, filter = "") {
  const f = filter.toLowerCase();
  const ls = M.layers.filter((L) => clientTheme(L) === theme && drawable(L) && canonical.get(L.id) === L.id && (!f || `${nameOf(L)} ${L.name}`.toLowerCase().includes(f)));
  const rank = (L: Layer) => coreRank(L) * 1e7 + (isSpecialist(L) ? 5e6 : 0) + (L.geom === "Point" && L.label ? 0 : 1e6) - Math.min(L.n, 999999);
  ls.sort((a, b) => rank(a) - rank(b));
  const main = ls.filter((L) => isCore(L) || (!isSpecialist(L) && ls.filter(isCore).length < 3)).slice(0, 8);
  const more = ls.filter((L) => !main.includes(L)).sort((a, b) => nameOf(a).localeCompare(nameOf(b)));
  return { main, more, all: ls };
}

const pick = (...res: RegExp[]) => res.map((r) => M.layers.find((L) => drawable(L) && canonical.get(L.id) === L.id && r.test(L.id))?.id).filter(Boolean) as string[];
export const basics = () => pick(/^land-parcels$/, /^street-names?$/, /^address$/, /^wards?$/);
export const quickViews = (): [string, string, string[]][] => ([
  ["Property Search", "Erven, street numbers, zoning, servitudes, heritage grading", pick(/^land-parcels$/, /^street-names?$/, /^address$/, /^zoning$/, /servitude/, /^heritage-inventory$/, /^split-zoning$/)],
  ["Public Facilities", "Schools, clinics, libraries, halls, grounds", pick(/^land-parcels$/, /^street-names?$/, /^schools?$/, /health-care|clinic/, /^libraries$/, /community-centres/, /sports-grounds/, /^parks?$/)],
  ["Law & Order", "Police, courts, fire, Koeberg zones and evacuation routes", pick(/police-stations/, /municipal-courts/, /fire-stations/, /koeberg-radii/, /south-evacuation/, /east-evacuation/, /health-care|clinic/)],
  ["Incidents & Complaints", "Service requests and incidents since 2023, by category", pick(/^service-requests$/, /^wards?$/, /official-suburb|^suburbs?$/)],
  ["Transport & Roads", "Roads, MyCiTi, rail and taxi routes", pick(/^street-names?$/, /myciti-bus-stops/, /myciti-bus-routes/, /rail-station/, /taxi-routes/)],
  ["Nature", "Wetlands, dunes, watercourses, natural vegetation", pick(/^wetlands$/, /^dunes$/, /stormwater-open-watercourse-main|^open-watercourses?$/, /terrestrial-biodiversity|biodiversity-network/, /indigenous-vegetation-current/)],
  ["Historical Record", "Graded places, protected sites, recorded finds", pick(/^heritage-inventory$/, /formal-protections?-nhra|nhra-protection/, /heritage-audit-areas/, /research|finds/, /^land-parcels$/)],
  ["Utilities", "Load-shedding blocks, substations, water and sewer", pick(/loadshedding/, /electricity-supply-authority/, /electricity-substations/, /bulk-water-reservoir/, /sewer-pump/)],
] as [string, string, string[]][]).filter(([, , ids]) => ids.length > 0);

const ABBR: Record<string, string> = { PRTY: "property", NMBR: "number", NO: "number", SBRB: "suburb", ADR: "address", STR: "street", DSCR: "description", DESC: "description",
  CNCL: "council", SUB: "sub", STS: "status", LGL: "legal", OFC: "official", RGN: "region", TYP: "type", TYPE: "type", CTGR: "category", CDTN: "condition", LCTN: "location",
  PRMT: "permit", NM: "name", NAME: "name", SFX: "suffix", PRF: "prefix", ALT: "alternative", LU: "", SL: "", INT: "", ZONE: "zone", CD: "code", VSTD: "vested", PRVT: "private",
  IND: "indicator", BGN: "start", END: "end", DATE: "date", DGRM: "diagram", SRVT: "servitude", EXTN: "extent", INST: "institution", MDF: "modifier", DRCT: "direction", CMPLX: "complex",
  WARD: "ward", AREA: "area", VAL: "value", VALUE: "value", CODE: "code", GRD: "grade", USE: "use", CLS: "class", STN: "station" };
const FIELD: Record<string, string> = { ADR_NO: "Street number", ADDR_NO: "Street number", ADR_NO_SFX: "Street number suffix", PRTY_NMBR: "Erf number",
  OFC_SBRB_NAME: "Official suburb", ALT_NAME: "Allotment", LU_LGL_STS_DSCR: "Legal status", ZONING: "Zoning", SUB_CNCL_NMBR: "Subcouncil", WARD_NAME: "Ward", FULL_ADR: "Full address" };
export const TECH = /(^|_)(KEY|GUID|GLOBALID|OBJECTID|OID|FID|SHAPE|SG26|created_user|created_date|last_edited_user|last_edited_date)(_|$)|STArea|STLength|Shape__|^_oid$|^ANGLE$/i;
export const fieldLabel = (f: [string, string | null]) => {
  const a = f[1]?.trim();
  if (FIELD[f[0].toUpperCase()]) return FIELD[f[0].toUpperCase()];
  if (a && a !== f[0] && !/^[A-Z0-9_]+$/.test(a) && !/\b(Addr|Adr|Nmbr|Dscr|Sbrb|Ofc)\b/i.test(a)) return a;
  const w = f[0].split(/_+/).map((p) => ABBR[p.toUpperCase()] ?? p.toLowerCase()).filter(Boolean).join(" ");
  return w ? w.charAt(0).toUpperCase() + w.slice(1) : f[0];
};
const VALUES: Record<string, string> = { PAWC: "Provincial Government (Western Cape)", CCT: "City of Cape Town", "CONTRA-FLOW": "Contra-flow lane", SAPS: "SA Police Service",
  DOH: "Provincial Department of Health", NGO: "Non-profit organisation", PVT: "Private", GOV: "Government", "N/A": "Not recorded", UNK: "Unknown", Y: "Yes", N: "No" };
export const legendValue = (L: Layer, c: string, by = "") => {
  if (VALUES[c.toUpperCase()]) return VALUES[c.toUpperCase()];
  if (/^\d+(\.\d+)?$/.test(c)) { const k = `${L.id} ${L.name} ${by}`.toLowerCase();
    if (/radi|distance|km/.test(k)) return `${c} km`; if (/height|elev|contour|depth/.test(k)) return `${c} m`; if (/speed/.test(k)) return `${c} km/h`; if (/year|yr/.test(k)) return c; if (/grade|grading/.test(k)) return `Grade ${c}`; }
  // shouted values in words: "CITY OF CAPE TOWN" → "City of Cape Town"
  if (/^[A-Z][A-Z ,&'-]{4,}$/.test(c)) return (c.charAt(0) + c.slice(1).toLowerCase()).replace(/\bcape town\b/g, "Cape Town").replace(/\bwestern cape\b/g, "Western Cape");
  return c;
};
export const layerLabel = (id: string) => nameOf(layerById.get(id));
/** base layers: the map's ground (erven, streets, addresses); never in the legend */
export const isBase = (id: string) => /^(land-parcels|street-names?|address|street-number)$/.test(id);
