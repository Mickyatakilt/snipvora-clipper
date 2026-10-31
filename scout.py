#!/usr/bin/env python3
"""Daily Content Rewards scout. Plain Python (stdlib only): NO AI, NO Claude usage, no login.

Reads the public discover page, filters/scores campaigns for a brand-new English TikTok clipping account,
then opens the top ones to read the payout table + brief and flags blockers (apply, dedicated page, Tier 1, Discord...).
Writes scout/latest.md (read this), latest.json, history/<date>.json. Pops a Mac notification when a NEW strong campaign appears.
"""
import os, json, re, math, subprocess, sys, time, datetime, urllib.request, html
from pathlib import Path

ROOT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
BASE = "https://contentrewards.com/c"

BLOCK = re.compile(r"gambl|casino|\bbet(s|ting)?\b|sportsbook|crypto|bitcoin|forex|trading|stake\b|shuffle|poker|slots?\b|supplement|weight ?loss|"
                   r"political|politic|election|religio|adult|nsfw|onlyfans|mlm|loan|\bcbd\b|vape|alcohol|betting|"
                   r"sin ?party|teas(e|ing)|\bsexy\b|18\+|dating app|finance|financial|\bbank|invest|\bstocks?\b|insurance|credit card|sofi", re.I)
NOT_FIT = re.compile(r"slideshow|\bugc\b|app install|download the app|unboxing|product (review|demo)|photo ?mode|mobile game|"
                     r"edit(or)?s? wanted|motion graphics", re.I)
SUPPLY = re.compile(r"podcast|interview|stream|episode|footage|gameplay|clip|highlights?|full video|youtube", re.I)
FOREIGN = re.compile(r"\b(para|con|por|clips? hablando|campagne|pour|avec|und|für|que|cada|visitas|vues)\b", re.I)


def get(url, tries=3):
    err = None
    for i in range(tries):  # curl: this Mac's python has no CA bundle
        r = subprocess.run(["curl", "-sL", "-m", "40", "-A", UA["User-Agent"], url], capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 5000:
            return r.stdout.decode("utf8", "replace")
        err = RuntimeError(f"curl rc={r.returncode} bytes={len(r.stdout)} {url[-40:]}")
        time.sleep(3 * (i + 1))
    raise err


def rsc_text(raw):
    """Next.js embeds page data as self.__next_f.push([1,"..."]) string chunks; join + decode them."""
    parts = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', raw)
    return "".join(json.loads(p) for p in parts)


def campaigns_from_discover(raw):
    h = rsc_text(raw)
    dec, out, seen = json.JSONDecoder(), [], set()
    for m in re.finditer(r'\{"availableBudgetRaw":', h):  # first key of every campaign object
        try:
            c, _ = dec.raw_decode(h[m.start():])
        except Exception:
            continue
        if c.get("id") and c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out


def stage1(c):
    """Cheap filter + score from the list data. Returns (score, reasons) or None to drop."""
    text = f"{c.get('title','')} {c.get('description','')} {c.get('category','')}"
    plats = c.get("platforms") or []
    if "tiktok" not in plats:
        return None
    if BLOCK.search(text) or NOT_FIT.search(text) or FOREIGN.search(text):
        return None
    if len(re.findall(r"[^\x00-\x7f]", text)) > 2:
        return None  # mostly non-English
    avail = float(c.get("availableBudgetRaw") or 0)
    prog = float(c.get("progressPercentage") or 0)
    if avail < 300 or prog > 92:
        return None
    rate = float(c.get("payoutSortRaw") or 0)
    creators = int(c.get("creatorCountRaw") or 0)
    s = rate * 10 + math.log10(avail + 1) * 3 - min(creators, 500) * 0.01
    why = []
    if c.get("requiresApplication"):
        s -= 6; why.append("needs application")
    if c.get("isVerified"):
        s += 2
    if SUPPLY.search(text):
        s += 5; why.append("clippable source")
    age_d = (time.time() * 1000 - float(c.get("launchedAtMs") or 0)) / 86_400_000
    if age_d < 10:
        s += 2; why.append("new")
    return round(s, 1), why


def detail(cid):
    raw = get(f"{BASE}/campaigns/{cid}")
    h = rsc_text(raw)
    d = {"flags": [], "brief": ""}
    bc = re.search(r'"briefCounts":\{"contentRules":(\d+),"creatorRequirements":(\d+),"references":(\d+)\}', h)
    if bc:  # how many rules/requirements/reference files exist (their text is hidden until you join)
        d["hidden_counts"] = {"rules": int(bc.group(1)), "requirements": int(bc.group(2)), "references": int(bc.group(3))}
    for m in re.finditer(r'\{"maxPayout":(\d+),"minPayout":(\d+),"platform":"(\w+)","rate":(\d+)\}', h):
        mx, mn, plat, rate = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
        if plat == "tiktok" and rate:
            d["tiktok"] = {"rate_per_1k": rate / 100, "min_payout": mn / 100, "max_payout": mx / 100,
                           "views_to_first_payout": round(mn / rate * 1000)}
    chunks = []  # long text blocks (the written brief) are shipped as "<id>:T<hexlen>,<text>" chunks
    for m in re.finditer(r"\n[0-9a-f]+:T([0-9a-f]+),", h):
        c = h[m.end():m.end() + int(m.group(1), 16)]
        if '"@type"' not in c[:400] and not c.lstrip().startswith(("{", "[")):  # skip JSON-LD / data blobs, keep prose
            chunks.append(c)
    cr = re.search(r'"creatorRequirements":\[(.*?)\]', h, re.S)
    desc = re.search(r'"description":"((?:[^"\\]|\\.)*)"', h)
    txt = " ".join(chunks + ([cr.group(1)] if cr else []) + ([desc.group(1)] if desc else []))
    txt = re.sub(r"\s+", " ", html.unescape(txt))
    d["brief"] = txt[:1500]
    d["_full"] = txt
    rules = [
        (r"dedicated (page|account)|only post|only (feature|show)s?|only .{0,25} content", "dedicated page required"),
        (r"tier[ -]?1|usa,? ?uk|us ?(and|&) ?uk|united states", "tier-1 audience required"),
        (r"\d[\d,\.]*\s?k?\s*(\+)?\s*followers", "follower minimum"),
        (r"\b\d{1,3}(,\d{3})?\s?k?\s*views? (in|within) \d+ ?(day|hour)", "view target inside a deadline"),
        (r"discord", "footage/rules via Discord"),
        (r"apply|application|approved before", "application"),
        (r"analytics (screen ?)?(recording|screenshot)", "analytics proof"),
        (r"watermark|logo", "branding rules"),
    ]
    for rx, label in rules:
        if re.search(rx, txt, re.I):
            d["flags"].append(label)
    return d


def push_phone(top):
    """Phone alert via the free ntfy app (topic in scout/ntfy_topic.txt). Tap a button -> campaign page opens -> you tap Join.
    Only campaigns not pushed before; no AI, no Claude."""
    tf = ROOT / "ntfy_topic.txt"
    env_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not tf.exists() and not env_topic:
        return
    topic = env_topic or tf.read_text().strip()
    sf = ROOT / "pushed.json"
    pushed = json.loads(sf.read_text()) if sf.exists() else {}
    picks = [t for t in top[:6] if t["id"] not in pushed and not t.get("requires_application")][:3]
    if not picks:
        return
    lines = []
    for i, t in enumerate(picks, 1):
        tt = t.get("tiktok") or {}
        lines.append(f"{i}. {t['title'][:55]} - ${tt.get('rate_per_1k', t['rate_per_1k'])}/1k, pays at ~{tt.get('views_to_first_payout', '?')} views, ${t['budget_left']:.0f} left")
    body = "Join these on Content Rewards, then open the studio and tell Claude which you joined.\n" + "\n".join(lines)
    actions = "; ".join(f"view, Join {i}, {t['url']}" for i, t in enumerate(picks, 1))
    r = subprocess.run(["curl", "-s", "-m", "20", "-o", "/dev/null", "-w", "%{http_code}", "-H", "Title: Join these campaigns", "-H", "Tags: moneybag",
                        "-H", f"Click: {picks[0]['url']}", "-H", f"Actions: {actions}", "--data-binary", "@-", f"https://ntfy.sh/{topic}"],
                       input=body.encode(), capture_output=True)
    if r.stdout.decode().strip() == "200":
        for t in picks:
            pushed[t["id"]] = time.strftime("%Y-%m-%d")
        sf.write_text(json.dumps(pushed, indent=1))


def main():
    now = datetime.datetime.now()
    today = now.date().isoformat()
    rows = campaigns_from_discover(get(f"{BASE}/discover"))
    scored = []
    for c in rows:
        r = stage1(c)
        if r:
            scored.append((r[0], r[1], c))
    scored.sort(key=lambda x: -x[0])
    top = []
    for sc, why, c in scored[:15]:
        try:
            d = detail(c["id"])
        except Exception as e:
            d = {"flags": [f"detail failed: {e!r}"[:60]], "brief": ""}
        # bonus: low payout threshold is what a 0-follower account needs
        tt_rate = (d.get("tiktok") or {}).get("rate_per_1k")
        if tt_rate is not None:  # list page shows the best rate across platforms; we post on TikTok
            sc -= (float(c.get("payoutSortRaw") or 0) - tt_rate) * 10
            c["payoutSortRaw"] = tt_rate
        v = (d.get("tiktok") or {}).get("views_to_first_payout")
        if v is not None:
            sc += 6 if v <= 2000 else 3 if v <= 5000 else 0 if v <= 10000 else -6
        sc -= 4 * sum(f in d["flags"] for f in ("dedicated page required", "follower minimum", "view target inside a deadline"))
        sc -= 2 * ("tier-1 audience required" in d["flags"])
        top.append({"id": c["id"], "title": c.get("title"), "brand": c.get("brand"), "category": c.get("category"),
                    "score": round(sc, 1), "why": why, "rate_per_1k": c.get("payoutSortRaw"),
                    "budget_left": c.get("availableBudgetRaw"), "creators": c.get("creatorCountRaw"),
                    "platforms": c.get("platforms"), "requires_application": c.get("requiresApplication"),
                    "url": f"{BASE}/campaigns/{c['id']}", "description": (c.get("description") or "")[:240], **{k: v for k, v in d.items() if k != "_full"}})
        time.sleep(1.5)
    top.sort(key=lambda x: -x["score"])

    hist = ROOT / "history"
    hist.mkdir(exist_ok=True)
    prev_ids = set()
    for p in sorted(hist.glob("*.json"))[-1:]:
        prev_ids = {x["id"] for x in json.loads(p.read_text())["top"]}
    for t in top:
        t["new"] = t["id"] not in prev_ids
    watch = []  # campaigns we joined (docs/campaigns.json): how much hidden rule text each one has, for the dashboard "Needs screenshot" flag
    try:
        for c in json.loads((ROOT / "docs" / "campaigns.json").read_text()):
            try:
                row = next((r for r in rows if r.get("id") == c["id"]), None)  # list page = live budget; missing from the list = likely ended/full
                watch.append({"id": c["id"], "hidden_counts": detail(c["id"]).get("hidden_counts"), "listed": row is not None,
                              "budget_left": (row or {}).get("availableBudgetRaw")})
            except Exception as e:
                watch.append({"id": c["id"], "hidden_counts": None, "error": repr(e)[:60]})
            time.sleep(1.5)
    except Exception:
        pass
    out = {"scanned_at": now.strftime("%Y-%m-%d %H:%M"), "listed": len(rows), "kept": len(scored), "top": top, "watch": watch}
    (ROOT / "latest.json").write_text(json.dumps(out, indent=1))
    (hist / f"{today}.json").write_text(json.dumps(out, indent=1))

    L = [f"# Campaign scout - {out['scanned_at']}", f"{len(rows)} campaigns listed, {len(scored)} fit (TikTok, English, open budget, no gambling/crypto/etc).",
         "Score favors: low views-to-first-payout, no dedicated-page/Tier-1/deadline traps, a clippable source, healthy budget.", ""]
    for i, t in enumerate(top[:10], 1):
        tt = t.get("tiktok") or {}
        L.append(f"## {i}. {t['title']}  (score {t['score']}){'  NEW' if t['new'] else ''}")
        L.append(f"- ${t['rate_per_1k']}/1k TikTok | first payout at ~{tt.get('views_to_first_payout','?')} views (${tt.get('min_payout','?')} min) | "
                 f"${t['budget_left']:.0f} left | {t['creators']} creators | {'APPLY NEEDED' if t['requires_application'] else 'open join'}")
        L.append(f"- flags: {', '.join(t['flags']) or 'none visible - the written rules are hidden until you join, so CHECK THEM before relying on this'}")
        L.append(f"- {t['description'][:200]}")
        L.append(f"- {t['url']}\n")
    (ROOT / "latest.md").write_text("\n".join(L))

    push_phone(top)
    best_new = [t for t in top[:5] if t["new"]]
    if best_new:
        msg = f"New campaign: {best_new[0]['title'][:60]}"
        if sys.platform == "darwin": subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Campaign scout"'], check=False)
    print("OK", out["scanned_at"], len(rows), "listed", len(scored), "fit")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        (ROOT / "last_error.txt").write_text(f"{time.strftime('%F %T')} {e!r}")
        print("FAIL", repr(e))
        sys.exit(1)
