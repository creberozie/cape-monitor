// Panels the user can close and resize: the layer panel (left), the file panel (right) and the lower panel.
// Each has a close button and a drag edge; sizes and open/closed state are kept in this browser.
import { map } from "./map";
const root = document.documentElement, body = document.body;
const KEY = "cm-panels-v1";
type State = { left: number; right: number; dock: number; noleft: boolean; noright: boolean };
const load = (): Partial<State> => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } };
const save = (s: Partial<State>) => { try { localStorage.setItem(KEY, JSON.stringify({ ...load(), ...s })); } catch { /* storage blocked */ } };
const resize = () => setTimeout(() => map?.resize(), 30);
const desktop = () => innerWidth > 900;

function apply(s: Partial<State>) {
  if (s.left) root.style.setProperty("--leftw", s.left + "px");
  if (s.right) root.style.setProperty("--rightw", s.right + "px");
  if (s.dock) root.style.setProperty("--dock", s.dock + "px");
  body.classList.toggle("noleft", !!s.noleft); body.classList.toggle("noright", !!s.noright);
}
function drag(handle: HTMLElement, axis: "left" | "right" | "dock") {
  handle.addEventListener("pointerdown", (e) => {
    if (!desktop()) return; e.preventDefault(); handle.setPointerCapture(e.pointerId); body.classList.add("dragging");
    const move = (ev: PointerEvent) => {
      const v = axis === "left" ? Math.min(560, Math.max(200, ev.clientX)) : axis === "right" ? Math.min(760, Math.max(260, innerWidth - ev.clientX))
        : Math.min(innerHeight * 0.75, Math.max(34, innerHeight - ev.clientY));
      root.style.setProperty(axis === "left" ? "--leftw" : axis === "right" ? "--rightw" : "--dock", Math.round(v) + "px"); map?.resize();
    };
    const up = (ev: PointerEvent) => { handle.releasePointerCapture(ev.pointerId); handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up); body.classList.remove("dragging");
      const cs = getComputedStyle(root); save({ left: parseInt(cs.getPropertyValue("--leftw")) || undefined, right: parseInt(cs.getPropertyValue("--rightw")) || undefined, dock: parseInt(cs.getPropertyValue("--dock")) || undefined }); resize(); };
    handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", up);
  });
  handle.addEventListener("dblclick", () => { root.style.removeProperty(axis === "left" ? "--leftw" : axis === "right" ? "--rightw" : "--dock"); save({ [axis]: undefined } as any); resize(); });
}
export function setPanel(which: "left" | "right", open: boolean) { body.classList.toggle("no" + which, !open); save({ ["no" + which]: !open } as any); resize(); }
/** the layer panel starts closed where it has little to offer (the city-wide page) unless the user opened it before */
export function initPanels(leftDefaultOpen: boolean) {
  const s = load(); if (s.noleft === undefined) s.noleft = !leftDefaultOpen; apply(s);
  const mk = (html: string, parent: HTMLElement, cls: string, title: string) => { const b = document.createElement("button"); b.className = cls; b.title = title; b.setAttribute("aria-label", title); b.innerHTML = html; parent.appendChild(b); return b; };
  const mw = document.getElementById("mapwrap")!;
  mk("‹", document.body, "pclose pl", "Close the layer panel").onclick = () => setPanel("left", false);
  mk("›", document.body, "pclose pr", "Close the file panel").onclick = () => setPanel("right", false);
  mk("☰ Layers", mw, "popen pl", "Open the layer panel").onclick = () => setPanel("left", true);
  mk("File ‹", mw, "popen pr", "Open the file panel").onclick = () => setPanel("right", true);
  for (const [id, ax] of [["left", "left"], ["right", "right"], ["dock", "dock"]] as const) { const h = document.createElement("div"); h.className = `rsz rsz-${ax}`; h.title = "Drag to resize; double-click to reset"; document.body.appendChild(h); drag(h, ax); void id; }
  // a file opening on a closed right panel opens it
  new MutationObserver(() => { if (body.classList.contains("noright") && document.getElementById("right")!.querySelector(".card.primary h2")?.textContent && body.classList.contains("inspect")) setPanel("right", true); })
    .observe(document.getElementById("right")!, { childList: true });
}
