import { chromium } from "@playwright/test";
const [url, out, w, h] = [process.argv[2], process.argv[3], +(process.argv[4] || 1600), +(process.argv[5] || 900)];
const b = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {}); const p = await b.newPage({ viewport: { width: w, height: h } });
const errs = []; p.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); }); p.on("pageerror", (e) => errs.push("PAGEERROR " + e.message));
await p.goto(url); await p.waitForTimeout(6000);
for (const step of (process.argv[6] || "").split(";").filter(Boolean)) {
  const i = step.indexOf("="); const kind = step.slice(0, i), arg = step.slice(i + 1);
  if (kind === "click") await p.click(arg).catch((e) => errs.push("click " + arg + " " + e.message.split("\n")[0]));
  if (kind === "wait") await p.waitForTimeout(+arg);
  if (kind === "type") { const [sel, txt] = arg.split("|"); await p.fill(sel, txt); }
}
await p.screenshot({ path: out }); console.log(JSON.stringify(errs.slice(0, 15)));
await b.close();
