"""How City layers are grouped in the app, and which ones are left out (with the reason, so nothing is dropped silently)."""
import re

THEMES = [  # id, English, Afrikaans: the layer groups shown in the app
    ("money", "Money and tenders", "Geld en tenders"),
    ("justice", "Justice", "Justisie"),
    ("notices", "Notices and gazettes", "Kennisgewings en koerante"),
    ("property", "Property and planning", "Eiendom en beplanning"),
    ("safety", "Safety", "Veiligheid"),
    ("utilities", "Utilities and infrastructure", "Nutsdienste en infrastruktuur"),
    ("community", "Community and City services", "Gemeenskap en Stadsdienste"),
    ("environment", "Environment", "Omgewing"),
    ("heritage", "Heritage", "Erfenis"),
    ("live", "Live", "Regstreeks"),
]
# the pilot's finer subjects, folded into the groups above
FOLD = {"boundaries": "property", "complaints": "community", "infra": "utilities", "transport": "utilities", "economy": "community"}
# utilities are hundreds of pipe, cable and road layers: grouped by network so the list stays short
UTIL_SUB = [(r"water(?!course)|reservoir|hydrant|valve|meter|bulk|pump", "Water"), (r"sewer|sewage|waste ?water|effluent|treatment", "Sewer"),
            (r"electric|substation|cable|power|lighting|street ?light|transformer|kiosk|load ?shed|minisub", "Electricity"),
            (r"storm|drain|culvert|catchment|retention|detention|canal", "Stormwater"), (r"telecom|fibre|fiber|broadband|duct|wi-?fi|mast", "Telecoms"),
            (r"road|street|rail|myciti|taxi|parking|speed|pedestrian|intersection|traffic|bus|transport|route|bridge|cycle", "Roads and transport"),
            (r"refuse|landfill|drop off|recycl|solid waste", "Refuse")]


def util_sub(name):
    for pat, sub in UTIL_SUB:
        if re.search(pat, name, re.I):
            return sub
    return "Other"


BY_SERVICE = {
    "Land_Administration": "property", "Land_Parcel_Zonning": "property", "Open_Data_Service_Zonning": "property", "Spatial_Planning": "property",
    "Heritage": "heritage", "Safety_Security": "safety", "Transport": "transport", "Basic_Services_Infrastructure": "infra",
    "Wayleave_Infrastructure": "infra", "Wayleaves_Regions": "boundaries", "Natural_Resources_Environment": "environment",
    "Water_Quality_Dashboard_Reporting": "environment", "Community_Services": "community", "Health": "community",
    "Social_Development": "community", "Human_Settlements": "community", "Economic_Development": "economy",
    "Political_Administrative_Boundaries": "boundaries",
}
KEYWORDS = [  # for the ODP_SPLIT services, which mix subjects
    (r"heritage|monument|nhra|hpoz|historic", "heritage"), (r"zon|land parcel|erf|servitude|sectional|complex|estate|valuation|home owner|development|urban|corridor|node|overlay|subdivision|lftea|scheme", "property"),
    (r"koeberg|police|fire|evacuat|protective|court", "safety"), (r"electric|water|sewer|storm|refuse|waste|landfill|substation|drop off|recycl|load ?shed|survey mark|footprint|contour|building", "infra"),
    (r"road|street|rail|myciti|taxi|parking|speed|pedestrian|intersection|traffic|bus", "transport"),
    (r"wetland|dune|vegetation|biodivers|watercourse|coast|air quality|soil|rainfall|dam|park|beach|tidal", "environment"),
    (r"school|library|clinic|health|hall|pool|sport|cemeter|worship|ecd|toilet|community|resort|recreation|old age|shelter|housing", "community"),
    (r"tourism|wine|trading|business|scenic|film", "economy"), (r"ward|suburb|subcouncil|district|region|area|improvement|ratepayer", "boundaries"),
]

# left out on purpose; listed in the Sources panel with the reason
EXCLUDE = [
    (r"^Tree Canopies$", "over a million tree-canopy outlines in this district; too heavy for a phone. Planned as a separate download."),
    (r"Ground Level Map 2m Contours|GLM.*2m", "2 m contours are very heavy; the 5 m contours are included"),
    (r"labels only|Labels$", "label-only copy of another layer"),
    (r"Inland Water Quality Results \(Raw\)", "337,000 individual laboratory results; the City server stalls on bulk download. The monitoring points are in 'Routine Inland Water Quality Monitoring'; the results will be added as a table per point."),
    (r"^Aerial Photography Grid", "index grid for ordering aerial photos, not information about places"),
    (r"Floor area Factor|Cape Town CBD|Roggebaai|St George|V&A Waterfront", "applies only to the Cape Town CBD, not this district"),
]


def theme_for(service, name):
    t = BY_SERVICE.get(service)
    if not t:
        n = name.lower()
        t = next((t for pat, t in KEYWORDS if re.search(pat, n)), "property")
    return FOLD.get(t, t)


def excluded(name):
    for pat, why in EXCLUDE:
        if re.search(pat, name, re.I):
            return why
    return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48]
