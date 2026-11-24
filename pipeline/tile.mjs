// Vector tiler: GeoJSON layers -> Mapbox Vector Tiles (z/x/y.pbf), one folder per tileset.
// Usage: node pipeline/tile.mjs <jobs.json>
// jobs.json: [{ "tileset": "property", "out": "dir", "layers": [{ "id": "land-parcels", "file": "x.geojson", "minzoom": 12, "maxzoom": 16 }] }]
import fs from "node:fs"; import path from "node:path"; import geojsonvt from "geojson-vt"; import vtpbf from "vt-pbf"; import zlib from "node:zlib";

const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const lon2x = (lon, z) => Math.floor((lon + 180) / 360 * 2 ** z);
const lat2y = (lat, z) => { const r = lat * Math.PI / 180; return Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * 2 ** z); };

for (const job of jobs) {
  const idx = [], bb = [180, 90, -180, -90];
  let zmin = 99, zmax = 0;
  for (const L of job.layers) {
    const fc = JSON.parse(fs.readFileSync(L.file, "utf8"));
    for (const f of fc.features) { const w = (c) => typeof c[0] === "number" ? (bb[0] = Math.min(bb[0], c[0]), bb[1] = Math.min(bb[1], c[1]), bb[2] = Math.max(bb[2], c[0]), bb[3] = Math.max(bb[3], c[1])) : c.forEach(w); if (f.geometry) w(f.geometry.coordinates); }
    idx.push({ L, vt: new geojsonvt(fc, { maxZoom: L.maxzoom, indexMaxZoom: Math.min(L.maxzoom, 10), indexMaxPoints: 50000, tolerance: L.tolerance ?? 2, extent: 4096, buffer: 64 }) });
    zmin = Math.min(zmin, L.minzoom); zmax = Math.max(zmax, L.maxzoom);
  }
  let n = 0, bytes = 0;
  for (let z = zmin; z <= zmax; z++) {
    const x0 = lon2x(bb[0], z), x1 = lon2x(bb[2], z), y0 = lat2y(bb[3], z), y1 = lat2y(bb[1], z);
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
      const layers = {};
      for (const { L, vt } of idx) { if (z < L.minzoom || z > L.maxzoom) continue; const t = vt.getTile(z, x, y); if (t && t.features.length) layers[L.id] = t; }
      if (!Object.keys(layers).length) continue;
      const buf = zlib.gzipSync(Buffer.from(vtpbf.fromGeojsonVt(layers, { version: 2 })));
      const dir = path.join(job.out, String(z), String(x)); fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, `${y}.pbf`), buf); n++; bytes += buf.length;
    }
  }
  console.log(`${job.tileset}: ${n} tiles, ${(bytes / 1e6).toFixed(1)} MB, z${zmin}-${zmax}`);
}
