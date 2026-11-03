"""Marks posted TikToks as deleted when TikTok says the video is gone (page statusCode 10204).
Free, no AI. Only flips a flag when TikTok clearly answered; a blocked/odd answer changes nothing."""
import json, re, subprocess, sys
from datetime import datetime, timezone
P = "docs/posted.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

def status(url):
    m = re.search(r"/video/(\d+)", url or "")
    if not m: return None
    try:
        s = subprocess.run(["curl", "-sL", "-m", "25", "-A", UA, "https://www.tiktok.com/@snipvora/video/" + m.group(1)],
                           capture_output=True, text=True, timeout=40).stdout
    except Exception:
        return None
    if "__UNIVERSAL_DATA_FOR_REHYDRATION__" not in s: return None   # blocked or captcha: unknown
    c = re.search(r'"statusCode":(\d+)', s)
    return int(c.group(1)) if c else None

d = json.load(open(P)); changed = False
for k, v in d.items():
    st = status(v.get("url"))
    print(k, st)
    if st == 10204 and not v.get("deleted"):
        v["deleted"] = True; v["deletedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"); changed = True
    elif st == 0 and v.get("deleted"):
        v.pop("deleted", None); v.pop("deletedAt", None); changed = True
if changed:
    json.dump(d, open(P, "w"), indent=1, ensure_ascii=False); print("posted.json updated")
