"""Adds the text of Google Docs linked from a captured campaign page (docs/captures/*.json). Works for docs shared as 'anyone with the link'."""
import glob, json, os, re, urllib.request

for f in glob.glob("docs/captures/*.json"):
    if os.path.basename(f).startswith("_"):
        continue  # index files, not captures
    cap = json.load(open(f))
    if not isinstance(cap, dict):
        continue
    text = cap.get("text", "")
    changed = False
    for did in dict.fromkeys(re.findall(r"docs\.google\.com/document/d/([\w-]{20,})", text)):
        if f"=== DOC {did} ===" in text:
            continue
        grabbed = f"docs/captures/{re.sub('[^a-z0-9-]', '', 'doc-' + did, flags=re.I)[:40]}.json"  # doc grabbed straight from Google Docs (works for private docs too)
        if os.path.exists(grabbed):
            raw = json.load(open(grabbed))["text"].split(f"=== DOC {did} ===", 1)[-1]
        else:
            raw = None
        try:
            if raw is None:
                raw = urllib.request.urlopen(f"https://docs.google.com/document/d/{did}/export?format=txt", timeout=30).read().decode("utf-8", "ignore")
        except Exception as ex:
            print(f"{f}: doc {did} not readable ({type(ex).__name__}); needs 'anyone with the link'")
            continue
        probe = " ".join(raw.split())[:120]
        if probe and probe in " ".join(text.split()):
            print(f"{f}: doc {did} text already present, skipped")
            continue
        text += f"\n\n=== DOC {did} ===\n{raw.strip()[:60000]}"
        changed = True
        print(f"{f}: added doc {did} ({len(raw)} chars)")
    if changed:
        cap["text"] = text
        json.dump(cap, open(f, "w"), indent=1)

# index of docs grabbed straight from Google Docs, so the dashboard can list them
docs = []
for f in sorted(glob.glob("docs/captures/doc-*.json")):
    c = json.load(open(f))
    docs.append({"id": os.path.basename(f)[:-5], "title": c.get("title", ""), "chars": len(c.get("text", "")), "capturedAt": c.get("capturedAt", "")})
json.dump(docs, open("docs/captures/_docs.json", "w"), indent=1)
