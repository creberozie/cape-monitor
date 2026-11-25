"""Supplier name normalisation: one rule, used everywhere a published name is matched to a profile."""
import re

SUFFIX = re.compile(r"\b(PTY|PTY\.|PROPRIETARY|PLY|LTD|LIMITED|LTD\.|LT|CC|C\.C\.|INC|INCORPORATED|SOC|NPC|RF|NPO|PLC|LLC|HOLDINGS LTD)\b")
def norm(name):
    n = str(name or "").upper().replace("&", " AND ").replace(" ", " ")
    n = re.sub(r"\(COPY ATTACHED\)|\(ALTERNATIVE SERVICE PROVIDER\)|\(PREFERRED\)|\(SECOND\)|\(FIRST\)", " ", n)
    n = re.split(r"\bT/A\b|\bTRADING AS\b", n)[0]
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    n = SUFFIX.sub(" ", n)
    n = re.sub(r"^THE ", "", re.sub(r"\s+", " ", n).strip())
    return n




# Words that mark an organisation, never a private individual: companies and trades, plus religious bodies, trusts, NPCs,
# associations, foundations, co-operatives and statutory or public bodies.
ORGANISATION = re.compile(
    r"\b(PTY|LTD|CC|INC|LIMITED|INCORPORATED|TRADING|PROJECTS?|CONSTRUCTION|SERVICES?|ENTERPRISES?|HOLDINGS|GROUP|SOLUTIONS|CONSULT\w*|ENGINEER\w*|"
    r"SUPPL\w*|INVESTMENTS?|DEVELOPMENTS?|PROPERT(Y|IES)|ASSOCIATES|AND SONS|CATERERS?|SECURITY|TRANSPORT|MAINTENANCE|MANAGEMENT|FACILITIES|"
    r"SOFTWARE|TRAINING|PARTNERS|AUDITORS|ARCHITECTS|PLANNERS|AUTOMATION|INNOVATIONS|MECHANICAL|DIVISION|VENTURE|PUMPS|ELECTRICAL|PLUMBING|MOTORS|"
    r"SYSTEMS|TECHNOLOG\w*|STUDIO|CLUB|CENTRE|CENTER|COMPANY|CORPORATION|BANK|T/A|JV|SA|AFRICA|ATTORNEYS|NOTARIES|CONVEYANCERS|"
    r"TRUST|TRUSTEES?|NPC|NPO|PBO|SECTION 21|ASSOCIATION|FOUNDATION|SOCIETY|INSTITUTE|ACADEMY|FORUM|NETWORK|CONNECT|ORGANI[SZ]ATION|"
    r"CO-?OP(ERATIVE)?|PRIMARY CO|ARCHDIOCESE|DIOCESE|CHURCH|PARISH|CATHEDRAL|CONGREGATION|MINISTR(Y|IES)|MOSQUE|MASJID|SYNAGOGUE|TEMPLE|"
    r"MISSION|ASSEMBL\\w*|MOVEMENT|FELLOWSHIP|CHAPEL|GOSPEL|CHRIST\\w*|ISLAMIC|MUSLIM|JEWISH|HEBREW|HINDU|BUDDHIST|ROMAN CATHOLIC|ANGLICAN|METHODIST|DUTCH REFORMED|NG KERK|KERK|MUNICIPALITY|DEPARTMENT|COUNCIL|BOARD|AGENCY|"
    r"AUTHORITY|COMMISSION|UNIVERSITY|COLLEGE|SCHOOL|GOVERNMENT|PROVINCE|PROVINCIAL|STATE|SOC|ESKOM|TRANSNET|PRASA|SANRAL|ENTITY)\b", re.I)


def looks_like_person(name, land_only=False):
    """Conservative label for a private individual, used only to mark and optionally hide; never to remove a record.
    True for a City land buyer with no organisation word, or a personal title followed by two to four name words."""
    n = str(name or "").replace("\u2019", "'")
    if ORGANISATION.search(n) or re.search(r"\d|&amp|\(", n): return False
    if land_only: return True
    return bool(re.match(r"^(MR|MRS|MS|MISS|DR|PROF)\.?\s+[A-Z][A-Za-z'.-]*(\s+[A-Z][A-Za-z'.-]+){1,3}$", n, re.I))
