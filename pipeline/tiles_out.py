"""Deploy step: move every tile file (PMTiles) under dist/t/, where the range-request Function answers it.
dist/data/d/<slug>/tiles/<set>.pmtiles -> dist/t/<slug>/<set>.pmtiles; dist/basemap/capetown.pmtiles -> dist/t/basemap/capetown.pmtiles"""
import os, shutil, glob
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist")
n = 0
for p in glob.glob(os.path.join(D, "data", "d", "*", "tiles", "*.pmtiles")):
    slug = p.split(os.sep)[-3]; dest = os.path.join(D, "t", slug, os.path.basename(p))
    os.makedirs(os.path.dirname(dest), exist_ok=True); shutil.move(p, dest); n += 1
b = os.path.join(D, "basemap", "capetown.pmtiles")
if os.path.exists(b):
    os.makedirs(os.path.join(D, "t", "basemap"), exist_ok=True); shutil.move(b, os.path.join(D, "t", "basemap", "capetown.pmtiles")); n += 1
print(n, "tile files moved under dist/t/")
