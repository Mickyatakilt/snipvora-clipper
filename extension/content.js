// Auto rules grab: on a Content Rewards campaign page you have JOINED, send the page text to the Snipvora helper (same /rules endpoint the bookmark uses).
// Sends once per campaign, and again only if the brief text changes. Nothing is sent from pages you have not joined.
const WORKER = "https://snipvora-helper.mickyatakilt.workers.dev";
const m = location.pathname.match(/campaigns\/([0-9a-f-]{36})/);
if (m) run(m[1]);

function toast(msg, bad) {
  let t = document.getElementById("snip-toast");
  if (!t) { t = document.createElement("div"); t.id = "snip-toast"; document.body.appendChild(t); }
  t.style.cssText = "position:fixed;z-index:2147483647;bottom:16px;right:16px;max-width:320px;padding:10px 14px;border-radius:10px;font:14px sans-serif;color:#fff;background:" + (bad ? "#c0392b" : "#6c5ce7");
  t.textContent = "Snipvora: " + msg;
}
const hash = s => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return String(h); };
const store = { get: k => new Promise(r => chrome.storage.local.get(k, v => r(v[k]))), set: (k, v) => new Promise(r => chrome.storage.local.set({ [k]: v }, r)) };

function build() {
  const t = document.title + "\nURL: " + location.href + "\n\n" + document.body.innerText;
  const L = [].slice.call(document.querySelectorAll("a[href]")).map(a => (a.innerText || "").trim().slice(0, 60) + " -> " + a.href)
    .filter(x => /^[^>]*->\s*https?:/.test(x) && !/contentrewards\.com\/(c\/discover|c\/?$|$)/.test(x));
  const R = [];
  try { (self.__next_f || []).forEach(c => { const s = c && c[1]; if (typeof s === "string" && /creatorRequirements|contentRules|references/.test(s)) R.push(s); }); } catch (e) {}
  return "CAMPAIGN RULES GRAB\n" + t.slice(0, 30000) + "\n\n=== LINKS ===\n" + L.slice(0, 80).join("\n") + "\n\n=== PAGE DATA ===\n" + R.join("\n").slice(0, 20000);
}

async function run(id) {
  // wait up to 20 s for the page to finish loading and show the Joined badge + brief
  for (let i = 0; i < 40; i++) {
    const txt = document.body.innerText;
    if (/\nBrief\n/.test(txt) || /\nJoined\n/.test(txt)) break;
    await new Promise(r => setTimeout(r, 500));
  }
  const txt = document.body.innerText;
  // not joined = the page shows a "Join Campaign" button (verified on an unjoined campaign). Joined pages show "Joined", "Draft in review", etc., so test for the button, not the badge.
  if (/(^|\n)Join Campaign(\n|$)/.test(txt) || [].some.call(document.querySelectorAll("button,a"), b => (b.innerText || "").trim() === "Join Campaign")) return;
  const brief = (txt.split("\nBrief\n")[1] || txt).split("\nTop clippers")[0];
  const h = hash(brief);
  if ((await store.get("sent:" + id)) === h) { toast("rules already sent ✓"); return; }
  toast("sending rules...");
  try {
    const r = await fetch(WORKER + "/rules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ campaign: id, title: document.title, text: build() }) });
    if (!r.ok) throw "error " + r.status;
    await store.set("sent:" + id, h);
    toast("rules sent ✓ the cloud takes it from here");
  } catch (e) { toast("FAILED: " + e, true); }
}
