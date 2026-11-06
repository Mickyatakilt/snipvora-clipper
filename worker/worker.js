// Snipvora helper (Cloudflare Worker). Secret (set in Cloudflare, never in this repo): GH_TOKEN. No passcode: every route is limited by origin, real ids, size/format and cool-downs.
// POST /upload?campaign=<id>&name=<file>  raw file body  -> stored as an asset on GitHub release "campaign-inputs"
// POST /rules {campaign,title,text} (no passcode, locked down) -> saves captured campaign rules into the repo for the dashboard
// POST /post  {video, caption?, when?}     -> starts the post-clip workflow
const REPO = "Mickyatakilt/snipvora-clipper";
const ORIGINS = ["https://mickyatakilt.github.io", "https://contentrewards.com", "https://www.contentrewards.com"];
let CORS = {};
const setCors = (req) => { const o = req.headers.get("Origin"); CORS = {"Access-Control-Allow-Origin": ORIGINS.includes(o) ? o : ORIGINS[0], "Access-Control-Allow-Headers": "Content-Type, X-Passcode", "Access-Control-Allow-Methods": "POST, OPTIONS", "Vary": "Origin"}; };
const gh = (env, extra = {}) => ({"Authorization": `Bearer ${env.GH_TOKEN}`, "User-Agent": "snipvora-helper", "Accept": "application/vnd.github+json", ...extra});
const out = (obj, status = 200) => new Response(JSON.stringify(obj), {status, headers: {...CORS, "Content-Type": "application/json"}});

async function release(env) {
  let r = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/campaign-inputs`, {headers: gh(env)});
  if (r.status === 404) {
    r = await fetch(`https://api.github.com/repos/${REPO}/releases`, {method: "POST", headers: gh(env),
      body: JSON.stringify({tag_name: "campaign-inputs", name: "campaign-inputs", body: "Files uploaded from the dashboard"})});
  }
  if (!r.ok) throw new Error("release " + r.status);
  return r.json();
}

export default {
  async fetch(req, env) {
    setCors(req);
    if (req.method === "OPTIONS") return new Response(null, {headers: CORS});
    const url = new URL(req.url);
    if (req.method === "GET" && url.pathname === "/health") {  // used by the worker-health workflow: proves GH_TOKEN is present and accepted by GitHub
      const r = await fetch(`https://api.github.com/repos/${REPO}`, {headers: gh(env)});
      return out({ok: r.ok, github: r.status, hasToken: !!env.GH_TOKEN}, r.ok ? 200 : 503);
    }
    if (req.method !== "POST") return out({error: "POST only"}, 405);
    // No passcode anywhere (Mike's decision). Every route is locked down instead: own pages only, real ids, size/format limits, cool-downs.
    if (!ORIGINS.includes(req.headers.get("Origin"))) return out({error: "origin not allowed"}, 403);
    try {
      if (url.pathname === "/upload") {
        // strict: real campaign (rules captured), video/photo files, 100 MB max, 10 files per campaign
        const camp = (url.searchParams.get("campaign") || "").replace(/[^a-z0-9-]/gi, "").slice(0, 40);
        const name = (url.searchParams.get("name") || "file").replace(/[^a-z0-9._-]/gi, "_").slice(0, 80);
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(camp)) return out({error: "bad campaign id"}, 400);
        if (!/\.(mp4|mov|m4v|webm|jpe?g|png|webp)$/i.test(name)) return out({error: "only video or photo files"}, 400);
        const len = Number(req.headers.get("Content-Length") || 0);
        if (!len) return out({error: "no file size"}, 411);
        if (len > 100 * 1024 * 1024) return out({error: "file bigger than 100 MB"}, 413);
        const realC = await fetch(`https://api.github.com/repos/${REPO}/contents/docs/captures/${camp}.json`, {headers: gh(env)});
        if (!realC.ok) return out({error: "unknown campaign"}, 404);
        const rel = await release(env);
        if (((rel.assets || []).filter((a) => a.name.startsWith(camp + "__")).length) >= 10) return out({error: "10 files already attached for this campaign"}, 429);
        const up = await fetch(`https://uploads.github.com/repos/${REPO}/releases/${rel.id}/assets?name=${camp}__${Date.now()}__${name}`,
          {method: "POST", headers: gh(env, {"Content-Type": req.headers.get("Content-Type") || "application/octet-stream", "Content-Length": req.headers.get("Content-Length") || ""}), body: req.body});
        if (!up.ok) return out({error: "github " + up.status}, 502);
        return out({ok: true, asset: (await up.json()).name});
      }
      if (url.pathname === "/job") {  // dashboard Run again / Stop for the campaign cloud job. Own pages only, real campaign id, no double start, 2 min cool-down.
        if (!ORIGINS.includes(req.headers.get("Origin"))) return out({error: "origin not allowed"}, 403);
        let b; try { b = JSON.parse(await req.text()); } catch (e) { return out({error: "bad json"}, 400); }
        const camp = String(b.campaign || "");
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(camp)) return out({error: "bad campaign id"}, 400);
        if (b.action !== "start" && b.action !== "stop") return out({error: "bad action"}, 400);
        const real = await fetch(`https://api.github.com/repos/${REPO}/contents/docs/captures/${camp}.json`, {headers: gh(env)});  // only campaigns whose rules were really captured
        if (!real.ok) return out({error: "unknown campaign"}, 404);
        const lr = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/campaign-job.yml/runs?per_page=30`, {headers: gh(env)});
        if (!lr.ok) return out({error: "github " + lr.status}, 502);
        const all = (await lr.json()).workflow_runs || [];
        const mine = all.filter((r) => (r.display_title || "").includes(camp));
        const active = mine.filter((r) => ["queued", "in_progress", "waiting", "pending", "requested"].includes(r.status));
        if (b.action === "stop") {
          if (!active.length) return out({error: "no running job for this campaign"}, 409);
          let n = 0;
          for (const r of active) { const c = await fetch(`https://api.github.com/repos/${REPO}/actions/runs/${r.id}/cancel`, {method: "POST", headers: gh(env)}); if (c.status === 202) n++; }
          return n ? out({ok: true, stopped: n}) : out({error: "github could not cancel"}, 502);
        }
        if (active.length) return out({error: "already running"}, 409);
        if (all[0] && Date.now() - new Date(all[0].created_at).getTime() < 120000) return out({error: "a job started less than 2 minutes ago, wait"}, 429);  // one shared cool-down for every campaign
        const d = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/campaign-job.yml/dispatches`, {method: "POST", headers: gh(env), body: JSON.stringify({ref: "main", inputs: {campaign: camp, force: "true"}})});
        return d.status === 204 ? out({ok: true}) : out({error: "github " + d.status}, 502);
      }
      if (url.pathname === "/rules") {  // rules grabber bookmark: saves the captured page text as docs/captures/<campaign>.json
        if (!ORIGINS.includes(req.headers.get("Origin"))) return out({error: "origin not allowed"}, 403);
        const raw = await req.text();
        if (raw.length > 200000) return out({error: "too big"}, 413);
        let b; try { b = JSON.parse(raw); } catch (e) { return out({error: "bad json"}, 400); }
        const camp = String(b.campaign || "").replace(/[^a-z0-9-]/gi, "").slice(0, 40);
        if (!/^([jx]-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^doc-[a-z0-9-]{10,40}$/i.test(camp)) return out({error: "bad campaign id"}, 400);
        const txt = String(b.text || "");
        const marker = /^[jx]-/i.test(camp);  // dashboard "I joined" / "Remove" markers carry JSON
        let okText = /^(CAMPAIGN RULES GRAB|GOOGLE DOC GRAB)\n/.test(txt);
        if (marker) { try { okText = typeof JSON.parse(txt) === "object"; } catch (e) { okText = false; } }
        if (!okText) return out({error: "not a rules grab"}, 400);
        const content = JSON.stringify({capturedAt: new Date().toISOString(), title: String(b.title || "").slice(0, 200), text: String(b.text || "").slice(0, 120000)}, null, 1);
        const api = `https://api.github.com/repos/${REPO}/contents/docs/captures/${camp}.json`;
        const cur = await fetch(api, {headers: gh(env)});
        const sha = cur.ok ? (await cur.json()).sha : undefined;
        const put = await fetch(api, {method: "PUT", headers: gh(env), body: JSON.stringify({message: `rules captured ${camp}`, content: btoa(unescape(encodeURIComponent(content))), sha})});
        return put.ok ? out({ok: true}) : out({error: "github " + put.status}, 502);
      }
      // default: the dashboard Post button sends the clip item as JSON
      // default route = the dashboard Post button. Strict: a real clip path, sane caption/time, and one post per 2 minutes.
      let item; try { item = JSON.parse(await req.text()); } catch (e) { return out({error: "bad json"}, 400); }
      const vid = String(item.video || item.file || "");
      if (!/^[A-Za-z0-9_\-./:]{1,300}\.mp4$/i.test(vid) || vid.includes("..")) return out({error: "bad video"}, 400);
      const cap = String(item.caption || "").slice(0, 2200);
      const when = String(item.when || "");
      if (when && (isNaN(Date.parse(when)) || Date.parse(when) > Date.now() + 60 * 864e5)) return out({error: "bad time"}, 400);
      const pr = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/post-clip.yml/runs?per_page=1`, {headers: gh(env)});
      if (pr.ok) { const last = ((await pr.json()).workflow_runs || [])[0]; if (last && Date.now() - new Date(last.created_at).getTime() < 120000) return out({error: "a post started less than 2 minutes ago, wait"}, 429); }
      const d = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/post-clip.yml/dispatches`, {method: "POST", headers: gh(env),
        body: JSON.stringify({ref: "main", inputs: {video: vid, caption: cap, when}})});
      return d.status === 204 ? out({ok: true}) : out({error: "github " + d.status}, 502);
    } catch (e) {
      return out({error: String(e).slice(0, 120)}, 500);
    }
  }
};
