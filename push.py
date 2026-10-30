"""Phone push through Web Push (same idea as the trading app). Usage: python push.py "Title" "Body" [url]. Never fails the job."""
import json, os, sys
try:
    from pywebpush import webpush
    sub = os.environ.get("PUSH_SUB", "").strip()
    key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not sub or not key:
        print("push skipped: PUSH_SUB or VAPID_PRIVATE_KEY secret missing"); sys.exit(0)
    t, b = sys.argv[1], sys.argv[2]
    u = sys.argv[3] if len(sys.argv) > 3 else "./"
    webpush(subscription_info=json.loads(sub), data=json.dumps({"title": t, "body": b[:300], "url": u}),
            vapid_private_key=key, vapid_claims={"sub": "mailto:mickyatakilt@gmail.com"}, ttl=3600)
    print("push sent")
except SystemExit:
    raise
except Exception as ex:
    print("push failed:", type(ex).__name__, str(ex)[:150])
