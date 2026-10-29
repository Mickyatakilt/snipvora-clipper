"""Cloud clipper for the MW4 campaign: official MediaSilo share link -> 720p copy -> N vertical clips (original audio only).
Plain code, no AI. Campaign rules (read Oct 28): official footage only, >=10s, keep original audio, no AI voice, caption needs @callofduty + #ad."""
import asyncio, json, os, re, subprocess, sys
import numpy as np
from playwright.async_api import async_playwright

QL = "6ae109cef2c6470f09434547"
FOLDER = "28abc944-ea6b-4c31-8412-2feabade068e"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
N = int(os.environ.get("N_CLIPS", "4")); CLIP_SEC = 22
CAPTIONS = ["The new Call of Duty looks INSANE", "MW4 Multiplayer is looking unreal", "COD Multiplayer has never looked better", "The graphics are actually crazy"]


async def fetch(path="src.mp4"):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        c = await b.new_context(user_agent=UA, viewport={"width": 1400, "height": 850}, locale="en-US", timezone_id="America/New_York")
        await c.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        pg = await c.new_page()
        await pg.goto(f"https://app.mediasilo.com/review/{QL}", wait_until="domcontentloaded", timeout=90000)
        await pg.wait_for_timeout(8000)
        r = await c.request.get(f"https://api.mediasilo.com/v3/quicklinks/{QL}/folders/{FOLDER}/assets")
        d = await r.json()
        items = d if isinstance(d, list) else d.get("items") or d.get("assets") or d.get("data") or []
        v = [a for a in items if a.get("type") == "video"][0]
        der = {(x.get("name") or x.get("type") or x.get("format")): x for x in v.get("derivatives", [])}
        pick = der.get("proxy") or der.get("source")
        url = pick.get("url") or pick.get("path")
        print("downloading derivative:", list(der), pick.get("width"), "x", pick.get("height"), flush=True)
        await b.close()
    subprocess.run(["curl", "-sL", "--fail", "-m", "600", "-o", path, url], check=True)
    print("saved", os.path.getsize(path) // 1_000_000, "MB", flush=True)


def energy(path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "8000", "a.wav"], check=True)
    a = np.frombuffer(open("a.wav", "rb").read()[44:], dtype=np.int16).astype(np.float32)
    s = len(a) // 8000
    return np.sqrt((a[: s * 8000].reshape(s, 8000) ** 2).mean(axis=1))


def fetch_with_retry(tries=3):
    for i in range(1, tries + 1):
        try:
            asyncio.run(fetch())
            if os.path.getsize("src.mp4") < 100_000_000:
                raise RuntimeError("downloaded file too small")
            return
        except Exception as ex:  # real failures are retried, then the job fails loudly
            print(f"attempt {i}/{tries} failed: {ex!r}", flush=True)
            if i == tries:
                raise
            import time; time.sleep(20 * i)


def validate(meta):
    """A clip only counts if it is 1080x1920, 10s+, has audio, and has real size. Anything else fails the whole job."""
    for m in meta:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-show_entries", "format=duration",
                                       "-of", "json", m["file"]])
        j = json.loads(out)
        kinds = {x["codec_type"] for x in j["streams"]}
        v = next(x for x in j["streams"] if x["codec_type"] == "video")
        assert "audio" in kinds, f"{m['file']}: no audio"
        assert (v["width"], v["height"]) == (1080, 1920), f"{m['file']}: bad size"
        assert float(j["format"]["duration"]) >= 10, f"{m['file']}: shorter than 10s"
        assert os.path.getsize(m["file"]) > 500_000, f"{m['file']}: too small"
    assert len(meta) >= 3, f"only {len(meta)} valid clips"


def main():
    fetch_with_retry()
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "src.mp4"]))
    e = energy("src.mp4")
    print(f"source {dur:.0f}s", flush=True)
    win = np.convolve(e, np.ones(CLIP_SEC) / CLIP_SEC, mode="valid")
    used = json.load(open("used.json")) if os.path.exists("used.json") else []  # windows already cut on earlier days
    picks = []
    for i in np.argsort(-win):
        if all(abs(i - j) >= CLIP_SEC + 5 for j in picks + used):
            picks.append(int(i))
        if len(picks) >= N:
            break
    if len(picks) < 3:
        sys.exit(f"SOURCE EXHAUSTED: only {len(picks)} unused windows left ({len(used)} already used) - need new footage or reset used.json")
    os.makedirs("out", exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p"  # full-screen 9:16, exactly as uploaded
    meta = []
    for k, st in enumerate(sorted(picks), 1):
        out = f"out/mw4_clip{k}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(st), "-t", str(CLIP_SEC), "-i", "src.mp4", "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "3", "-i", out, "-frames:v", "1", "-vf", "scale=540:-2", out.replace(".mp4", ".jpg")], check=True)
        cap = f"{CAPTIONS[(len(used) + k) % len(CAPTIONS)]}\n#ad @callofduty"
        meta.append({"campaign": "Call of Duty MW4 Multiplayer", "file": out, "start": st, "seconds": CLIP_SEC, "caption": cap})
        print("clip", k, "from", st, "s", flush=True)
    validate(meta)
    json.dump(meta, open("out/clips.json", "w"), indent=1)
    json.dump(used + picks, open("used.json", "w"))
    print("VALIDATED", len(meta), "clips", flush=True)


main()
