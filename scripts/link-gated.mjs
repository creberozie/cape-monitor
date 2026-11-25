// The gated test build has its own index.html and app code but shares everything else (data, tiles, base map) with dist/
// through symbolic links, so the CI runner does not hold a second copy of the data.
import fs from "node:fs"; import path from "node:path";
const src = path.resolve("dist"), dst = path.resolve("dist-gated");
for (const name of fs.readdirSync(src)) {
  if (name === "index.html" || name === "assets") continue;
  const to = path.join(dst, name);
  fs.rmSync(to, { recursive: true, force: true });
  fs.symlinkSync(path.join(src, name), to);
}
console.log("dist-gated linked to dist for", fs.readdirSync(src).length - 2, "entries");
