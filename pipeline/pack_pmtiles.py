"""Pack a z/x/y.pbf folder (gzipped MVT) into a single PMTiles v3 file. Usage: pack_pmtiles.py <dir> <out.pmtiles> <name>"""
import os, sys, json
from pmtiles.writer import Writer
from pmtiles.tile import zxy_to_tileid, TileType, Compression

src, out, name = sys.argv[1], sys.argv[2], sys.argv[3]
tiles = []
for z in [d for d in os.listdir(src) if d.isdigit()]:
    for x in os.listdir(os.path.join(src, z)):
        for f in os.listdir(os.path.join(src, z, x)):
            tiles.append((zxy_to_tileid(int(z), int(x), int(f.split(".")[0])), os.path.join(src, z, x, f)))
tiles.sort()
zs = [int(z) for z in os.listdir(src) if z.isdigit()]
with open(out, "wb") as fh:
    w = Writer(fh)
    for tid, p in tiles:
        w.write_tile(tid, open(p, "rb").read())
    meta = json.load(open(os.path.join(src, "meta.json"))) if os.path.exists(os.path.join(src, "meta.json")) else {}
    b = meta.get("bounds", [18.3, -33.9, 18.8, -33.4])
    w.finalize({"tile_type": TileType.MVT, "tile_compression": Compression.GZIP, "min_zoom": min(zs), "max_zoom": max(zs),
                "min_lon_e7": int(b[0] * 1e7), "min_lat_e7": int(b[1] * 1e7), "max_lon_e7": int(b[2] * 1e7), "max_lat_e7": int(b[3] * 1e7),
                "center_zoom": min(zs) + 2, "center_lon_e7": int((b[0] + b[2]) / 2 * 1e7), "center_lat_e7": int((b[1] + b[3]) / 2 * 1e7)},
               {"name": name, "vector_layers": meta.get("vector_layers", [])})
print(out, len(tiles), "tiles", round(os.path.getsize(out) / 1e6, 1), "MB")
