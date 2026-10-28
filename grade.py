"""Grades each clip 1-10 (post or not) with a one-sentence reason. OpenAI gpt-4o-mini on 3 frames per clip (~1 cent per clip). No Claude."""
import base64, json, os, subprocess, urllib.request

KEY = os.environ.get("OPENAI_API_KEY", "").strip()
meta = json.load(open("out/clips.json"))
if not KEY:
    print("GRADING SKIPPED: no OPENAI_API_KEY secret"); raise SystemExit(0)

PROMPT = ("You grade a short vertical gameplay clip for a Call of Duty MW4 TikTok clipping page (3 frames from the clip, early to late). "
          "Score 1-10 for 'should we post this': strong visible action/payoff and clear picture = high; menu screens, empty walking, black/blurry frames, "
          "or any offensive/explicit text such as gamertags = low. Campaign rules: no explicit content, original game footage only. "
          'Reply JSON only: {"score": int 1-10, "reason": "one short sentence"}')

def frames(path):
    out = []
    for i, t in enumerate((3, 11, 19)):
        f = f"g{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", path, "-frames:v", "1", "-vf", "scale=480:-2", f], check=True)
        out.append("data:image/jpeg;base64," + base64.b64encode(open(f, "rb").read()).decode())
    return out

for m in meta:
    body = {"model": "gpt-4o-mini", "response_format": {"type": "json_object"}, "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}] +
                          [{"type": "image_url", "image_url": {"url": u}} for u in frames(m["file"])]}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    g = json.loads(r["choices"][0]["message"]["content"])
    m["grade"] = max(1, min(10, int(g["score"]))); m["reason"] = str(g["reason"])[:160]
    print("graded", m["file"], m["grade"], flush=True)
json.dump(meta, open("out/clips.json", "w"), indent=1)
