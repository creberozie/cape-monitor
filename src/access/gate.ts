// The sign-up / sign-in screen. Shown before the app starts when the wall is on (ACCESS.requireAccount) and nobody is
// signed in; resolves once the user is in. When the wall is off this returns at once and never draws anything.
import { ACCESS } from "./config";
import { restore, signIn, signUp } from "./auth";

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

export async function accessGate(brand = "CAPE MONITOR", blurb = "Public records of the City of Cape Town, joined and sourced."): Promise<void> {
  if (!ACCESS.configured) return;
  const signedIn = await restore().catch(() => false);
  if (!ACCESS.requireAccount || signedIn) return;
  return new Promise((resolve) => {
    const box = document.createElement("div"); box.id = "gate";
    box.innerHTML = `<form class="gate" novalidate>
      <div class="brand big"><span class="dot"></span>${esc(brand)}</div>
      <p class="mu">${esc(blurb)} Sign in, or create a free account to start.</p>
      <div class="seg" role="tablist"><button type="button" data-m="up" aria-pressed="true">Create account</button><button type="button" data-m="in" aria-pressed="false">Sign in</button></div>
      <label class="nm">Name<input name="name" autocomplete="name" maxlength="80"></label>
      <label>E-mail<input name="email" type="email" autocomplete="email" required></label>
      <label>Password<input name="password" type="password" autocomplete="new-password" minlength="8" required></label>
      <button class="tb on" type="submit">Create account</button>
      <div class="msg" role="status" aria-live="polite"></div>
      <p class="note">Cape Monitor records your sign-in and the main actions you take (district, panels and records opened, exports) so the operator can see how it is used. The records are kept for 12 months and are not shared. The number of people online is shown to everyone; names are not.</p>
    </form>`;
    document.body.appendChild(box);
    const f = box.querySelector("form")!; let mode: "up" | "in" = "up";
    const msg = box.querySelector(".msg") as HTMLElement, go = f.querySelector("button[type=submit]") as HTMLButtonElement;
    box.querySelectorAll("[data-m]").forEach((b) => (b as HTMLElement).onclick = () => {
      mode = (b as HTMLElement).dataset.m as any; box.querySelectorAll("[data-m]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      (box.querySelector(".nm") as HTMLElement).hidden = mode === "in"; go.textContent = mode === "up" ? "Create account" : "Sign in";
      (f.elements.namedItem("password") as HTMLInputElement).autocomplete = mode === "up" ? "new-password" : "current-password"; msg.textContent = "";
    });
    f.onsubmit = async (e) => {
      e.preventDefault();
      const v = (n: string) => (f.elements.namedItem(n) as HTMLInputElement).value.trim();
      if (!/^\S+@\S+\.\S+$/.test(v("email"))) { msg.textContent = "Enter a valid e-mail address."; return; }
      if (v("password").length < 8) { msg.textContent = "Use a password of at least 8 characters."; return; }
      go.disabled = true; msg.textContent = mode === "up" ? "Creating your account…" : "Signing in…";
      const r = mode === "up" ? await signUp(v("email"), v("password"), v("name")) : await signIn(v("email"), v("password"));
      go.disabled = false;
      if (r.ok) { box.remove(); resolve(); } else msg.textContent = esc(r.message || "Something went wrong.");
    };
  });
}
