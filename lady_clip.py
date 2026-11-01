"""Lady A - Bigger Picture clips (no AI, plain ffmpeg). Cuts 9:16 clips from the campaign's no-lyrics footage and burns in one of the client's on-screen lines.
Rules (brief read Nov 1): >=8s, on-screen text on every post, official sound attached IN TikTok by Mike, #BiggerPicture #LadyA, no re-cuts of clips the band posted."""
import glob, json, os, random, subprocess, sys, textwrap

SRC_DIR = os.environ.get("LADY_SRC", "lady_src")
FONT = os.environ.get("FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
N = int(os.environ.get("N_CLIPS", "4")); CLIP_SEC = 18
LINES = ["Share this with someone that could really use a small lift right now.",
         "Share this with someone to let them know you're thinking about them.",
         "A reminder that you just got to believe.",
         "Then I remember, I'm only human.",
         "Feeling doubt, but then I'm reminded it's all part of the Bigger Picture."]
CAPTION = "Bigger Picture by Lady A\n#BiggerPicture #LadyA"
NOTE = "Attach the official TikTok sound in the app, and tag the artist, before posting. Do not use the dashboard Post button."


def dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]))


def main():
    files = sorted(f for f in glob.glob(f"{SRC_DIR}/**/*", recursive=True) if f.lower().endswith((".mov", ".mp4", ".m4v")) and "no lyrics" in f.lower())
    if not files:
        open("alert.txt", "w").write("LADY A: no 'no lyrics' footage files found in the Dropbox download")
        sys.exit("no source files")
    used = json.load(open("used_lady.json")) if os.path.exists("used_lady.json") else []  # [[file, start], ...]
    cands = []
    for f in files:
        d = dur(f); name = os.path.basename(f)
        s = 4.0
        while s + CLIP_SEC <= d - 3:
            if all(not (u[0] == name and abs(u[1] - s) < CLIP_SEC + 4) for u in used):
                cands.append((name, f, s))
            s += 7
    random.Random(len(used)).shuffle(cands)
    picks = []
    for c in cands:  # keep clips from the same file at least a clip apart
        if all(not (p[0] == c[0] and abs(p[2] - c[2]) < CLIP_SEC + 4) for p in picks):
            picks.append(c)
        if len(picks) >= N:
            break
    if len(picks) < 3:
        open("alert.txt", "w").write(f"LADY A: footage windows used up ({len(used)} used) - ask Claude for more")
        sys.exit("LADY A source exhausted")
    os.makedirs("out", exist_ok=True)
    vf_base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    meta = []
    for k, (name, f, st) in enumerate(picks, 1):
        line = LINES[(len(used) + k) % len(LINES)]
        tf = f"out/text{k}.txt"
        open(tf, "w", encoding="utf-8").write("\n".join(textwrap.wrap(line, 22)))
        out = f"out/lady_clip{k}.mp4"
        vf = vf_base + ",format=yuv420p" if os.environ.get("NO_TEXT") else f"{vf_base},drawtext=fontfile={FONT}:textfile={tf}:fontcolor=white:fontsize=64:line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2-260:shadowcolor=black@0.7:shadowx=3:shadowy=3:box=1:boxcolor=black@0.25:boxborderw=24,format=yuv420p"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(st), "-t", str(CLIP_SEC), "-i", f, "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "3", "-i", out, "-frames:v", "1", "-vf", "scale=540:-2", out.replace(".mp4", ".jpg")], check=True)
        meta.append({"campaign": "Lady A - Bigger Picture", "campaignUrl": "https://contentrewards.com/c/campaigns/835da2bd-6a51-4024-8dfd-d603a8f5e761",
                     "file": out, "start": st, "seconds": CLIP_SEC, "source": name, "text_on_screen": line, "caption": CAPTION, "note": NOTE})
        print("clip", k, name, st, flush=True)
    for m in meta:  # validate: 1080x1920, >=8s, has audio, real size
        j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-show_entries", "format=duration", "-of", "json", m["file"]]))
        v = next(x for x in j["streams"] if x["codec_type"] == "video")
        assert any(x["codec_type"] == "audio" for x in j["streams"]), f"{m['file']}: no audio"
        assert (v["width"], v["height"]) == (1080, 1920), f"{m['file']}: bad size"
        assert float(j["format"]["duration"]) >= 8, f"{m['file']}: shorter than 8s"
        assert os.path.getsize(m["file"]) > 300_000, f"{m['file']}: too small"
    json.dump(meta, open("out/clips.json", "w"), indent=1)
    json.dump(used + [[p[0], p[2]] for p in picks], open("used_lady.json", "w"))
    print("VALIDATED", len(meta), "Lady A clips", flush=True)


main()
