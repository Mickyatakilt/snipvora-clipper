"""Adds the text of Google Docs linked from a captured campaign page (docs/captures/*.json). Works for docs shared as 'anyone with the link'."""
import glob, json, re, urllib.request

for f in glob.glob("docs/captures/*.json"):
    cap = json.load(open(f))
    text = cap.get("text", "")
    changed = False
    for did in dict.fromkeys(re.findall(r"docs\.google\.com/document/d/([\w-]{20,})", text)):
        if f"=== DOC {did} ===" in text:
            continue
        try:
            raw = urllib.request.urlopen(f"https://docs.google.com/document/d/{did}/export?format=txt", timeout=30).read().decode("utf-8", "ignore")
        except Exception as ex:
            print(f"{f}: doc {did} not readable ({type(ex).__name__}); needs 'anyone with the link'")
            continue
        text += f"\n\n=== DOC {did} ===\n{raw.strip()[:60000]}"
        changed = True
        print(f"{f}: added doc {did} ({len(raw)} chars)")
    if changed:
        cap["text"] = text
        json.dump(cap, open(f, "w"), indent=1)
