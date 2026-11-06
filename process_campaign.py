"""After the rules of a joined campaign arrive (docs/captures/<id>.json), run the automatic part: fit check -> footage link -> download -> clip -> status.
Usage: python3 process_campaign.py <campaignId> [--force]
Writes docs/status/<id>.json (state: stopped | missing_footage | ready | error) and, when ready, out/<id8>/clip.mp4 + caption.txt.
No AI, no Claude. Only fetches footage from links the campaign itself gives (direct video, Dropbox, Google Drive file). Never posts anything."""
import glob, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request, zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
CAP_DIR = os.environ.get("CAPTURE_DIR", os.path.join(ROOT, "docs", "captures"))
ST_DIR = os.environ.get("STATUS_DIR", os.path.join(ROOT, "docs", "status"))
OUT_ROOT = os.environ.get("OUT_DIR", os.path.join(ROOT, "out"))
MAX_MB = 600
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
VID = (".mp4", ".mov", ".m4v", ".webm"); IMG = (".jpg", ".jpeg", ".png", ".webp")


def analyze(t):  # same rules as analyze() in docs/index.html
    t = re.sub(r"\bno official (tiktok |ig |instagram )?(sound|audio)( needed| required)?", "", t, flags=re.I)
    stop, warn = [], []
    if re.search(r"majority tier 1|tier 1 \(?majority|\d+\s*%\+?\s*(usa|us|u\.s\.|united states)\b|\b(usa|us|u\.s\.)\s*(audience|only)|must be (based )?in the (us|usa|uk)", t, re.I):
        stop.append("needs a mostly US/UK (Tier 1) audience; account region is Ethiopia")
    if re.search(r"official (tiktok |ig |instagram )?(sound|audio)|use the (provided )?audio|must use the audio", t, re.I):
        warn.append("needs the official sound attached in the TikTok app")
    if re.search(r"discord", t, re.I):
        warn.append("needs joining a Discord to get paid")
    if re.search(r"\b\d[\d,]*\s*\+?\s*followers", t, re.I):
        warn.append("mentions a follower minimum")
    if re.search(r"(fortnite|gaming|[a-z]+)[- ]focused account|dedicated (page|account) (is )?required|must have a dedicated", t, re.I):
        warn.append("wants a niche-focused account")
    return stop, warn


def first_payout_views(t):  # TikTok block: "Per 1K views\n\n$10.00 ... Min payout\n\n$10.00"
    i = t.find("TikTok\n")
    blk = t[i:i + 400] if i >= 0 else t
    r = re.search(r"Per 1K views\s*\n\s*\$([\d,.]+)", blk); m = re.search(r"Min payout\s*\n\s*\$([\d,.]+)", blk)
    if r and m:
        rate, mn = float(r.group(1).replace(",", "")), float(m.group(1).replace(",", ""))
        if rate > 0:
            return round(mn / rate * 1000)
    return None


def footage_links(t):
    out = []
    for u in re.findall(r"https?://[^\s\"'<>)\]]+", t):
        u = u.rstrip(".,;")
        if re.search(r"docs\.google\.com/(document|spreadsheets|presentation)", u):
            continue  # a brief, not footage
        if re.search(r"\.(mp4|mov|m4v|webm)(\?|$)|dropbox\.com|drive\.google\.com|picflow|mediasilo|frame\.io|wetransfer|footage\.", u, re.I) and u not in out:
            out.append(u)
    return out


def fetch(u, dest, limit=MAX_MB * 1024 * 1024):
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        ctype = r.headers.get("Content-Type", ""); n = 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            n += len(b)
            if n > limit:
                raise RuntimeError(f"file bigger than {MAX_MB} MB")
            f.write(b)
    return ctype, n


def get_footage(links, src):
    """Try each link; returns (ok, notes). Only direct video, Dropbox and Google Drive FILE links can be fetched without a login."""
    os.makedirs(src, exist_ok=True); notes = []
    for u in links:
        host = urllib.parse.urlparse(u).netloc.lower(); dest = os.path.join(src, "dl.bin")
        try:
            if "picflow" in host:
                notes.append(f"{u}: photo gallery, the cloud cannot read it"); continue
            if "dropbox.com" in host:
                u2 = re.sub(r"([?&])dl=0", r"\1dl=1", u) + ("" if "dl=1" in u else ("&" if "?" in u else "?") + "dl=1")
            elif "drive.google.com" in host:
                m = re.search(r"/file/d/([\w-]+)", u) or re.search(r"[?&]id=([\w-]+)", u)
                if not m:
                    notes.append(f"{u}: Google Drive folder, needs a login"); continue
                u2 = f"https://drive.google.com/uc?export=download&id={m.group(1)}"
            elif re.search(r"\.(mp4|mov|m4v|webm)(\?|$)", u, re.I):
                u2 = u
            else:
                notes.append(f"{u}: not a direct download"); continue
            ctype, n = fetch(u2, dest)
            if "text/html" in ctype.lower():
                notes.append(f"{u}: gave a web page, not a file (login or folder)"); continue
            if zipfile.is_zipfile(dest):
                with zipfile.ZipFile(dest) as z:
                    z.extractall(os.path.join(src, "zip"))
                os.remove(dest)
            else:
                name = os.path.basename(urllib.parse.urlparse(u).path) or "footage.mp4"
                if not name.lower().endswith(VID + IMG):
                    name += ".mp4"
                os.replace(dest, os.path.join(src, name))
            found = [f for f in glob.glob(os.path.join(src, "**", "*"), recursive=True) if f.lower().endswith(VID + IMG)]
            if found:
                return True, [f"{u}: downloaded {len(found)} file(s)"]
            notes.append(f"{u}: downloaded but no photo/video inside")
        except Exception as e:
            notes.append(f"{u}: {type(e).__name__} {str(e)[:80]}")
    return False, notes


STEP_NAMES = ["Rules received", "Fit check", "Footage link found", "Footage downloaded", "Clip built"]


def with_steps(st, done):
    """done = [(name, "ok"|"fail"|"warn", note)] in order; steps not reached show as "wait". The dashboard draws these as a tracker."""
    seen = {d[0] for d in done}
    st["steps"] = [{"k": k, "s": s_, "n": (n or "")[:200]} for k, s_, n in done] + [{"k": k, "s": "wait", "n": ""} for k in STEP_NAMES if k not in seen]
    return st


def write_status(cid, st):
    os.makedirs(ST_DIR, exist_ok=True)
    st["at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    json.dump(st, open(os.path.join(ST_DIR, f"{cid}.json"), "w"), indent=1)
    print(json.dumps(st, indent=1))
    open("alert_body.txt", "w").write(f"{st['state']}|{st.get('title','')}|{st.get('msg','')}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cid = sys.argv[1]; force = "--force" in sys.argv
    cp = os.path.join(CAP_DIR, f"{cid}.json")
    if not os.path.exists(cp):
        sys.exit(f"no capture for {cid}")
    cap = json.load(open(cp)); text = cap["text"]
    title = re.sub(r"\s*\|\s*Content Rewards\s*$", "", cap.get("title", cid))
    rh = hashlib.sha1(text.split("\nBrief\n")[-1].split("\nTop clippers")[0].encode()).hexdigest()[:12]
    sp = os.path.join(ST_DIR, f"{cid}.json")
    if os.path.exists(sp) and not force:
        old = json.load(open(sp))
        if old.get("rules_hash") == rh and old.get("state") != "error":
            print("already processed, same rules; nothing to do"); open("alert_body.txt", "w").write(""); return
    base = {"id": cid, "title": title, "rules_hash": rh}
    done = [("Rules received", "ok", cap.get("capturedAt", ""))]
    stop, warn = analyze(text)
    fp = first_payout_views(text)
    if fp and fp > 1000:
        stop.append(f"first payout only after about {fp} views (your rule is 1,000)")
    if stop:
        return write_status(cid, with_steps({**base, "state": "stopped", "msg": "; ".join(stop), "warnings": warn}, done + [("Fit check", "fail", "; ".join(stop))]))
    done.append(("Fit check", "warn" if warn else "ok", "; ".join(warn) or "no blockers found"))
    links = footage_links(text)
    src = os.path.join(OUT_ROOT, "_src", cid[:8]); shutil.rmtree(src, ignore_errors=True)
    ok, notes = get_footage(links, src) if links else (False, ["no footage link found in the rules"])
    done.append(("Footage link found", "ok" if links else "fail", f"{len(links)} link(s)" if links else "none in the rules"))
    if not ok:
        done.append(("Footage downloaded", "fail", " | ".join(notes)))
        return write_status(cid, with_steps({**base, "state": "missing_footage", "msg": "rules are in, but the footage can't be fetched by the cloud: " + " | ".join(notes)[:400], "links": links, "warnings": warn}, done))
    done.append(("Footage downloaded", "ok", " | ".join(notes)))
    out_dir = os.path.join(OUT_ROOT, cid[:8])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "clip_generic.py"), cid, src, out_dir], capture_output=True, text=True, env={**os.environ, "CAPTURE_DIR": CAP_DIR})
    if r.returncode != 0:
        return write_status(cid, with_steps({**base, "state": "error", "msg": "clip builder failed: " + (r.stdout + r.stderr)[-300:], "warnings": warn}, done + [("Clip built", "fail", (r.stdout + r.stderr)[-150:])]))
    rep = json.load(open(os.path.join(out_dir, "report.json")))
    msg = f"clip ready ({rep['seconds']} s). Caption: {rep['caption']}"
    if rep["rules_read"].get("needs_approval"):
        msg += ". NOTE: drafts need brand approval before posting"
    write_status(cid, with_steps({**base, "state": "ready", "msg": msg, "warnings": warn, "caption": rep["caption"], "seconds": rep["seconds"]}, done + [("Clip built", "ok", f"{rep['seconds']} s")]))


main()
