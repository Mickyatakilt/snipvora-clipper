"""Counts mp4 clips in the latest release (names on stdin) that are not in docs/posted.json. Usage: gate.py <tag>"""
import json, sys
tag = sys.argv[1]
posted = json.load(open("docs/posted.json"))
names = [l.strip() for l in sys.stdin if l.strip()]
print(sum(1 for x in names if f"clips/{tag}/{x}" not in posted))
