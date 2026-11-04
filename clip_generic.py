"""Generic clip builder (no AI, plain ffmpeg + PIL).
Usage: python3 clip_generic.py <campaignId> <source_dir> [out_dir]
Reads the grabbed rules (docs/captures/<campaignId>.json), pulls the hook line, required caption word, hashtags, @tag and minimum length out of the
rules text, and builds a 1080x1920 clip from the photos (jpg/png/webp) or videos (mp4/mov/m4v) in source_dir.
Photos -> slideshow (blurred background, slow zoom); videos -> 18 s cuts. Writes clip.mp4 + caption.txt + report.json.
Never commit brand photos: source_dir must stay outside the public repo."""
import glob, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]


def rules_text(cid):
    p = os.path.join(os.environ.get("CAPTURE_DIR", os.path.join(ROOT, "docs", "captures")), f"{cid}.json")
    if not os.path.exists(p):
        sys.exit(f"NO RULES: grab the rules for {cid} first (bookmark on the campaign page)")
    return json.load(open(p))["text"]


def parse(t):
    r = {}
    m = re.search(r"Hook[^\n]*?[：:]\s*[^“\"\n]*[“\"]([^”\"]+)[”\"]", t)
    r["hook"] = m.group(1).strip() if m else None
    m = re.search(r"Use caption\s*\n\s*[“\"]([^”\"]+)[”\"]", t)
    r["caption_word"] = m.group(1).strip() if m else None
    r["hashtags"] = list(dict.fromkeys(re.findall(r"Include (#\w+)", t)))
    r["tags"] = list(dict.fromkeys(re.findall(r"Tag (@\w+)", t)))
    m = re.search(r"Minimum clip length\s*\n\s*(\d+)\s*s", t)
    r["min_sec"] = int(m.group(1)) if m else 10
    r["needs_approval"] = bool(re.search(r"[Dd]rafts? require[s]? pre-?approval", t))
    r["official_sound"] = bool(re.search(r"official (sound|audio)", t, re.I))
    return r


def hook_png(text, path):
    from PIL import Image, ImageDraw, ImageFont
    font = next((f for f in FONTS if os.path.exists(f)), None)
    f = ImageFont.truetype(font, 66) if font else ImageFont.load_default()
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    words, lines, cur = text.split(), [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=f) > W - 160 and cur:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    y = 150
    for l in lines:
        d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill="white", stroke_width=6, stroke_fill="black"); y += 86
    img.save(path)


def dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]))


def photos_clip(photos, hook, out, per=2.2, hook_sec=4.4, max_n=8):
    photos = photos[:max_n]; n = len(photos); ins, fc = [], ""
    for i, p in enumerate(photos):
        ins += ["-loop", "1", "-t", str(per), "-i", p]
        fc += (f"[{i}:v]split=2[a{i}][b{i}];[a{i}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5[bg{i}];"
               f"[b{i}]scale=1000:1780:force_original_aspect_ratio=decrease,zoompan=z='min(1+0.0015*on,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1000x1780:fps=25[fg{i}];"
               f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v{i}];")
    fc += "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[c]"
    if hook:
        ins += ["-loop", "1", "-t", "60", "-i", os.path.join(os.path.dirname(out), "hook.png")]
        fc += f";[c][{n}:v]overlay=0:0:enable='lt(t,{hook_sec})'[out]"
    else:
        fc = fc.replace("[c]", "[out]")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex", fc, "-map", "[out]", "-t", str(n * per), "-r", "25",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-movflags", "+faststart", out], check=True)


def video_clip(src, hook, out, sec=18, hook_sec=4.4):
    d = dur(src); st = min(4.0, max(0, d - sec - 1))
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p"
    ins = ["-ss", str(st), "-t", str(sec), "-i", src]
    if hook:
        ins += ["-loop", "1", "-t", str(sec), "-i", os.path.join(os.path.dirname(out), "hook.png")]
        fc = f"[0:v]{vf}[v];[v][1:v]overlay=0:0:enable='lt(t,{hook_sec})'[out]"
    else:
        fc = f"[0:v]{vf}[out]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex", fc, "-map", "[out]", "-map", "0:a?", "-t", str(sec),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out], check=True)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cid, src = sys.argv[1], sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join("out", cid[:8])
    os.makedirs(out_dir, exist_ok=True)
    r = parse(rules_text(cid))
    if r["official_sound"]:
        print("WARNING: rules mention an official sound; this builder adds none. Check before posting.")
    files = sorted(glob.glob(os.path.join(src, "*")))
    photos = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    videos = [f for f in files if f.lower().endswith((".mp4", ".mov", ".m4v"))]
    if not photos and not videos:
        sys.exit(f"NO FOOTAGE in {src}")
    if r["hook"]:
        hook_png(r["hook"], os.path.join(out_dir, "hook.png"))
    out = os.path.join(out_dir, "clip.mp4")
    if videos:
        video_clip(videos[0], r["hook"], out); kind = "video"
    else:
        photos_clip(photos, r["hook"], out); kind = "photos"
    cap = " ".join([r["caption_word"]] * bool(r["caption_word"]) + r["hashtags"] + r["tags"]).strip()
    open(os.path.join(out_dir, "caption.txt"), "w").write(cap)
    j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-show_entries", "format=duration,size", "-of", "json", out]))
    v = j["streams"][0]; d = float(j["format"]["duration"])
    ok = (v["width"], v["height"]) == (W, H) and d >= r["min_sec"]
    rep = {"campaign": cid, "kind": kind, "seconds": round(d, 1), "size": int(j["format"]["size"]), "caption": cap, "rules_read": r, "meets_min_length": d >= r["min_sec"], "ok": ok}
    json.dump(rep, open(os.path.join(out_dir, "report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))
    if not ok:
        sys.exit("VALIDATION FAILED")


main()
