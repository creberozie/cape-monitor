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


