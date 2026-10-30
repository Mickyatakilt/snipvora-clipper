// Snipvora helper (Cloudflare Worker). Secrets (set in Cloudflare, never in this repo): GH_TOKEN, PASSCODE.
// POST /upload?campaign=<id>&name=<file>  raw file body  -> stored as an asset on GitHub release "campaign-inputs"
// POST /post  {video, caption?, when?}     -> starts the post-clip workflow
const REPO = "Mickyatakilt/snipvora-clipper";
const CORS = {"Access-Control-Allow-Origin": "https://mickyatakilt.github.io", "Access-Control-Allow-Headers": "Content-Type, X-Passcode", "Access-Control-Allow-Methods": "POST, OPTIONS"};
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
    if (req.method === "OPTIONS") return new Response(null, {headers: CORS});
    if (req.method !== "POST") return out({error: "POST only"}, 405);
    if (!env.PASSCODE || req.headers.get("X-Passcode") !== env.PASSCODE) return out({error: "wrong passcode"}, 401);
    const url = new URL(req.url);
    try {
      if (url.pathname === "/upload") {
        const camp = (url.searchParams.get("campaign") || "misc").replace(/[^a-z0-9-]/gi, "").slice(0, 40);
        const name = (url.searchParams.get("name") || "file").replace(/[^a-z0-9._-]/gi, "_").slice(0, 80);
        const rel = await release(env);
        const up = await fetch(`https://uploads.github.com/repos/${REPO}/releases/${rel.id}/assets?name=${camp}__${Date.now()}__${name}`,
          {method: "POST", headers: gh(env, {"Content-Type": req.headers.get("Content-Type") || "application/octet-stream", "Content-Length": req.headers.get("Content-Length") || ""}), body: req.body});
        if (!up.ok) return out({error: "github " + up.status}, 502);
        return out({ok: true, asset: (await up.json()).name});
      }
      // default: the dashboard Post button sends the clip item as JSON
      const item = await req.json();
      const d = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/post-clip.yml/dispatches`, {method: "POST", headers: gh(env),
        body: JSON.stringify({ref: "main", inputs: {video: item.video || item.file || "", caption: item.caption || "", when: item.when || ""}})});
      return d.status === 204 ? out({ok: true}) : out({error: "github " + d.status}, 502);
    } catch (e) {
      return out({error: String(e).slice(0, 120)}, 500);
    }
  }
};
